import test from 'node:test';
import assert from 'node:assert/strict';
import {estimate,filterOffers,escape,hasLatamProjection,airlineLabel,origins,calendarCandidates} from '../web/domain.js';
test('a simulação inclui custo das milhas e taxas, sem inventar uma cotação',()=>{
 const s=estimate(4000,20,350);
 assert.equal(s.low,2800);assert.equal(s.high,3000);
 assert.ok(s.miles/1000*20+350<=s.target);
 assert.ok((s.miles+1000)/1000*20+350>s.target);
 assert.equal(estimate(100,20,350).miles,0);
});

test('a seleção de calendário mantém cinco datas distintas por permanência',()=>{
 const entries=[7,10].flatMap(stay_days=>Array.from({length:7},(_,i)=>({origin:'FLN',destination:'MIA',stay_days,departure_date:`2026-11-${String(i+1).padStart(2,'0')}`,return_date:`2026-11-${String(i+1+stay_days).padStart(2,'0')}`,price_brl:5000-i*100})));
 entries.push({...entries.at(-1),price_brl:3840});
 const selected=calendarCandidates(entries);
 assert.equal(selected.length,10);
 for(const days of [7,10])assert.equal(selected.filter(e=>e.stay_days===days).length,5);
 assert.equal(new Set(selected.map(e=>e.departure_date+'|'+e.return_date)).size,10);
 assert.equal(selected[0].price_brl,3840);
});
test('filtros combinam região, origem, destino, preço e intervalo inclusivo',()=>{
 const offers=[{region:'Europa',origin:'FLN',city:'Paris',country:'França',destination:'CDG',price_brl:4000,departure_date:'2027-01-01'},{region:'EUA',origin:'GRU',city:'Miami',country:'Estados Unidos',destination:'MIA',price_brl:3000,departure_date:'2027-02-01'}];
 assert.equal(filterOffers(offers,{region:'Europa',origin:'FLN',search:'cdg',maxPrice:4000,departureFrom:'2027-01-01',departureTo:'2027-01-01'}).length,1);
 assert.equal(filterOffers(offers,{region:'Europa',maxPrice:3999}).length,0);
});
test('conteúdo externo é escapado antes de entrar no HTML',()=>assert.equal(escape('<img src="x" onerror="alert(1)">'), '&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;'));

test('projeção aparece somente para LATAM identificada, sem companhias mistas ou desconhecidas',()=>{
 assert.equal(hasLatamProjection({airlines:['LA']}),true);
 for(const airlines of [['TP'],['LA','AA'],['UNKNOWN'],[],undefined])assert.equal(hasLatamProjection({airlines}),false);
 assert.equal(airlineLabel({airlines:['TP'],airline_names:['TAP Air Portugal']}),'TAP Air Portugal');
 assert.deepEqual(origins.map(o=>o[0]),['CWB','JOI','NVT','FLN','VCP','GRU']);
});
