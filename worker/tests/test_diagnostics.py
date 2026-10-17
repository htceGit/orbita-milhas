import unittest
from unittest.mock import patch
from worker.diagnostics import SearchFailure,diagnose,safe_message
from worker.main import child_search,run
from worker.provider import parse_response
from worker.telemetry import TelemetryFailure
from calendar_service.domain import CalendarQuery,CalendarCapture,CalendarPrice,CalendarBlocked
from calendar_service.jobs import process_queued
from worker.planner import Search
from datetime import date,timedelta
from test_hybrid import FakeStore
class NoFlights(Exception):pass

class DiagnosticTests(unittest.TestCase):
 def test_original_cause_survives_child_process_boundary(self):
  class Connection:
   def send(self,value):self.value=value
   def close(self):pass
  connection=Connection()
  with patch('worker.main.FastFlightsProvider') as factory:
   factory.return_value.search.side_effect=IndexError('list index out of range')
   child_search(connection,None,{},2,None)
  kind,data=connection.value
  self.assertEqual(kind,'error');self.assertEqual(data['cause_type'],'IndexError')
  self.assertEqual(SearchFailure.from_diagnostic(data).code,'parse_error')
 def test_secrets_urls_emails_and_paths_are_removed(self):
  value=safe_message('Authorization: Bearer abc123 token=hidden password=secret https://example.test/?key=secret /Users/person/secrets.txt somebody@example.test')
  for secret in ['abc123','hidden','secret','example.test','/Users/person','somebody@']:self.assertNotIn(secret,value)
  self.assertNotIn('quoted secret',safe_message('{"token":"quoted secret"}'))
 def test_http_status_and_challenge_are_not_treated_as_parse_failures(self):
  for status,code in [(429,'rate_limited'),(403,'access_denied'),(503,'upstream_http')]:
   with self.assertRaises(SearchFailure) as context:parse_response(status,'','https://www.google.com',lambda _:[],Exception)
   self.assertEqual(context.exception.code,code);self.assertEqual(context.exception.http_status,status)
  with self.assertRaises(SearchFailure) as context:parse_response(200,'unusual traffic from your computer network','https://www.google.com',lambda _:[],Exception)
  self.assertEqual(context.exception.code,'challenge')
 def test_empty_valid_response_differs_from_upstream_error_and_parser_bug(self):
  self.assertEqual(parse_response(200,'valid','https://www.google.com',lambda _:[],NoFlights),[])
  def upstream(_):raise NoFlights('received error')
  with self.assertRaises(SearchFailure) as context:parse_response(200,'errorHasStatus: true','https://www.google.com',upstream,NoFlights)
  self.assertEqual(context.exception.code,'upstream_error')
  def broken(_):raise IndexError('missing field')
  with self.assertRaises(SearchFailure) as context:parse_response(200,'valid','https://www.google.com',broken,NoFlights)
  self.assertEqual(context.exception.cause_type,'IndexError');self.assertFalse(context.exception.retryable)

class RecoveryTests(unittest.TestCase):
 @patch.dict('os.environ',{'QUERY_DELAY_SECONDS':'0','RETRY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_retry_does_not_spend_reserved_second_candidate_call(self):
  store=FakeStore(4);calls=[]
  def calendar(a,b,start,end,low,high,stops,*args):
   q=CalendarQuery(a,b,start,end,low,high,stops)
   entries=[CalendarPrice(Search(a,b,start+timedelta(days=i),start+timedelta(days=i+low)),3000+i) for i in range(2)]
   return CalendarCapture(q,entries,search_calls=2,calendar_requests=1)
  def search(query,*args):
   calls.append(query)
   if len(calls)==1:raise SearchFailure('timeout','TimeoutError','Timeout',retryable=True)
   return None
  run(store,search=search,calendar_search=calendar)
  self.assertEqual(len(set(calls)),2)
  self.assertEqual(store.result['queries_attempted'],4)
  self.assertEqual(store.result['retries_count'],0)
 @patch.dict('os.environ',{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_partial_calendar_block_preserves_prices_and_stops_before_details(self):
  store=FakeStore(10)
  def calendar(a,b,start,end,low,high,stops,*args):
   q=CalendarQuery(a,b,start,end,low,high,stops)
   return CalendarCapture(q,[CalendarPrice(Search(a,b,start,start+timedelta(days=low)),3000)],status='partial',search_calls=2,calendar_requests=1,diagnostic=diagnose(CalendarBlocked('Limited',429)))
  def details(*args):self.fail('No details after a block')
  run(store,search=details,calendar_search=calendar)
  self.assertEqual(store.result['calendar_priced_combinations'],1)
  self.assertEqual(store.result['detail_queries'],0)
  self.assertEqual(store.result['error_counts'],{'rate_limited':1})
 @patch.dict('os.environ',{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_infrastructure_failure_is_not_retried_as_provider_failure(self):
  store=FakeStore(10);store.settings['search_strategy']='detailed'
  def search(*args):raise TelemetryFailure('Database unavailable')
  with self.assertRaises(TelemetryFailure):run(store,search=search,calendar_search=lambda *args:None)
  self.assertEqual(store.result['status'],'failed')
  self.assertEqual(store.result['retries_count'],0)
 def test_queued_calendar_block_leaves_remaining_jobs_untouched(self):
  q=CalendarQuery('GRU','MIA',date(2026,11,1),date(2026,11,5),7,7,2)
  class Store:
   def request(self,*args):return [{'id':str(i),'status':'queued','request':q.json()} for i in range(2)]
   def patch(self,*args):pass
  class Engine:
   calls=0
   def capture(self,*args,**kwargs):self.calls+=1;raise CalendarBlocked('Limited',429)
  engine=Engine();result=process_queued(Store(),engine,'run',100)
  self.assertEqual(engine.calls,1)
  self.assertEqual(result['diagnostics'][0]['code'],'rate_limited')
 @patch.dict('os.environ',{'QUERY_DELAY_SECONDS':'0','RETRY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_transient_error_retries_once_within_budget_and_preserves_diagnosis(self):
  store=FakeStore(3);store.settings['search_strategy']='detailed';calls=[]
  def search(query,*args):
   calls.append(query)
   if len(calls)==1:raise SearchFailure('network_error','ConnectionError','Connection reset',retryable=True)
   return None
  run(store,search=search,calendar_search=lambda *args:None)
  self.assertEqual(store.result['queries_attempted'],3)
  self.assertEqual(store.result['retries_count'],1)
  self.assertEqual(store.result['recovered_queries'],1)
  self.assertEqual(store.result['empty_results'],2)
  self.assertEqual(store.result['error_counts'],{'network_error':1})
  self.assertEqual(store.result['last_error']['cause_type'],'ConnectionError')
  self.assertEqual(store.result['status'],'completed')
 @patch.dict('os.environ',{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_explicit_block_stops_session_without_retries(self):
  store=FakeStore(1000);store.settings['search_strategy']='detailed'
  def blocked(*args):raise SearchFailure('rate_limited','HTTPError','HTTP 429',429)
  run(store,search=blocked,calendar_search=lambda *args:None)
  self.assertEqual(store.result['queries_attempted'],1)
  self.assertEqual(store.result['retries_count'],0)
  self.assertEqual(store.result['error_counts'],{'rate_limited':1})

if __name__=='__main__':unittest.main()
