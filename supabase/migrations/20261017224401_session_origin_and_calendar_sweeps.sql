alter table public.scan_runs
 add column trigger_source text not null default 'legacy' check(trigger_source in ('legacy','manual','schedule','continuation')),
 add column query_budget_override integer check(query_budget_override>0),
 add column calendar_sweeps_requested integer check(calendar_sweeps_requested>=0),
 add column calendar_sweeps_completed integer check(calendar_sweeps_completed>=0);
comment on column public.scan_runs.calendar_queries is 'Calendar HTTP requests attempted, including retries. Not complete date-range sweeps.';
comment on column public.scan_runs.calendar_sweeps_completed is 'Completed captures for one route and fixed stay across the entire requested departure interval. Null on legacy runs.';
