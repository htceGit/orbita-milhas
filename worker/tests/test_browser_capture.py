"""Native picker contract: real request shapes, mocked browser/HTTP only."""
from contextlib import contextmanager
from datetime import date,timedelta
from types import SimpleNamespace as N
from unittest.mock import Mock
from urllib.parse import urlencode
import base64,json,unittest
from calendar_service.browser import BrowserCalendarEngine
from calendar_service.domain import CalendarQuery


def response(q,stay,failed=False):
 def leg(a,b):return [[[[a,0]]],[[[b,0]]],None,q.max_stops+1]
 settings=[None]*14;settings[2]=1;settings[5]=1;settings[6]=[1,0,0,0];settings[13]=[leg(q.origin,q.destination),leg(q.destination,q.origin)]
 request=N(post_data=urlencode({'f.req':json.dumps([None,json.dumps([None,settings,[str(q.departure_start),str(q.departure_end)],None,[stay,stay]])])}))
 token=base64.urlsafe_b64encode(b'\x1a\x05\x1a\x03BRL').decode()
 cells=[[str(q.departure_start),str(q.departure_start+timedelta(days=stay)),[[None,2500],token]]]
 frame=['wrb.fr',None,None,None,None,[13]] if failed else ['wrb.fr',None,json.dumps([None,cells])]
 return N(url='https://www.google.com/_/FlightsFrontendUi/data/travel.frontend.flights.FlightsFrontendService/GetCalendarPicker',status=200,request=request,text=lambda:")]}'\n"+json.dumps([frame]))


class PickerTests(unittest.TestCase):
 def test_one_failed_duration_preserves_other_durations_and_reuses_context(self):
  start=date.today()+timedelta(days=1);q=CalendarQuery('FLN','MIA',start,start+timedelta(days=3),7,10)
  page=Mock();page.url='https://www.google.com/travel/flights';page.locator.return_value.count.return_value=0
  page.goto.return_value=N(status=200)
  replies=iter([response(q,n,n==8) for n in range(7,11)])
  @contextmanager
  def waiting(predicate,**kwargs):
   r=next(replies);self.assertTrue(predicate(r));yield N(value=r)
  page.expect_response.side_effect=waiting
  engine=BrowserCalendarEngine();engine.browser=Mock();engine._start=Mock();engine.context=Mock();engine.context.new_page.return_value=page
  result=engine.capture(q)
  self.assertEqual(result.status,'partial')
  self.assertEqual(result.attempted_stays,[7,8,9,10])
  self.assertEqual(result.completed_sweeps,3)
  self.assertEqual(result.requested_sweeps,4)
  self.assertEqual(result.calendar_requests,4)
  self.assertEqual(result.search_calls,5)
  self.assertEqual({(v.query.returning-v.query.departure).days for v in result.entries},{7,9,10})
  self.assertEqual(result.diagnostic['code'],'upstream_error')
  page.goto.assert_called_once();page.close.assert_called_once()
  engine.browser.new_context.assert_not_called()
