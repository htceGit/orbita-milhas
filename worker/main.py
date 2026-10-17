"""Run via python -m worker.main. GitHub Actions schedules this every 4 hours."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from multiprocessing import get_context
from time import monotonic,sleep
import os
import sys
from .planner import Planner
from .storage import Store
from .provider import FastFlightsProvider

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

def run(store,search=bounded_search,clock=monotonic):
    settings=store.request('scanner_settings',params={'id':'eq.1'})[0]
    if not settings['enabled']:
        print('Motor pausado pela administração.')
        return 0
    # Active account check also prevents suspended customers from adding work.
    profiles=store.read_all('profiles',{'select':'id,plan,pro_until,role','status':'eq.active'})
    active={p['id'] for p in profiles}
    monitors=[m for m in store.read_all('monitors',{'enabled':'eq.true','order':'created_at.asc'}) if m['user_id'] in active]
    now=datetime.now(timezone.utc)
    limited=[]
    for p in profiles:
        until=datetime.fromisoformat(p['pro_until'].replace('Z','+00:00')) if p.get('pro_until') else None
        pro=p['role']=='admin' or p['plan']=='pro' and(not until or until>now)
        limited.extend([m for m in monitors if m['user_id']==p['id']][:(30 if pro else 3)])
    planner=Planner(settings,limited,datetime.now(ZoneInfo('America/Sao_Paulo')).date())
    state=store.request('scanner_state',params={'id':'eq.1'})[0]
    cursor=state['cursor_position'] if state.get('config_hash')==planner.fingerprint else 0
    if settings['search_mode']=='exhaustive':cursor=0
    budget=planner.total if settings['search_mode']=='exhaustive' else min(settings['query_budget'],planner.total)
    run=store.request('scan_runs','POST',{'total_combinations':planner.total,'message':f'Modo {settings["search_mode"]}; início da fila {cursor}.'})[0]
    attempts=found=errors=consecutive=0
    started=clock()
    reason=''
    try:
        for index in range(budget):
            if clock()-started>3*3600:
                reason='Interrompido no limite de 3 horas. A fila será retomada.';break
            query=planner.at(cursor+index)
            attempts+=1
            try:
                offer=search(query,planner.destinations[query.destination],settings['max_stops'],os.environ.get('FLIGHTS_PROXY') or None)
                if offer:store.save_offer(offer);found+=1
                consecutive=0
            except Exception as exc:
                errors+=1;consecutive+=1
                print(f'Consulta {attempts}: {type(exc).__name__}',flush=True)
            next_cursor=(cursor+attempts)%planner.total
            # Checkpoint after EVERY query. Failed cells are retried next cycle.
            store.patch('scanner_state',1,{'cursor_position':next_cursor,'config_hash':planner.fingerprint,'anchor_date':planner.today.isoformat(),'last_run_id':run['id'],'updated_at':datetime.now(timezone.utc).isoformat()})
            if attempts%20==0:
                store.patch('scan_runs',run['id'],{'queries_attempted':attempts,'offers_found':found,'errors_count':errors})
                print(f'{attempts}/{budget} consultas; {found} tarifas; {errors} falhas.',flush=True)
            if consecutive>=8:
                reason='Circuito interrompido após 8 falhas consecutivas no provedor.';break
            sleep(float(os.environ.get('QUERY_DELAY_SECONDS','1.5')))
        complete=attempts==planner.total and errors==0
        status='failed' if attempts and errors==attempts else('completed' if attempts==budget and not errors else 'partial')
        store.patch('scan_runs',run['id'],{'status':status,'finished_at':datetime.now(timezone.utc).isoformat(),'queries_attempted':attempts,'offers_found':found,'errors_count':errors,'coverage_complete':complete,'message':reason or('Cobertura integral.' if complete else'Rodada encerrada; cobertura parcial da matriz de datas e rotas.')})
        # Historical fares expire from the UI after 8 hours; bounded retention.
        cutoff=(datetime.now(timezone.utc).timestamp()-90*86400)
        store.request('fare_history','DELETE',params={'observed_at':'lt.'+datetime.fromtimestamp(cutoff,timezone.utc).isoformat()},prefer='return=minimal')
        store.request('offers','DELETE',params={'return_date':'lt.'+planner.today.isoformat()},prefer='return=minimal')
        print(f'Rodada {status}: {attempts}/{planner.total} combinações, {found} tarifas.',flush=True)
        return 1 if status=='failed' else 0
    except Exception as exc:
        store.patch('scan_runs',run['id'],{'status':'failed','finished_at':datetime.now(timezone.utc).isoformat(),'queries_attempted':attempts,'offers_found':found,'errors_count':errors,'message':f'Falha de infraestrutura: {type(exc).__name__}'})
        raise

if __name__=='__main__':
    sys.exit(run(Store(os.environ.get('SUPABASE_URL',''),os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))))
