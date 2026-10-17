-- Órbita: tabelas de produto, autenticação e permissões.
create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated, service_role;

create table public.profiles (
 id uuid primary key references auth.users(id) on delete cascade,
 email text not null,
 full_name text not null default '',
 role text not null default 'member' check(role in ('member','admin')),
 plan text not null default 'free' check(plan in ('free','pro')),
 status text not null default 'active' check(status in ('active','suspended')),
 pro_until timestamptz,
 terms_version text,
 terms_accepted_at timestamptz,
 created_at timestamptz not null default now()
);
create function private.is_admin() returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.profiles where id=(select auth.uid()) and role='admin' and status='active');
$$;
create function private.is_active() returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.profiles where id=(select auth.uid()) and status='active');
$$;
create function private.is_pro() returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.profiles where id=(select auth.uid()) and status='active' and (role='admin' or(plan='pro' and(pro_until is null or pro_until>now()))));
$$;
revoke all on function private.is_admin(),private.is_active(),private.is_pro() from public,anon;
grant execute on function private.is_admin(),private.is_active(),private.is_pro() to authenticated;

create function private.on_auth_user_created() returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.profiles(id,email,full_name,terms_version,terms_accepted_at)
 values(new.id,coalesce(new.email,''),left(coalesce(new.raw_user_meta_data->>'full_name','Viajante'),100),new.raw_user_meta_data->>'terms_version',case when new.raw_user_meta_data->>'terms_accepted_at' ~ '^\d{4}-\d{2}-\d{2}T' then(new.raw_user_meta_data->>'terms_accepted_at')::timestamptz else null end);
 return new;
end;$$;
revoke all on function private.on_auth_user_created() from public,anon,authenticated;
create trigger orbita_new_user after insert on auth.users for each row execute function private.on_auth_user_created();

create table public.preferences (
 user_id uuid primary key references public.profiles(id) on delete cascade,
 cost_per_thousand numeric(8,2) not null default 20 check(cost_per_thousand between 1 and 200),
 estimated_taxes numeric(10,2) not null default 350 check(estimated_taxes between 0 and 10000)
);
create table public.scanner_settings (
 id integer primary key default 1 check(id=1),
 enabled boolean not null default true,
 origins text[] not null default array['FLN','NVT','JOI','CWB','IGU','LDB','GRU','CGH','VCP'],
 destinations jsonb not null default '[]'::jsonb check(jsonb_typeof(destinations)='array'),
 min_days integer not null default 7 check(min_days between 1 and 60),
 max_days integer not null default 20 check(max_days between 1 and 60 and max_days>=min_days),
 horizon_months integer not null default 6 check(horizon_months between 1 and 6),
 query_budget integer not null default 600 check(query_budget between 1 and 100000),
 search_mode text not null default 'rolling' check(search_mode in ('rolling','exhaustive')),
 max_stops integer not null default 2 check(max_stops between 0 and 2),
 updated_at timestamptz not null default now(),
 check(cardinality(origins) between 1 and 20)
);
create table public.monitors (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references public.profiles(id) on delete cascade,
 origin text not null check(origin in ('FLN','NVT','JOI','CWB','IGU','LDB','GRU','CGH','VCP')),
 destination text not null check(destination ~ '^[A-Z]{3}$'),
 min_days integer not null default 7 check(min_days between 1 and 60),
 max_days integer not null default 20 check(max_days between 1 and 60 and max_days>=min_days),
 target_price numeric(10,2) check(target_price>0),
 enabled boolean not null default true,
 created_at timestamptz not null default now(),
 unique(user_id,origin,destination,min_days,max_days)
);
create index monitors_user_idx on public.monitors(user_id);
create function private.enforce_monitor_limit() returns trigger language plpgsql security definer set search_path='' as $$
declare max_count integer;
begin
 if new.user_id is distinct from (select auth.uid()) then raise exception 'Usuário inválido.'; end if;
 if not private.is_active() then raise exception 'Conta sem acesso ativo.'; end if;
 perform pg_advisory_xact_lock(hashtextextended(new.user_id::text,0));
 max_count:=case when private.is_pro() then 30 else 3 end;
 if(select count(*) from public.monitors where user_id=new.user_id)>=max_count then raise exception 'Limite de radares do plano atingido.';end if;
 return new;
end;$$;
revoke all on function private.enforce_monitor_limit() from public,anon,authenticated;
create trigger enforce_monitor_limit before insert on public.monitors for each row execute function private.enforce_monitor_limit();

create table public.offers (
 id uuid primary key default gen_random_uuid(),
 origin text not null,
 destination text not null,
 city text not null,
 country text not null,
 region text not null,
 departure_date date not null,
 return_date date not null check(return_date>departure_date),
 stay_days integer generated always as(return_date-departure_date) stored,
 price_brl numeric(12,2) not null check(price_brl>0),
 airlines text[] not null check(cardinality(airlines)>0 and airlines<@array['LA']),
 stops integer not null default 0 check(stops>=0),
 source text not null default 'google_flights',
 provider text not null default 'fast_flights',
 fare_scope text not null default 'round_trip_search' check(fare_scope='round_trip_search'),
 carrier_validation text not null default 'search_filter_and_outbound',
 booking_url text not null check(booking_url like 'https://www.google.com/travel/flights%'),
 collected_at timestamptz not null default now(),
 expires_at timestamptz not null default(now()+interval '8 hours'),
 unique(origin,destination,departure_date,return_date)
);
create index offers_valid_price_idx on public.offers(expires_at,price_brl);
create index offers_route_date_idx on public.offers(origin,destination,departure_date);
create table public.fare_history (
 id bigint generated always as identity primary key,
 offer_id uuid not null references public.offers(id) on delete cascade,
 price_brl numeric(12,2) not null check(price_brl>0),
 observed_at timestamptz not null default now()
);
create index fare_history_offer_idx on public.fare_history(offer_id,observed_at desc);
create table public.favorites (
 user_id uuid not null references public.profiles(id) on delete cascade,
 offer_id uuid not null references public.offers(id) on delete cascade,
 created_at timestamptz not null default now(),
 primary key(user_id,offer_id)
);
create index favorites_offer_idx on public.favorites(offer_id);
create table public.pro_interest (
 user_id uuid primary key references public.profiles(id) on delete cascade,
 created_at timestamptz not null default now()
);
create table public.scan_runs (
 id uuid primary key default gen_random_uuid(),
 started_at timestamptz not null default now(),
 finished_at timestamptz,
 status text not null default 'running' check(status in ('running','completed','partial','failed')),
 queries_attempted integer not null default 0,
 total_combinations integer not null default 0,
 offers_found integer not null default 0,
 errors_count integer not null default 0,
 coverage_complete boolean not null default false,
 provider text not null default 'fast_flights',
 message text
);
create table public.scanner_state (
 id integer primary key default 1 check(id=1),
 cursor_position bigint not null default 0,
 config_hash text,
 anchor_date date,
 last_run_id uuid references public.scan_runs(id),
 updated_at timestamptz not null default now()
);
create table private.billing_events (
 provider_event_id text primary key,
 user_id uuid references public.profiles(id) on delete set null,
 provider text not null,
 received_at timestamptz not null default now(),
 processed_at timestamptz
);
alter table private.billing_events enable row level security;
comment on table private.billing_events is 'Reservado para webhooks de cobrança verificados e idempotentes. Sem gateway ativo.';

create function private.admin_update_member(target_id uuid,new_plan text,new_status text,valid_until timestamptz) returns void language plpgsql security definer set search_path='' as $$
begin
 if(select auth.uid()) is null or not private.is_admin() then raise exception 'Acesso administrativo necessário.';end if;
 if target_id=(select auth.uid()) and new_status<>'active' then raise exception 'Você não pode suspender sua própria conta.';end if;
 if new_plan not in ('free','pro') or new_status not in ('active','suspended') then raise exception 'Plano ou status inválido.';end if;
 update public.profiles set plan=new_plan,status=new_status,pro_until=case when new_plan='pro' then valid_until else null end where id=target_id;
 if not found then raise exception 'Usuário não encontrado.';end if;
end;$$;
create function public.admin_update_member(target_id uuid,new_plan text,new_status text,valid_until timestamptz default null) returns void language sql security invoker set search_path='' as $$select private.admin_update_member(target_id,new_plan,new_status,valid_until);$$;
revoke all on function private.admin_update_member(uuid,text,text,timestamptz),public.admin_update_member(uuid,text,text,timestamptz) from public,anon;
grant execute on function private.admin_update_member(uuid,text,text,timestamptz),public.admin_update_member(uuid,text,text,timestamptz) to authenticated;

alter table public.profiles enable row level security;
alter table public.preferences enable row level security;
alter table public.scanner_settings enable row level security;
alter table public.monitors enable row level security;
alter table public.offers enable row level security;
alter table public.fare_history enable row level security;
alter table public.favorites enable row level security;
alter table public.pro_interest enable row level security;
alter table public.scan_runs enable row level security;
alter table public.scanner_state enable row level security;

-- Remover concessões automáticas. Somente operações explícitas abaixo.
revoke all on public.profiles,public.preferences,public.scanner_settings,public.monitors,public.offers,public.fare_history,public.favorites,public.pro_interest,public.scan_runs,public.scanner_state from anon,authenticated;
grant select on public.profiles,public.preferences,public.scanner_settings,public.monitors,public.offers,public.fare_history,public.favorites,public.pro_interest,public.scan_runs to authenticated;
grant update(full_name) on public.profiles to authenticated;
grant insert,update,delete on public.preferences,public.monitors,public.favorites to authenticated;
grant insert,update on public.pro_interest to authenticated;
grant update on public.scanner_settings to authenticated;
grant all on public.profiles,public.preferences,public.scanner_settings,public.monitors,public.offers,public.fare_history,public.favorites,public.pro_interest,public.scan_runs,public.scanner_state to service_role;
grant usage,select on sequence public.fare_history_id_seq to service_role;
create policy profiles_read on public.profiles for select to authenticated using(id=(select auth.uid()) or(select private.is_admin()));
create policy profiles_update on public.profiles for update to authenticated using(id=(select auth.uid()) and(select private.is_active())) with check(id=(select auth.uid()) and(select private.is_active()));
create policy preferences_owner on public.preferences for all to authenticated using(user_id=(select auth.uid()) and(select private.is_active())) with check(user_id=(select auth.uid()) and(select private.is_active()));
create policy monitors_owner on public.monitors for all to authenticated using(user_id=(select auth.uid()) and(select private.is_active())) with check(user_id=(select auth.uid()) and(select private.is_active()));
create policy offers_read on public.offers for select to authenticated using((select private.is_active()) and expires_at>now() and departure_date>=(now() at time zone 'America/Sao_Paulo')::date);
create policy fare_history_pro on public.fare_history for select to authenticated using((select private.is_pro()));
create policy favorites_owner on public.favorites for all to authenticated using(user_id=(select auth.uid()) and(select private.is_active())) with check(user_id=(select auth.uid()) and(select private.is_active()));
create policy interest_owner on public.pro_interest for all to authenticated using(user_id=(select auth.uid()) and(select private.is_active())) with check(user_id=(select auth.uid()) and(select private.is_active()));
create policy settings_read on public.scanner_settings for select to authenticated using((select private.is_active()));
create policy settings_admin on public.scanner_settings for update to authenticated using((select private.is_admin())) with check((select private.is_admin()));
create policy runs_read on public.scan_runs for select to authenticated using((select private.is_active()));
insert into public.scanner_settings(id,destinations) values(1,'[
 {"code":"MIA","city":"Miami","country":"Estados Unidos","region":"EUA","enabled":true},
 {"code":"JFK","city":"Nova York","country":"Estados Unidos","region":"EUA","enabled":true},
 {"code":"LAX","city":"Los Angeles","country":"Estados Unidos","region":"EUA","enabled":true},
 {"code":"MCO","city":"Orlando","country":"Estados Unidos","region":"EUA","enabled":true},
 {"code":"BOS","city":"Boston","country":"Estados Unidos","region":"EUA","enabled":true},
 {"code":"LIS","city":"Lisboa","country":"Portugal","region":"Europa","enabled":true},
 {"code":"MAD","city":"Madri","country":"Espanha","region":"Europa","enabled":true},
 {"code":"BCN","city":"Barcelona","country":"Espanha","region":"Europa","enabled":true},
 {"code":"CDG","city":"Paris","country":"França","region":"Europa","enabled":true},
 {"code":"LHR","city":"Londres","country":"Reino Unido","region":"Europa","enabled":true},
 {"code":"FCO","city":"Roma","country":"Itália","region":"Europa","enabled":true},
 {"code":"MXP","city":"Milão","country":"Itália","region":"Europa","enabled":true},
 {"code":"FRA","city":"Frankfurt","country":"Alemanha","region":"Europa","enabled":true},
 {"code":"NRT","city":"Tóquio","country":"Japão","region":"Ásia","enabled":false},
 {"code":"ICN","city":"Seul","country":"Coreia do Sul","region":"Ásia","enabled":false},
 {"code":"BKK","city":"Bangkok","country":"Tailândia","region":"Ásia","enabled":false}
]');
insert into public.scanner_state(id) values(1);
