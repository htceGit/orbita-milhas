-- Restrict global configuration and future personal monitors to six origins.
update public.scanner_settings set origins=array['CWB','JOI','NVT','FLN','VCP','GRU'];
alter table public.scanner_settings alter column origins set default array['CWB','JOI','NVT','FLN','VCP','GRU'];
alter table public.scanner_settings add constraint scanner_origins_allowed check(origins <@ array['CWB','JOI','NVT','FLN','VCP','GRU']);
-- Preserve old monitors, but disable removed origins. Their owners can delete them.
update public.monitors set enabled=false where origin not in ('CWB','JOI','NVT','FLN','VCP','GRU');
alter table public.monitors add constraint monitors_enabled_origins check(not enabled or origin in ('CWB','JOI','NVT','FLN','VCP','GRU'));
alter table public.offers drop constraint offers_airlines_check;
alter table public.offers add constraint offers_airlines_check check(cardinality(airlines) between 1 and 8 and array_position(airlines,null) is null);
alter table public.offers add column airline_names text[] not null default '{}';
update public.offers set airline_names=array['LATAM'] where airlines=array['LA'];
alter table public.scanner_settings add column search_strategy text not null default 'hybrid' check(search_strategy in ('hybrid','detailed'));
alter table public.scanner_state add column calendar_cursor bigint not null default 0 check(calendar_cursor>=0);
alter table public.scan_runs
 add column calendar_queries integer not null default 0 check(calendar_queries>=0),
 add column calendar_entries integer not null default 0 check(calendar_entries>=0),
 add column detail_queries integer not null default 0 check(detail_queries>=0),
 add column detail_dates_checked integer not null default 0 check(detail_dates_checked>=0),
 add column calendar_status text not null default 'disabled' check(calendar_status in ('pending','available','unavailable','disabled'));
update public.scan_runs set detail_queries=queries_attempted where provider='fast_flights';
comment on column public.offers.carrier_validation is 'outbound_only: initial result identifies outbound carriers; return segments and LATAM Pass inventory require confirmation.';
comment on column public.scan_runs.calendar_entries is 'Date pairs with positive calendar prices; not detailed fare or carrier validation and not exhaustive coverage.';
