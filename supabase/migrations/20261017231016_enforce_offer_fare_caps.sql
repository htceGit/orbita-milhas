-- Cash round-trip caps apply to every airline, before any mileage projection.
-- Keep the policy literal aligned with fare-policy.json (covered by the DB test).
create function private.offer_fare_cap(destination text, country text, region text)
returns numeric language sql immutable set search_path = '' as $$
 select (p->'caps'->>coalesce(
   p->'destination_regions'->>upper(btrim(destination)),
   p->'country_regions'->>lower(btrim(country)),
   p->'region_names'->>lower(btrim(region))
 ))::numeric
 from (select '{"caps":{"EUA":3000,"Europa":3500},"destination_regions":{"MIA":"EUA","JFK":"EUA","LAX":"EUA","MCO":"EUA","BOS":"EUA","LIS":"Europa","MAD":"Europa","BCN":"Europa","CDG":"Europa","LHR":"Europa","FCO":"Europa","MXP":"Europa","FRA":"Europa"},"country_regions":{"estados unidos":"EUA","united states":"EUA","us":"EUA","usa":"EUA","portugal":"Europa","espanha":"Europa","frança":"Europa","reino unido":"Europa","itália":"Europa","alemanha":"Europa"},"region_names":{"eua":"EUA","europa":"Europa"}}'::jsonb as p) policy;
$$;
revoke all on function private.offer_fare_cap(text,text,text) from public,anon,authenticated;
grant usage on schema private to service_role;
grant execute on function private.offer_fare_cap(text,text,text) to service_role;

create function private.enforce_offer_fare_cap()
returns trigger language plpgsql set search_path = '' as $$
declare cap numeric;
begin
 cap := private.offer_fare_cap(new.destination,new.country,new.region);
 -- Legacy rejected fares may remain expired for history and favorites integrity.
 if cap is not null and new.price_brl > cap and (tg_op = 'INSERT' or new.expires_at > now()) then
   raise exception 'Tarifa acima do teto em dinheiro de R$ %', cap using errcode = '23514';
 end if;
 return new;
end;
$$;
revoke all on function private.enforce_offer_fare_cap() from public,anon,authenticated;
grant execute on function private.enforce_offer_fare_cap() to service_role;
create trigger offers_enforce_fare_cap before insert or update on public.offers
 for each row execute function private.enforce_offer_fare_cap();

-- Withdraw existing over-cap offers without deleting price history or favorites.
update public.offers set expires_at=now()
where expires_at>now() and price_brl>private.offer_fare_cap(destination,country,region);

alter table public.scan_runs add column offers_price_filtered integer check(offers_price_filtered>=0);
alter table public.scan_events drop constraint scan_events_outcome_check;
alter table public.scan_events add constraint scan_events_outcome_check
 check(outcome in ('started','success','empty','filtered','error','retry','finished'));
comment on column public.scan_runs.offers_price_filtered is 'Detailed fares rejected by the cash price cap. NULL for sessions before this policy.';
