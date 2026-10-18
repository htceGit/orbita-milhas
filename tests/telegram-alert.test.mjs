import test from 'node:test';
import assert from 'node:assert/strict';
import {createTelegramHandler} from '../supabase/functions/telegram-alert/handler.js';

const ids={alert_id:'10000000-0000-4000-8000-000000000001',nonce:'20000000-0000-4000-8000-000000000002'};
const request=data=>new Request('https://example.test',{method:'POST',body:JSON.stringify(data)});
const claim={bot_token:'example-token',chat_id:77,text:'FLN → MIA · Ida e volta: R$ 2.999,00',booking_url:'https://www.google.com/travel/flights?test=1'};

test('relay rejeita entradas inválidas e não envia sem um despacho válido no banco',async()=>{
 let calls=0;
 const handler=createTelegramHandler({rpc:async()=>{calls++;return {data:null,error:null};}},async()=>{throw Error('Não deve chamar Telegram');});
 assert.equal((await handler(new Request('https://example.test'))).status,405);
 assert.equal((await handler(request({alert_id:'invalid',nonce:'x'}))).status,400);
 assert.equal(calls,0);
 assert.deepEqual(await (await handler(request(ids))).json(),{ok:true,ignored:true});
 assert.equal(calls,1);
});

test('envia os dados fixados pelo servidor e confirma a entrega sem expor token',async()=>{
 const calls=[];let sent;
 const client={rpc:async(name,params)=>{calls.push({name,params});return {data:name==='claim_telegram_alert'?claim:'sent',error:null};}};
 const handler=createTelegramHandler(client,async(url,options)=>{
  assert.equal(url,'https://api.telegram.org/botexample-token/sendMessage');
  sent=JSON.parse(options.body);
  return new Response(JSON.stringify({ok:true,result:{message_id:42}}));
 });
 const response=await handler(request({...ids,chat_id:999,text:'conteúdo adulterado'}));
 assert.deepEqual(calls[0],{name:'claim_telegram_alert',params:ids});
 assert.equal(sent.chat_id,77);assert.equal(sent.text,claim.text);
 assert.equal(sent.reply_markup.inline_keyboard[0][0].url,claim.booking_url);
 assert.equal(calls[1].params.delivered,true);assert.equal(calls[1].params.message_id,42);
 const output=await response.text();
 assert.ok(!output.includes('example-token'));assert.ok(!output.includes('chat_id'));
 assert.deepEqual(JSON.parse(output),{ok:true,status:'sent'});
});

test('registra rate limit e timeout para repetição sem retornar erros com credenciais',async()=>{
 for(const mode of ['429','timeout']){
  let completion;
  const handler=createTelegramHandler({rpc:async(name,params)=>{
   if(name==='claim_telegram_alert')return {data:claim,error:null};
   completion=params;return {data:'queued',error:null};
  }},async()=>{
   if(mode==='timeout')throw Error('https://api.telegram.org/botexample-token/sendMessage');
   return new Response(JSON.stringify({ok:false,error_code:429,parameters:{retry_after:120}}),{status:429});
  });
  const response=await handler(request(ids));
  assert.equal(completion.delivered,false);
  assert.equal(completion.error_code,mode==='429'?429:0);
  assert.equal(completion.retry_after,mode==='429'?120:null);
  assert.ok(!(await response.text()).includes('example-token'));
 }
});
