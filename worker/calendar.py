"""Calendar RPC protocol reference: licheng5625/google-flights,
d8962650dbcb79dd378d7ce92f41500e2ec8b024, fast_flights/calendar.py.
Local implementation with validation and timeouts. HTTP 200 RPC errors are
failures, never empty successful calendars. No third-party fork code is bundled.
"""
from dataclasses import dataclass
from datetime import date,timedelta
import json
import math
from .planner import Search

class CalendarUnavailable(RuntimeError):pass

@dataclass(frozen=True)
class CalendarPrice:
    query: Search
    price: float

def request_payload(origin,destination,start,end,stay,max_stops):
    def leg(a,b,day):
        return [[[[a,0]]],[[[b,0]]],None,max_stops+1,None,None,str(day),None,None,None,None,None,None,None,3]
    journey=[None,None,1,None,[],1,[1,0,0,0],None,None,None,None,None,None,
             [leg(origin,destination,start),leg(destination,origin,start+timedelta(days=stay))],
             None,None,None,1,None,None,None,None,None,[destination]]
    inner=[None,journey,[str(start),str(end)],None,[stay,stay]]
    return json.dumps([None,json.dumps(inner,separators=(',',':'))],separators=(',',':'))

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
                    if isinstance(price,bool) or not isinstance(price,(float,int)) or not math.isfinite(price) or price<=0:continue
                    query=Search(origin,destination,departure,returning)
                    entries[query]=min(price,entries.get(query,math.inf))
                except (ValueError,TypeError,IndexError,KeyError):continue
    if not valid:raise CalendarUnavailable('Calendário sem payload válido (bloqueio ou erro RPC).')
    return [CalendarPrice(q,p) for q,p in entries.items()]

def best_candidates(entries,limit=3):
    return sorted(entries,key=lambda x:(x.price,x.query.departure))[:limit]

class CalendarProvider:
    def search(self,origin,destination,start,end,stay,max_stops,proxy=None):
        from curl_cffi import requests
        url='https://www.google.com/_/FlightsFrontendUi/data/travel.frontend.flights.FlightsFrontendService/GetCalendarPicker'
        with requests.Session() as client:
            result=client.post(url,params={'hl':'pt-BR','gl':'BR','curr':'BRL','rt':'c'},
                data={'f.req':request_payload(origin,destination,start,end,stay,max_stops)},
                impersonate='chrome',timeout=30,proxy=proxy)
            if result.status_code!=200:raise CalendarUnavailable(f'Calendário HTTP {result.status_code}')
            return parse_calendar(result.text,origin,destination,start,end,stay)
