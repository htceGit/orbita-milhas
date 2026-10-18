-- pg_net is managed by Supabase. Its internal queues can have broad grants,
-- so authenticated Telegram URLs and bot tokens must never enter those queues.
alter table private.telegram_settings add column relay_url text
 check(relay_url ~ '^https://[a-z0-9]+\.supabase\.co/functions/v1/telegram-alert$');
alter table private.telegram_settings add constraint telegram_enabled_relay
 check(not enabled or relay_url is not null);
alter table private.telegram_alerts add column dispatch_nonce uuid;
alter table private.telegram_alerts drop constraint telegram_alerts_status_check;
alter table private.telegram_alerts add constraint telegram_alerts_status_check
 check(status in ('queued','sending','processing','sent','failed','skipped'));

create or replace function private.dispatch_telegram_alert(alert_id uuid) returns boolean
language plpgsql security definer set search_path='' as $$
declare alert private.telegram_alerts; config private.telegram_settings; req_id bigint; nonce uuid;
begin
 select * into alert from private.telegram_alerts where id=alert_id and status='queued'
  and attempts<3 and next_attempt_at<=now() for update skip locked;
 if not found then return false; end if;
 select * into config from private.telegram_settings where id=1 for update;
 if not config.enabled or config.chat_id is null or config.relay_url is null or config.next_send_at>clock_timestamp() then return false; end if;
 if alert.kind='offer' and not exists(select 1 from public.offers o where o.id=alert.offer_id
  and o.expires_at>now() and o.departure_date>=(now() at time zone 'America/Sao_Paulo')::date
  and o.price_brl=alert.price_brl and o.airlines=alert.airlines) then
  update private.telegram_alerts set status='skipped',last_error_code='fare_outdated' where id=alert.id;
  return false;
 end if;
 nonce:=gen_random_uuid();
 req_id:=net.http_post(url:=config.relay_url,
  body:=jsonb_build_object('alert_id',alert.id,'nonce',nonce),
  headers:='{"Content-Type":"application/json"}'::jsonb,timeout_milliseconds:=30000);
 update private.telegram_alerts set status='sending',attempts=attempts+1,request_id=req_id,dispatch_nonce=nonce,
  requested_at=now(),last_error_code=null where id=alert.id;
 update private.telegram_settings set next_send_at=clock_timestamp()+interval '1100 milliseconds' where id=1;
 return true;
exception when others then
 update private.telegram_alerts set last_error_code='dispatch_unavailable',next_attempt_at=now()+interval '1 minute' where id=alert_id;
 return false;
end;
$$;

-- An unguessable one-time dispatch can send only an already queued message to
-- the fixed recipient. Only the Edge Function's service identity may claim it.
create function private.claim_telegram_alert(alert_id uuid,nonce uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare alert private.telegram_alerts; config private.telegram_settings; bot_token text;
begin
 select * into alert from private.telegram_alerts a where a.id=alert_id and a.dispatch_nonce=nonce and a.status='sending'
  for update skip locked;
 if not found then return null; end if;
 select * into config from private.telegram_settings where id=1;
 if not config.enabled or config.chat_id is null then return null; end if;
 if alert.kind='offer' and not exists(select 1 from public.offers o where o.id=alert.offer_id
  and o.expires_at>now() and o.departure_date>=(now() at time zone 'America/Sao_Paulo')::date
  and o.price_brl=alert.price_brl and o.airlines=alert.airlines) then
  update private.telegram_alerts set status='skipped',last_error_code='fare_outdated' where id=alert.id;
  return null;
 end if;
 select decrypted_secret into bot_token from vault.decrypted_secrets where name='orbita_telegram_bot_token';
 if bot_token is null then return null; end if;
 update private.telegram_alerts set status='processing',requested_at=now() where id=alert.id;
 return jsonb_build_object('bot_token',bot_token,'chat_id',config.chat_id,'text',alert.message_text,'booking_url',alert.booking_url);
end;
$$;
create function public.claim_telegram_alert(alert_id uuid,nonce uuid) returns jsonb
language sql security invoker set search_path='' as $$select private.claim_telegram_alert(alert_id,nonce)$$;
revoke all on function private.claim_telegram_alert(uuid,uuid),public.claim_telegram_alert(uuid,uuid) from public,anon,authenticated;
grant execute on function private.claim_telegram_alert(uuid,uuid),public.claim_telegram_alert(uuid,uuid) to service_role;

create function private.complete_telegram_alert(alert_id uuid,nonce uuid,delivered boolean,message_id bigint default null,error_code integer default null,retry_after integer default null)
returns text language plpgsql security definer set search_path='' as $$
declare result text;
begin
 update private.telegram_alerts a set
  status=case when delivered then 'sent' when a.attempts<3 and (coalesce(error_code,0)=0 or error_code=429 or error_code>=500) then 'queued' else 'failed' end,
  sent_at=case when delivered then now() else null end,telegram_message_id=case when delivered then message_id else null end,
  next_attempt_at=now()+make_interval(secs=>least(86400,greatest(60,coalesce(retry_after,60*(2^(a.attempts-1))::integer)))),
  last_error_code=case when delivered then null when coalesce(error_code,0)=0 then 'delivery_unknown' else 'telegram_http_'||error_code end
 where a.id=alert_id and a.dispatch_nonce=nonce and a.status='processing'
 returning a.status into result;
 return result;
end;
$$;
create function public.complete_telegram_alert(alert_id uuid,nonce uuid,delivered boolean,message_id bigint default null,error_code integer default null,retry_after integer default null)
returns text language sql security invoker set search_path='' as $$select private.complete_telegram_alert(alert_id,nonce,delivered,message_id,error_code,retry_after)$$;
revoke all on function private.complete_telegram_alert(uuid,uuid,boolean,bigint,integer,integer),public.complete_telegram_alert(uuid,uuid,boolean,bigint,integer,integer) from public,anon,authenticated;
grant execute on function private.complete_telegram_alert(uuid,uuid,boolean,bigint,integer,integer),public.complete_telegram_alert(uuid,uuid,boolean,bigint,integer,integer) to service_role;

create or replace function private.process_telegram_alerts() returns integer
language plpgsql security definer set search_path='' as $$
declare candidate uuid;
begin
 if not pg_try_advisory_xact_lock(728193541) then return 0; end if;
 -- Edge records the Telegram result itself. A missing Edge response is retried
 -- after five minutes; a hard relay HTTP error can be retried on the next tick.
 update private.telegram_alerts a set
  status=case when attempts<3 then 'queued' else 'failed' end,
  next_attempt_at=now()+interval '1 minute',last_error_code='relay_unavailable'
 where a.status in ('sending','processing') and
  (a.requested_at<now()-interval '5 minutes' or
   (a.status='sending' and exists(select 1 from net._http_response r where r.id=a.request_id and (r.status_code>=400 or r.timed_out or r.error_msg is not null))));
 select id into candidate from private.telegram_alerts where status='queued' and next_attempt_at<=now() order by created_at limit 1;
 if candidate is not null then perform private.dispatch_telegram_alert(candidate); end if;
 delete from cron.job_run_details where jobid in (select jobid from cron.job where jobname='orbita-telegram-alerts') and end_time<now()-interval '1 day';
 delete from private.telegram_alerts where created_at<now()-interval '90 days' and status in ('sent','failed','skipped');
 return case when candidate is null then 0 else 1 end;
end;
$$;
comment on table private.telegram_alerts is 'Server-only outbox. HTTP queue contains only an alert UUID and one-time dispatch nonce. Bot token and recipient are fetched only by the service-authenticated Edge Function. Deduplicates route/dates/price/carriers; a delivery timeout may cause a duplicate on retry.';
