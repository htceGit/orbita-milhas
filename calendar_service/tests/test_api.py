from datetime import date,timedelta
from unittest.mock import patch
import unittest
from fastapi.testclient import TestClient
from calendar_service.api import create_app
from calendar_service.domain import CalendarCapture,CalendarPrice,CalendarUnavailable
from worker.planner import Search

class FakeEngine:
 calls=0
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def capture(self,q):
  FakeEngine.calls+=1
  return CalendarCapture(q,[CalendarPrice(Search(q.origin,q.destination,q.departure_start,q.departure_start+timedelta(days=q.min_days)),3000)],search_calls=2,calendar_requests=1)

class ApiTests(unittest.TestCase):
 @patch.dict('os.environ',{'CALENDAR_API_TOKEN':'test-token-'*4})
 def test_auth_validation_cache_and_response(self):
  FakeEngine.calls=0;client=TestClient(create_app(FakeEngine));headers={'Authorization':'Bearer '+'test-token-'*4}
  body={'origin':'GRU','destination':'MIA','departure_start':str(date.today()+timedelta(days=1)),'departure_end':str(date.today()+timedelta(days=10)),'min_days':7,'max_days':8}
  self.assertEqual(client.post('/v1/calendar',json=body).status_code,401)
  self.assertEqual(client.post('/v1/calendar',headers=headers,json={**body,'origin':'CGH'}).status_code,422)
  self.assertEqual(client.post('/v1/calendar',headers=headers,json={**body,'min_days':True}).status_code,422)
  first=client.post('/v1/calendar',headers=headers,json=body)
  self.assertEqual(first.status_code,200);self.assertFalse(first.json()['cached'])
  self.assertEqual(first.json()['entries'][0]['price_brl'],3000)
  self.assertTrue(client.post('/v1/calendar',headers=headers,json=body).json()['cached'])
  self.assertEqual(FakeEngine.calls,1)
 @patch.dict('os.environ',{'CALENDAR_API_TOKEN':'test-token-'*4})
 def test_provider_failure_is_503_not_empty_success(self):
  class Broken(FakeEngine):
   def capture(self,q):raise CalendarUnavailable('Google indisponível')
  client=TestClient(create_app(Broken));body={'origin':'GRU','destination':'MIA','departure_start':str(date.today()+timedelta(days=1)),'departure_end':str(date.today()+timedelta(days=2))}
  self.assertEqual(client.post('/v1/calendar',headers={'Authorization':'Bearer '+'test-token-'*4},json=body).status_code,503)

if __name__=='__main__':unittest.main()
