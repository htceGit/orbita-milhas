"""Run via python -m worker.main. GitHub Actions schedules this every 4 hours."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from multiprocessing import get_context
from time import monotonic,sleep
import os
import sys
from .planner import Planner
from .storage import Store
from .provider import FastFlightsProvider
from .calendar import BrowserCalendarEngine,best_candidates
from calendar_service.domain import CalendarQuery,CalendarBlocked
from calendar_service.jobs import capture_record,process_queued

def child_search(connection,query,metadata,max_stops,proxy):
    try:
        connection.send(('ok',FastFlightsProvider(max_stops,proxy).search(query,metadata)))
    except Exception as exc:
        connection.send(('error',type(exc).__name__))
    finally:
        connection.close()

def bounded_search(query,metadata,max_stops,proxy,timeout=40):
    # The library's transport has no stable timeout argument. A subprocess
    # provides a hard upper bound, including parser hangs or network stalls.
    context=get_context('spawn')
    parent,child=context.Pipe(False)
    process=context.Process(target=child_search,args=(child,query,metadata,max_stops,proxy))
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):raise TimeoutError('Tempo de consulta excedido')
        kind,payload=parent.recv()
        if kind!='ok':raise RuntimeError(payload)
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
    budget=planner.total if settings['search_mode']=='exhaustive' else min(settings['query_budget'],planner.total)
    override=int(os.environ.get('QUERY_BUDGET_OVERRIDE','0') or 0)
    if override>0:budget=min(budget,override)
    calendar_active=settings.get('search_strategy','hybrid')=='hybrid'
    engine=BrowserCalendarEngine() if calendar_search is None else None
    if engine:
        calendar_search=lambda a,b,start,end,low,high,stops,proxy,max_calls:engine.capture(CalendarQuery(a,b,start,end,low,high,stops),max_search_calls=max_calls,proxy=proxy)
    run=store.request('scan_runs','POST',{'total_combinations':planner.total,'provider':'orbita_browser_calendar' if calendar_active else 'fast_flights','message':'Calendário para descobrir datas; consulta detalhada para confirmar tarifa e companhia.'})[0]
    attempts=found=errors=consecutive=calendar_queries=calendar_entries=detail_queries=calendar_search_calls=calendar_routes=calendar_errors=0
    calendar_status='pending' if calendar_active else 'disabled'
    checked=set();started=clock();reason='';seen=set();calendar_partial=False
    proxy=os.environ.get('FLIGHTS_PROXY') or None
    def metrics():
        return {'queries_attempted':attempts,'offers_found':found,'errors_count':errors,
                'calendar_queries':calendar_queries,'calendar_entries':calendar_entries,
                'calendar_search_calls':calendar_search_calls,'calendar_routes':calendar_routes,'detail_queries':detail_queries,'detail_dates_checked':len(checked),'calendar_status':calendar_status}
    def checkpoint(force=False):
        store.patch('scanner_state',1,{'cursor_position':cursor,'calendar_cursor':calendar_cursor,
            'config_hash':planner.fingerprint,'anchor_date':planner.today.isoformat(),'last_run_id':run['id'],
            'updated_at':datetime.now(timezone.utc).isoformat()})
        # Keep the durable cursor after every call, but batch UI progress writes
        # to avoid spending the free Edge quota on redundant status updates.
        if force or attempts==1 or attempts%20==0:store.patch('scan_runs',run['id'],metrics())
    try:
        if engine:
            queued=process_queued(store,engine,run['id'],budget,proxy)
            attempts+=queued['search_calls'];calendar_search_calls+=queued['search_calls'];calendar_queries+=queued['calendars'];calendar_entries+=queued['entries'];calendar_routes+=queued['routes'];errors+=queued['errors']
            if queued['routes']:calendar_status='available'
            calendar_partial=bool(queued['errors'])
        while attempts<budget:
            if clock()-started>3*3600:
                reason='Limite de 3 horas; a fila será retomada.';break
            candidates=[]
            task=planner.calendar_tasks[calendar_cursor%len(planner.calendar_tasks)]
            calendar_query=CalendarQuery(task[0],task[1],planner.today+timedelta(days=1),planner.today+timedelta(days=planner.days),task[2],task[3],settings['max_stops'])
            if calendar_active and calendar_query.estimated_calls+1<=budget-attempts:
                try:
                    capture=calendar_search(*task[:2],calendar_query.departure_start,calendar_query.departure_end,*task[2:],settings['max_stops'],proxy,budget-attempts-1)
                except Exception as exc:
                    used=max(1,getattr(exc,'search_calls',0));attempts+=used;calendar_search_calls+=used
                    errors+=1;calendar_errors+=1;calendar_status='unavailable';calendar_partial=True
                    calendar_active=calendar_errors<3 and not isinstance(exc,CalendarBlocked)
                    print(f'Calendário indisponível ({type(exc).__name__}); falha {calendar_errors}/3.',flush=True)
                else:
                    attempts+=capture.search_calls;calendar_search_calls+=capture.search_calls;calendar_queries+=capture.calendar_requests
                    calendar_entries+=len(capture.entries);calendar_routes+=1;calendar_status='available';calendar_errors=0
                    if capture.status!='completed':errors+=1;calendar_partial=True
                    store.request('calendar_jobs','POST',capture_record(capture,run['id']))
                    candidates=[v.query for v in best_candidates(capture.entries,min(3,budget-attempts))]
                    print(f'Calendário {task[0]}–{task[1]}: {len(capture.entries)} preços; {capture.search_calls} chamadas; {capture.status}.',flush=True)
                calendar_cursor=(calendar_cursor+1)%len(planner.calendar_tasks)
                checkpoint(True)
                if calendar_active and not candidates:
                    sleep(float(os.environ.get('QUERY_DELAY_SECONDS','1.5')));continue
            if not candidates:
                candidates=[planner.at(cursor)];cursor=(cursor+1)%planner.total
            for query in candidates:
                if attempts>=budget:break
                if query in seen:continue
                seen.add(query);attempts+=1;detail_queries+=1
                try:
                    offer=search(query,planner.destinations[query.destination],settings['max_stops'],proxy)
                    checked.add(query);consecutive=0
                except Exception as exc:
                    errors+=1;consecutive+=1;offer=None
                    print(f'Consulta {attempts}: {type(exc).__name__}',flush=True)
                # Infrastructure failures must fail the run, never be mistaken
                # for a provider outage or counted as successfully stored fares.
                if offer:store.save_offer(offer);found+=1
                checkpoint()
                if consecutive>=8:
                    reason='Circuito interrompido após 8 falhas consecutivas nas consultas detalhadas.';break
                sleep(float(os.environ.get('QUERY_DELAY_SECONDS','1.5')))
            if consecutive>=8:break
        if calendar_entries and calendar_partial:calendar_status='partial'
        complete=len(checked)==planner.total and errors==0
        status='failed' if detail_queries and not checked else('completed' if attempts>=budget and not errors else 'partial')
        message=reason or ('Rodada encerrada; descoberta de datas e validação detalhada são contadas separadamente.')
        if calendar_status=='unavailable':message+=' Calendário indisponível: busca detalhada utilizada automaticamente.'
        store.patch('scan_runs',run['id'],{**metrics(),'status':status,'finished_at':datetime.now(timezone.utc).isoformat(),'coverage_complete':complete,'message':message})
        cutoff=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()-90*86400,timezone.utc)
        store.request('fare_history','DELETE',params={'observed_at':'lt.'+cutoff.isoformat()},prefer='return=minimal')
        store.request('offers','DELETE',params={'return_date':'lt.'+planner.today.isoformat()},prefer='return=minimal')
        store.request('calendar_jobs','DELETE',prefer='return=minimal')
        print(f'Rodada {status}: {calendar_queries} calendários, {calendar_entries} preços de calendário, {detail_queries} consultas detalhadas, {found} tarifas.',flush=True)
        return 1 if status=='failed' else 0
    except Exception as exc:
        store.patch('scan_runs',run['id'],{**metrics(),'status':'failed','finished_at':datetime.now(timezone.utc).isoformat(),'message':f'Falha de infraestrutura: {type(exc).__name__}'})
        raise
    finally:
        if engine:engine.close()

if __name__=='__main__':
    sys.exit(run(Store(os.environ.get('SUPABASE_URL',''),os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))))
