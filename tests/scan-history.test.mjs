import test from 'node:test';
import assert from 'node:assert/strict';
import {scanHistoryView,runOrigin,sweepsLabel} from '../web/scan-history.js';

test('requisições parciais não são apresentadas como varreduras completas',()=>{
 const run={started_at:'2026-10-17T22:09:23Z',status:'partial',query_budget:20,query_budget_override:20,trigger_source:'manual',queries_attempted:12,calendar_queries:4,calendar_entries:120,calendar_sweeps_requested:2,calendar_sweeps_completed:0,detail_dates_checked:4,detail_queries:5,offers_found:4,errors_count:2};
 const html=scanHistoryView([run]);
 assert.match(html,/Requisições de calendário<\/dt><dd>4/);
 assert.match(html,/Varreduras completas \/ solicitadas<\/dt><dd>0 \/ 2/);
 assert.match(html,/12 de 20 chamadas/);
 assert.match(html,/Manual · teste/);
 assert.equal(sweepsLabel({}),'Não registrado');
});
test('origem distingue continuidade automática de disparo manual',()=>{
 assert.equal(runOrigin({trigger_source:'continuation'}),'Automática · continuidade');
 assert.equal(runOrigin({trigger_source:'manual'}),'Manual');
 assert.equal(runOrigin({trigger_source:'other'}),'Origem não registrada');
});
