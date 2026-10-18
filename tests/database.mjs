import {PGlite} from '@electric-sql/pglite';
import {readFile,readdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const db=new PGlite();
await db.exec(`
 create role anon;create role authenticated;create role service_role bypassrls;
 create schema auth;
 create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}'::jsonb,email_confirmed_at timestamptz);
 create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 grant usage on schema public,auth to anon,authenticated,service_role;
 grant execute on function auth.uid() to anon,authenticated,service_role;
`);
const files=(await readdir('supabase/migrations')).filter(f=>f.endsWith('.sql')).sort();
for(const f of files){
 if(f.endsWith('_enforce_offer_fare_caps.sql')){
  await db.exec(`insert into public.offers(origin,destination,city,country,region,departure_date,return_date,price_brl,airlines,airline_names,booking_url,carrier_validation) values
   ('GRU','MIA','Miami','Estados Unidos','EUA','2027-02-01','2027-02-15',3000.01,array['LA'],array['LATAM'],'https://www.google.com/travel/flights','outbound_only'),
   ('GRU','LIS','Lisboa','Portugal','Europa','2027-02-01','2027-02-15',3500.01,array['TP'],array['TAP'],'https://www.google.com/travel/flights','outbound_only');
   insert into public.fare_history(offer_id,price_brl) select id,price_brl from public.offers;`);
 }
 let migration=await readFile('supabase/migrations/'+f,'utf8');
 if(f.endsWith('_telegram_offer_alerts.sql')){
  await db.exec(await readFile('tests/telegram-transport-fixture.sql','utf8'));
  migration=migration.replace(/^create extension if not exists (pg_net|pg_cron) with schema \w+;$/gm,'');
 }
 await db.exec(migration);
}
assert.equal((await db.query('select count(*)::int n from public.offers where expires_at>now()')).rows[0].n,0,'ofertas legadas acima do teto são expiradas');
assert.equal((await db.query('select count(*)::int n from public.fare_history')).rows[0].n,2,'histórico de preços preservado');
await assert.rejects(db.exec("update public.offers set expires_at=now()+interval '8 hours'"),/Tarifa acima do teto/,'ofertas antigas não podem ser republicadas acima do teto');
await db.exec('delete from public.offers');
const farePolicy=JSON.parse(await readFile('fare-policy.json','utf8'));
for(const [destination,region] of Object.entries(farePolicy.destination_regions))assert.equal(Number((await db.query('select private.offer_fare_cap($1,$2,$3) cap',[destination,'',''])).rows[0].cap),farePolicy.caps[region]);
for(const [country,region] of Object.entries(farePolicy.country_regions))assert.equal(Number((await db.query('select private.offer_fare_cap($1,$2,$3) cap',['ZZZ',country,''])).rows[0].cap),farePolicy.caps[region]);
for(const [region,label] of Object.entries(farePolicy.region_names))assert.equal(Number((await db.query('select private.offer_fare_cap($1,$2,$3) cap',['ZZZ','',region])).rows[0].cap),farePolicy.caps[label]);
const a='10000000-0000-4000-8000-000000000001',b='10000000-0000-4000-8000-000000000002',admin='10000000-0000-4000-8000-000000000003';
await db.query(`insert into auth.users(id,email,raw_user_meta_data) values($1,'a@example.test','{"full_name":"A","role":"admin","plan":"pro"}'),($2,'b@example.test','{}'),($3,'admin@example.test','{}')`,[a,b,admin]);
await db.query(`update public.profiles set role='admin' where id=$1`,[admin]);
const as=async id=>{await db.exec('reset role');await db.query("select set_config('request.jwt.claim.sub',$1,false)",[id||'']);await db.exec('set role authenticated');};
await as(a);
assert.equal((await db.query('select count(*)::int n from public.profiles')).rows[0].n,1,'isolamento entre usuários');
assert.equal((await db.query('select role,plan from public.profiles')).rows[0].role,'member','metadata não eleva acesso');
await assert.rejects(db.exec("update public.profiles set plan='pro'"),/permission denied/,'não é possível autoatribuir Pro');
await assert.rejects(db.exec("update public.profiles set role='admin'"),/permission denied/,'não é possível autoatribuir Admin');
await db.query(`insert into public.monitors(user_id,origin,destination) values($1,'FLN','MIA'),($1,'CWB','LIS'),($1,'GRU','JFK')`,[a]);
await assert.rejects(db.query(`insert into public.monitors(user_id,origin,destination) values($1,'GRU','CDG')`,[a]),/Limite de radares/,'limite Free no banco');
await assert.rejects(db.query(`insert into public.monitors(user_id,origin,destination) values($1,'GRU','CDG')`,[b]),/Usuário inválido/,'não cria radar para outro usuário');
await assert.rejects(db.query(`select public.admin_update_member($1,'pro','active',null)`,[a]),/administrativo/,'membro não libera plano');
await db.exec("update public.scanner_settings set query_budget=1");
assert.equal((await db.query('select query_budget from public.scanner_settings')).rows[0].query_budget,1000,'RLS bloqueia configuração global');
await as(admin);
await db.query(`select public.admin_update_member($1,'pro','active',null)`,[a]);
await assert.rejects(db.query(`select public.admin_update_member($1,'pro','suspended',null)`,[admin]),/própria conta/);
await as(a);
await db.query(`insert into public.monitors(user_id,origin,destination) values($1,'GRU','CDG')`,[a]);
assert.equal((await db.query('select count(*)::int n from public.monitors')).rows[0].n,4,'Pro permite mais radares');
await as(b);
assert.equal((await db.query('select count(*)::int n from public.monitors')).rows[0].n,0,'radares isolados');
await as(admin);
await db.query(`select public.admin_update_member($1,'free','suspended',null)`,[a]);
await as(a);
assert.equal((await db.query('select count(*)::int n from public.scanner_settings')).rows[0].n,0,'suspensão vale mesmo com token antigo');
await db.exec('reset role;set role anon');
await assert.rejects(db.query('select * from public.offers'),/permission denied/,'visitante sem dados');
await assert.rejects(db.query('select * from public.profiles'),/permission denied/,'visitante sem perfis');
await db.exec('reset role');
await db.exec("insert into private.admin_reservations(email) values('reserved@example.test')");
const reserved='10000000-0000-4000-8000-000000000004';
await db.query("insert into auth.users(id,email) values($1,'reserved@example.test')",[reserved]);
assert.equal((await db.query('select role from public.profiles where id=$1',[reserved])).rows[0].role,'member','reserva ainda não confirmada não vira admin');
await db.query('update auth.users set email_confirmed_at=now() where id=$1',[reserved]);
assert.equal((await db.query('select role from public.profiles where id=$1',[reserved])).rows[0].role,'admin','confirmação consome reserva administrativa');
const allowedOrigins=['CWB','JOI','NVT','FLN','VCP','GRU'];
assert.deepEqual((await db.query('select origins from public.scanner_settings')).rows[0].origins,allowedOrigins);
await assert.rejects(db.exec("update public.scanner_settings set origins=array['CGH']"),/scanner_origins_allowed/);
await db.exec(`insert into public.offers(origin,destination,city,country,region,departure_date,return_date,price_brl,airlines,airline_names,booking_url,carrier_validation) values('GRU','MIA','Miami','Estados Unidos','EUA','2027-01-01','2027-01-15',3000,array['AV'],array['Avianca'],'https://www.google.com/travel/flights','outbound_only')`);
assert.equal((await db.query('select airline_names from public.offers')).rows[0].airline_names[0],'Avianca');
await db.exec('set role service_role');
await assert.rejects(db.exec("update public.offers set price_brl=3000.01"),/Tarifa acima do teto/,'até o servidor não pode atualizar oferta acima do teto');
for(const [destination,country,region,price] of [['JFK','Estados Unidos','EUA',3000.01],['SFO','Estados Unidos','EUA',4000],['LIS','Portugal','Europa',3500.01]])await assert.rejects(db.query(`insert into public.offers(origin,destination,city,country,region,departure_date,return_date,price_brl,airlines,airline_names,booking_url,carrier_validation) values('GRU',$1,'Destino',$2,$3,'2027-01-01','2027-01-15',$4,array['LA'],array['LATAM'],'https://www.google.com/travel/flights','outbound_only')`,[destination,country,region,price]),/Tarifa acima do teto/,'LATAM também obedece ao teto no banco');
await db.exec(`insert into public.offers(origin,destination,city,country,region,departure_date,return_date,price_brl,airlines,airline_names,booking_url,carrier_validation) values('GRU','LIS','Lisboa','Portugal','Europa','2027-01-01','2027-01-15',3500,array['TP'],array['TAP'],'https://www.google.com/travel/flights','outbound_only')`);
await db.exec('reset role');

await as(admin);
await assert.rejects(db.query(`insert into public.monitors(user_id,origin,destination) values($1,'CGH','MIA')`,[admin]),/monitors_enabled_origins/);
await db.exec('reset role');
const jobParams=JSON.stringify({origin:'GRU',destination:'MIA',departure_start:'2027-01-01',departure_end:'2027-01-15'});
await db.query(`insert into public.calendar_jobs(user_id,request,cache_key,status) values(null,$1,$2,'completed'),($3,$1,$2,'completed'),($4,$1,$2,'queued')`,[jobParams,'a'.repeat(64),a,b]);
await assert.rejects(db.query(`insert into public.calendar_jobs(user_id,request,cache_key) values($1,$2,$3)`,[b,jobParams,'a'.repeat(64)]),/calendar_jobs_one_pending/);
await as(b);
assert.equal((await db.query('select id from public.calendar_jobs')).rows.length,2,'capturas privadas de outra conta ficam isoladas');
await assert.rejects(db.query('select entries_gzip from public.calendar_jobs'),/permission denied/,'dados comprimidos acessíveis apenas pela API autenticada');
await assert.rejects(db.query(`insert into public.calendar_jobs(user_id,request,cache_key) values($1,$2,$3)`,[b,jobParams,'b'.repeat(64)]),/permission denied/,'clientes não podem forjar resultados');
await as(a);
assert.equal((await db.query('select id from public.calendar_jobs')).rows.length,0,'contas suspensas perdem acesso aos calendários');
await db.exec('reset role');
const scan=(await db.query("insert into public.scan_runs(diagnostics_version,query_budget,phase) values(1,1000,'calendar') returning id")).rows[0].id;
await db.query("insert into public.scan_events(run_id,stage,outcome,error_code,cause_type,message) values($1,'detail','error','parse_error','IndexError','missing field')",[scan]);
await as(b);
assert.equal((await db.query('select id from public.scan_events')).rows.length,0,'diagnósticos ficam restritos à administração');
await assert.rejects(db.query("insert into public.scan_events(run_id,stage,outcome) values($1,'detail','success')",[scan]),/permission denied/,'membro não forja eventos');
await as(admin);
assert.equal((await db.query('select cause_type from public.scan_events')).rows[0].cause_type,'IndexError','admin consulta causa original');
await assert.rejects(db.exec("update public.scan_events set message='tampered'"),/permission denied/,'admin cliente não altera registros do motor');
await db.exec('reset role;set role anon');
await assert.rejects(db.query('select * from public.scan_events'),/permission denied/,'diagnósticos não são públicos');
await db.exec('reset role');
// Session composition: complete aggregation, access control, and durable snapshots.
const compositionRun=(await db.query("insert into public.scan_runs(detail_queries,diagnostics_version) values(69,1) returning id")).rows[0].id;
const calendarRequest={origin:'FLN',destination:'MIA',departure_start:'2026-10-18',departure_end:'2027-04-17',min_days:7,max_days:8,max_stops:2};
await db.query(`insert into public.calendar_jobs(run_id,request,cache_key,status,result) values($1,$2,$3,'partial','{"priced_combinations":120,"completed_sweeps":0,"requested_sweeps":2}')`,[compositionRun,JSON.stringify(calendarRequest),'c'.repeat(64)]);
await db.query(`insert into public.scan_events(run_id,stage,outcome,origin,destination,departure_date,return_date,stay_days) values
 ($1,'detail','error','FLN','MIA','2026-11-07','2026-11-17',10),
 ($1,'detail','retry','FLN','MIA','2026-11-07','2026-11-17',10),
 ($1,'detail','success','FLN','MIA','2026-11-07','2026-11-17',10),
 ($1,'detail','filtered','FLN','MIA','2026-11-16','2026-11-26',10),
 ($1,'detail','empty','CWB','LIS','2026-12-01','2026-12-15',14),
 ($1,'calendar','error','FLN','MIA',null,null,null)`,[compositionRun]);
await db.query(`insert into public.scan_events(run_id,stage,outcome,origin,destination,departure_date,return_date,stay_days)
 select $1,'detail','empty','FLN','MIA',date '2027-01-01'+n,date '2027-01-08'+n,7 from generate_series(1,65) n`,[compositionRun]);
await db.query(`insert into public.scan_events(run_id,stage,outcome,origin,destination,departure_start,departure_end,min_days,max_days)
 values($1,'calendar','error','CWB','JFK','2026-10-18','2027-04-17',9,10)`,[compositionRun]);
await as(b);
await assert.rejects(db.query('select public.get_session_composition($1)',[compositionRun]),/administrativo/,'membro não acessa composição administrativa');
assert.equal((await db.query('select count(*)::int n from public.scan_session_summaries')).rows[0].n,0);
await as(admin);
const composition=(await db.query('select public.get_session_composition($1) result',[compositionRun])).rows[0].result;
assert.equal(composition.detail_attempts_recorded,69,'resumo considera mais de 60 eventos');
assert.equal(composition.calendars.length,2,'captura parcial não é duplicada pelo evento de erro');
const observed=composition.details.find(d=>d.stay_days===10);
assert.equal(observed.attempts,3,'evento retry não é outra chamada');
assert.equal(observed.dates_attempted,2,'tentativa repetida não cria outro par de datas');
assert.equal(observed.dates_completed,2);
assert.equal(observed.filtered,1);
assert.equal(observed.return_end,'2026-11-26');
assert.equal(composition.calendars.find(c=>c.destination==='JFK').departure_start,'2026-10-18','falha preserva o período solicitado');
await assert.rejects(db.exec('delete from public.scan_session_summaries'),/permission denied/,'cliente admin não forja resumos');
await db.exec('reset role;set role service_role');
await db.query("update public.scan_runs set status='completed',detail_queries=70,finished_at=now() where id=$1",[compositionRun]);
assert.equal((await db.query('select count(*)::int n from public.scan_session_summaries where run_id=$1',[compositionRun])).rows[0].n,1,'encerramento pelo worker cria snapshot');
await db.query('delete from public.scan_events where run_id=$1',[compositionRun]);
await db.query('delete from public.calendar_jobs where run_id=$1',[compositionRun]);
await as(admin);
assert.deepEqual((await db.query('select public.get_session_composition($1) result',[compositionRun])).rows[0].result,{...composition,detail_attempts_expected:70},'composição permanece depois da retenção dos dados brutos');
await db.exec('reset role;set role anon');
await assert.rejects(db.query('select public.get_session_composition($1)',[compositionRun]),/permission denied/);
await assert.rejects(db.query('select * from public.scan_session_summaries'),/permission denied/);
await db.exec('reset role');
// Telegram: outbox and relay never put the bot token or recipient in pg_net.
await db.exec('delete from private.telegram_alerts;delete from net.http_request_queue');
const notificationOffer=(await db.query(`insert into public.offers(origin,destination,city,country,region,departure_date,return_date,price_brl,airlines,airline_names,booking_url,carrier_validation)
 values('FLN','MIA','Miami','Estados Unidos','EUA',current_date+30,current_date+40,2999,array['LA'],array['LATAM'],'https://www.google.com/travel/flights?test=1','outbound_only') returning id`)).rows[0].id;
assert.equal((await db.query('select count(*)::int n from private.telegram_alerts where offer_id=$1',[notificationOffer])).rows[0].n,1);
assert.equal((await db.query('select count(*)::int n from net.http_request_queue')).rows[0].n,0,'sem destinatário ativado não envia');
await db.exec("insert into vault.test_secrets values('orbita_telegram_bot_token','example-token');update private.telegram_settings set enabled=true,chat_id=77,relay_url='https://example.supabase.co/functions/v1/telegram-alert',next_send_at=now()-interval '1 second'");
await db.query("update public.offers set expires_at=now()+interval '8 hours' where id=$1",[notificationOffer]);
assert.equal((await db.query('select count(*)::int n from private.telegram_alerts where offer_id=$1',[notificationOffer])).rows[0].n,1,'mesma tarifa e preço não repetem o alerta');
await db.exec('select private.process_telegram_alerts()');
let telegramAlert=(await db.query('select * from private.telegram_alerts where offer_id=$1',[notificationOffer])).rows[0];
assert.equal(telegramAlert.status,'sending');assert.equal(telegramAlert.attempts,1);
const telegramRequest=(await db.query('select url,body from net.http_request_queue where id=$1',[telegramAlert.request_id])).rows[0];
assert.deepEqual(Object.keys(telegramRequest.body).sort(),['alert_id','nonce']);
assert.equal(telegramRequest.url,'https://example.supabase.co/functions/v1/telegram-alert');
assert.ok(!JSON.stringify(telegramRequest).includes('example-token'));
await db.exec('set role service_role');
assert.equal((await db.query('select public.claim_telegram_alert($1,$2) result',[telegramAlert.id,'00000000-0000-4000-8000-000000000000'])).rows[0].result,null,'nonce incorreto não libera segredo nem envio');
const claimed=(await db.query('select public.claim_telegram_alert($1,$2) result',[telegramAlert.id,telegramAlert.dispatch_nonce])).rows[0].result;
assert.equal(claimed.chat_id,77);assert.equal(claimed.bot_token,'example-token');
for(const expected of ['FLN → MIA','LATAM','R$ 2.999,00','10 dias','Projeção LATAM','1 adulto'])assert.ok(claimed.text.includes(expected),expected);
assert.equal((await db.query('select public.claim_telegram_alert($1,$2) result',[telegramAlert.id,telegramAlert.dispatch_nonce])).rows[0].result,null,'despacho só pode ser consumido uma vez');
await db.query('select public.complete_telegram_alert($1,$2,true,42)',[telegramAlert.id,telegramAlert.dispatch_nonce]);
await db.exec('reset role');
assert.equal((await db.query('select status from private.telegram_alerts where id=$1',[telegramAlert.id])).rows[0].status,'sent');
await db.exec("update private.telegram_settings set next_send_at=now()-interval '1 second'");
await db.query('update public.offers set price_brl=2900 where id=$1',[notificationOffer]);
telegramAlert=(await db.query('select * from private.telegram_alerts where offer_id=$1 and price_brl=2900',[notificationOffer])).rows[0];
assert.equal(telegramAlert.status,'sending','preço novo gera outro alerta');
await db.exec('set role service_role');
await db.query('select public.claim_telegram_alert($1,$2)',[telegramAlert.id,telegramAlert.dispatch_nonce]);
await db.query('select public.complete_telegram_alert($1,$2,false,null,429,120)',[telegramAlert.id,telegramAlert.dispatch_nonce]);
await db.exec('reset role');
const retryState=(await db.query("select status,attempts,next_attempt_at>now()+interval '119 seconds' respects_backoff from private.telegram_alerts where id=$1",[telegramAlert.id])).rows[0];
assert.equal(retryState.status,'queued');assert.equal(retryState.attempts,1);assert.equal(retryState.respects_backoff,true);
for(let attempt=2;attempt<=3;attempt++){
 await db.query("update private.telegram_alerts set next_attempt_at=now()-interval '1 second' where id=$1",[telegramAlert.id]);
 await db.exec("update private.telegram_settings set next_send_at=now()-interval '1 second';select private.process_telegram_alerts()");
 const current=(await db.query('select dispatch_nonce,attempts from private.telegram_alerts where id=$1',[telegramAlert.id])).rows[0];
 assert.equal(current.attempts,attempt);
 await db.exec('set role service_role');
 await db.query('select public.claim_telegram_alert($1,$2)',[telegramAlert.id,current.dispatch_nonce]);
 await db.query('select public.complete_telegram_alert($1,$2,false,null,503)',[telegramAlert.id,current.dispatch_nonce]);
 await db.exec('reset role');
}
assert.equal((await db.query('select status from private.telegram_alerts where id=$1',[telegramAlert.id])).rows[0].status,'failed','limite de três tentativas');
const beforeRejected=(await db.query('select count(*)::int n from private.telegram_alerts')).rows[0].n;
await assert.rejects(db.query('update public.offers set price_brl=3000.01 where id=$1',[notificationOffer]),/Tarifa acima do teto/);
assert.equal((await db.query('select count(*)::int n from private.telegram_alerts')).rows[0].n,beforeRejected,'tarifas rejeitadas não geram alertas');
await db.exec("update private.telegram_settings set next_send_at=now()+interval '1 hour'");
await db.query('update public.offers set price_brl=2800 where id=$1',[notificationOffer]);
await db.query("update public.offers set expires_at=now()-interval '1 second' where id=$1",[notificationOffer]);
await db.exec("update private.telegram_settings set next_send_at=now()-interval '1 second';select private.process_telegram_alerts()");
assert.equal((await db.query('select status from private.telegram_alerts where offer_id=$1 and price_brl=2800',[notificationOffer])).rows[0].status,'skipped','preço expirado não é enviado depois');
const nonLatam=(await db.query("select private.telegram_offer_text(o) message from public.offers o where o.destination='LIS' limit 1")).rows[0].message;
assert.ok(!nonLatam.includes('Projeção LATAM'));
await as(admin);
for(const query of ['select * from private.telegram_settings','select * from private.telegram_alerts','select * from vault.decrypted_secrets','select * from net.http_request_queue','select private.process_telegram_alerts()'])await assert.rejects(db.query(query),/permission denied/,'mesmo admin no navegador não acessa token ou envio privilegiado');
await assert.rejects(db.query('select public.claim_telegram_alert($1,$2)',[telegramAlert.id,telegramAlert.dispatch_nonce]),/permission denied/);
await as(b);
await assert.rejects(db.query('select private.dispatch_telegram_alert($1)',[telegramAlert.id]),/permission denied/);
await db.exec('reset role');
const rls=await db.query("select tablename from pg_tables where schemaname in ('public','private') and rowsecurity=false");
assert.equal(rls.rows.length,0,'RLS em todas as tabelas do produto');
console.log('Banco validado: isolamento, limites Free/Pro, bloqueio de elevação de privilégio, suspensão e acesso administrativo.');
await db.close();
