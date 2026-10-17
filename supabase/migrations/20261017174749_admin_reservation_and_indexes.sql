create index billing_events_user_idx on private.billing_events(user_id);
create index scanner_state_last_run_idx on public.scanner_state(last_run_id);
create policy scanner_state_no_clients on public.scanner_state for all to anon,authenticated using(false) with check(false);
create policy billing_events_no_clients on private.billing_events for all to anon,authenticated using(false) with check(false);

create table private.admin_reservations (
 email text primary key,
 consumed_at timestamptz,
 claimed_by uuid references auth.users(id) on delete set null,
 created_at timestamptz not null default now(),
 check(email=lower(email))
);
create index admin_reservations_claimed_idx on private.admin_reservations(claimed_by);
alter table private.admin_reservations enable row level security;
create policy admin_reservations_no_clients on private.admin_reservations for all to anon,authenticated using(false) with check(false);
revoke all on private.admin_reservations from public,anon,authenticated;
create function private.on_email_confirmed() returns trigger language plpgsql security definer set search_path='' as $$
begin
 if new.email_confirmed_at is not null then
  update private.admin_reservations set consumed_at=now(),claimed_by=new.id
   where email=lower(new.email) and consumed_at is null;
  if found then
   update public.profiles set role='admin',plan='pro' where id=new.id;
  end if;
 end if;
 return new;
end;$$;
revoke all on function private.on_email_confirmed() from public,anon,authenticated;
create trigger orbita_confirmed_admin after update of email_confirmed_at on auth.users for each row execute function private.on_email_confirmed();
