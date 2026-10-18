import test from 'node:test';
import assert from 'node:assert/strict';
import {compositionModel,sessionCompositionView,stayLabel} from '../web/session-composition.js';

const summary={run_id:'one',detail_attempts_expected:5,detail_attempts_recorded:4,calendars:[
 {origin:'FLN',destination:'MIA',departure_start:'2026-10-18',departure_end:'2027-04-17',min_days:7,max_days:8,status:'partial',prices:120},
 {origin:'FLN',destination:'MIA',departure_start:'2026-10-18',departure_end:'2027-04-17',min_days:10,max_days:10,status:'failed',prices:null}
],details:[
 {origin:'FLN',destination:'MIA',stay_days:7,departure_start:'2026-11-07',departure_end:'2026-11-16',return_start:'2026-11-14',return_end:'2026-11-23',attempts:3,dates_attempted:2,dates_completed:2,errors:1,filtered:1},
 {origin:'CWB',destination:'LIS',stay_days:14,departure_start:'2027-01-02',departure_end:'2027-01-02',return_start:'2027-01-16',return_end:'2027-01-16',attempts:1,dates_attempted:1,dates_completed:1,errors:0,filtered:0}
]};
test('composição agrupa por rota e preserva permanências não consecutivas',()=>{
 const model=compositionModel(summary);
 assert.equal(model.routes.length,2);assert.equal(model.origins,2);assert.equal(model.destinations,2);
 assert.equal(model.routes.find(r=>r.origin==='FLN').calendars.length,2);
 assert.equal(model.missingDetails,1);
 assert.equal(stayLabel([10,7,8,10,12,13]),'7–8, 10, 12–13 dias');
});
test('período solicitado ao calendário é separado das datas de ida e volta consultadas',()=>{
 const html=sessionCompositionView(summary,{status:'partial'});
 for(const text of ['Composição executada','FLN','MIA','18/10/2026 a 17/04/2027','07/11/2026 a 16/11/2026','14/11/2026 a 23/11/2026','7–8, 10 dias','Resumo parcial','4 de 5','não significam que todos os dias','Ver períodos por permanência'])assert.ok(html.includes(text),text);
 assert.ok(html.includes('2 pares concluídos de 2 consultados'));
 assert.ok(html.includes('Não registrado'));
});
test('sessões sem registros não recebem períodos inventados e dados externos são escapados',()=>{
 assert.match(sessionCompositionView(null,{}),/Carregando/);
 assert.match(sessionCompositionView({calendars:[],details:[]},{status:'running'}),/primeiras consultas/);
 assert.match(sessionCompositionView({calendars:[],details:[]},{status:'failed'}),/Não há registros/);
 const html=sessionCompositionView({details:[{origin:'<img src=x>',destination:'<script>',attempts:1}],calendars:[]},{});
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img src=x>'));assert.ok(html.includes('&lt;script&gt;'));
});
