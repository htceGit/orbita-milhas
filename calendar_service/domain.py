"""Validated calendar contracts and parsers. No network or browser dependency."""
from dataclasses import dataclass,asdict,field
from datetime import date,datetime,timedelta,timezone
from math import isfinite
import base64
import json
import re
from worker.planner import Search,ORIGINS,months_after,calendar_calls,CALENDAR_DETAILS_PER_STAY

class CalendarUnavailable(RuntimeError):pass
class CalendarBlocked(CalendarUnavailable):pass

@dataclass(frozen=True)
class CalendarQuery:
    origin:str
    destination:str
    departure_start:date
    departure_end:date
    min_days:int=7
    max_days:int=20
    max_stops:int=2

    @classmethod
    def from_dict(cls,value,today=None):
        allowed={'origin','destination','departure_start','departure_end','min_days','max_days','max_stops'}
        if not isinstance(value,dict) or set(value)-allowed:raise ValueError('Parâmetros de calendário inválidos.')
        try:
            result=cls(**{**value,'departure_start':date.fromisoformat(value['departure_start']),'departure_end':date.fromisoformat(value['departure_end'])})
        except (KeyError,TypeError,ValueError):raise ValueError('Informe origem, destino e datas ISO válidas.') from None
        result.validate(today);return result

    def validate(self,today=None):
        today=today or datetime.now(timezone(timedelta(hours=-3))).date()
        if self.origin not in ORIGINS or not isinstance(self.destination,str) or not re.fullmatch(r'[A-Z]{3}',self.destination) or self.origin==self.destination:raise ValueError('Rota inválida.')
        if not today<self.departure_start<=self.departure_end<=months_after(today,6):raise ValueError('As saídas devem estar entre amanhã e seis meses à frente.')
        if any(type(v) is not int for v in (self.min_days,self.max_days,self.max_stops)):raise ValueError('Os limites devem ser inteiros.')
        if not 1<=self.min_days<=self.max_days<=60 or not 0<=self.max_stops<=2:raise ValueError('Permanência ou conexões inválidas.')

    def json(self):
        return {**asdict(self),'departure_start':str(self.departure_start),'departure_end':str(self.departure_end)}

    @property
    def days(self):return (self.departure_end-self.departure_start).days+1
    @property
    def estimated_calls(self):return calendar_calls(self.days,self.max_days-self.min_days+1)

    @property
    def detail_reserve(self):return min(CALENDAR_DETAILS_PER_STAY,self.days)*(self.max_days-self.min_days+1)

@dataclass(frozen=True)
class CalendarPrice:
    query:Search
    price:float

    def json(self):
        return {'origin':self.query.origin,'destination':self.query.destination,'departure_date':str(self.query.departure),'return_date':str(self.query.returning),'stay_days':(self.query.returning-self.query.departure).days,'price_brl':self.price,'currency':'BRL'}

@dataclass
class CalendarCapture:
    request:CalendarQuery
    entries:list[CalendarPrice]=field(default_factory=list)
    search_calls:int=0
    calendar_requests:int=0
    completed_sweeps:int=0
    status:str='completed'
    note:str=''
    collected_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat())

    def json(self):
        return {'request':self.request.json(),'status':self.status,'source':'google_flights_calendar','transport':'browser_ui',
            'currency':'BRL','collected_at':self.collected_at,'search_calls':self.search_calls,'calendar_requests':self.calendar_requests,
            'completed_sweeps':self.completed_sweeps,'requested_sweeps':self.request.max_days-self.request.min_days+1,
            'priced_combinations':len(self.entries),'total_combinations':self.request.days*(self.request.max_days-self.request.min_days+1),
            'note':self.note,'entries':[e.json() for e in sorted(self.entries,key=lambda e:e.price)]}

def _bytes_field(data,target):
    pos=0
    def varint():
        nonlocal pos
        value=shift=0
        while pos<len(data) and shift<70:
            byte=data[pos];pos+=1;value|=(byte&127)<<shift
            if byte<128:return value
            shift+=7
        raise ValueError('Protobuf inválido')
    while pos<len(data):
        tag=varint();wire=tag&7
        if wire==0:varint()
        elif wire==2:
            size=varint();value=data[pos:pos+size];pos+=size
            if len(value)!=size:raise ValueError('Protobuf truncado')
            if tag>>3==target:return value
        elif wire in (1,5):pos+=8 if wire==1 else 4
        else:raise ValueError('Wire type inválido')
    raise ValueError('Campo ausente')

def price_currency(token):
    try:
        token=token.replace('\\u003d','=');data=base64.urlsafe_b64decode(token+'='*(-len(token)%4))
        return _bytes_field(_bytes_field(data,3),3).decode('ascii')
    except (ValueError,TypeError,AttributeError,UnicodeError):return None

def parse_calendar(text,origin,destination,start,end,stay):
    valid=False;entries={}
    for line in text.removeprefix(")]}'").splitlines():
        try:frames=json.loads(line)
        except (ValueError,TypeError):continue
        if not isinstance(frames,list):continue
        for frame in frames:
            if not isinstance(frame,list) or len(frame)<3 or frame[0]!='wrb.fr' or not isinstance(frame[2],str):continue
            try:payload=json.loads(frame[2])
            except ValueError:continue
            if not isinstance(payload,list) or len(payload)<2 or not isinstance(payload[1],list):continue
            valid=True
            for cell in payload[1]:
                try:
                    departure=date.fromisoformat(cell[0]);returning=date.fromisoformat(cell[1])
                    price=cell[2][0][1]
                    if not start<=departure<=end or (returning-departure).days!=stay:continue
                    if isinstance(price,bool) or not isinstance(price,(float,int)) or not isfinite(price) or price<=0:continue
                    if price_currency(cell[2][1])!='BRL':continue
                    query=Search(origin,destination,departure,returning)
                    entries[query]=min(float(price),entries.get(query,float('inf')))
                except (ValueError,TypeError,IndexError,KeyError):continue
    if not valid:raise CalendarUnavailable('O Google não devolveu um calendário válido.')
    return [CalendarPrice(q,p) for q,p in entries.items()]

def best_candidates(entries,limit=3):return sorted(entries,key=lambda x:(x.price,x.query.departure))[:limit]

def best_candidates_per_stay(entries,limit=CALENDAR_DETAILS_PER_STAY):
    """Pick distinct dates across the entire capture, independently per stay."""
    unique={}
    for entry in entries:
        if entry.query not in unique or entry.price<unique[entry.query].price:unique[entry.query]=entry
    groups={}
    for entry in unique.values():
        q=entry.query;key=(q.origin,q.destination,(q.returning-q.departure).days)
        groups.setdefault(key,[]).append(entry)
    selected=[entry for group in groups.values() for entry in best_candidates(group,limit)]
    return sorted(selected,key=lambda x:(x.price,x.query.origin,x.query.destination,x.query.departure,x.query.returning))
