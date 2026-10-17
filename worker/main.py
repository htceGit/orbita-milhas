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
from .calendar import CalendarProvider,best_candidates

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
    calendar_search=calendar_search or CalendarProvider().search
    run=store.request('scan_runs','POST',{'total_combinations':planner.total,'provider':'hybrid_calendar_fast_flights' if calendar_active else 'fast_flights','message':'Calendário para descobrir datas; consulta detalhada para confirmar tarifa e companhia.'})[0]
    attempts=found=errors=consecutive=calendar_queries=calendar_entries=detail_queries=0
    calendar_status='pending' if calendar_active else 'disabled'
    checked=set();started=clock();reason='';seen=set()
    proxy=os.environ.get('FLIGHTS_PROXY') or None
    def metrics():
        return {'queries_attempted':attempts,'offers_found':found,'errors_count':errors,
                'calendar_queries':calendar_queries,'calendar_entries':calendar_entries,
                'detail_queries':detail_queries,'detail_dates_checked':len(checked),'calendar_status':calendar_status}
    def checkpoint():
        store.patch('scanner_state',1,{'cursor_position':cursor,'calendar_cursor':calendar_cursor,
            'config_hash':planner.fingerprint,'anchor_date':planner.today.isoformat(),'last_run_id':run['id'],
            'updated_at':datetime.now(timezone.utc).isoformat()})
        # Keep the durable cursor after every call, but batch UI progress writes
        # to avoid spending the free Edge quota on redundant status updates.
        if attempts==1 or attempts%20==0:store.patch('scan_runs',run['id'],metrics())
    try:
        while attempts<budget:
            if clock()-started>3*3600:
                reason='Limite de 3 horas; a fila será retomada.';break
            candidates=[]
            if calendar_active and budget-attempts>=2:
                a,b,stay=planner.lanes[calendar_cursor%len(planner.lanes)]
                attempts+=1;calendar_queries+=1
                try:
                    entries=calendar_search(a,b,planner.today+timedelta(days=1),planner.today+timedelta(days=planner.days),stay,settings['max_stops'],proxy)
                    calendar_entries+=len(entries);calendar_status='available'
                    candidates=[v.query for v in best_candidates(entries,min(3,budget-attempts))]
                    calendar_cursor=(calendar_cursor+1)%len(planner.lanes)
                except Exception as exc:
                    errors+=1;calendar_status='unavailable';calendar_active=False
                    print(f'Calendário indisponível ({type(exc).__name__}); usando consultas detalhadas.',flush=True)
                checkpoint()
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
        complete=len(checked)==planner.total and errors==0
        status='failed' if detail_queries and not checked else('completed' if attempts>=budget and not errors else 'partial')
        message=reason or ('Rodada encerrada; descoberta de datas e validação detalhada são contadas separadamente.')
        if calendar_status=='unavailable':message+=' Calendário indisponível: busca detalhada utilizada automaticamente.'
        store.patch('scan_runs',run['id'],{**metrics(),'status':status,'finished_at':datetime.now(timezone.utc).isoformat(),'coverage_complete':complete,'message':message})
        cutoff=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()-90*86400,timezone.utc)
        store.request('fare_history','DELETE',params={'observed_at':'lt.'+cutoff.isoformat()},prefer='return=minimal')
        store.request('offers','DELETE',params={'return_date':'lt.'+planner.today.isoformat()},prefer='return=minimal')
        print(f'Rodada {status}: {calendar_queries} calendários, {calendar_entries} preços de calendário, {detail_queries} consultas detalhadas, {found} tarifas.',flush=True)
        return 1 if status=='failed' else 0
    except Exception as exc:
        store.patch('scan_runs',run['id'],{**metrics(),'status':'failed','finished_at':datetime.now(timezone.utc).isoformat(),'message':f'Falha de infraestrutura: {type(exc).__name__}'})
        raise

if __name__=='__main__':
    sys.exit(run(Store(os.environ.get('SUPABASE_URL',''),os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))))
