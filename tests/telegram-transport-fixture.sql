-- Local-only transport doubles. Production uses pg_net, Vault and pg_cron.
create schema net;
create table net.http_request_queue(id bigint generated always as identity primary key,url text,body jsonb);
create table net._http_response(id bigint,status_code integer,content text,timed_out boolean,error_msg text);
create function net.http_post(url text,body jsonb default '{}',params jsonb default '{}',headers jsonb default '{}',timeout_milliseconds integer default 2000)
returns bigint language sql as $$insert into net.http_request_queue(url,body) values(url,body) returning id$$;
create schema vault;
create table vault.test_secrets(name text,decrypted_secret text);
create view vault.decrypted_secrets as select * from vault.test_secrets;
create schema cron;
create table cron.job(jobid bigint generated always as identity primary key,jobname text,schedule text,command text);
create table cron.job_run_details(jobid bigint,end_time timestamptz);
create function cron.schedule(job_name text,schedule text,command text) returns bigint language sql as $$
 insert into cron.job(jobname,schedule,command) values(job_name,schedule,command) returning jobid;
$$;
