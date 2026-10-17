"""Resumable scanner. Scheduled sessions are gated by a minimum 15-minute rest."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from multiprocessing import get_context
from time import monotonic,sleep
import os
import sys
from .planner import Planner
from .storage import Store
from .provider import FastFlightsProvider
from .calendar import BrowserCalendarEngine,best_candidates_per_stay
from .diagnostics import SearchFailure,diagnose
from .telemetry import SessionReporter,TelemetryFailure
from calendar_service.domain import CalendarQuery,CalendarBlocked
from calendar_service.jobs import capture_record,process_queued

def child_search(connection,query,metadata,max_stops,proxy):
    try:
        connection.send(('ok',FastFlightsProvider(max_stops,proxy).search(query,metadata)))
    except Exception as exc:
        connection.send(('error',diagnose(exc)))
    finally:
        connection.close()

def bounded_search(query,metadata,max_stops,proxy,timeout=40):
    # A subprocess adds a hard upper bound to the transport timeout,
    # including parser hangs or network stalls.
    context=get_context('spawn')
    parent,child=context.Pipe(False)
    process=context.Process(target=child_search,args=(child,query,metadata,max_stops,proxy))
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):raise SearchFailure('timeout','TimeoutError','A consulta detalhada excedeu 40 segundos.',retryable=True)
        try:kind,payload=parent.recv()
        except EOFError as exc:raise SearchFailure('worker_crash','EOFError','O subprocesso encerrou sem devolver resultado.') from exc
        if kind!='ok':raise SearchFailure.from_diagnostic(payload)
        return payload
    finally:
        if process.is_alive():process.terminate()
        process.join(5)
        if process.is_alive():process.kill();process.join()
        parent.close()

def run(store,search=bounded_search,clock=monotonic,calendar_search=None):
    settings=store.request('scanner_settings',params={'id':'eq.1'})[0]
    if not settings['enabled']:
        print('Motor pausado pela administração.');return 0
    profiles=store.read_all('profiles',{'select':'id,plan,pro_until,role','status':'eq.active'})
    active={p['id'] for p in profiles}
    monitors=[m for m in store.read_all('monitors',{'enabled':'eq.true','order':'created_at.asc'}) if m['user_id'] in active]
    now=datetime.now(timezone.utc);limited=[]
    for p in profiles:
        until=datetime.fromisoformat(p['pro_until'].replace('Z','+00:00')) if p.get('pro_until') else None
        pro=p['role']=='admin' or p['plan']=='pro' and(not until or until>now)
        limited.extend([m for m in monitors if m['user_id']==p['id']][:(30 if pro else 3)])
    planner=Planner(settings,limited,datetime.now(ZoneInfo('America/Sao_Paulo')).date())
    state=store.request('scanner_state',params={'id':'eq.1'})[0]
    same=state.get('config_hash')==planner.fingerprint
    cursor=state['cursor_position'] if same else 0
    calendar_cursor=state.get('calendar_cursor',0) if same else 0
    if settings['search_mode']=='exhaustive':cursor=calendar_cursor=0
    calendar_active=settings.get('search_strategy','hybrid')=='hybrid'
    budget=planner.total if settings['search_mode']=='exhaustive' else settings['query_budget']
    if not calendar_active:budget=min(budget,planner.total)
    override=int(os.environ.get('QUERY_BUDGET_OVERRIDE','0') or 0)
    if override>0:budget=min(budget,override)
    engine=BrowserCalendarEngine() if calendar_search is None else None
    if engine:
        calendar_search=lambda a,b,start,end,low,high,stops,proxy,max_calls:engine.capture(CalendarQuery(a,b,start,end,low,high,stops),max_search_calls=max_calls,proxy=proxy,progress=capture_progress)
    workflow_id=os.environ.get('GITHUB_RUN_ID','')
    workflow_url=f'https://github.com/htceGit/orbita-milhas/actions/runs/{workflow_id}' if workflow_id.isdigit() else None
    run=store.request('scan_runs','POST',{'total_combinations':planner.total,'provider':'orbita_browser_calendar' if calendar_active else 'fast_flights','message':'Calendário para descobrir datas; consulta detalhada para confirmar tarifa e companhia.',
        'diagnostics_version':1,'query_budget':budget,'phase':'planning','workflow_url':workflow_url,'heartbeat_at':datetime.now(timezone.utc).isoformat()})[0]
    attempts=found=errors=consecutive=calendar_queries=calendar_entries=detail_queries=calendar_search_calls=calendar_routes=calendar_errors=0
    calendar_status='pending' if calendar_active else 'disabled'
    checked=set();started=clock();reason='';seen=set();calendar_partial=False;pending_candidates=[];pending_stops={}
    calendar_tasks_attempted=fallback_tasks_attempted=0;planned_stop=False
    retries=empty_results=recovered=final_errors=0;priced=set();phase='planning';current=None;last_cursor_write=-100
    reporter=SessionReporter(store,run['id'],clock)
    proxy=os.environ.get('FLIGHTS_PROXY') or None
    def metrics():
        return {'queries_attempted':attempts,'offers_found':found,'errors_count':errors,
                'calendar_queries':calendar_queries,'calendar_entries':calendar_entries,
                'calendar_search_calls':calendar_search_calls,'calendar_routes':calendar_routes,'detail_queries':detail_queries,'detail_dates_checked':len(checked),'calendar_status':calendar_status,
                'retries_count':retries,'empty_results':empty_results,'recovered_queries':recovered,'calendar_priced_combinations':len(priced)}
    def checkpoint(force=False):
        nonlocal last_cursor_write
        if force or clock()-last_cursor_write>=15:
            store.patch('scanner_state',1,{'cursor_position':cursor,'calendar_cursor':calendar_cursor,
                'config_hash':planner.fingerprint,'anchor_date':planner.today.isoformat(),'last_run_id':run['id'],
                'updated_at':datetime.now(timezone.utc).isoformat()})
            last_cursor_write=clock()
        reporter.publish(metrics(),phase,current,force)
    def capture_progress(progress):
        live=metrics();prices={v.query for v in progress['prices'] if planner.contains(v.query)}
        live.update(queries_attempted=attempts+progress['search_calls'],calendar_search_calls=calendar_search_calls+progress['search_calls'],
            calendar_queries=calendar_queries+progress['calendar_requests'],calendar_entries=calendar_entries+len(progress['prices']),calendar_priced_combinations=len(priced|prices))
        reporter.publish(live,'calendar',progress['current'])
    try:
        reporter.event('planning','started',message=f'Sessão com teto de {budget} chamadas; duas datas por duração.')
        checkpoint(True)
        if engine:
            phase='calendar'
            queued=process_queued(store,engine,run['id'],budget,proxy,progress=capture_progress)
            attempts+=queued['search_calls'];calendar_search_calls+=queued['search_calls'];calendar_queries+=queued['calendars'];calendar_entries+=queued['entries'];calendar_routes+=queued['routes'];errors+=queued['errors']
            if queued['routes']:calendar_status='available'
            calendar_partial=bool(queued['errors']);pending_candidates=queued['candidates'];pending_stops=queued['candidate_stops']
            for capture in queued.get('captures',[]):priced.update(v.query for v in capture.entries if planner.contains(v.query))
            for diag in queued.get('diagnostics',[]):reporter.event('calendar','error',diagnostic=diag)
            if any(diag['code'] in ('rate_limited','access_denied','challenge') for diag in queued.get('diagnostics',[])):
                reason='Sessão interrompida por limitação ou verificação de acesso do Google.'
            if queued['search_calls']:checkpoint(True)
        while attempts<budget and not reason:
            if clock()-started>3*3600:
                reason='Limite de 3 horas; a fila será retomada.';break
            candidates=pending_candidates;pending_candidates=[]
            if not candidates and calendar_active:
                if calendar_tasks_attempted>=len(planner.calendar_tasks):
                    if calendar_status=='unavailable':calendar_active=False
                    else:
                        reason='Todos os calendários da fila foram percorridos nesta rodada.';planned_stop=True;break
                task=planner.calendar_batch(calendar_cursor,budget-attempts,len(planner.calendar_tasks)-calendar_tasks_attempted) if calendar_active else None
                if calendar_active and task is None:
                    reason='Saldo reservado: a próxima sessão retoma o próximo calendário com até dois detalhes por permanência.';planned_stop=True;break
            if not candidates and calendar_active:
                calendar_query=CalendarQuery(task[0],task[1],planner.today+timedelta(days=1),planner.today+timedelta(days=planner.days),task[2],task[3],settings['max_stops'])
                phase='calendar';current={**calendar_query.json()};checkpoint(True);call_started=clock()
                try:
                    capture=calendar_search(*task[:2],calendar_query.departure_start,calendar_query.departure_end,*task[2:],settings['max_stops'],proxy,budget-attempts-calendar_query.detail_reserve)
                except TelemetryFailure:raise
                except Exception as exc:
                    used=max(1,getattr(exc,'search_calls',0));attempts+=used;calendar_search_calls+=used
                    errors+=1;calendar_errors+=1;calendar_status='unavailable';calendar_partial=True
                    calendar_active=calendar_errors<3 and not isinstance(exc,CalendarBlocked)
                    diagnostic=diagnose(exc);reporter.event('calendar','error',diagnostic=diagnostic,duration_ms=(clock()-call_started)*1000,context=current)
                    print(f'Calendário {task[0]}–{task[1]}: {diagnostic["code"]} / {diagnostic["cause_type"]}: {diagnostic["message"]}',flush=True)
                    if diagnostic['code'] in ('rate_limited','access_denied','challenge'):reason='Sessão interrompida por limitação ou verificação de acesso do Google.'
                else:
                    attempts+=capture.search_calls;calendar_search_calls+=capture.search_calls;calendar_queries+=capture.calendar_requests
                    calendar_entries+=len(capture.entries);calendar_routes+=1;calendar_status='available';calendar_errors=0
                    if capture.status!='completed':errors+=1;calendar_partial=True
                    priced.update(v.query for v in capture.entries if planner.contains(v.query))
                    reporter.event('calendar','error' if capture.status!='completed' else 'success',diagnostic=capture.diagnostic if capture.status!='completed' else None,duration_ms=(clock()-call_started)*1000,message=f'{len(capture.entries)} preços capturados para {task[0]}–{task[1]}, {task[2]}–{task[3]} dias.',context=current)
                    if capture.diagnostic and capture.diagnostic['code'] in ('rate_limited','access_denied','challenge'):
                        reason='Sessão interrompida por limitação ou verificação de acesso do Google.'
                    store.request('calendar_jobs','POST',capture_record(capture,run['id']))
                    candidates=[v.query for v in best_candidates_per_stay(capture.entries)]
                    print(f'Calendário {task[0]}–{task[1]} ({task[2]}–{task[3]} dias): {len(capture.entries)} preços; {capture.search_calls} chamadas; {len(candidates)} datas selecionadas; {capture.status}.',flush=True)
                task_count=task[3]-task[2]+1
                calendar_tasks_attempted+=task_count
                calendar_cursor=(calendar_cursor+task_count)%len(planner.calendar_tasks)
                checkpoint(True)
                if reason:break
                if calendar_active and not candidates:
                    sleep(float(os.environ.get('QUERY_DELAY_SECONDS','1.5')));continue
            if not candidates:
                if fallback_tasks_attempted>=planner.total:
                    reason='A fila detalhada foi percorrida nesta rodada.';planned_stop=True;break
                candidates=[planner.at(cursor)];cursor=(cursor+1)%planner.total
                fallback_tasks_attempted+=1
            for candidate_index,query in enumerate(candidates):
                if attempts>=budget:break
                if clock()-started>3*3600:
                    reason='Limite de 3 horas; a fila será retomada.';break
                if query in seen:continue
                seen.add(query);offer=None;phase='detail'
                current={'origin':query.origin,'destination':query.destination,'departure_date':str(query.departure),'return_date':str(query.returning),'stay_days':(query.returning-query.departure).days}
                for trial in (1,2):
                    attempts+=1;detail_queries+=1;current['attempt']=trial;checkpoint();call_started=clock()
                    try:
                        offer=search(query,planner.destinations.get(query.destination,{'city':query.destination}),pending_stops.get(query,settings['max_stops']),proxy)
                        checked.add(query);consecutive=0
                        if trial==2:recovered+=1
                        if not offer:empty_results+=1
                        reporter.event('detail','success' if offer else 'empty',query,attempt=trial,duration_ms=(clock()-call_started)*1000,message='Tarifa identificada.' if offer else 'Consulta concluída sem tarifa válida para o par de datas.')
                        break
                    except TelemetryFailure:raise
                    except Exception as exc:
                        errors+=1;offer=None;diagnostic=diagnose(exc)
                        reporter.event('detail','error',query,diagnostic,trial,(clock()-call_started)*1000)
                        print(f'Consulta {attempts} {query.origin}–{query.destination} {query.departure}: {diagnostic["code"]} / {diagnostic["cause_type"]}: {diagnostic["message"]}',flush=True)
                        if diagnostic['code'] in ('rate_limited','access_denied','challenge'):
                            final_errors+=1;reason='Sessão interrompida por limitação ou verificação de acesso do Google.';break
                        slots_left=len(candidates)-candidate_index-1
                        if trial==1 and diagnostic['retryable'] and budget-attempts>slots_left and clock()-started<3*3600-45:
                            retries+=1;reporter.event('detail','retry',query,attempt=2,message='Uma nova tentativa após falha transitória, dentro do orçamento.');phase='backoff';checkpoint(True);sleep(float(os.environ.get('RETRY_DELAY_SECONDS','3')));phase='detail';continue
                        final_errors+=1;consecutive+=1;break
                # Infrastructure failures must fail the run, never be mistaken
                # for a provider outage or counted as successfully stored fares.
                if offer:store.save_offer(offer);found+=1
                checkpoint()
                if reason:break
                if consecutive>=8:
                    reason='Circuito interrompido após 8 falhas consecutivas nas consultas detalhadas.';break
                sleep(float(os.environ.get('QUERY_DELAY_SECONDS','1.5')))
            if consecutive>=8 or reason:break
        if calendar_entries and calendar_partial:calendar_status='partial'
        complete=len(checked)==planner.total and errors==0
        status='failed' if detail_queries and not checked else('completed' if (attempts>=budget or planned_stop) and not final_errors and not calendar_partial else 'partial')
        message=reason or ('Rodada encerrada; descoberta de datas e validação detalhada são contadas separadamente.')
        if calendar_status=='unavailable':message+=' Calendário indisponível: busca detalhada utilizada automaticamente.'
        phase='finished';current=None;reporter.event('system','finished',message=message);checkpoint(True)
        store.patch('scan_runs',run['id'],{**metrics(),'status':status,'finished_at':datetime.now(timezone.utc).isoformat(),'coverage_complete':complete,'message':message})
        cutoff=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()-90*86400,timezone.utc)
        store.request('fare_history','DELETE',params={'observed_at':'lt.'+cutoff.isoformat()},prefer='return=minimal')
        store.request('offers','DELETE',params={'return_date':'lt.'+planner.today.isoformat()},prefer='return=minimal')
        store.request('calendar_jobs','DELETE',prefer='return=minimal')
        store.request('scan_events','DELETE',prefer='return=minimal')
        print(f'Rodada {status}: {calendar_queries} calendários, {calendar_entries} preços de calendário, {detail_queries} consultas detalhadas, {found} tarifas.',flush=True)
        return 1 if status=='failed' else 0
    except Exception as exc:
        reporter.event('system','error',diagnostic=diagnose(exc));reporter.flush_events()
        store.patch('scan_runs',run['id'],{**metrics(),'status':'failed','phase':'failed','heartbeat_at':datetime.now(timezone.utc).isoformat(),'error_counts':reporter.error_counts,'last_error':reporter.last_error,'finished_at':datetime.now(timezone.utc).isoformat(),'message':f'Falha de infraestrutura: {type(exc).__name__}'})
        raise
    finally:
        if engine:engine.close()

if __name__=='__main__':
    sys.exit(run(Store(os.environ.get('SUPABASE_URL',''),os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))))
