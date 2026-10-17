"""Bounded batches of admin-only diagnostics and periodic progress snapshots."""
from datetime import datetime,timezone
from time import monotonic
from .diagnostics import safe_message

class TelemetryFailure(RuntimeError):pass

class SessionReporter:
    def __init__(self,store,run_id,clock=monotonic):
        self.store=store;self.run_id=run_id;self.clock=clock
        self.events=[];self.last_write=-100;self.phase=None;self.error_counts={};self.last_error=None
    def event(self,stage,outcome,query=None,diagnostic=None,attempt=1,duration_ms=None,message=None,context=None):
        row={'run_id':self.run_id,'stage':stage,'outcome':outcome,'attempt':attempt,'created_at':datetime.now(timezone.utc).isoformat()}
        # PostgREST bulk inserts require exactly the same keys in every row.
        row.update({key:None for key in ('origin','destination','departure_date','return_date','stay_days','duration_ms','error_code','cause_type','message','http_status')})
        row['retryable']=False
        if query:
            row.update(origin=query.origin,destination=query.destination,departure_date=str(query.departure),return_date=str(query.returning),stay_days=(query.returning-query.departure).days)
        elif context:
            row.update({key:context[key] for key in ('origin','destination','stay_days') if key in context})
        if duration_ms is not None:row['duration_ms']=min(20000000,max(0,round(duration_ms)))
        if diagnostic:
            row.update(error_code=diagnostic['code'],cause_type=diagnostic['cause_type'],message=safe_message(diagnostic['message']),http_status=diagnostic.get('http_status'),retryable=diagnostic.get('retryable',False))
            self.error_counts[diagnostic['code']]=self.error_counts.get(diagnostic['code'],0)+1
            self.last_error=diagnostic
        elif message:row['message']=safe_message(message)
        self.events.append(row)
        if len(self.events)>=50:self.flush_events()
    def flush_events(self):
        if self.events:
            try:self.store.request('scan_events','POST',self.events,prefer='return=minimal')
            except Exception as exc:raise TelemetryFailure('Falha ao persistir diagnóstico da sessão.') from exc
            self.events=[]
    def publish(self,metrics,phase,current=None,force=False):
        if force or phase!=self.phase or self.clock()-self.last_write>=15:
            self.flush_events()
            try:
                self.store.patch('scan_runs',self.run_id,{**metrics,'phase':phase,'current_query':current,
                    'heartbeat_at':datetime.now(timezone.utc).isoformat(),'error_counts':self.error_counts,'last_error':self.last_error})
            except Exception as exc:raise TelemetryFailure('Falha ao atualizar progresso da sessão.') from exc
            self.last_write=self.clock();self.phase=phase
