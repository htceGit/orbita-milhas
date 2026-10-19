/** Airport choices come exclusively from the fares currently in the catalogue. */
export function airportLabel(value,code){
 const name=typeof value==='string'?value.trim():'';
 if(!name)return code;
 const marker=name.toUpperCase().indexOf('('+code+')');
 return (marker>=0?name.slice(0,marker).trim():name)||code;
}
export function airportOptions(offers){
 const origins=new Map(),destinations=new Map();
 const add=(map,code,value)=>{if(!/^[A-Z]{3}$/.test(code||''))return;const label=airportLabel(value,code);if(!map.has(code)||map.get(code)===code&&label!==code)map.set(code,label);};
 for(const offer of offers){add(origins,offer.origin,offer.origin_name);add(destinations,offer.destination,offer.destination_name||offer.city);}
 const sorted=map=>[...map].sort(([aCode,aName],[bCode,bName])=>aName.localeCompare(bName,'pt-BR')||aCode.localeCompare(bCode));
 return {origins:sorted(origins),destinations:sorted(destinations)};
}
