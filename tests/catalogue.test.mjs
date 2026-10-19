import test from 'node:test';
import assert from 'node:assert/strict';
import {createFilters,readFilters,filterUrl,groupRoutes,monthFacets,toggleValue,appliedFilters} from '../web/catalogue.js';
import {filterOffers} from '../web/domain.js';
const offers=[
 {id:'1',origin:'FLN',origin_name:'Florianópolis',destination:'MIA',city:'Miami',country:'Estados Unidos',region:'EUA',price_brl:2900,departure_date:'2026-11-07',return_date:'2026-11-17',trip_type:'round_trip',stay_days:10,airline_names:['LATAM'],stops:1},
 {id:'2',origin:'FLN',origin_name:'Florianópolis',destination:'MIA',city:'Miami',country:'Estados Unidos',region:'EUA',price_brl:2400,departure_date:'2026-12-07',return_date:'2026-12-17',trip_type:'round_trip',stay_days:10,airline_names:['LATAM','Delta'],stops:1},
 {id:'3',origin:'GRU',origin_name:'Guarulhos',destination:'MIA',city:'Miami',country:'Estados Unidos',region:'EUA',price_brl:2600,departure_date:'2026-11-10',trip_type:'one_way',stay_days:null,airline_names:['American Airlines'],stops:0},
 {id:'4',origin:'CWB',origin_name:'Curitiba',destination:'LIS',city:'Lisboa',country:'Portugal',region:'Europa',price_brl:3300,departure_date:'2027-01-03',return_date:'2027-01-17',trip_type:'round_trip',stay_days:14,airline_names:['TAP Air Portugal'],stops:1}
];
test('múltiplas opções somam dentro do filtro e cruzam com os outros filtros',()=>{
 const filters={...createFilters(),origin:['FLN','CWB'],region:['EUA','Europa'],months:['2026-11','2027-01']};
 assert.deepEqual(filterOffers(offers,filters).map(o=>o.id),['1','4']);
 assert.deepEqual(filterOffers(offers,{...filters,destination:['LIS']}).map(o=>o.id),['4']);
 assert.deepEqual(filterOffers(offers,{...createFilters(),airline:['LATAM','TAP Air Portugal']}).map(o=>o.id),['1','2','4'],'companhia selecionada inclui trechos em parceria');
 assert.equal(filterOffers(offers,{...createFilters(),trip:['one_way','round_trip']}).length,4);
 assert.equal(filterOffers(offers,{...createFilters(),origin:[]}).length,4,'seleção vazia significa qualquer opção');
});
test('rotas separam aeroportos e o preço mínimo respeita os meses selecionados',()=>{
 const all=groupRoutes(offers);assert.equal(all.length,3);assert.equal(all[0].key,'FLN-MIA');assert.equal(all[0].offers.length,2);assert.equal(all[0].minPrice,2400);assert.deepEqual([...all[0].months],['2026-11','2026-12']);
 const november=groupRoutes(filterOffers(offers,{...createFilters(),months:['2026-11']}));assert.equal(november[0].minPrice,2900);assert.equal(november[0].offers.length,1);assert.equal(november[1].key,'GRU-MIA');assert.equal(offers.length,4);
});
test('URLs preservam múltiplas seleções, o ano dos meses e links antigos',()=>{
 const filters={...createFilters(),origin:['FLN','GRU'],destination:['MIA','LIS'],months:['2026-11','2027-01'],airline:['LATAM','TAP Air Portugal'],direct:true,maxPrice:'3500'};
 const url=filterUrl('https://example.test/?demo=1&oferta=1#ofertas',filters,'departure');const back=readFilters(url.search);
 assert.deepEqual(back,{filters,sort:'departure'});assert.equal(url.searchParams.get('demo'),'1');assert.equal(url.searchParams.get('oferta'),'1');assert.equal(url.hash,'#ofertas');
 assert.deepEqual(readFilters('?origin=FLN&region=EUA&trip=round_trip').filters.origin,['FLN']);assert.deepEqual(readFilters('?origin=all&region=all').filters.region,[]);
 const invalid=readFilters('?origin=invalid&months=2026-13&departureFrom=2026-02-30&minStay=-1&maxPrice=Infinity&trip=nope').filters;assert.deepEqual(invalid,createFilters());
});
test('botões de mês contam opções com os demais filtros e distinguem anos',()=>{
 const facets=monthFacets(offers,{...createFilters(),origin:['FLN'],months:['2026-11']},'2026-10-31');
 assert.equal(facets.find(m=>m.key==='2026-11').count,1);assert.equal(facets.find(m=>m.key==='2026-12').count,1,'selecionar novembro não esconde dezembro');assert.equal(facets.find(m=>m.key==='2027-01').count,0);assert.ok(facets.some(m=>m.key==='2027-04'));
 assert.equal(monthFacets(offers,createFilters(),'2026-10-31').find(m=>m.key==='2026-11').count,2);
});
test('remover uma seleção mantém as demais e os filtros vazios não geram chips',()=>{
 assert.deepEqual(toggleValue(['FLN','GRU'],'FLN'),['GRU']);assert.deepEqual(toggleValue(['FLN'],'GRU'),['FLN','GRU']);assert.deepEqual(appliedFilters(createFilters()),[]);
 assert.deepEqual(appliedFilters({...createFilters(),origin:['FLN','GRU'],direct:true}),[{key:'origin',value:'FLN'},{key:'origin',value:'GRU'},{key:'direct',value:true}]);
});
