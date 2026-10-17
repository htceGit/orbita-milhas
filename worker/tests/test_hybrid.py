import json
import os
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from worker.calendar import CalendarPrice,CalendarUnavailable,parse_calendar,best_candidates,best_candidates_per_stay
from calendar_service.domain import CalendarQuery,CalendarCapture
from calendar_service.jobs import capture_record
import base64,gzip
from worker.planner import Search
from worker.main import run

class CalendarTests(unittest.TestCase):
 def test_rpc_error_is_not_empty_success(self):
  with self.assertRaises(CalendarUnavailable):
   parse_calendar(')]}\'\n39\n[["wrb.fr",null,null,null,null,[13]]]', 'GRU','MIA',date.today(),date.today(),7)
 def test_candidates_require_valid_date_stay_price_and_deduplicate(self):
  start=date(2026,11,1);end=date(2026,11,30)
  cells=[['2026-11-02','2026-11-09',[[None,3500]]],['2026-11-02','2026-11-09',[[None,3000]]],
         ['2026-11-03','2026-11-10',[[None,2500]]],['2026-11-04','2026-11-12',[[None,1000]]],
         ['2026-12-02','2026-12-09',[[None,900]]],['2026-11-05','2026-11-12',[[None,True]]],
         ['2026-11-06','2026-11-13',[[None,0]]]]
  token=base64.urlsafe_b64encode(b'\x1a\x05\x1a\x03BRL').decode()
  for cell in cells:cell[2].append(token)
  text=")]}'\n"+json.dumps([['wrb.fr',None,json.dumps([None,cells])]])
  values=parse_calendar(text,'GRU','MIA',start,end,7)
  self.assertEqual([v.price for v in best_candidates(values)],[2500,3000])
  self.assertEqual(best_candidates(values,1)[0].query.departure,date(2026,11,3))
 def test_five_distinct_cheapest_dates_for_each_route_and_duration(self):
  entries=[];start=date(2026,10,18)
  for origin in ['FLN','GRU']:
   for stay in [10,11]:
    for offset in range(7):
     departure=start+timedelta(days=offset*25)
     entries.append(CalendarPrice(Search(origin,'MIA',departure,departure+timedelta(days=stay)),5000-offset*100+stay))
  # Repeated dates from overlapping windows cannot occupy two top-five slots.
  entries.append(CalendarPrice(entries[-1].query,1000))
  selected=best_candidates_per_stay(entries)
  self.assertEqual(len(selected),20)
  self.assertEqual(len({v.query for v in selected}),20)
  for origin in ['FLN','GRU']:
   for stay in [10,11]:
    group=[v for v in selected if v.query.origin==origin and (v.query.returning-v.query.departure).days==stay]
    self.assertEqual(len(group),5)
    self.assertEqual({(v.query.departure-start).days for v in group},{50,75,100,125,150})
  self.assertEqual(min(v.price for v in selected),1000)

class FakeStore:
 def __init__(self,budget=5):
  self.settings={'enabled':True,'origins':['GRU'],'destinations':[{'code':'MIA','enabled':True}],
    'min_days':7,'max_days':7,'horizon_months':1,'query_budget':budget,'search_mode':'rolling','search_strategy':'hybrid','max_stops':2}
  self.state={'cursor_position':0};self.result={};self.saved=[]
 def read_all(self,*a):return []
 def request(self,table,method='GET',data=None,**kw):
  if method=='DELETE':return None
  if table=='scanner_settings':return [self.settings]
  if table=='scanner_state':return [self.state]
  return [{'id':'run'}]
 def patch(self,table,id,data):
  (self.state if table=='scanner_state' else self.result).update(data)
 def save_offer(self,offer):self.saved.append(offer)

class HybridTests(unittest.TestCase):
 @patch.dict(os.environ,{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_rpc_failure_falls_back_and_preserves_budget(self):
  store=FakeStore(9);calls=[]
  def unavailable(*a):raise CalendarUnavailable('RPC')
  def details(query,*a):calls.append(query);return {'price_brl':3000,'airlines':['AA']}
  self.assertEqual(run(store,search=details,calendar_search=unavailable),0)
  self.assertEqual(store.result['queries_attempted'],9)
  self.assertEqual(store.result['calendar_search_calls'],1)
  self.assertEqual(store.result['detail_queries'],8)
  self.assertEqual(len(store.saved),8)
  self.assertEqual(store.result['calendar_status'],'unavailable')
  self.assertFalse(store.result['coverage_complete'])
  self.assertEqual(store.state['calendar_cursor'],0)
 @patch.dict(os.environ,{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_calendar_prices_are_not_published_without_details(self):
  store=FakeStore(7);calls=[]
  def calendar(a,b,start,end,low,high,stops,*args):
   entries=[CalendarPrice(Search(a,b,start+timedelta(days=i),start+timedelta(days=i+low)),p) for i,p in enumerate([4000,2000,3000])]
   return CalendarCapture(CalendarQuery(a,b,start,end,low,high,stops),entries,search_calls=1,calendar_requests=1)
  def details(query,*a):calls.append(query);return None
  run(store,search=details,calendar_search=calendar)
  self.assertEqual(store.result['queries_attempted'],4)
  self.assertEqual(store.result['calendar_entries'],3)
  self.assertEqual(store.result['detail_dates_checked'],3)
  self.assertEqual(store.saved,[])
  self.assertEqual(calls[0].departure,min(q.departure for q in calls)+timedelta(days=1))

 @patch.dict(os.environ,{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_validates_only_five_cheapest_per_duration_then_stops(self):
  store=FakeStore(60);store.settings['max_days']=8;calls=[]
  def calendar(a,b,start,end,low,high,stops,*args):
   query=CalendarQuery(a,b,start,end,low,high,stops)
   entries=[CalendarPrice(Search(a,b,start+timedelta(days=i),start+timedelta(days=i+stay)),4000-i*100+stay) for stay in range(low,high+1) for i in range(7)]
   self.assertEqual(args[-1],50,'reserves all ten detailed queries')
   return CalendarCapture(query,entries,search_calls=query.estimated_calls,calendar_requests=2)
  def details(query,*args):calls.append(query);return {'price_brl':3000}
  run(store,search=details,calendar_search=calendar)
  self.assertEqual(store.result['queries_attempted'],13)
  self.assertEqual(store.result['calendar_entries'],14)
  self.assertEqual(store.result['detail_queries'],10)
  self.assertEqual(len(store.saved),10)
  for stay in [7,8]:
   self.assertEqual(len([q for q in calls if (q.returning-q.departure).days==stay]),5)
  self.assertEqual(store.result['status'],'completed')

 @patch.dict(os.environ,{'QUERY_DELAY_SECONDS':'0','QUERY_BUDGET_OVERRIDE':'0'})
 def test_small_budget_resumes_next_duration_without_losing_selected_dates(self):
  store=FakeStore(7);store.settings['max_days']=8;calls=[];captures=[]
  def calendar(a,b,start,end,low,high,stops,*args):
   q=CalendarQuery(a,b,start,end,low,high,stops);captures.append((low,high))
   self.assertEqual(args[-1],2)
   entries=[CalendarPrice(Search(a,b,start+timedelta(days=i),start+timedelta(days=i+low)),4000-i*100) for i in range(7)]
   return CalendarCapture(q,entries,search_calls=2,calendar_requests=1)
  def details(query,*args):calls.append(query);return None
  for _ in range(2):
   run(store,search=details,calendar_search=calendar)
   self.assertEqual(store.result['queries_attempted'],7)
   self.assertEqual(store.result['detail_queries'],5)
  self.assertEqual(captures,[(7,7),(8,8)])
  self.assertEqual(len(set(calls)),10)
  self.assertEqual(store.state['calendar_cursor'],0)

if __name__=='__main__':unittest.main()
