import {escape as e,number,origins,destinations} from './domain.js';

const date=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'')?value.split('-').reverse().join('/'):'Não registrado';
const range=(start,end)=>start&&end?(start===end?date(start):`${date(start)} a ${date(end)}`):'Não registrado';
const bounds=(rows,key,compare)=>rows.map(row=>row[key]).filter(Boolean).sort().at(compare==='max'?-1:0);
const sum=(rows,key)=>rows.reduce((total,row)=>total+(Number(row[key])||0),0);
const city=code=>origins.find(row=>row[0]===code)?.[1]||destinations.find(row=>row.code===code)?.city||code;
const state={completed:'Completo',partial:'Parcial',failed:'Falhou',running:'Em andamento',queued:'Na fila'};

export function stayLabel(values){
 const sorted=[...new Set(values.filter(n=>Number.isInteger(n)&&n>0&&n<=60))].sort((a,b)=>a-b),parts=[];
 for(let i=0;i<sorted.length;i++){
  const start=sorted[i];let end=start;
  while(sorted[i+1]===end+1)end=sorted[++i];
  parts.push(start===end?String(start):`${start}–${end}`);
 }
 return parts.length?parts.join(', ')+' dias':'Não registrada';
}

export function compositionModel(composition){
 const groups=new Map();
 for(const kind of ['calendars','details'])for(const row of composition?.[kind]||[]){
  if(!row.origin||!row.destination)continue;
  const key=row.origin+'|'+row.destination;
  if(!groups.has(key))groups.set(key,{origin:row.origin,destination:row.destination,calendars:[],details:[]});
  groups.get(key)[kind].push(row);
 }
 const routes=[...groups.values()].sort((a,b)=>a.origin.localeCompare(b.origin)||a.destination.localeCompare(b.destination));
 return {routes,origins:new Set(routes.map(r=>r.origin)).size,destinations:new Set(routes.map(r=>r.destination)).size,
  missingDetails:Math.max(0,(Number(composition?.detail_attempts_expected)||0)-(Number(composition?.detail_attempts_recorded)||0))};
}

function routeCard(route){
 const {calendars,details}=route;
 const stays=calendars.flatMap(c=>Number.isInteger(c.min_days)&&Number.isInteger(c.max_days)&&c.max_days>=c.min_days&&c.max_days<=60?Array.from({length:c.max_days-c.min_days+1},(_,i)=>c.min_days+i):[]);
 const knownPrices=calendars.some(c=>c.prices!=null);
 return `<article class="composition-route"><header><div><h4>${e(route.origin)} <span>→</span> ${e(route.destination)}</h4><p>${e(city(route.origin))} → ${e(city(route.destination))}</p></div><span class="count-tag">${number(sum(details,'attempts'))} consultas detalhadas</span></header><div class="composition-columns"><section><h5>Calendário · período solicitado</h5><dl><div><dt>Saídas</dt><dd>${e(range(bounds(calendars,'departure_start'),bounds(calendars,'departure_end','max')))}</dd></div><div><dt>Permanências</dt><dd>${e(stayLabel(stays))}</dd></div><div><dt>Preços capturados</dt><dd>${knownPrices?number(sum(calendars,'prices')):'Não registrado'}</dd></div></dl>${calendars.some(c=>c.status!=='completed')?'<p class="composition-caution">Há capturas parciais, falhas ou consultas em andamento.</p>':''}</section><section><h5>Detalhes · datas consultadas</h5><dl><div><dt>Idas</dt><dd>${e(range(bounds(details,'departure_start'),bounds(details,'departure_end','max')))}</dd></div><div><dt>Voltas</dt><dd>${e(range(bounds(details,'return_start'),bounds(details,'return_end','max')))}</dd></div><div><dt>Permanências</dt><dd>${e(stayLabel(details.map(d=>d.stay_days)))}</dd></div></dl><p class="composition-result">${number(sum(details,'dates_completed'))} pares concluídos de ${number(sum(details,'dates_attempted'))} consultados · ${number(sum(details,'filtered'))} acima do teto · ${number(sum(details,'errors'))} falhas</p></section></div><details class="composition-breakdown" data-composition-route="${e(route.origin+'|'+route.destination)}"><summary>Ver períodos por permanência</summary><div class="composition-periods">${calendars.map(c=>`<p><b>Calendário · ${e(c.min_days===c.max_days?stayLabel([c.min_days]):c.min_days&&c.max_days?`${c.min_days}–${c.max_days} dias`:'Permanência não registrada')}</b><span>Saídas: ${e(range(c.departure_start,c.departure_end))}</span><small>${e(state[c.status]||'Não registrado')} · ${c.prices==null?'Preços não registrados':number(c.prices)+' preços'}${c.completed_sweeps==null?'':` · ${number(c.completed_sweeps)} / ${number(c.requested_sweeps)} varreduras completas`}</small></p>`).join('')}${details.map(d=>`<p><b>Detalhes · ${e(stayLabel([d.stay_days]))}</b><span>Idas: ${e(range(d.departure_start,d.departure_end))}</span><span>Voltas: ${e(range(d.return_start,d.return_end))}</span><small>${number(d.dates_completed)} / ${number(d.dates_attempted)} pares concluídos · ${number(d.attempts)} tentativas</small></p>`).join('')}</div></details></article>`;
}

export function sessionCompositionView(composition,run){
 const model=compositionModel(composition);
 return `<section class="session-composition" data-composition-run="${e(run?.id)}" aria-label="Composição executada da sessão"><div class="composition-heading"><div><h3>Composição executada</h3><p>Origem × destino × período desta sessão.</p></div>${model.routes.length?`<span>${number(model.routes.length)} rotas · ${number(model.origins)} origens · ${number(model.destinations)} destinos</span>`:''}</div>${!composition?'<p class="composition-empty">Carregando a composição da sessão…</p>':model.routes.length?`${model.missingDetails?`<p class="composition-caution">Resumo parcial: ${number(composition.detail_attempts_recorded)} de ${number(composition.detail_attempts_expected)} tentativas detalhadas têm registros disponíveis.</p>`:''}<div class="composition-routes">${model.routes.map(routeCard).join('')}</div><p class="composition-note">O período do calendário representa o intervalo solicitado. As faixas de ida e volta mostram a primeira e a última data consultadas; não significam que todos os dias entre elas foram pesquisados. Abra os períodos por permanência para conferir cada grupo.</p>`:`<p class="composition-empty">${run?.status==='running'?'A composição aparecerá após as primeiras consultas registradas.':'Não há registros de rotas e períodos disponíveis para esta sessão.'}</p>`}</section>`;
}
