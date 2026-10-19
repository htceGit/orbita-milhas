export const money = n => {const value=Number(n)||0;return new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:2,minimumFractionDigits:Number.isInteger(value)?0:2}).format(value);};
export function offerAllowed(offer){return typeof offer.price_brl==='number'&&Number.isFinite(offer.price_brl)&&offer.price_brl>0;}
export const number = n => new Intl.NumberFormat('pt-BR').format(Number(n)||0);
export const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function estimate(price, costPerThousand=20, taxes=350, discount=.275) {
  const target=price*(1-discount);
  const miles=Math.max(0,Math.floor((target-taxes)/costPerThousand*1000/1000)*1000);
  return {low:price*.70,high:price*.75,miles,target,taxes,costPerThousand};
}
export function filterOffers(offers, filters) {
  const fold=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const matches=(selection,value)=>Array.isArray(selection)?!selection.length||selection.includes(value):!selection||selection==='all'||selection===value;
  const carrierMatches=offer=>{
    const selected=Array.isArray(filters.airline)?filters.airline:filters.airline&&filters.airline!=='all'?[filters.airline]:[];
    return !selected.length||selected.some(name=>airlineLabel(offer)===name||offer.airline_names?.includes(name));
  };
  return offers.filter(o=>offerAllowed(o)
    &&matches(filters.region,o.region)
    &&matches(filters.origin,o.origin)
    &&matches(filters.destination,o.destination)
    &&matches(filters.months,o.departure_date?.slice(0,7))
    &&(!filters.search||fold(`${o.city} ${o.destination} ${o.country} ${o.origin_name} ${o.origin} ${airlineLabel(o)}`).includes(fold(filters.search)))
    &&(!filters.maxPrice||o.price_brl<=filters.maxPrice)
    &&(!filters.departureFrom||o.departure_date>=filters.departureFrom)
    &&(!filters.departureTo||o.departure_date<=filters.departureTo)
    &&carrierMatches(o)
    &&matches(filters.trip,o.trip_type)
    &&(!filters.direct||o.stops===0)
    &&(!filters.minStay||Number.isInteger(o.stay_days)&&o.stay_days>=filters.minStay)
    &&(!filters.maxStay||Number.isInteger(o.stay_days)&&o.stay_days<=filters.maxStay));
}
export const origins=[['CWB','Curitiba','PR'],['JOI','Joinville','SC'],['NVT','Navegantes','SC'],['FLN','Florianópolis','SC'],['VCP','Campinas','SP'],['GRU','Guarulhos','SP']];
export const destinations=[
 ['MIA','Miami','Estados Unidos','EUA'],['JFK','Nova York','Estados Unidos','EUA'],['LAX','Los Angeles','Estados Unidos','EUA'],['MCO','Orlando','Estados Unidos','EUA'],['BOS','Boston','Estados Unidos','EUA'],
 ['LIS','Lisboa','Portugal','Europa'],['MAD','Madri','Espanha','Europa'],['BCN','Barcelona','Espanha','Europa'],['CDG','Paris','França','Europa'],['LHR','Londres','Reino Unido','Europa'],['FCO','Roma','Itália','Europa'],['MXP','Milão','Itália','Europa'],['FRA','Frankfurt','Alemanha','Europa'],
 ['NRT','Tóquio','Japão','Ásia'],['ICN','Seul','Coreia do Sul','Ásia'],['BKK','Bangkok','Tailândia','Ásia']
].map(([code,city,country,region])=>({code,city,country,region,enabled:!['NRT','ICN','BKK'].includes(code)}));
export function addDays(offset){const d=new Date();d.setDate(d.getDate()+offset);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
const demoRoutes=[
 ['MIA','Miami','Estados Unidos','EUA','FLN',2790,28,13,1,'miami'],
 ['LIS','Lisboa','Portugal','Europa','CWB',3290,45,14,1,'lisbon'],
 ['JFK','Nova York','Estados Unidos','EUA','GRU',2970,63,10,0,'newyork'],
 ['CDG','Paris','França','Europa','GRU',3490,76,15,0,'paris'],
 ['MAD','Madri','Espanha','Europa','FLN',3120,94,12,1,'madrid'],
 ['MCO','Orlando','Estados Unidos','EUA','CWB',2820,112,14,1,'orlando'],
 ['LHR','Londres','Reino Unido','Europa','GRU',3390,126,16,0,'london'],
 ['LAX','Los Angeles','Estados Unidos','EUA','GRU',2980,147,18,0,'la']
].map(([destination,city,country,region,origin,price_brl,offset,stay,stops,art],i)=>({id:`demo-${i}`,destination,city,country,region,origin,price_brl,departure_date:addDays(offset),return_date:addDays(offset+stay),stay_days:stay,stops,art,airlines:i===1?['TP']:i===2?['AA']:i===3?['AF']:['LA'],airline_names:[i===1?'TAP Air Portugal':i===2?'American Airlines':i===3?'Air France':'LATAM'],carrier_validation:'outbound_only',collected_at:new Date().toISOString(),expires_at:new Date(Date.now()+8*3600000).toISOString(),booking_url:`https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&q=${encodeURIComponent(`${origin} ${destination} ${addDays(offset)} ${addDays(offset+stay)} round trip`)}`,is_demo:true}));
const shiftDemoDate=(value,days)=>{const d=new Date(value+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10);};
export const demoOffers=demoRoutes.flatMap(route=>[0,7,21].map((days,index)=>({...route,trip_type:'round_trip',id:index?route.id+'-'+index:route.id,departure_date:shiftDemoDate(route.departure_date,days),return_date:shiftDemoDate(route.return_date,days),price_brl:route.price_brl+index*120,booking_url:'https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&q='+encodeURIComponent(`${route.origin} ${route.destination} ${shiftDemoDate(route.departure_date,days)} ${shiftDemoDate(route.return_date,days)} round trip`)})));


export function hasLatamProjection(offer){return Array.isArray(offer.airlines)&&offer.airlines.length===1&&offer.airlines[0]==='LA';}
export function airlineLabel(offer){return (offer.airline_names?.length?offer.airline_names:offer.airlines?.map(c=>c==='LA'?'LATAM':c)||['Companhia não identificada']).join(' + ');}
