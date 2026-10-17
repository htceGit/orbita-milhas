"""Continue after GitHub's environment wait timer, without an idle runner.
The job token is temporary, repository-scoped and never leaves GitHub.
"""
import json
import os
from time import sleep
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

REPOSITORY='htceGit/orbita-milhas'
ENVIRONMENT='scanner-pause-15m'

def dispatch_next(token,repository,ref,opener=urlopen,pause=sleep):
    if repository!=REPOSITORY or ref!='refs/heads/main':raise ValueError('Continuidade permitida apenas no repositório e branch principais.')
    if not token:raise ValueError('Identidade temporária do job ausente.')
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json','User-Agent':'orbita-session-continuation'}
    base='https://api.github.com/repos/'+REPOSITORY
    try:
        with opener(Request(base+'/environments/'+ENVIRONMENT,headers=headers),timeout=30) as response:environment=json.load(response)
    except HTTPError as exc:
        if exc.code!=403:raise
        # The public wait-timer metadata needs no secret or extra permissions.
        public_headers={key:value for key,value in headers.items() if key!='Authorization'}
        with opener(Request(base+'/environments/'+ENVIRONMENT,headers=public_headers),timeout=30) as response:environment=json.load(response)
    if not any(rule.get('type')=='wait_timer' and rule.get('wait_timer')==15 for rule in environment.get('protection_rules',[])):
        raise RuntimeError('Pausa nativa de 15 minutos ausente; continuidade bloqueada para evitar repetições sem espera.')
    body=json.dumps({'ref':'main','inputs':{'query_limit':'0','mode':'scan','trigger_source':'continuation'}}).encode()
    for attempt in range(3):
        try:
            with opener(Request(base+'/actions/workflows/scanner.yml/dispatches',data=body,headers=headers,method='POST'),timeout=30) as response:
                if response.status!=204:raise RuntimeError('O GitHub não confirmou o disparo da próxima sessão.')
            print('Próxima sessão solicitada automaticamente, com o orçamento configurado no portal.',flush=True)
            return
        except HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt==2:raise RuntimeError(f'Falha ao solicitar próxima sessão: HTTP {exc.code}.') from None
        except URLError:
            if attempt==2:raise RuntimeError('GitHub indisponível ao solicitar a próxima sessão.') from None
        pause(2**attempt)

if __name__=='__main__':dispatch_next(os.environ.get('GH_TOKEN',''),os.environ.get('GITHUB_REPOSITORY',''),os.environ.get('GITHUB_REF',''))
