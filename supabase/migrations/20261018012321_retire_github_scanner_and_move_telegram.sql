-- Keep the existing Vault token, fixed recipient, Edge relay and retry protocol.
-- Only the source and the Telegram-specific price rule change.
alter table private.telegram_alerts add column tarifa_id bigint
 references public.tarifaspromo(id) on delete set null;
create index telegram_alerts_tarifa_idx on private.telegram_alerts(tarifa_id);
update private.telegram_alerts set status='skipped',last_error_code='legacy_source_retired'
 where kind='offer' and status in ('queued','sending','processing');

create function private.tarifapromo_is_latam(t public.tarifaspromo) returns boolean
language sql immutable set search_path='' as $$
 select coalesce(upper(trim(t.companhia)) ~ '^(LA|LATAM( AIRLINES)?( BRASIL)?)$',false)
 and not exists(select 1 from regexp_matches(upper(coalesce(t.voos,'')),'\m([A-Z][A-Z0-9])\s*[0-9]{1,4}\M','g') carrier where carrier[1]<>'LA');
$$;
create function private.telegram_tarifa_eligible(t public.tarifaspromo) returns boolean
language sql stable set search_path='' as $$
 select t.data_ida>=(now() at time zone 'America/Sao_Paulo')::date and t.preco>0
  and t.preco < case when private.tarifapromo_is_latam(t) then 3000 else 2500 end;
$$;
create function private.telegram_tarifa_text(t public.tarifaspromo) returns text
language plpgsql immutable set search_path='' as $$
declare message text;
begin
 message:=format(E'✈️ Órbita · nova tarifa\n\n%s → %s · %s\nIda: %s\n%s\nCompanhia: %s\nVoos: %s\nHorários: %s → %s\nDuração do voo: %s\nConexões: %s\n\n%s: %s por pessoa\n',
  t.origem,t.destino,coalesce(t.destino_nome,t.destino),to_char(t.data_ida,'DD/MM/YYYY'),
  case when t.data_volta is not null then format('Volta: %s · %s dias',to_char(t.data_volta,'DD/MM/YYYY'),t.data_volta-t.data_ida) else 'Somente ida' end,
  coalesce(nullif(t.companhia,''),'Não informada'),coalesce(nullif(t.voos,''),'A confirmar'),
  coalesce(nullif(t.horario_partida,''),'A confirmar'),coalesce(nullif(t.horario_chegada,''),'A confirmar'),
  coalesce(nullif(t.duracao_total,''),'A confirmar'),coalesce(nullif(t.escalas,''),'A confirmar'),
  case when t.data_volta is not null then 'Ida e volta' else 'Somente ida' end,private.telegram_brl(t.preco));
 if private.tarifapromo_is_latam(t) then
  message:=message||format(E'\nProjeção LATAM com milhas: %s a %s (25–30%%). Estimativa, sem resgate confirmado.\n',
   private.telegram_brl(t.preco*.70),private.telegram_brl(t.preco*.75));
 end if;
 return left(message||E'\nConfira todos os trechos, bagagem e preço final no Google Flights.',3900);
end $$;
revoke all on function private.tarifapromo_is_latam(public.tarifaspromo),private.telegram_tarifa_eligible(public.tarifaspromo),private.telegram_tarifa_text(public.tarifaspromo)
 from public,anon,authenticated,service_role;

create or replace function private.dispatch_telegram_alert(alert_id uuid) returns boolean
language plpgsql security definer set search_path='' as $$
declare alert private.telegram_alerts; config private.telegram_settings; req_id bigint; nonce uuid;
begin
 select * into alert from private.telegram_alerts where id=alert_id and status='queued'
  and attempts<3 and next_attempt_at<=now() for update skip locked;
 if not found then return false; end if;
 select * into config from private.telegram_settings where id=1 for update;
 if not config.enabled or config.chat_id is null or config.relay_url is null or config.next_send_at>clock_timestamp() then return false; end if;
 if alert.kind='offer' and not exists(select 1 from public.tarifaspromo t where t.id=alert.tarifa_id
  and private.telegram_tarifa_eligible(t) and t.preco=alert.price_brl
  and md5(jsonb_build_array(t.origem,t.destino,t.data_ida,t.data_volta,t.preco,t.companhia,t.voos)::text)=alert.dedupe_key) then
  update private.telegram_alerts set status='skipped',last_error_code='fare_outdated' where id=alert.id;return false;
 end if;
 nonce:=gen_random_uuid();
 req_id:=net.http_post(url:=config.relay_url,body:=jsonb_build_object('alert_id',alert.id,'nonce',nonce),
  headers:='{"Content-Type":"application/json"}'::jsonb,timeout_milliseconds:=30000);
 update private.telegram_alerts set status='sending',attempts=attempts+1,request_id=req_id,dispatch_nonce=nonce,
  requested_at=now(),last_error_code=null where id=alert.id;
 update private.telegram_settings set next_send_at=clock_timestamp()+interval '1100 milliseconds' where id=1;
 return true;
exception when others then
 update private.telegram_alerts set last_error_code='dispatch_unavailable',next_attempt_at=now()+interval '1 minute' where id=alert_id;
 return false;
end $$;

create or replace function private.claim_telegram_alert(alert_id uuid,nonce uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare alert private.telegram_alerts; config private.telegram_settings; bot_token text;
begin
 select * into alert from private.telegram_alerts a where a.id=alert_id and a.dispatch_nonce=nonce and a.status='sending' for update skip locked;
 if not found then return null; end if;
 select * into config from private.telegram_settings where id=1;
 if not config.enabled or config.chat_id is null then return null; end if;
 if alert.kind='offer' and not exists(select 1 from public.tarifaspromo t where t.id=alert.tarifa_id
  and private.telegram_tarifa_eligible(t) and t.preco=alert.price_brl
  and md5(jsonb_build_array(t.origem,t.destino,t.data_ida,t.data_volta,t.preco,t.companhia,t.voos)::text)=alert.dedupe_key) then
  update private.telegram_alerts set status='skipped',last_error_code='fare_outdated' where id=alert.id;return null;
 end if;
 select decrypted_secret into bot_token from vault.decrypted_secrets where name='orbita_telegram_bot_token';
 if bot_token is null then return null; end if;
 update private.telegram_alerts set status='processing',requested_at=now() where id=alert.id;
 return jsonb_build_object('bot_token',bot_token,'chat_id',config.chat_id,'text',alert.message_text,'booking_url',alert.booking_url);
end $$;

create function private.enqueue_telegram_tarifa() returns trigger
language plpgsql security definer set search_path='' as $$
declare alert_id uuid; fingerprint text;
begin
 if not private.telegram_tarifa_eligible(new) then return new; end if;
 fingerprint:=md5(jsonb_build_array(new.origem,new.destino,new.data_ida,new.data_volta,new.preco,new.companhia,new.voos)::text);
 insert into private.telegram_alerts(tarifa_id,dedupe_key,message_text,booking_url,price_brl,airlines)
 values(new.id,fingerprint,private.telegram_tarifa_text(new),new.link_google_voos,new.preco,
  case when private.tarifapromo_is_latam(new) then array['LA'] else array[coalesce(new.companhia,'UNKNOWN')] end)
 on conflict(dedupe_key) do nothing returning id into alert_id;
 if alert_id is not null then perform private.dispatch_telegram_alert(alert_id);end if;
 return new;
end $$;
revoke all on function private.enqueue_telegram_tarifa(),private.dispatch_telegram_alert(uuid) from public,anon,authenticated,service_role;
create trigger tarifaspromo_telegram_alert after insert or update of preco,companhia,voos,origem,destino,data_ida,data_volta on public.tarifaspromo
 for each row execute function private.enqueue_telegram_tarifa();

-- Drop only the retired collector's objects; the external collector's feed,
-- timestamp trigger, view, authentication and Telegram transport remain intact.
alter table private.telegram_alerts drop column offer_id;
drop function private.telegram_offer_text(public.offers);
drop table public.favorites,public.fare_history,public.offers;
drop table public.calendar_jobs,public.scan_events,public.scan_session_summaries,public.scanner_state,public.scan_runs,public.scanner_settings;
drop table private.billing_events;
drop function if exists public.get_session_composition(uuid);
drop function if exists private.build_session_composition(uuid);
drop function if exists private.snapshot_session_composition();
drop function if exists private.enqueue_telegram_offer();
drop function if exists private.enforce_offer_fare_cap();
drop function if exists private.offer_fare_cap(text,text,text);
