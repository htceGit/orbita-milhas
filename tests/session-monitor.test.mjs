import test from 'node:test';
import assert from 'node:assert/strict';
import {sessionModel,sessionMonitorView} from '../web/session-monitor.js';

test('orçamento consumido e cobertura única são medidas independentes',()=>{
 const view=sessionModel({query_budget:1000,queries_attempted:200,total_combinations:200000,calendar_entries:10000,calendar_priced_combinations:5000,diagnostics_version:1,started_at:'2026-10-17T12:00:00Z',finished_at:'2026-10-17T12:02:30Z'});
 assert.equal(view.consumed,20);assert.equal(view.coverage,2.5);assert.equal(view.elapsed,150);
 assert.equal(sessionModel({diagnostics_version:0,total_combinations:200000,calendar_entries:10000}).coverage,null);
});
test('sinal atrasado é indicado apenas para sessão em execução',()=>{
 const now=Date.parse('2026-10-17T12:05:00Z'),run={status:'running',started_at:'2026-10-17T12:00:00Z',heartbeat_at:'2026-10-17T12:01:00Z'};
 assert.equal(sessionModel(run,now).stale,true);
 assert.equal(sessionModel({...run,status:'completed'},now).stale,false);
});
test('diagnósticos são escapados e links de execução ficam restritos ao repositório',()=>{
 const html=sessionMonitorView({runs:[{id:'one',status:'partial',diagnostics_version:1,phase:'finished',error_counts:{timeout:1},workflow_url:'javascript:alert(1)',started_at:'2026-10-17T12:00:00Z'}],events:[{stage:'detail',outcome:'error',cause_type:'<script>alert(1)</script>',message:'<img src=x onerror=alert(1)>',error_code:'timeout'}]});
 assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('href="javascript:'));
 assert.ok(html.includes('Formato')===false);assert.ok(html.includes('Tempo excedido'));
});
