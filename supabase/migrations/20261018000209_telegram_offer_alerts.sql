create extension if not exists pg_net with schema extensions;
create extension if not exists pg_cron with schema pg_catalog;
-- Network queues contain authenticated URLs; no browser role may inspect them.
revoke all on schema net from public,anon,authenticated;
revoke all on all tables in schema net from public,anon,authenticated;
revoke all on vault.decrypted_secrets from public,anon,authenticated;

create table private.telegram_settings (
 id integer primary key check(id=1),
 enabled boolean not null default false,
 chat_id bigint,
 next_send_at timestamptz not null default now(),
 check(not enabled or chat_id is not null)
);
insert into private.telegram_settings(id) values(1);
alter table private.telegram_settings enable row level security;
revoke all on private.telegram_settings from public,anon,authenticated,service_role;

create table private.telegram_alerts (
 id uuid primary key default gen_random_uuid(),
 offer_id uuid references public.offers(id) on delete set null,
 kind text not null default 'offer' check(kind in ('offer','test')),
 dedupe_key text not null unique,
 message_text text not null check(length(message_text)<=4000),
 booking_url text,
 price_brl numeric(12,2),
 airlines text[],
 status text not null default 'queued' check(status in ('queued','sending','sent','failed','skipped')),
 attempts integer not null default 0 check(attempts between 0 and 3),
 next_attempt_at timestamptz not null default now(),
 request_id bigint,
 requested_at timestamptz,
 sent_at timestamptz,
 telegram_message_id bigint,
 last_error_code text,
 created_at timestamptz not null default now()
);
create index telegram_alerts_queue_idx on private.telegram_alerts(next_attempt_at) where status='queued';
create index telegram_alerts_pending_idx on private.telegram_alerts(request_id) where status='sending';
create index telegram_alerts_offer_idx on private.telegram_alerts(offer_id);
alter table private.telegram_alerts enable row level security;
revoke all on private.telegram_alerts from public,anon,authenticated,service_role;

create function private.telegram_brl(value numeric) returns text
language sql immutable set search_path='' as $$
 select 'R$ '||translate(to_char(value,'FM999,999,990.00'),',.','.,');
$$;

create function private.telegram_offer_text(offer public.offers) returns text
language plpgsql immutable set search_path='' as $$
declare message text;
begin
 message := format(E'✈️ Órbita · nova tarifa\n\n%s → %s · %s, %s\nIda: %s\nVolta: %s · %s dias\nCompanhia: %s\n%s\n\nIda e volta: %s por pessoa\nEconômica · 1 adulto\n',
  offer.origin,offer.destination,offer.city,offer.country,
  to_char(offer.departure_date,'DD/MM/YYYY'),to_char(offer.return_date,'DD/MM/YYYY'),
  offer.return_date-offer.departure_date,array_to_string(offer.airline_names,' + '),
  case when offer.stops=0 then 'Voo direto' else offer.stops||' conexão(ões)' end,
  private.telegram_brl(offer.price_brl));
 if offer.airlines=array['LA'] then
  message := message||format(E'\nProjeção LATAM com milhas: %s a %s (25–30%%). Estimativa, sem resgate confirmado.\n',
   private.telegram_brl(offer.price_brl*.70),private.telegram_brl(offer.price_brl*.75));
 end if;
 return left(message||E'\nCompanhia identificada na ida. Confira os voos, bagagem e preço final no Google Flights.',3900);
end;
$$;
revoke all on function private.telegram_brl(numeric),private.telegram_offer_text(public.offers) from public,anon,authenticated,service_role;

-- Only the database can read the bot token from Vault and choose the fixed chat.
create function private.dispatch_telegram_alert(alert_id uuid) returns boolean
language plpgsql security definer set search_path='' as $$
declare alert private.telegram_alerts; config private.telegram_settings; bot_token text; req_id bigint; buttons jsonb;
begin
 select * into alert from private.telegram_alerts where id=alert_id and status='queued'
  and attempts<3 and next_attempt_at<=now() for update skip locked;
 if not found then return false; end if;
 select * into config from private.telegram_settings where id=1 for update;
 if not config.enabled or config.chat_id is null or config.next_send_at>clock_timestamp() then return false; end if;
 select decrypted_secret into bot_token from vault.decrypted_secrets where name='orbita_telegram_bot_token';
 if bot_token is null then return false; end if;
 if alert.kind='offer' and not exists(select 1 from public.offers o where o.id=alert.offer_id
  and o.expires_at>now() and o.departure_date>=(now() at time zone 'America/Sao_Paulo')::date
  and o.price_brl=alert.price_brl and o.airlines=alert.airlines) then
  update private.telegram_alerts set status='skipped',last_error_code='fare_outdated' where id=alert.id;
  return false;
 end if;
 buttons := jsonb_build_array(jsonb_build_array(jsonb_build_object('text','Abrir Órbita','url','https://htcegit.github.io/orbita-milhas/')));
 if alert.booking_url like 'https://www.google.com/travel/flights%' then
  buttons := jsonb_build_array(jsonb_build_array(jsonb_build_object('text','Ver tarifa no Google Flights','url',alert.booking_url)))||buttons;
 end if;
 req_id := net.http_post(url:='https://api.telegram.org/bot'||bot_token||'/sendMessage',
  body:=jsonb_build_object('chat_id',config.chat_id,'text',alert.message_text,
   'link_preview_options',jsonb_build_object('is_disabled',true),'reply_markup',jsonb_build_object('inline_keyboard',buttons)),
  headers:='{"Content-Type":"application/json"}'::jsonb,timeout_milliseconds:=15000);
 update private.telegram_alerts set status='sending',attempts=attempts+1,request_id=req_id,
  requested_at=now(),last_error_code=null where id=alert.id;
 update private.telegram_settings set next_send_at=clock_timestamp()+interval '1100 milliseconds' where id=1;
 return true;
exception when others then
 -- Never emit the authenticated URL or raw upstream errors into application logs.
 update private.telegram_alerts set last_error_code='dispatch_unavailable',next_attempt_at=now()+interval '1 minute' where id=alert_id;
 return false;
end;
$$;
revoke all on function private.dispatch_telegram_alert(uuid) from public,anon,authenticated,service_role;

create function private.enqueue_telegram_offer() returns trigger
language plpgsql security definer set search_path='' as $$
declare alert_id uuid; fingerprint text;
begin
 if new.expires_at<=now() or new.departure_date<(now() at time zone 'America/Sao_Paulo')::date then return new; end if;
 fingerprint := md5(jsonb_build_array(new.origin,new.destination,new.departure_date,new.return_date,new.price_brl,new.airlines)::text);
 insert into private.telegram_alerts(offer_id,dedupe_key,message_text,booking_url,price_brl,airlines)
 values(new.id,fingerprint,private.telegram_offer_text(new),new.booking_url,new.price_brl,new.airlines)
 on conflict(dedupe_key) do nothing returning id into alert_id;
 if alert_id is not null then perform private.dispatch_telegram_alert(alert_id); end if;
 return new;
end;
$$;
revoke all on function private.enqueue_telegram_offer() from public,anon,authenticated,service_role;
create trigger offers_telegram_alert after insert or update of price_brl,airlines,expires_at on public.offers
 for each row execute function private.enqueue_telegram_offer();

create function private.process_telegram_alerts() returns integer
language plpgsql security definer set search_path='' as $$
declare alert private.telegram_alerts; response record; body jsonb; code integer; delay_seconds integer; candidate uuid; dispatched integer:=0;
begin
 if not pg_try_advisory_xact_lock(728193541) then return 0; end if;
 for alert in select * from private.telegram_alerts where status='sending' order by requested_at limit 100 for update skip locked loop
  select status_code,content,timed_out,error_msg into response from net._http_response where id=alert.request_id;
  if not found and alert.requested_at>now()-interval '5 minutes' then continue; end if;
  body := '{}'::jsonb;
  if found then
   begin body:=coalesce(response.content,'{}')::jsonb; exception when others then body:='{}'::jsonb; end;
  end if;
  code:=coalesce(response.status_code,0);
  if code=200 and body->>'ok'='true' then
   update private.telegram_alerts set status='sent',sent_at=now(),telegram_message_id=(body#>>'{result,message_id}')::bigint,last_error_code=null where id=alert.id;
  else
   delay_seconds:=least(86400,greatest(60,coalesce((body#>>'{parameters,retry_after}')::integer,60*(2^(alert.attempts-1))::integer)));
   update private.telegram_alerts set
    status=case when alert.attempts<3 and (code=0 or code=429 or code>=500) then 'queued' else 'failed' end,
    next_attempt_at=now()+make_interval(secs=>delay_seconds),
    last_error_code=case when code=0 then 'delivery_unknown' else 'telegram_http_'||code end
    where id=alert.id;
  end if;
 end loop;
 select id into candidate from private.telegram_alerts where status='queued' and next_attempt_at<=now() order by created_at limit 1;
 if candidate is not null and private.dispatch_telegram_alert(candidate) then dispatched:=1; end if;
 -- Keep only this integration's scheduler history bounded.
 delete from cron.job_run_details where jobid in (select jobid from cron.job where jobname='orbita-telegram-alerts') and end_time<now()-interval '1 day';
 delete from private.telegram_alerts where created_at<now()-interval '90 days' and status in ('sent','failed','skipped');
 return dispatched;
end;
$$;
revoke all on function private.process_telegram_alerts() from public,anon,authenticated,service_role;
select cron.schedule('orbita-telegram-alerts','* * * * *','select private.process_telegram_alerts()');

comment on table private.telegram_alerts is 'Server-only outbox. Identical route/dates/price/carriers are deduplicated. pg_net sends after commit; a timeout can lead to a duplicate on retry. No bot token is stored in this table.';
comment on table private.telegram_settings is 'Fixed private Telegram recipient. The bot token is stored only in Supabase Vault, named orbita_telegram_bot_token.';
