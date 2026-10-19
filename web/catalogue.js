import {filterOffers} from './domain.js';

export const MULTI_FILTERS=['origin','destination','region','airline','trip','months'];
export function createFilters(){return {region:[],origin:[],destination:[],months:[],airline:[],trip:[],search:'',maxPrice:'',departureFrom:'',departureTo:'',direct:false,minStay:'',maxStay:''};}
export const toggleValue=(values,value)=>values.includes(value)?values.filter(v=>v!==value):[...values,value];
export function appliedFilters(filters){return Object.entries(filters).flatMap(([key,value])=>Array.isArray(value)?value.map(item=>({key,value:item})):value!==''&&value!==false?[{key,value}]:[]);}
const isDate=value=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value+'T12:00:00Z'))&&new Date(value+'T12:00:00Z').toISOString().slice(0,10)===value;
export function readFilters(query){
 const q=new URLSearchParams(query),filters=createFilters();
 const allowed={region:v=>['EUA','Europa','Ásia','Outros'].includes(v),origin:v=>/^[A-Z]{3}$/.test(v),destination:v=>/^[A-Z]{3}$/.test(v),months:v=>/^\d{4}-(0[1-9]|1[0-2])$/.test(v),trip:v=>['one_way','round_trip'].includes(v),airline:v=>v.length>0&&v.length<=150};
 for(const key of MULTI_FILTERS)filters[key]=[...new Set(q.getAll(key).filter(value=>value!=='all'&&allowed[key](value)))].slice(0,100);
 for(const key of ['search','maxPrice','departureFrom','departureTo','minStay','maxStay']){
  const value=q.get(key);if(!value||value.length>100)continue;
  if(['maxPrice','minStay','maxStay'].includes(key)&&(!Number.isFinite(Number(value))||Number(value)<=0))continue;
  if(['minStay','maxStay'].includes(key)&&(!Number.isInteger(Number(value))||Number(value)>365))continue;
  if(['departureFrom','departureTo'].includes(key)&&!isDate(value))continue;
  filters[key]=value;
 }
 filters.direct=q.get('direct')==='1';
 return {filters,sort:['price','recent','departure','stay'].includes(q.get('sort'))?q.get('sort'):'price'};
}
export function filterUrl(href,filters,sort='price'){
 const url=new URL(href);
 for(const [key,value] of Object.entries(filters)){
  url.searchParams.delete(key);
  if(Array.isArray(value)){for(const item of value)url.searchParams.append(key,item);}
  else if(value!==''&&value!==false)url.searchParams.set(key,value===true?'1':String(value));
 }
 url.searchParams.delete('sort');if(sort!=='price')url.searchParams.set('sort',sort);
 return url;
}
export function groupRoutes(offers){
 const routes=new Map();
 for(const offer of offers){
  const key=offer.origin+'-'+offer.destination;
  if(!routes.has(key))routes.set(key,{key,origin:offer.origin,destination:offer.destination,city:offer.city,origin_name:offer.origin_name,country:offer.country,offers:[],minPrice:Infinity,months:new Set()});
  const route=routes.get(key);route.offers.push(offer);route.minPrice=Math.min(route.minPrice,offer.price_brl);route.months.add(offer.departure_date.slice(0,7));
 }
 return [...routes.values()];
}
export function monthFacets(offers,filters,today){
 const keys=new Set(filters.months||[]),base=new Date(today+'T12:00:00Z');base.setUTCDate(1);
 for(let offset=0;offset<=6;offset++){const month=new Date(base);month.setUTCMonth(base.getUTCMonth()+offset);keys.add(month.toISOString().slice(0,7));}
 for(const offer of offers)keys.add(offer.departure_date.slice(0,7));
 const counts=new Map();for(const offer of filterOffers(offers,{...filters,months:[]})){const key=offer.departure_date.slice(0,7);counts.set(key,(counts.get(key)||0)+1);}
 return [...keys].sort().map(key=>({key,count:counts.get(key)||0}));
}
export function monthName(key,short=false){return new Date(key+'-01T12:00:00Z').toLocaleDateString('pt-BR',{month:short?'short':'long',year:'numeric',timeZone:'UTC'}).replaceAll('.','').replace(' de ',' ');}
