export const money = n => new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0}).format(Number(n)||0);
export const number = n => new Intl.NumberFormat('pt-BR').format(Number(n)||0);
export const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function estimate(price, costPerThousand=20, taxes=350, discount=.275) {
  const target=price*(1-discount);
  const miles=Math.max(0,Math.floor((target-taxes)/costPerThousand*1000/1000)*1000);
  return {low:price*.70,high:price*.75,miles,target,taxes,costPerThousand};
}
export function filterOffers(offers, filters) {
  return offers.filter(o=>(!filters.region||filters.region==='all'||o.region===filters.region)&&(!filters.origin||filters.origin==='all'||o.origin===filters.origin)&&(!filters.search||`${o.city} ${o.destination} ${o.country} ${airlineLabel(o)}`.toLowerCase().includes(filters.search.toLowerCase()))&&(!filters.maxPrice||o.price_brl<=filters.maxPrice)&&(!filters.departureFrom||o.departure_date>=filters.departureFrom)&&(!filters.departureTo||o.departure_date<=filters.departureTo));
}
export const origins=[['CWB','Curitiba','PR'],['JOI','Joinville','SC'],['NVT','Navegantes','SC'],['FLN','Florianópolis','SC'],['VCP','Campinas','SP'],['GRU','Guarulhos','SP']];
export const destinations=[
 ['MIA','Miami','Estados Unidos','EUA'],['JFK','Nova York','Estados Unidos','EUA'],['LAX','Los Angeles','Estados Unidos','EUA'],['MCO','Orlando','Estados Unidos','EUA'],['BOS','Boston','Estados Unidos','EUA'],
 ['LIS','Lisboa','Portugal','Europa'],['MAD','Madri','Espanha','Europa'],['BCN','Barcelona','Espanha','Europa'],['CDG','Paris','França','Europa'],['LHR','Londres','Reino Unido','Europa'],['FCO','Roma','Itália','Europa'],['MXP','Milão','Itália','Europa'],['FRA','Frankfurt','Alemanha','Europa'],
 ['NRT','Tóquio','Japão','Ásia'],['ICN','Seul','Coreia do Sul','Ásia'],['BKK','Bangkok','Tailândia','Ásia']
].map(([code,city,country,region])=>({code,city,country,region,enabled:!['NRT','ICN','BKK'].includes(code)}));
export const defaultSettings={id:1,enabled:true,origins:origins.map(o=>o[0]),destinations,min_days:7,max_days:20,horizon_months:6,query_budget:1000,search_mode:'rolling',search_strategy:'hybrid',max_stops:2};
export function addDays(offset){const d=new Date();d.setDate(d.getDate()+offset);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
export const demoOffers=[
 ['MIA','Miami','Estados Unidos','EUA','FLN',3290,28,13,1,'miami'],
 ['LIS','Lisboa','Portugal','Europa','CWB',3890,45,14,1,'lisbon'],
 ['JFK','Nova York','Estados Unidos','EUA','GRU',3670,63,10,0,'newyork'],
 ['CDG','Paris','França','Europa','GRU',4290,76,15,0,'paris'],
 ['MAD','Madri','Espanha','Europa','FLN',4120,94,12,1,'madrid'],
 ['MCO','Orlando','Estados Unidos','EUA','CWB',3520,112,14,1,'orlando'],
 ['LHR','Londres','Reino Unido','Europa','GRU',4590,126,16,0,'london'],
 ['LAX','Los Angeles','Estados Unidos','EUA','GRU',3980,147,18,0,'la']
].map(([destination,city,country,region,origin,price_brl,offset,stay,stops,art],i)=>({id:`demo-${i}`,destination,city,country,region,origin,price_brl,departure_date:addDays(offset),return_date:addDays(offset+stay),stay_days:stay,stops,art,airlines:i===1?['TP']:i===2?['AA']:i===3?['AF']:['LA'],airline_names:[i===1?'TAP Air Portugal':i===2?'American Airlines':i===3?'Air France':'LATAM'],carrier_validation:'outbound_only',collected_at:new Date().toISOString(),expires_at:new Date(Date.now()+8*3600000).toISOString(),booking_url:`https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&q=${encodeURIComponent(`${origin} ${destination} ${addDays(offset)} ${addDays(offset+stay)} round trip`)}`,is_demo:true}));

export function hasLatamProjection(offer){return Array.isArray(offer.airlines)&&offer.airlines.length===1&&offer.airlines[0]==='LA';}
export function airlineLabel(offer){return (offer.airline_names?.length?offer.airline_names:offer.airlines?.map(c=>c==='LA'?'LATAM':c)||['Companhia não identificada']).join(' + ');}

export function calendarCandidates(entries,limit=2){
  const unique=new Map();
  for(const entry of entries){
    const key=[entry.origin,entry.destination,entry.departure_date,entry.return_date].join('|');
    if(!unique.has(key)||entry.price_brl<unique.get(key).price_brl)unique.set(key,entry);
  }
  const counts=new Map();
  return [...unique.values()].sort((a,b)=>a.price_brl-b.price_brl||a.departure_date.localeCompare(b.departure_date)).filter(entry=>{
    const group=[entry.origin,entry.destination,entry.stay_days].join('|'),count=counts.get(group)||0;
    if(count>=limit)return false;
    counts.set(group,count+1);return true;
  });
}
