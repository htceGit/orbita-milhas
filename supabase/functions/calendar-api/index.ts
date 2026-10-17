// Public URL, authenticated API. Google capture runs in the isolated worker;
// this function manages requests, permissions, cache and result delivery.
const base=Deno.env.get('SUPABASE_URL')!;
const serviceKey=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const allowedOrigins=new Set(['https://htcegit.github.io','http://127.0.0.1:4173']);
const airports=new Set(['CWB','JOI','NVT','FLN','VCP','GRU']);
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const fields=['id','user_id','request','status','result','error','created_at','finished_at','expires_at'];
async function database(query:Record<string,string>,method='GET',data?:unknown){
 const res=await fetch(base+'/rest/v1/calendar_jobs?'+new URLSearchParams(query),{method,headers:{apikey:serviceKey,Authorization:'Bearer '+serviceKey,'Content-Type':'application/json',Prefer:'return=representation'},...(data?{body:JSON.stringify(data)}:{}),signal:AbortSignal.timeout(15000)});
 return {ok:res.ok,status:res.status,data:await res.json()};
}
function validateRequest(value:Record<string,unknown>){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!['origin','destination','departure_start','departure_end','min_days','max_days','max_stops'].includes(k)))throw Error('Parâmetros inválidos.');
 const q={origin:value.origin,destination:value.destination,departure_start:value.departure_start,departure_end:value.departure_end,min_days:value.min_days??7,max_days:value.max_days??20,max_stops:value.max_stops??2};
 if(!airports.has(String(q.origin))||!/^([A-Z]{3})$/.test(String(q.destination))||q.origin===q.destination)throw Error('Rota inválida.');
 for(const key of ['departure_start','departure_end'] as const){
  if(typeof q[key]!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(q[key] as string)||new Date(q[key] as string).toISOString().slice(0,10)!==q[key])throw Error('Data inválida.');
 }
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo'}).format(new Date());
 const [year,month,day]=today.split('-').map(Number);const last=new Date(Date.UTC(year,month-1+6,1));
 last.setUTCDate(Math.min(day,new Date(Date.UTC(last.getUTCFullYear(),last.getUTCMonth()+1,0)).getUTCDate()));
 if(String(q.departure_start)<=today||String(q.departure_end)<String(q.departure_start)||String(q.departure_end)>last.toISOString().slice(0,10))throw Error('As saídas devem estar entre amanhã e seis meses à frente.');
 if(!Number.isInteger(q.min_days)||!Number.isInteger(q.max_days)||!Number.isInteger(q.max_stops)||Number(q.min_days)<1||Number(q.max_days)>60||Number(q.min_days)>Number(q.max_days)||Number(q.max_stops)<0||Number(q.max_stops)>2)throw Error('Permanência ou conexões inválidas.');
 return q;
}
Deno.serve(async(req:Request)=>{
 const origin=req.headers.get('Origin');
 const cors={'Access-Control-Allow-Origin':origin&&allowedOrigins.has(origin)?origin:'https://htcegit.github.io','Access-Control-Allow-Headers':'authorization, apikey, content-type, x-client-info','Access-Control-Allow-Methods':'POST, OPTIONS','Vary':'Origin'};
 const respond=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{...cors,'Content-Type':'application/json','Cache-Control':'no-store'}});
 if(req.method==='OPTIONS')return new Response(null,{status:204,headers:cors});
 if(req.method!=='POST')return respond({error:'Use POST com action create ou get.'},405);
 if(origin&&!allowedOrigins.has(origin))return respond({error:'Origem não permitida.'},403);
 const authorization=req.headers.get('Authorization')||'';
 if(!/^Bearer /i.test(authorization))return respond({error:'Autenticação obrigatória.'},401);
 try{
  const auth=await fetch(base+'/auth/v1/user',{headers:{apikey:serviceKey,Authorization:authorization},signal:AbortSignal.timeout(10000)});
  if(!auth.ok)return respond({error:'Sessão inválida ou expirada.'},401);
  const user=await auth.json();
  const profiles=await fetch(base+'/rest/v1/profiles?'+new URLSearchParams({id:'eq.'+user.id,select:'role,status'}),{headers:{apikey:serviceKey,Authorization:'Bearer '+serviceKey},signal:AbortSignal.timeout(10000)});
  const profile=(await profiles.json())[0];
  if(!profile||profile.status!=='active')return respond({error:'Conta sem acesso ativo.'},403);
  const raw=await req.text();if(raw.length>4096)return respond({error:'Requisição muito grande.'},413);
  const input=JSON.parse(raw);
  if(input.action==='get'){
   if(!uuid.test(input.id))return respond({error:'Identificador inválido.'},400);
   const read=await database({id:'eq.'+input.id,select:[...fields,'entries_gzip'].join(','),limit:'1'});
   if(!read.ok)return respond({error:'Falha ao consultar a captura.'},502);
   const job=read.data[0];
   if(!job||job.user_id&&job.user_id!==user.id&&profile.role!=='admin')return respond({error:'Captura não encontrada.'},404);
   const {entries_gzip,...body}=job;
   if(entries_gzip){
    if(entries_gzip.length>200000)return respond({error:'Resultado excede o limite.'},502);
    const bytes=Uint8Array.from(atob(entries_gzip),(c:string)=>c.charCodeAt(0));
    const text=await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
    if(text.length>3000000)return respond({error:'Resultado excede o limite.'},502);
    body.result={...body.result,entries:JSON.parse(text)};
   }
   return respond({...body,stale:new Date(job.expires_at)<new Date()});
  }
  if(input.action!=='create')return respond({error:'Ação inválida.'},400);
  if(profile.role!=='admin')return respond({error:'Capturas sob demanda estão disponíveis à administração.'},403);
  let request;
  try{request=validateRequest(input.request);}catch(error){return respond({error:error instanceof Error?error.message:'Parâmetros inválidos.'},422);}
  const canonical=Object.fromEntries(Object.keys(request).sort().map(k=>[k,request[k as keyof typeof request]]));
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(canonical))));
  const cache_key=Array.from(digest,b=>b.toString(16).padStart(2,'0')).join('');
  const cached=await database({cache_key:'eq.'+cache_key,status:'eq.completed',expires_at:'gt.'+new Date().toISOString(),or:`(user_id.is.null,user_id.eq.${user.id})`,select:fields.join(','),order:'created_at.desc',limit:'1'});
  if(!cached.ok)return respond({error:'Falha ao consultar o cache.'},502);
  if(cached.data.length)return respond({job_id:cached.data[0].id,status:'completed',cached:true});
  const recent=await database({user_id:'eq.'+user.id,created_at:'gt.'+new Date(Date.now()-60000).toISOString(),select:'id',limit:'1'});
  if(!recent.ok)return respond({error:'Falha ao verificar a fila.'},502);
  if(recent.data.length)return respond({error:'Aguarde um minuto antes de pedir outra captura.'},429);
  const inserted=await database({},'POST',{user_id:user.id,request,cache_key});
  if(!inserted.ok)return respond({error:inserted.status===409?'Já existe uma captura sua aguardando processamento.':'Não foi possível criar a captura.'},inserted.status===409?409:502);
  return respond({job_id:inserted.data[0].id,status:'queued',cached:false,processing:'Próxima execução do motor, programada a cada 4 horas.'},202);
 }catch(error){console.error('Calendar API failure',error instanceof Error?error.name:'Unknown');return respond({error:'Não foi possível processar a requisição.'},400);}
});
