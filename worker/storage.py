"""Supabase REST service adapter. The service key stays inside GitHub Secrets."""
import json
import os
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode

class Store:
    def __init__(self,url,key=None):
        if not url.startswith('https://'):
            raise ValueError('SUPABASE_URL é obrigatória.')
        self.url=url.rstrip('/')+'/rest/v1/'
        self.key=key
        self.edge=url.rstrip('/')+'/functions/v1/scan-api'
        self.token=None
        self.token_time=0
        if not key and not os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL'):
            raise ValueError('Execute pelo GitHub Actions com identidade OIDC, ou configure uma chave de serviço local.')

    def identity(self):
        if not self.token or time.monotonic()-self.token_time>180:
            endpoint=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
            endpoint+=('&' if '?' in endpoint else '?')+'audience=orbita-scanner'
            request=Request(endpoint,headers={'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
            with urlopen(request,timeout=30) as res:self.token=json.load(res)['value']
            self.token_time=time.monotonic()
        return self.token

    def request(self,table,method='GET',data=None,params=None,prefer='return=representation'):
        url=self.url+table+('?' + urlencode(params) if params else '')
        headers={'Content-Type':'application/json','Prefer':prefer}
        body=json.dumps(data).encode() if data is not None else None
        actual_method=method
        if self.key:
            headers.update({'apikey':self.key,'Authorization':'Bearer '+self.key})
        else:
            url=self.edge
            headers['Authorization']='Bearer '+self.identity()
            body=json.dumps({'table':table,'method':method,'data':data,'params':params or {}}).encode()
            actual_method='POST'
        for attempt in range(3):
            try:
                with urlopen(Request(url,data=body,headers=headers,method=actual_method),timeout=40) as res:
                    raw=res.read()
                    return json.loads(raw) if raw else None
            except HTTPError as exc:
                if exc.code not in(429,500,502,503,504) or attempt==2:
                    raise RuntimeError(f'Supabase {method} {table}: HTTP {exc.code}') from None
            except URLError:
                if attempt==2:
                    raise RuntimeError(f'Supabase {method} {table}: conexão indisponível') from None
            time.sleep(2**attempt)

    def read_all(self,table,params=None):
        items=[]
        offset=0
        while True:
            batch=self.request(table,params={**(params or {}),'limit':1000,'offset':offset})
            items.extend(batch)
            if len(batch)<1000:return items
            offset+=1000

    def patch(self,table,id,data):
        return self.request(table,'PATCH',data,{'id':'eq.'+str(id)})

    def save_offer(self,offer):
        row=self.request('offers','POST',offer,{'on_conflict':'origin,destination,departure_date,return_date'},'resolution=merge-duplicates,return=representation')[0]
        self.request('fare_history','POST',{'offer_id':row['id'],'price_brl':offer['price_brl']},prefer='return=minimal')

