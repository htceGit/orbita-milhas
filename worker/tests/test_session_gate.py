import unittest
from datetime import datetime,timedelta,timezone
from worker.session_gate import session_decision,check_session,reconcile_run

class SessionGateTests(unittest.TestCase):
 def setUp(self):self.now=datetime(2026,10,17,21,0,tzinfo=timezone.utc)
 def finished(self,minutes,status='completed'):
  return {'status':status,'started_at':(self.now-timedelta(hours=1)).isoformat(),'finished_at':(self.now-timedelta(minutes=minutes)).isoformat()}
 def test_pause_is_measured_from_end_and_includes_partial_or_failed_sessions(self):
  for status in ['completed','partial','failed']:
   self.assertFalse(session_decision(self.finished(14,status),self.now)[0])
   self.assertTrue(session_decision(self.finished(15,status),self.now)[0])
 def test_running_session_blocks_another_but_stale_state_can_recover(self):
  running={'status':'running','started_at':(self.now-timedelta(hours=1)).isoformat(),'finished_at':None}
  self.assertFalse(session_decision(running,self.now)[0])
  running['started_at']=(self.now-timedelta(hours=4)).isoformat()
  self.assertTrue(session_decision(running,self.now)[0])
 def test_first_session_and_paused_motor(self):
  self.assertTrue(session_decision(None,self.now)[0])
  class Store:
   def request(self,table,**kwargs):
    if table!='scanner_settings':raise AssertionError('paused scanner should not query runs')
    return [{'enabled':False}]
  self.assertFalse(check_session(Store(),self.now)[0])
 def test_completed_workflow_closes_orphan_and_preserves_pause(self):
  latest={'id':'old','status':'running','started_at':(self.now-timedelta(minutes=10)).isoformat(),'workflow_url':'https://github.com/htceGit/orbita-milhas/actions/runs/123'}
  state={'status':'completed','path':'.github/workflows/scanner.yml','head_branch':'main','conclusion':'failure','updated_at':(self.now-timedelta(minutes=5)).isoformat()}
  class Store:
   def patch(self,*args):self.patch_data=args[-1]
  store=Store();closed=reconcile_run(store,latest,self.now,lambda _:state)
  self.assertEqual(closed['status'],'failed')
  self.assertFalse(session_decision(closed,self.now)[0])
  self.assertIn('último progresso salvo',store.patch_data['message'])
 def test_reconciliation_failure_or_active_workflow_cannot_unlock_session(self):
  latest={'id':'old','status':'running','started_at':(self.now-timedelta(minutes=10)).isoformat(),'workflow_url':'https://github.com/htceGit/orbita-milhas/actions/runs/123'}
  class Store:
   def patch(self,*args):raise AssertionError('must not mutate')
  def offline(_):raise OSError('offline')
  for fetch in (offline,lambda _:{'status':'in_progress'}):
   self.assertEqual(reconcile_run(Store(),latest,self.now,fetch),latest)
   self.assertFalse(session_decision(latest,self.now)[0])
 def test_preflight_rechecks_last_finished_session_and_allows_scan_after_rest(self):
  latest=self.finished(16)
  class Store:
   def request(self,table,**kwargs):return [{'enabled':True}] if table=='scanner_settings' else [latest]
  self.assertTrue(check_session(Store(),self.now)[0])
  latest['finished_at']=(self.now-timedelta(minutes=2)).isoformat()
  self.assertFalse(check_session(Store(),self.now)[0])

if __name__=='__main__':unittest.main()
