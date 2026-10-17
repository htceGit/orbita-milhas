"""Deterministic, resumable planning; no network and no credential access."""
from __future__ import annotations
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from math import gcd,ceil
import json
import re

ORIGINS = ('CWB','JOI','NVT','FLN','VCP','GRU')
CALENDAR_DETAILS_PER_STAY = 5
CALENDAR_WINDOW_DAYS = 60

def calendar_calls(days:int,stays:int) -> int:
    return ceil(days/CALENDAR_WINDOW_DAYS)*(stays+1)

@dataclass(frozen=True)
class Search:
    origin: str
    destination: str
    departure: date
    returning: date

def months_after(day: date, count: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + count, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))

class Planner:
    def __init__(self, settings: dict, monitors: list[dict], today: date):
        low, high = int(settings['min_days']), int(settings['max_days'])
        horizon = int(settings['horizon_months'])
        if not 1 <= low <= high <= 60 or not 1 <= horizon <= 6:
            raise ValueError('Intervalo de datas inválido.')
        codes = settings['origins']
        if not codes or any(c not in ORIGINS for c in codes):
            raise ValueError('Origens inválidas.')
        routes = {}
        self.destinations = {d['code']:d for d in settings['destinations']}
        for origin in codes:
            for d in settings['destinations']:
                if d.get('enabled'):
                    routes.setdefault((origin,d['code']),set()).update(range(low,high+1))
        for m in monitors:
            if m.get('enabled') and m['origin'] in codes:
                if not 1<=m['min_days']<=m['max_days']<=60:
                    raise ValueError('Permanência do radar inválida.')
                routes.setdefault((m['origin'],m['destination']),set()).update(range(m['min_days'],m['max_days']+1))
                self.destinations.setdefault(m['destination'],{'code':m['destination'],'city':m['destination'],'country':'Internacional','region':'Outros'})
        if not routes:
            raise ValueError('Nenhuma rota ativa.')
        if any(not re.fullmatch(r'[A-Z]{3}', v) for route in routes for v in route):
            raise ValueError('Código de aeroporto inválido.')
        self.routes = sorted(routes)
        # The durable cursor addresses one route and one duration. Adjacent
        # durations may share browser pages without losing their own top five.
        self.calendar_tasks=[(a,b,n,n) for (a,b),stays in routes.items() for n in sorted(stays)]
        self.calendar_tasks.sort(key=lambda v:(sha256(f'{v[0]}:{v[1]}'.encode()).digest(),v[2]))
        self.lanes = [(a,b,n) for (a,b),stays in routes.items() for n in sorted(stays)]
        # Hash ordering distributes all regions and lengths through every batch.
        self.lanes.sort(key=lambda v:sha256(f'{v[0]}:{v[1]}:{v[2]}'.encode()).digest())
        self.today = today
        self.days = (months_after(today,horizon)-today).days
        self.total = len(self.lanes)*self.days
        step=max(1,int(self.days*.618))
        while gcd(step,self.days)!=1:
            step+=1
        self.step=step
        self.fingerprint=sha256(json.dumps({'calendar_plan':'browser-v2-top5-per-stay','lanes':self.lanes,'months':horizon,'stops':settings['max_stops']},sort_keys=True).encode()).hexdigest()

    def calendar_batch(self,cursor:int,budget:int,max_tasks:int|None=None):
        """Largest contiguous group that leaves room for every selected detail."""
        index=cursor%len(self.calendar_tasks)
        available=min(len(self.calendar_tasks)-index,max_tasks if max_tasks is not None else len(self.calendar_tasks))
        first=self.calendar_tasks[index];batch=None
        for count in range(1,available+1):
            task=self.calendar_tasks[index+count-1]
            if task[:2]!=first[:2] or task[2]!=first[2]+count-1:break
            reserve=min(CALENDAR_DETAILS_PER_STAY,self.days)*count
            if calendar_calls(self.days,count)+reserve>budget:break
            batch=(first[0],first[1],first[2],task[2])
        return batch

    def at(self,index:int) -> Search:
        index %= self.total
        # Adjacent queries explore different dates as well as different routes.
        lane_index=index % len(self.lanes)
        cycle=index // len(self.lanes)
        departure_offset=((cycle+lane_index)*self.step)%self.days+1
        a,b,stay=self.lanes[lane_index]
        departure=self.today+timedelta(days=departure_offset)
        return Search(a,b,departure,departure+timedelta(days=stay))

