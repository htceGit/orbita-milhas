import base64
import json
import unittest
from datetime import date
from unittest.mock import Mock,patch
from types import SimpleNamespace as N
from worker.detail_parser import parse_detail_script,parse_detail_html
from worker.detail_worker import DetailWorker,serve
from worker.provider import normalize_cheapest,FastFlightsProvider
from worker.planner import Search
from worker.diagnostics import SearchFailure


def option(price=2500,currency='BRL',destination='MIA'):
 token=base64.urlsafe_b64encode(b'\x1a\x05\x1a\x03'+currency.encode()).decode()
 segment=[None]*21;segment[3]='FLN';segment[6]=destination;segment[20]=[2026,11,7]
 flight=[None,['LA'],[segment]]
 return [flight,[[None,price],token]]


def script(recommended=None,other=None):
 payload=[None,None,[recommended or []],[other or []]]
 return 'AF_initDataCallback({key:"ds:1",data:'+json.dumps(payload)+',sideChannel:{}});'


class DetailParserTests(unittest.TestCase):
 def test_recommended_cheaper_than_other_is_included_without_optional_fields(self):
  values=parse_detail_script(script([option(2500)],[option(6000)]))
  q=Search('FLN','MIA',date(2026,11,7),date(2026,11,17))
  fare=normalize_cheapest(values,q,{},'https://example.test',max_stops=2)
  self.assertEqual(fare['price_brl'],2500)
  self.assertEqual(fare['airlines'],['LA'])
  self.assertEqual(fare['carrier_validation'],'outbound_only')
 def test_bad_or_optional_rows_do_not_discard_valid_fares(self):
  broken=option(100);broken[0][2][0][20]=None
  disconnected=option(90);disconnected[0][2].append(option()[0][2][0])
  values=parse_detail_script(script([None,{},[None],option(True),option(900,'USD'),broken,disconnected,option()]))
  self.assertEqual(len(values),1)
  self.assertEqual(values[0].price,2500)
 def test_route_date_and_connections_are_checked_after_parse(self):
  values=parse_detail_script(script([option(90,destination='JFK'),option(2500)]))
  q=Search('FLN','MIA',date(2026,11,7),date(2026,11,17))
  self.assertEqual(normalize_cheapest(values,q,{},'url')['price_brl'],2500)
  wrong=Search('FLN','MIA',date(2026,11,8),date(2026,11,18))
  self.assertIsNone(normalize_cheapest(values,wrong,{},'url'))
  self.assertIsNone(normalize_cheapest(values,q,{},'url',max_stops=-1))
 def test_upstream_error_differs_from_valid_empty_data_or_missing_script(self):
  self.assertEqual(parse_detail_script(script()),[])
  with self.assertRaises(SearchFailure) as caught:parse_detail_script('data:[],errorHasStatus: true')
  self.assertEqual(caught.exception.code,'upstream_error')
  self.assertTrue(caught.exception.retryable)
  with self.assertRaises(SearchFailure) as caught:parse_detail_html('<html></html>')
  self.assertEqual(caught.exception.code,'parse_error')
  with self.assertRaises(SearchFailure):parse_detail_script('data:undefined,sideChannel:{}')
 def test_optional_metadata_is_safe_but_changed_fare_structure_is_reported(self):
  self.assertEqual(parse_detail_script('data:[null,null,[],null,null,null,null,[null,[7]]],sideChannel:{}'),[])
  with self.assertRaises(SearchFailure) as caught:parse_detail_script('data:[null,null,[8],null],sideChannel:{}')
  self.assertEqual(caught.exception.code,'parse_error')


class DetailWorkerTests(unittest.TestCase):
 def test_provider_reuses_the_http_client_between_searches(self):
  q=Search('FLN','MIA',date(2026,11,7),date(2026,11,17))
  with patch('primp.Client') as factory,patch('worker.detail_parser.parse_detail_html',return_value=[]):
   factory.return_value.get.return_value=N(status_code=200,text='',url='https://www.google.com/travel/flights')
   provider=FastFlightsProvider();provider.search(q,{});provider.search(q,{})
   self.assertEqual(factory.call_count,1);self.assertEqual(factory.return_value.get.call_count,2)
   provider.close();self.assertIsNone(provider.client)
 def test_serve_reuses_provider_for_success_and_error_then_closes(self):
  connection=Mock();connection.recv.side_effect=[('a',{}),('b',{}),('c',{}),None]
  with patch('worker.detail_worker.FastFlightsProvider') as factory:
   factory.return_value.search.side_effect=[{'price_brl':2500},SearchFailure('timeout','TimeoutError','Timeout',retryable=True),None]
   serve(connection,2,None)
   self.assertEqual(factory.call_count,1)
   self.assertEqual(factory.return_value.search.call_count,3)
   factory.return_value.close.assert_called_once()
  self.assertEqual([c.args[0][0] for c in connection.send.call_args_list],['ok','error','ok'])
  self.assertEqual(connection.send.call_args_list[1].args[0][1]['cause_type'],'TimeoutError')
 def test_deadline_restarts_before_next_query(self):
  connection=Mock();connection.poll.return_value=False
  process=Mock();process.is_alive.return_value=True
  worker=DetailWorker(.01);worker.process=process;worker.connection=connection;worker.key=(2,None)
  with self.assertRaises(SearchFailure) as caught:worker(None,{},2,None)
  self.assertEqual(caught.exception.code,'timeout');self.assertIsNone(worker.process)
  process.terminate.assert_called_once();process.kill.assert_called_once()
  connection.close.assert_called_once()
 def test_same_process_handles_multiple_queries(self):
  worker=DetailWorker();worker.connection=Mock();worker.process=Mock();worker.process.is_alive.return_value=True;worker.key=(2,None)
  worker.connection.recv.side_effect=[('ok',1),('ok',2)]
  self.assertEqual(worker('a',{},2,None),1);self.assertEqual(worker('b',{},2,None),2)
  self.assertEqual(worker.connection.send.call_count,2)
