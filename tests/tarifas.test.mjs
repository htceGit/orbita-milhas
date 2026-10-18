import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeTarifa,brasilToday,fareCurrent,feedSummary,tripLabel,stopsLabel,fetchTarifas} from '../web/tarifas.js';
import {filterOffers,hasLatamProjection} from '../web/domain.js';
const sample={id:'9007199254740993',origem:'CWB',destino:'MIA',origem_nome:'Curitiba (CWB) - Afonso Pena',destino_nome:'Miami (MIA) - Miami International Airport',tipo_viagem:'Ida e Volta',data_ida:'2026-11-11',data_volta:'2026-11-16',duracao_dias:5,preco:'3495.00',companhia:'LATAM',voos:'LA 3291 / LA 8190',horario_partida:'19:40',horario_chegada:'05:25',duracao_total:'11h 45m',escalas:'1 parada(s) em GRU',aeronave:'Airbus A321, Boeing 787',link_google_voos:'https://www.google.com/travel/flights',atualizado_em:'2026-10-18T01:13:57Z'};
test('o contrato do motor externo preserva IDs grandes, datas, preço e detalhes dos voos',()=>{
 const o=normalizeTarifa(sample);assert.equal(o.id,sample.id);assert.equal(o.city,'Miami');assert.equal(o.price_brl,3495);assert.equal(o.stay_days,5);assert.equal(o.stops,1);assert.equal(o.flight_numbers,sample.voos);assert.equal(o.departure_time,'19:40');assert.equal(o.aircraft,sample.aeronave);assert.equal(o.expires_at,null);assert.equal(hasLatamProjection(o),true);
 assert.equal(filterOffers([o],{}).length,1,'tarifas do novo motor não herdam o teto antigo de R$ 3.000');
 assert.equal(filterOffers([o],{maxPrice:3000}).length,0,'o filtro do usuário continua funcionando');
});
test('companhias mistas não recebem projeção LATAM, mesmo com rótulo incompleto',()=>{
 for(const row of [{companhia:'LATAM / American Airlines'},{companhia:'LATAM',voos:'LA 3291 / AA 8190'},{companhia:null,voos:null}])assert.equal(hasLatamProjection(normalizeTarifa({...sample,...row})),false);
 assert.equal(normalizeTarifa({...sample,companhia:'TAP Air Portugal',voos:'TP 85'}).airlines[0],'TP');
});
test('registros sem dados válidos são descartados e conexões ausentes não viram voo direto',()=>{
 for(const changes of [{preco:true},{preco:''},{preco:0},{preco:'NaN'},{data_ida:'2026-02-30'},{data_volta:null},{data_volta:'2026-11-01'},{origem:'A_1'},{id:9007199254740992}])assert.equal(normalizeTarifa({...sample,...changes}),null);
 assert.equal(normalizeTarifa({...sample,escalas:null}).stops,null);
 assert.equal(stopsLabel(normalizeTarifa({...sample,escalas:null})),'Conexões a confirmar');
});
test('somente ida não inventa volta e a validade usa a data de Brasília',()=>{
 const o=normalizeTarifa({...sample,tipo_viagem:'Só Ida',data_volta:null,escalas:'Direto'});
 assert.equal(o.return_date,null);assert.equal(o.stay_days,null);assert.equal(tripLabel(o),'Somente ida');assert.equal(stopsLabel(o),'Direto');
 assert.equal(brasilToday(new Date('2026-10-18T01:30:00Z')),'2026-10-17');
 assert.equal(fareCurrent(o,'2026-11-11'),true);assert.equal(fareCurrent(o,'2026-11-12'),false);
 assert.equal(fareCurrent({...o,collected_at:'2026-01-01T00:00:00Z'},'2026-10-17'),true,'não inventa expiração ausente no contrato');
});
test('o resumo de atualizações não simula estado de execução do coletor',()=>{
 const a=normalizeTarifa(sample),b=normalizeTarifa({...sample,id:'2',destino:'CDG',atualizado_em:'2026-10-18T02:00:00Z'});
 assert.deepEqual(feedSummary([a,b]),{total:2,routes:2,destinations:2,latest:'2026-10-18T02:00:00Z'});
 assert.equal(feedSummary([]).latest,null);
});
test('a leitura percorre páginas e não trunca silenciosamente no limite padrão da API',async()=>{
 let pages=0;const rows=Array.from({length:501},(_,i)=>({...sample,id:String(i+1)}));
 const db={from(name){assert.equal(name,'tarifaspromo');const q={select(){return q;},gte(){return q;},order(){return q;},async range(start,end){pages++;return {data:rows.slice(start,end+1),count:501,error:null};}};return q;}};
 const result=await fetchTarifas(db,'2026-10-17');assert.equal(pages,2);assert.equal(result.offers.length,501);assert.equal(result.limited,false);
});
