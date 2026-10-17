create table public.calendar_jobs (
 id uuid primary key default gen_random_uuid(),
 user_id uuid references public.profiles(id) on delete cascade,
 run_id uuid references public.scan_runs(id) on delete set null,
 request jsonb not null check(jsonb_typeof(request)='object'),
 cache_key text not null check(cache_key ~ '^[a-f0-9]{64}$'),
 status text not null default 'queued' check(status in ('queued','running','completed','partial','failed')),
 result jsonb,
 entries_gzip text,
 error text,
 created_at timestamptz not null default now(),
 started_at timestamptz,
 finished_at timestamptz,
 expires_at timestamptz not null default(now()+interval '4 hours')
);
alter table public.calendar_jobs enable row level security;
create index calendar_jobs_user_idx on public.calendar_jobs(user_id,created_at desc);
create index calendar_jobs_run_idx on public.calendar_jobs(run_id);
create index calendar_jobs_cache_idx on public.calendar_jobs(cache_key,expires_at desc) where status='completed';
create index calendar_jobs_queue_idx on public.calendar_jobs(created_at) where status='queued';
create unique index calendar_jobs_one_pending_per_user on public.calendar_jobs(user_id) where status in ('queued','running');
create policy calendar_jobs_read on public.calendar_jobs for select to authenticated using ((select private.is_active()) and (user_id is null or user_id=(select auth.uid()) or (select private.is_admin())));
revoke all on public.calendar_jobs from anon,authenticated;
grant select(id,user_id,run_id,request,cache_key,status,result,error,created_at,started_at,finished_at,expires_at) on public.calendar_jobs to authenticated;
grant all on public.calendar_jobs to service_role;
alter table public.scan_runs
 add column calendar_search_calls integer not null default 0 check(calendar_search_calls>=0),
 add column calendar_routes integer not null default 0 check(calendar_routes>=0);
comment on column public.calendar_jobs.entries_gzip is 'Gzip + base64 of public calendar price entries; available only through the authenticated API. Tokens, cookies and browser headers are never stored.';
comment on column public.scan_runs.calendar_entries is 'Positive priced origin/destination/date/stay combinations captured from native calendar responses; never carrier validation.';

alter table public.scan_runs drop constraint scan_runs_calendar_status_check;
alter table public.scan_runs add constraint scan_runs_calendar_status_check check(calendar_status in ('pending','available','unavailable','disabled','partial'));
