import test from 'node:test';
import assert from 'node:assert/strict';
import {estimate,filterOffers,escape,hasLatamProjection,airlineLabel,origins} from '../web/domain.js';
test('a simulação inclui custo das milhas e taxas, sem inventar uma cotação',()=>{
 const s=estimate(4000,20,350);
 assert.equal(s.low,2800);assert.equal(s.high,3000);
 assert.ok(s.miles/1000*20+350<=s.target);
 assert.ok((s.miles+1000)/1000*20+350>s.target);
 assert.equal(estimate(100,20,350).miles,0);
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
