create policy telegram_settings_deny_browser on private.telegram_settings
 for all to anon,authenticated using(false) with check(false);
create policy telegram_alerts_deny_browser on private.telegram_alerts
 for all to anon,authenticated using(false) with check(false);

-- Defense in depth: managed pg_net tables may retain inherited PUBLIC grants.
-- The following relay migration therefore keeps all credentials out of the
-- HTTP queue instead of depending on these ACL changes.
revoke all on all tables in schema net from public,anon,authenticated;
revoke all on schema net from public,anon,authenticated;
revoke all on vault.decrypted_secrets from public,anon,authenticated;
