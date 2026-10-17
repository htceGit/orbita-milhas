import {escape as e,number} from './domain.js';

export function runOrigin(run){
 if(run.trigger_source==='continuation')return 'Automática · continuidade';
 if(run.trigger_source==='schedule')return 'Automática · cron de reserva';
 if(run.trigger_source==='manual')return run.query_budget_override?'Manual · teste':'Manual';
 return 'Origem não registrada';
}

export function sweepsLabel(run){
 return run.calendar_sweeps_completed==null?'Não registrado':`${number(run.calendar_sweeps_completed)} / ${number(run.calendar_sweeps_requested)}`;
}

export function scanHistoryView(runs){
 return `<p class="history-explainer">Uma tentativa consulta uma janela de datas e pode falhar ou ser repetida. Uma varredura completa cobre todo o intervalo solicitado de uma rota e permanência. Os preços capturados são contados separadamente.</p><div class="scan-history">${runs.map(r=>`<article class="scan-history-card"><div class="scan-history-heading"><div><strong>${new Date(r.started_at).toLocaleString('pt-BR')}</strong><small>${e(runOrigin(r))}</small></div><span class="status-pill ${r.status==='completed'?'green':'neutral'}">${e({completed:'Concluída',partial:'Parcial',failed:'Falhou',running:'Em andamento'}[r.status]||r.status)}</span></div><div class="scan-history-budget"><b>${number(r.queries_attempted)} ${r.query_budget?'de '+number(r.query_budget):''} chamadas usadas</b><span>${r.query_budget_override?'Limite manual de teste: '+number(r.query_budget_override):r.query_budget?'Teto desta sessão: '+number(r.query_budget):'Teto não registrado nesta versão'}</span></div><dl class="scan-history-stats"><div><dt>Tentativas de calendário</dt><dd>${number(r.calendar_queries)}</dd></div><div><dt>Preços capturados</dt><dd>${number(r.calendar_entries)}</dd></div><div><dt>Varreduras completas / solicitadas</dt><dd>${e(sweepsLabel(r))}</dd></div><div><dt>Datas detalhadas / tentativas</dt><dd>${r.detail_dates_checked==null?'—':number(r.detail_dates_checked)} / ${number(r.detail_queries??r.queries_attempted)}</dd></div><div><dt>Tarifas salvas</dt><dd>${number(r.offers_found)}</dd></div><div><dt>Falhas registradas</dt><dd>${number(r.errors_count)}</dd></div></dl></article>`).join('')}</div>`;
}
