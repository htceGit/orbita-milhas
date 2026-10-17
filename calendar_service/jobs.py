"""Persist small summaries and compressed price arrays, without browser secrets."""
import base64
import gzip
import hashlib
import json
from datetime import datetime,timedelta,timezone
from .domain import CalendarQuery,best_candidates

def cache_key(query):return hashlib.sha256(json.dumps(query.json(),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def capture_record(capture,run_id=None,user_id=None):
    body=capture.json();entries=body.pop('entries')
    encoded=base64.b64encode(gzip.compress(json.dumps(entries,separators=(',',':')).encode(),mtime=0)).decode()
    return {'user_id':user_id,'run_id':run_id,'request':capture.request.json(),'cache_key':cache_key(capture.request),
        'status':capture.status,'result':body,'entries_gzip':encoded,
        'error':capture.note or None,'finished_at':datetime.now(timezone.utc).isoformat(),
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=4)).isoformat()}

def process_queued(store,engine,run_id,budget,proxy=None):
    used=prices=calendars=routes=errors=0;candidates=[];candidate_stops={}
    jobs=store.request('calendar_jobs') or []
    for job in jobs:
        if used>=budget:break
        if job['status']=='running':
            store.patch('calendar_jobs',job['id'],{'status':'failed','error':'A execução anterior foi interrompida. Solicite uma nova captura.','finished_at':datetime.now(timezone.utc).isoformat()});continue
        try:q=CalendarQuery.from_dict(job['request'])
        except ValueError as exc:
            store.patch('calendar_jobs',job['id'],{'status':'failed','error':str(exc),'finished_at':datetime.now(timezone.utc).isoformat()});continue
        if q.estimated_calls+len(candidates)+3>budget-used:break
        store.patch('calendar_jobs',job['id'],{'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'run_id':run_id})
        try:capture=engine.capture(q,max_search_calls=budget-used-len(candidates)-3,proxy=proxy)
        except Exception as exc:
            used+=max(1,getattr(exc,'search_calls',0));errors+=1
            store.patch('calendar_jobs',job['id'],{'status':'failed','error':str(exc)[:200] if isinstance(exc,ValueError) else 'O Google não devolveu um calendário válido.','finished_at':datetime.now(timezone.utc).isoformat()})
            continue
        if capture.status!='completed':errors+=1
        used+=capture.search_calls;prices+=len(capture.entries);calendars+=capture.calendar_requests;routes+=1
        store.patch('calendar_jobs',job['id'],capture_record(capture,run_id,job['user_id']))
        for value in best_candidates(capture.entries,3):
            candidates.append(value.query);candidate_stops[value.query]=q.max_stops
    return {'search_calls':used,'entries':prices,'calendars':calendars,'routes':routes,'errors':errors,'candidates':candidates,'candidate_stops':candidate_stops}
