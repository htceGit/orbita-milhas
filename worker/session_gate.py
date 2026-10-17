"""Cheap preflight: no browser installation or waiting runner during cooldown."""
from datetime import datetime,timedelta,timezone
from math import ceil
import os
import json
import re
from urllib.request import Request,urlopen
from .storage import Store

SESSION_PAUSE_MINUTES=15
STALE_RUN_HOURS=4

def workflow_state(run_id):
    request=Request(f'https://api.github.com/repos/htceGit/orbita-milhas/actions/runs/{run_id}',headers={'Accept':'application/vnd.github+json','User-Agent':'orbita-session-gate'})
    with urlopen(request,timeout=10) as response:return json.load(response)

def reconcile_run(store,latest,now,fetch=workflow_state):
    """Close orphaned records only after GitHub confirms their workflow ended."""
    if not latest or latest['status']!='running' or not latest.get('id'):return latest
    match=re.fullmatch(r'https://github\.com/htceGit/orbita-milhas/actions/runs/(\d+)',latest.get('workflow_url') or '',re.I)
    if not match:return latest
    started=datetime.fromisoformat(latest['started_at'].replace('Z','+00:00'))
    if now-started<timedelta(minutes=2):return latest
    try:
        state=fetch(match[1])
        if state.get('status')!='completed' or state.get('path')!='.github/workflows/scanner.yml' or state.get('head_branch')!='main':return latest
        if state.get('conclusion') not in ('success','failure','cancelled','timed_out','action_required','startup_failure','stale'):return latest
        finished=datetime.fromisoformat(state['updated_at'].replace('Z','+00:00'))
        if not started<=finished<=now:return latest
        patch={'status':'failed','phase':'failed','current_query':None,'finished_at':finished.isoformat(),
            'message':f'Encerramento reconciliado com GitHub Actions ({state["conclusion"]}). Os contadores refletem o último progresso salvo.'}
        store.patch('scan_runs',latest['id'],patch)
        print('Sessão anterior encerrada conforme o estado confirmado no GitHub Actions.',flush=True)
        return {**latest,**patch}
    except Exception:
        print('Não foi possível reconciliar a sessão anterior; mantido o bloqueio conservador.',flush=True)
        return latest

def session_decision(latest,now=None):
    now=now or datetime.now(timezone.utc)
    if not latest:return True,'Primeira sessão disponível.'
    if latest['status']=='running' or not latest.get('finished_at'):
        started=datetime.fromisoformat(latest['started_at'].replace('Z','+00:00'))
        if now-started<timedelta(hours=STALE_RUN_HOURS):
            return False,'Há uma sessão em andamento; esta verificação não inicia outra.'
        return True,'Sessão anterior sem encerramento há quatro horas; permitida a recuperação da fila.'
    finished=datetime.fromisoformat(latest['finished_at'].replace('Z','+00:00'))
    remaining=finished+timedelta(minutes=SESSION_PAUSE_MINUTES)-now
    if remaining.total_seconds()>0:
        return False,f'Pausa entre sessões: faltam {ceil(remaining.total_seconds()/60)} minutos. A próxima verificação tentará novamente.'
    return True,'Pausa mínima de 15 minutos concluída.'

def check_session(store,now=None,fetch_workflow=workflow_state):
    now=now or datetime.now(timezone.utc)
    settings=store.request('scanner_settings',params={'id':'eq.1'})[0]
    if not settings['enabled']:return False,'Motor pausado pela administração.'
    latest=store.request('scan_runs',params={'order':'started_at.desc','limit':1})
    return session_decision(reconcile_run(store,latest[0] if latest else None,now,fetch_workflow),now)

def main():
    allowed,reason=check_session(Store(os.environ.get('SUPABASE_URL',''),os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')))
    print(reason,flush=True)
    if output:=os.environ.get('GITHUB_OUTPUT'):
        with open(output,'a') as file:file.write(f'run_scan={str(allowed).lower()}\n')

if __name__=='__main__':main()
