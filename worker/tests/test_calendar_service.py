import base64,gzip,json,unittest
from datetime import date,timedelta
from calendar_service.domain import CalendarQuery,CalendarCapture,CalendarPrice,price_currency
from calendar_service.jobs import capture_record
from worker.planner import Search
from calendar_service.browser import rpc_range
from calendar_service.domain import CalendarUnavailable
from types import SimpleNamespace
from urllib.parse import urlencode

class CalendarServiceTests(unittest.TestCase):
 def test_validates_dates_origins_bounds_and_unknown_fields(self):
  data={'origin':'GRU','destination':'MIA','departure_start':'2026-10-18','departure_end':'2027-04-17','min_days':7,'max_days':20}
  q=CalendarQuery.from_dict(data,today=date(2026,10,17));self.assertEqual(q.estimated_calls,60)
  for patch in [{'origin':'CGH'},{'departure_start':'2026-10-17'},{'departure_end':'2027-04-18'},{'max_days':True},{'url':'https://example.test'}]:
   with self.assertRaises(ValueError):CalendarQuery.from_dict({**data,**patch},today=date(2026,10,17))
 def test_currency_token_cannot_turn_dollars_into_reals(self):
  for value in ['BRL','USD','EUR']:
   token=base64.urlsafe_b64encode(b'\x1a\x05\x1a\x03'+value.encode()).decode()
   self.assertEqual(price_currency(token),value)
  self.assertIsNone(price_currency('invalid'))
 def test_compressed_capture_round_trips_without_raw_browser_tokens(self):
  q=CalendarQuery('GRU','MIA',date(2026,11,1),date(2026,11,3),7,7)
  entries=[CalendarPrice(Search('GRU','MIA',q.departure_start+timedelta(days=i),q.departure_start+timedelta(days=i+7)),3000+i) for i in range(3)]
  record=capture_record(CalendarCapture(q,entries))
  decoded=json.loads(gzip.decompress(base64.b64decode(record['entries_gzip'])))
  self.assertEqual(len(decoded),3);self.assertEqual(decoded[0]['currency'],'BRL')
  self.assertNotIn('token',json.dumps(record));self.assertEqual(len(record['cache_key']),64)

class CalendarContextTests(unittest.TestCase):
 def test_rejects_calendar_from_different_route_or_passenger_count(self):
  q=CalendarQuery('GRU','MIA',date(2026,11,1),date(2026,11,15),7,7)
  def leg(a,b):return [[[[a,0]]],[[[b,0]]],None,3]
  settings=[None]*19;settings[2]=1;settings[5]=1;settings[6]=[1,0,0,0];settings[13]=[leg('GRU','MIA'),leg('MIA','GRU')]
  def request():return SimpleNamespace(post_data=urlencode({'f.req':json.dumps([None,json.dumps([None,settings,['2026-11-01','2026-12-30'],None,[7,7]])])}))
  self.assertEqual(rpc_range(request(),q)[2],[7,7])
  settings[13][0]=leg('GRU','JFK')
  with self.assertRaises(CalendarUnavailable):rpc_range(request(),q)
  settings[13][0]=leg('GRU','MIA');settings[6]=[2,0,0,0]
  with self.assertRaises(CalendarUnavailable):rpc_range(request(),q)

class QueuedCaptureTests(unittest.TestCase):
 def test_queued_prices_are_forwarded_for_detailed_validation(self):
  from calendar_service.jobs import process_queued
  today=date.today();q=CalendarQuery('GRU','MIA',today+timedelta(days=1),today+timedelta(days=2),7,7,0)
  class Store:
   def __init__(self):self.updated={}
   def request(self,*args):return [{'id':'job','user_id':'owner','status':'queued','request':q.json()}]
   def patch(self,table,id,data):self.updated.update(data)
  class Engine:
   def capture(self,query,**kwargs):
    self.budget=kwargs['max_search_calls']
    return CalendarCapture(query,[CalendarPrice(Search('GRU','MIA',q.departure_start,q.departure_start+timedelta(days=7)),3000)],search_calls=2,calendar_requests=1)
  store=Store();engine=Engine();result=process_queued(store,engine,'run',5)
  self.assertEqual(len(result['candidates']),1)
  self.assertEqual(result['candidates'][0].origin,'GRU')
  self.assertEqual(result['candidate_stops'][result['candidates'][0]],0)
  self.assertEqual(engine.budget,2,'reserva orçamento para validar as melhores datas')
  self.assertEqual(store.updated['status'],'completed')
