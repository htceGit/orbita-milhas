"""Live local HTTP API integration test. Keeps its ephemeral token in memory."""
from datetime import date,timedelta
from threading import Thread
from time import sleep
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json
import os
import secrets
import uvicorn
from .api import app

def main():
    token=secrets.token_urlsafe(48);os.environ['CALENDAR_API_TOKEN']=token
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=4184,log_level='error',access_log=False))
    thread=Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            sleep(.1)
        if not server.started:raise RuntimeError('API não iniciou')
        url='http://127.0.0.1:4184/v1/calendar'
        body=json.dumps({'origin':'GRU','destination':'MIA','departure_start':str(date.today()+timedelta(days=30)),'departure_end':str(date.today()+timedelta(days=44)),'min_days':7,'max_days':8,'max_stops':2}).encode()
        try:urlopen(Request(url,data=body,headers={'Content-Type':'application/json'}),timeout=5)
        except HTTPError as exc:
            if exc.code!=401:raise
        else:raise AssertionError('A API aceitou uma requisição sem credencial')
        headers={'Content-Type':'application/json','Authorization':'Bearer '+token}
        with urlopen(Request(url,data=body,headers=headers),timeout=270) as response:result=json.load(response)
        assert result['priced_combinations']>0 and result['currency']=='BRL'
        if result['status']=='completed':
            with urlopen(Request(url,data=body,headers=headers),timeout=10) as response:assert json.load(response)['cached'] is True
        public={k:v for k,v in result.items() if k!='entries'};public['sample']=result['entries'][:3]
        print(json.dumps(public,ensure_ascii=False),flush=True)
    finally:server.should_exit=True;thread.join(10)

if __name__=='__main__':main()
