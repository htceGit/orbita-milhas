alter table public.scanner_settings alter column query_budget set default 1000;
update public.scanner_settings set query_budget=1000 where id=1;
