import base64,gzip,json,unittest
from datetime import date,timedelta
from calendar_service.domain import CalendarQuery,CalendarCapture,CalendarPrice,price_currency
from calendar_service.jobs import capture_record
from worker.planner import Search

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
