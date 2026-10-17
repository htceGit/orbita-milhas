import { createRemoteJWKSet, jwtVerify } from 'npm:jose@6.2.12';

// Only this repository's scanner workflow on main may call the worker API.
// No long-lived Supabase secret is copied into GitHub or browser code.
const jwks=createRemoteJWKSet(new URL('https://token.actions.githubusercontent.com/.well-known/jwks'));
const base=Deno.env.get('SUPABASE_URL')!+'/rest/v1/';
const serviceKey=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
const readTables=new Set(['profiles','scanner_settings','monitors','scanner_state','calendar_jobs','scan_runs']);
const writeTables=new Set(['offers','fare_history','scan_runs','calendar_jobs','scan_events']);
const patchTables=new Set(['scan_runs','scanner_state','calendar_jobs']);
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const origins=new Set(['CWB','JOI','NVT','FLN','VCP','GRU']);

Deno.serve(async(req:Request)=>{
 if(req.method!=='POST')return response({error:'Método não permitido'},405);
 try{
  const token=req.headers.get('Authorization')?.replace(/^Bearer /,'');
  if(!token)return response({error:'Identidade do workflow obrigatória'},401);
  let claims;
  try{
   const {payload}=await jwtVerify(token,jwks,{issuer:'https://token.actions.githubusercontent.com',audience:'orbita-scanner',algorithms:['RS256'],clockTolerance:5,maxTokenAge:'10m'});
   claims=payload;
  }catch{return response({error:'Identidade inválida ou expirada'},401);}
  if(claims.repository_id!=='1423585297'||claims.repository_owner_id!=='183164872'||claims.ref!=='refs/heads/main'||claims.workflow_ref!=='htceGit/orbita-milhas/.github/workflows/scanner.yml@refs/heads/main'||!['schedule','workflow_dispatch'].includes(String(claims.event_name)))return response({error:'Workflow não autorizado'},403);
  const raw=await req.text();
  if(raw.length>150_000)return response({error:'Requisição muito grande'},413);
  const {table,method='GET',data,params={}}=JSON.parse(raw);
  const query:Record<string,string>={};
  let prefer='return=representation';
  if(method==='GET'&&readTables.has(table)){
   query.limit=String(Math.min(1000,Math.max(1,Number(params.limit)||1000)));
   query.offset=String(Math.max(0,Math.floor(Number(params.offset)||0)));
   if(table==='profiles'){query.select='id,plan,pro_until,role';query.status='eq.active';}
   if(table==='calendar_jobs'){query.status='in.(queued,running)';query.order='created_at.asc';query.limit='10';query.select='id,user_id,request,status';}
   if(table==='scan_runs'){query.order='started_at.desc';query.limit='1';query.offset='0';query.select='id,status,started_at,finished_at,workflow_url';}
   if(table==='monitors'){query.enabled='eq.true';query.order='created_at.asc';}
   if(table==='scanner_state'||table==='scanner_settings')query.id='eq.1';
  }else if(method==='POST'&&writeTables.has(table)){
   if(table==='scan_events'){
    const allowed=new Set(['run_id','created_at','stage','outcome','origin','destination','departure_date','return_date','stay_days','attempt','duration_ms','error_code','cause_type','message','http_status','retryable']);
    if(!Array.isArray(data)||!data.length||data.length>50||data.some(row=>!row||typeof row!=='object'||Object.keys(row).some(k=>!allowed.has(k))||!uuid.test(String(row.run_id))||!['planning','calendar','detail','system'].includes(row.stage)||!['started','success','empty','error','retry','finished'].includes(row.outcome)||row.message&&String(row.message).length>500))return response({error:'Eventos inválidos'},400);
    prefer='return=minimal';
   }else if(!data||typeof data!=='object'||Array.isArray(data))return response({error:'Dados inválidos'},400);
   if(table==='offers'){
    if(!origins.has(data.origin)||!/^[A-Z]{3}$/.test(data.destination)||!Number.isFinite(data.price_brl)||data.price_brl<=0||!Array.isArray(data.airlines)||data.airlines.length<1||data.airlines.length>8||data.airlines.some((a:unknown)=>typeof a!=='string'||!/^([A-Z0-9]{2,3}|UNKNOWN)$/.test(a))||!Array.isArray(data.airline_names)||data.airline_names.length<1||data.airline_names.length>8||data.airline_names.some((a:unknown)=>typeof a!=='string'||a.length<1||a.length>150)||data.carrier_validation!=='outbound_only'||!String(data.booking_url).startsWith('https://www.google.com/travel/flights'))return response({error:'Tarifa inválida'},400);
    query.on_conflict='origin,destination,departure_date,return_date';
    prefer='resolution=merge-duplicates,return=representation';
   }
  }else if(method==='PATCH'&&patchTables.has(table)){
   const id=String(params.id||'').replace(/^eq\./,'');
   if(table==='scanner_state'&&id!=='1'||['scan_runs','calendar_jobs'].includes(table)&&!uuid.test(id))return response({error:'Identificador inválido'},400);
   query.id='eq.'+id;
  }else if(method==='DELETE'&&['offers','fare_history','calendar_jobs','scan_events'].includes(table)){
   // Retention thresholds are computed here, never accepted from the client.
   if(table==='calendar_jobs'||table==='scan_events')query.created_at='lt.'+new Date(Date.now()-7*86400_000).toISOString();
   else if(table==='fare_history')query.observed_at='lt.'+new Date(Date.now()-90*86400_000).toISOString();
   else query.return_date='lt.'+new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo'}).format(new Date());
   prefer='return=minimal';
  }else return response({error:'Operação não permitida'},403);
  const upstream=await fetch(base+table+'?'+new URLSearchParams(query),{method,headers:{apikey:serviceKey,Authorization:'Bearer '+serviceKey,'Content-Type':'application/json',Prefer:prefer},...(['POST','PATCH'].includes(method)?{body:JSON.stringify(data)}:{})});
  if(!upstream.ok){console.error('Database operation failed',table,method,upstream.status);return response({error:'Falha no banco de dados',status:upstream.status},502);}
  const text=await upstream.text();
  return response(text?JSON.parse(text):null);
 }catch(error){console.error('Worker API failure',error instanceof Error?error.name:'Unknown');return response({error:'Requisição inválida'},400);}
});
