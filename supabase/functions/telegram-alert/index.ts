import {createClient} from 'npm:@supabase/supabase-js@2.118.0';
import {createTelegramHandler} from './handler.js';

// The fixed message/recipient and one-time dispatch are verified inside the DB.
// The service credential and Telegram token never enter the browser or pg_net.
const client=createClient(Deno.env.get('SUPABASE_URL')!,Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,{auth:{persistSession:false,autoRefreshToken:false}});
Deno.serve(createTelegramHandler(client));
