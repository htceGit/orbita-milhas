-- The promotions catalogue is public. Accounts and notification settings stay private.
alter table public.tarifaspromo enable row level security;
drop policy if exists tarifaspromo_active_read on public.tarifaspromo;
create policy tarifaspromo_public_read on public.tarifaspromo
  for select to anon, authenticated
  using (data_ida >= (now() at time zone 'America/Sao_Paulo')::date and preco > 0);

revoke all on public.tarifaspromo from anon;
grant select on public.tarifaspromo to anon, authenticated;
-- The external collector keeps its existing service_role write privileges.
