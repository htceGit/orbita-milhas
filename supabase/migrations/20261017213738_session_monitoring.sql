alter table public.scan_runs
 add column diagnostics_version integer not null default 0,
 add column query_budget integer check(query_budget between 1 and 1000000),
 add column phase text not null default 'legacy',
 add column heartbeat_at timestamptz,
 add column current_query jsonb,
 add column error_counts jsonb not null default '{}'::jsonb,
 add column last_error jsonb,
 add column retries_count integer not null default 0 check(retries_count>=0),
 add column recovered_queries integer not null default 0 check(recovered_queries>=0),
 add column empty_results integer not null default 0 check(empty_results>=0),
 add column calendar_priced_combinations integer not null default 0 check(calendar_priced_combinations>=0),
 add column workflow_url text;
create index scan_runs_started_idx on public.scan_runs(started_at desc);

create table public.scan_events (
 id bigint generated always as identity primary key,
 run_id uuid not null references public.scan_runs(id) on delete cascade,
 created_at timestamptz not null default now(),
 stage text not null check(stage in ('planning','calendar','detail','system')),
 outcome text not null check(outcome in ('started','success','empty','error','retry','finished')),
 origin text check(origin ~ '^[A-Z]{3}$'),
 destination text check(destination ~ '^[A-Z]{3}$'),
 departure_date date,
 return_date date,
 stay_days integer check(stay_days between 1 and 60),
 attempt integer not null default 1 check(attempt between 1 and 5),
 duration_ms integer check(duration_ms between 0 and 20000000),
 error_code text check(error_code ~ '^[a-z_]{1,40}$'),
 cause_type text check(length(cause_type)<=100),
 message text check(length(message)<=500),
 http_status integer check(http_status between 100 and 599),
 retryable boolean not null default false
);
create index scan_events_run_time_idx on public.scan_events(run_id,id desc);
create index scan_events_retention_idx on public.scan_events(created_at);
alter table public.scan_events enable row level security;
create policy scan_events_admin_read on public.scan_events for select to authenticated
 using ((select private.is_active()) and (select private.is_admin()));
revoke all on public.scan_events from anon,authenticated;
grant select on public.scan_events to authenticated;
grant all on public.scan_events to service_role;
grant usage,select on sequence public.scan_events_id_seq to service_role;
comment on table public.scan_events is 'Admin-only sanitized search diagnostics. No response HTML, cookies, credentials or request headers. Retained seven days.';
