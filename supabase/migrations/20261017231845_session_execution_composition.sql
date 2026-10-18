alter table public.scan_events
 add column departure_start date,
 add column departure_end date,
 add column min_days integer check(min_days between 1 and 60),
 add column max_days integer check(max_days between 1 and 60);

create table public.scan_session_summaries (
 run_id uuid primary key references public.scan_runs(id) on delete cascade,
 composition jsonb not null check(jsonb_typeof(composition)='object'),
 updated_at timestamptz not null default now()
);
alter table public.scan_session_summaries enable row level security;
create policy session_summaries_admin_read on public.scan_session_summaries
 for select to authenticated using ((select private.is_active()) and (select private.is_admin()));
revoke all on public.scan_session_summaries from public,anon,authenticated;
grant select on public.scan_session_summaries to authenticated;
grant all on public.scan_session_summaries to service_role;

-- Aggregate the entire session, independently of the UI's 60-event log window.
-- Date ranges are envelopes of observed dates, not continuous coverage claims.
create function private.build_session_composition(target_run_id uuid)
returns jsonb language sql stable security invoker set search_path='' as $$
 with jobs as (
  select j.id,j.request,j.status,j.result from public.calendar_jobs j where j.run_id=target_run_id
 ), calendars as (
  select request->>'origin' origin,request->>'destination' destination,
   request->>'departure_start' departure_start,request->>'departure_end' departure_end,
   (request->>'min_days')::integer min_days,(request->>'max_days')::integer max_days,status,
   (result->>'priced_combinations')::integer prices,
   (result->>'completed_sweeps')::integer completed_sweeps,
   (result->>'requested_sweeps')::integer requested_sweeps
  from jobs
  union all
  select e.origin,e.destination,e.departure_start::text,e.departure_end::text,
   e.min_days,e.max_days,'failed',null::integer,null::integer,null::integer
  from public.scan_events e where e.run_id=target_run_id and e.stage='calendar'
   and e.outcome='error' and e.origin is not null and e.destination is not null
   and not exists(select 1 from jobs j where j.request->>'origin'=e.origin and j.request->>'destination'=e.destination
    and (e.departure_start is null or (j.request->>'departure_start'=e.departure_start::text
      and j.request->>'departure_end'=e.departure_end::text
      and (j.request->>'min_days')::integer=e.min_days and (j.request->>'max_days')::integer=e.max_days)))
 ), details as (
  select e.origin,e.destination,e.stay_days,
   min(e.departure_date) departure_start,max(e.departure_date) departure_end,
   min(e.return_date) return_start,max(e.return_date) return_end,
   count(*)::integer attempts,
   count(distinct (e.departure_date,e.return_date))::integer dates_attempted,
   count(distinct (e.departure_date,e.return_date)) filter(where e.outcome in ('success','empty','filtered'))::integer dates_completed,
   count(*) filter(where e.outcome='error')::integer errors,
   count(*) filter(where e.outcome='filtered')::integer filtered
  from public.scan_events e where e.run_id=target_run_id and e.stage='detail'
   and e.outcome in ('success','empty','filtered','error')
   and e.origin is not null and e.destination is not null and e.departure_date is not null and e.return_date is not null
  group by e.origin,e.destination,e.stay_days
 )
 select jsonb_build_object('run_id',r.id,'detail_attempts_expected',r.detail_queries,
  'detail_attempts_recorded',coalesce((select sum(attempts) from details),0),
  'calendars',coalesce((select jsonb_agg(to_jsonb(c) order by origin,destination,departure_start,min_days) from calendars c),'[]'::jsonb),
  'details',coalesce((select jsonb_agg(to_jsonb(d) order by origin,destination,stay_days) from details d),'[]'::jsonb))
 from public.scan_runs r where r.id=target_run_id;
$$;
revoke all on function private.build_session_composition(uuid) from public,anon;
grant execute on function private.build_session_composition(uuid) to authenticated,service_role;

create function public.get_session_composition(target_run_id uuid)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare saved jsonb;
begin
 if (select auth.uid()) is null or not private.is_active() or not private.is_admin() then
  raise exception 'Acesso administrativo necessário.' using errcode='42501';
 end if;
 select s.composition into saved from public.scan_session_summaries s
  join public.scan_runs r on r.id=s.run_id where s.run_id=target_run_id and r.status<>'running';
 return coalesce(saved,private.build_session_composition(target_run_id));
end;
$$;
revoke all on function public.get_session_composition(uuid) from public,anon;
grant execute on function public.get_session_composition(uuid) to authenticated;

-- Snapshot once at closure, before raw logs and captures expire after seven days.
create function private.snapshot_session_composition()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
 insert into public.scan_session_summaries(run_id,composition)
 values(new.id,jsonb_set(private.build_session_composition(new.id),'{detail_attempts_expected}',to_jsonb(new.detail_queries)))
 on conflict(run_id) do update set composition=excluded.composition,updated_at=now();
 return new;
end;
$$;
revoke all on function private.snapshot_session_composition() from public,anon,authenticated;
grant execute on function private.snapshot_session_composition() to service_role;
create trigger snapshot_session_composition after update of status on public.scan_runs
 for each row when (new.status<>'running') execute function private.snapshot_session_composition();

insert into public.scan_session_summaries(run_id,composition)
 select id,private.build_session_composition(id) from public.scan_runs where status<>'running';
comment on table public.scan_session_summaries is 'Admin-only composition snapshots retained with each session. Calendar scopes are requested periods; detail ranges summarize observed dates, not continuous coverage.';
