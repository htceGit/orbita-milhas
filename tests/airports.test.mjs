import test from 'node:test';
import assert from 'node:assert/strict';
import {airportLabel,airportOptions} from '../web/airports.js';
import {normalizeTarifa} from '../web/tarifas.js';

test('filtros contêm somente aeroportos presentes nas tarifas, incluindo novos códigos',()=>{
 const fares=[{origin:'BSB',origin_name:'Brasília (BSB) - Internacional',destination:'ORD',destination_name:'Chicago (ORD) - O’Hare'},{origin:'SSA',origin_name:'Salvador',destination:'EZE',destination_name:'Buenos Aires (EZE)'},{origin:'BSB',origin_name:'Brasília',destination:'ORD',destination_name:'Chicago'}];
 assert.deepEqual(airportOptions(fares),{origins:[['BSB','Brasília'],['SSA','Salvador']],destinations:[['EZE','Buenos Aires'],['ORD','Chicago']]});
 assert.deepEqual(airportOptions([]),{origins:[],destinations:[]});
 assert.equal(airportOptions(fares).origins.some(([code])=>code==='FLN'),false,'aeroporto antigo sem tarifa não aparece');
});
test('nome cadastrado tem prioridade; ausência de nome usa código e não inventa opções',()=>{
 assert.equal(airportLabel('São Paulo / Guarulhos (GRU) - Aeroporto Internacional','GRU'),'São Paulo / Guarulhos');
 assert.equal(airportLabel(null,'REC'),'REC');
 assert.deepEqual(airportOptions([{origin:'REC',destination:'SCL'},{origin:'REC',origin_name:'Recife',destination:'SCL',city:'Santiago'}]),{origins:[['REC','Recife']],destinations:[['SCL','Santiago']]});
});
test('adaptação aceita rotas novas e usa os nomes recebidos mesmo para códigos já conhecidos',()=>{
 const fare={id:'1',origem:'CNF',origem_nome:'Belo Horizonte (CNF) - Confins',destino:'MIA',destino_nome:'Miami cadastrada (MIA) - Internacional',data_ida:'2027-03-01',data_volta:'2027-03-10',preco:2900,companhia:'LATAM'};
 const offer=normalizeTarifa(fare);assert.equal(offer.origin_name,'Belo Horizonte');assert.equal(offer.city,'Miami cadastrada');
 assert.deepEqual(airportOptions([offer]),{origins:[['CNF','Belo Horizonte']],destinations:[['MIA','Miami cadastrada']]});
 const unknown=normalizeTarifa({...fare,id:'2',origem:'REC',origem_nome:null,destino:'SCL',destino_nome:null});assert.equal(unknown.origin_name,'REC');assert.equal(unknown.city,'SCL');
});
