const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const reply=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});

export function createTelegramHandler(client,transport=fetch){return async request=>{
 if(request.method!=='POST')return reply({error:'Método não permitido'},405);
 let input;
 try{const raw=await request.text();if(raw.length>512)return reply({error:'Requisição inválida'},400);input=JSON.parse(raw);}catch{return reply({error:'Requisição inválida'},400);}
 if(!uuid.test(input?.alert_id)||!uuid.test(input?.nonce))return reply({error:'Despacho inválido'},400);
 const params={alert_id:input.alert_id,nonce:input.nonce};
 let claim;
 try{claim=await client.rpc('claim_telegram_alert',params);}catch{return reply({error:'Entrega indisponível'},503);}
 if(claim.error)return reply({error:'Entrega indisponível'},503);
 if(!claim.data)return reply({ok:true,ignored:true});
 // No token, authenticated URL, chat id or upstream body is logged or returned.
 const {bot_token,chat_id,text,booking_url}=claim.data;
 const buttons=[[{text:'Abrir Órbita',url:'https://htcegit.github.io/orbita-milhas/'}]];
 if(typeof booking_url==='string'&&booking_url.startsWith('https://www.google.com/travel/flights'))buttons.unshift([{text:'Ver tarifa no Google Flights',url:booking_url}]);
 let delivered=false,messageId=null,errorCode=0,retryAfter=null;
 try{
  const response=await transport(`https://api.telegram.org/bot${bot_token}/sendMessage`,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(15000),
   body:JSON.stringify({chat_id,text,link_preview_options:{is_disabled:true},reply_markup:{inline_keyboard:buttons}})});
  const body=await response.json();
  delivered=response.ok&&body.ok===true;
  if(delivered)messageId=Number.isSafeInteger(body.result?.message_id)?body.result.message_id:null;
  else{errorCode=Number.isInteger(body.error_code)?body.error_code:response.status;retryAfter=Number.isInteger(body.parameters?.retry_after)?body.parameters.retry_after:null;}
 }catch{errorCode=0;}
 let complete;
 try{complete=await client.rpc('complete_telegram_alert',{...params,delivered,message_id:messageId,error_code:errorCode,retry_after:retryAfter});}catch{return reply({error:'Confirmação indisponível'},503);}
 if(complete.error)return reply({error:'Confirmação indisponível'},503);
 return reply({ok:true,status:complete.data});
};}
