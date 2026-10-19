/** Read-only adapter for the external collector's public.tarifaspromo contract. */
import {destinations} from './domain.js';
import {airportLabel} from './airports.js';
export const TARIFA_COLUMNS='id::text,origem,destino,origem_nome,destino_nome,tipo_viagem,duracao_dias,data_ida,data_volta,preco,companhia,voos,horario_partida,horario_chegada,duracao_total,escalas,aeronave,link_google_voos,criado_em,atualizado_em';
const text=value=>typeof value==='string'?value.trim():'';
const plain=value=>text(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const dateValue=value=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;const d=new Date(`${value}T12:00:00Z`);return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===value?value:null;};
const dayDifference=(a,b)=>Math.round((Date.parse(b+'T12:00:00Z')-Date.parse(a+'T12:00:00Z'))/86400000);
export function brasilToday(now=new Date()){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);}
export function fareCurrent(offer,today=brasilToday()){return Boolean(offer?.departure_date&&offer.departure_date>=today&&(!offer.expires_at||new Date(offer.expires_at)>new Date()));}
const carriers={'latam':'LA','latam airlines':'LA','latam airlines brasil':'LA','la':'LA','azul':'AD','gol':'G3','american airlines':'AA','american':'AA','united':'UA','united airlines':'UA','delta':'DL','delta air lines':'DL','tap':'TP','tap air portugal':'TP','copa airlines':'CM','copa':'CM','avianca':'AV','air france':'AF','klm':'KL','iberia':'IB','british airways':'BA','lufthansa':'LH','swiss':'LX','turkish airlines':'TK','qatar airways':'QR','emirates':'EK'};
export function normalizeTarifa(row){
 if(!row||typeof row!=='object')return null;
 const id=typeof row.id==='number'?(Number.isSafeInteger(row.id)?String(row.id):''):text(row.id);
 const origin=text(row.origem).toUpperCase(),destination=text(row.destino).toUpperCase();
 const price=typeof row.preco==='number'||typeof row.preco==='string'&&row.preco.trim()?Number(row.preco):NaN;
 const departure=dateValue(row.data_ida),returning=dateValue(row.data_volta);
 const trip=plain(row.tipo_viagem),oneWay=/^(so ida|somente ida|ida|one.?way)$/.test(trip);
 if(!/^\d+$/.test(id)||!/^[A-Z]{3}$/.test(origin)||!/^[A-Z]{3}$/.test(destination)||origin===destination||!Number.isFinite(price)||price<=0||!departure||!oneWay&&(!returning||returning<departure))return null;
 const meta=destinations.find(d=>d.code===destination);
 const name=text(row.companhia),names=name?name.split(/\s*[,;+\/|&]\s*|\s+(?:e|and)\s+/i).filter(Boolean):[];
 const codes=new Set(names.map(n=>carriers[plain(n)]||(/^[A-Z0-9]{2}$/.test(n)?n:'UNKNOWN')));
 for(const match of text(row.voos).matchAll(/\b([A-Z][A-Z0-9])\s*\d{1,4}\b/g))codes.add(match[1]);
 if(!codes.size)codes.add('UNKNOWN');
 const stopsText=text(row.escalas),stopMatch=stopsText.match(/^(\d+)\b/);
 const stops=/^(direto|sem (?:escalas|paradas)|non.?stop)$/i.test(stopsText)?0:stopMatch?Number(stopMatch[1]):null;
 const updated=text(row.atualizado_em)||text(row.criado_em);
 const collected=Number.isFinite(Date.parse(updated))?updated:null;
 return {id,source:'tarifaspromo',origin,destination,origin_name:airportLabel(row.origem_nome,origin),
  city:airportLabel(row.destino_nome,destination),
  destination_name:text(row.destino_nome)||destination,country:meta?.country||'Internacional',region:meta?.region||'Outros',
  departure_date:departure,return_date:oneWay?null:returning,stay_days:oneWay?null:dayDifference(departure,returning),trip_type:oneWay?'one_way':'round_trip',
  price_brl:price,airlines:[...codes],airline_names:names.length?names:['Companhia não informada'],carrier_validation:'outbound_only',stops,
  stops_description:stopsText,flight_numbers:text(row.voos),departure_time:text(row.horario_partida),arrival_time:text(row.horario_chegada),
  flight_duration:text(row.duracao_total),aircraft:text(row.aeronave),booking_url:text(row.link_google_voos),collected_at:collected,expires_at:null};
}
export async function fetchTarifas(db,today=brasilToday()){
 const rows=[],size=500,max=10000;let total=0;
 for(let offset=0;offset<max;offset+=size){
  const result=await db.from('tarifaspromo').select(TARIFA_COLUMNS,offset===0?{count:'exact'}:{}).gte('data_ida',today).order('preco').order('id').range(offset,offset+size-1);
  if(result.error)throw result.error;
  if(offset===0)total=result.count??0;
  rows.push(...(result.data||[]));
  if((result.data||[]).length<size||rows.length>=total)break;
 }
 const unique=new Map();for(const row of rows){const offer=normalizeTarifa(row);if(offer&&fareCurrent(offer,today))unique.set(offer.id,offer);}
 return {offers:[...unique.values()],total,limited:total>rows.length};
}
export function tripLabel(offer){return offer.trip_type==='one_way'?'Somente ida':'Ida e volta';}
export function stopsLabel(offer){return offer.stops===0?'Direto':offer.stops===1?'1 conexão':Number.isInteger(offer.stops)?`${offer.stops} conexões`:'Conexões a confirmar';}
export function feedSummary(offers){
 const timestamps=offers.map(o=>o.collected_at).filter(v=>v&&Number.isFinite(Date.parse(v))).sort((a,b)=>Date.parse(b)-Date.parse(a));
 return {total:offers.length,routes:new Set(offers.map(o=>o.origin+'|'+o.destination)).size,destinations:new Set(offers.map(o=>o.destination)).size,latest:timestamps[0]||null};
}
