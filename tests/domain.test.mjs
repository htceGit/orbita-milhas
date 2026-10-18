import test from 'node:test';
import assert from 'node:assert/strict';
import {estimate,filterOffers,escape,hasLatamProjection,airlineLabel,origins,offerAllowed,demoOffers} from '../web/domain.js';
test('a simulação inclui custo das milhas e taxas, sem inventar uma cotação',()=>{
 const s=estimate(4000,20,350);
 assert.equal(s.low,2800);assert.equal(s.high,3000);
 assert.ok(s.miles/1000*20+350<=s.target);
 assert.ok((s.miles+1000)/1000*20+350>s.target);
 assert.equal(estimate(100,20,350).miles,0);
});

test('filtros combinam região, origem, destino, preço e intervalo inclusivo',()=>{
 const offers=[{region:'Europa',origin:'FLN',city:'Paris',country:'França',destination:'CDG',price_brl:3500,departure_date:'2027-01-01'},{region:'EUA',origin:'GRU',city:'Miami',country:'Estados Unidos',destination:'MIA',price_brl:3000,departure_date:'2027-02-01'}];
 assert.equal(filterOffers(offers,{region:'Europa',origin:'FLN',search:'cdg',maxPrice:3500,departureFrom:'2027-01-01',departureTo:'2027-01-01'}).length,1);
 assert.equal(filterOffers(offers,{region:'Europa',maxPrice:3499}).length,0);
});
test('busca pública ignora acentos e combina companhia, conexões e permanência',()=>{
 const offers=[{city:'Paris',country:'França',origin:'FLN',origin_name:'Florianópolis',destination:'CDG',price_brl:3500,airline_names:['Air France'],stops:0,stay_days:10,trip_type:'round_trip'},{city:'Paris',country:'França',origin:'GRU',destination:'CDG',price_brl:3200,airline_names:['LATAM'],stops:1,stay_days:7,trip_type:'round_trip'},{city:'Paris',country:'França',origin:'GRU',destination:'CDG',price_brl:2000,airline_names:['Air France'],stops:0,stay_days:null,trip_type:'one_way'}];
 assert.equal(filterOffers(offers,{search:'florianopolis'}).length,1);
 assert.equal(filterOffers(offers,{search:'franca'}).length,3);
 assert.equal(filterOffers(offers,{airline:'Air France',direct:true,minStay:7,maxStay:14,trip:'round_trip'}).length,1);
 assert.equal(filterOffers(offers,{direct:true,trip:'one_way'}).length,1);
 assert.equal(filterOffers(offers,{minStay:8,maxStay:9}).length,0);
});
test('o portal apresenta todas as tarifas válidas e respeita apenas o teto escolhido pelo usuário',()=>{
 const offers=[{destination:'MIA',price_brl:3495,airlines:['LA']},{destination:'LIS',price_brl:4200,airlines:['TP']}];
 assert.ok(offers.every(offerAllowed));assert.equal(filterOffers(offers,{}).length,2);assert.equal(filterOffers(offers,{maxPrice:3500}).length,1);
 for(const price_brl of [0,-1,NaN,Infinity,true,'3000'])assert.equal(offerAllowed({price_brl}),false);
 assert.ok(demoOffers.every(offerAllowed));
});
test('conteúdo externo é escapado antes de entrar no HTML',()=>assert.equal(escape('<img src="x" onerror="alert(1)">'), '&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;'));

test('projeção aparece somente para LATAM identificada, sem companhias mistas ou desconhecidas',()=>{
 assert.equal(hasLatamProjection({airlines:['LA']}),true);
 for(const airlines of [['TP'],['LA','AA'],['UNKNOWN'],[],undefined])assert.equal(hasLatamProjection({airlines}),false);
 assert.equal(airlineLabel({airlines:['TP'],airline_names:['TAP Air Portugal']}),'TAP Air Portugal');
 assert.deepEqual(origins.map(o=>o[0]),['CWB','JOI','NVT','FLN','VCP','GRU']);
});
