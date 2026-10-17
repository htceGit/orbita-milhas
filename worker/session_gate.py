"""Cheap preflight: no browser installation or waiting runner during cooldown."""
from datetime import datetime,timedelta,timezone
from math import ceil
import os
from .storage import Store

SESSION_PAUSE_MINUTES=15
STALE_RUN_HOURS=4

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

def check_session(store,now=None):
    settings=store.request('scanner_settings',params={'id':'eq.1'})[0]
    if not settings['enabled']:return False,'Motor pausado pela administração.'
    latest=store.request('scan_runs',params={'order':'started_at.desc','limit':1})
    return session_decision(latest[0] if latest else None,now)

def main():
    allowed,reason=check_session(Store(os.environ.get('SUPABASE_URL',''),os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')))
    print(reason,flush=True)
    if output:=os.environ.get('GITHUB_OUTPUT'):
        with open(output,'a') as file:file.write(f'run_scan={str(allowed).lower()}\n')

if __name__=='__main__':main()
