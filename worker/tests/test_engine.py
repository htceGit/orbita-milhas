import unittest
from datetime import date,timedelta
from types import SimpleNamespace as N
from worker.planner import Planner,Search,months_after
from worker.provider import normalize_cheapest

def config():return {'origins':['FLN','GRU'],'destinations':[{'code':'MIA','city':'Miami','enabled':True},{'code':'NRT','enabled':False}],'min_days':7,'max_days':20,'horizon_months':6,'max_stops':2}
class PlannerTests(unittest.TestCase):
 def test_calendar_months(self):
  self.assertEqual(months_after(date(2026,8,31),6),date(2027,2,28))
  self.assertEqual(months_after(date(2023,8,31),6),date(2024,2,29))
 def test_exhaustive_matrix_no_duplicates_and_bounds(self):
  today=date(2026,10,17);p=Planner(config(),[],today)
  cells=[p.at(i) for i in range(p.total)]
  self.assertEqual(len(set(cells)),2*14*182)
  self.assertEqual(min(q.departure for q in cells),today+timedelta(days=1))
  self.assertEqual(max(q.departure for q in cells),date(2027,4,17))
  self.assertEqual({(q.returning-q.departure).days for q in cells},set(range(7,21)))
  self.assertTrue(all(q.destination=='MIA' for q in cells))
 def test_rolling_spreads_dates_and_resumes(self):
  p=Planner(config(),[],date(2026,10,17));batch=[p.at(i) for i in range(20)]
  self.assertGreater((max(q.departure for q in batch)-min(q.departure for q in batch)).days,140)
  self.assertEqual(p.at(p.total+3),p.at(3))
 def test_custom_monitors_and_deduplication(self):
  m={'origin':'FLN','destination':'MIA','min_days':7,'max_days':20,'enabled':True}
  self.assertEqual(Planner(config(),[m],date(2026,10,17)).total,Planner(config(),[],date(2026,10,17)).total)
  m['min_days']=25;m['max_days']=26
  p=Planner(config(),[m],date(2026,10,17))
  self.assertIn(('FLN','MIA',26),p.lanes)
  self.assertIn(('FLN','MIA',7,7),p.calendar_tasks)
  self.assertIn(('FLN','MIA',26,26),p.calendar_tasks)
  self.assertEqual(len(p.calendar_tasks),30)
 def test_calendar_batch_reserves_two_details_per_duration_and_resumes(self):
  p=Planner(config(),[],date(2026,10,17))
  self.assertIsNone(p.calendar_batch(0,9))
  self.assertEqual(p.calendar_batch(0,10)[2:],(7,7))
  self.assertEqual(p.calendar_batch(0,88)[2:],(7,20))
  first=p.calendar_batch(0,52)
  self.assertEqual(first[2:],(7,14))
  following=p.calendar_batch(8,52)
  self.assertEqual(following[2:],(15,20))
  self.assertEqual(first[:2],following[:2])
  self.assertEqual(p.calendar_batch(8,88,max_tasks=2)[2:],(15,16))
 def test_removed_origins_cannot_reenter_via_monitor(self):
  m={'origin':'IGU','destination':'MIA','min_days':7,'max_days':20,'enabled':True}
  self.assertNotIn(('IGU','MIA'),Planner(config(),[m],date.today()).routes)
  c=config();c['origins']=['CGH']
  with self.assertRaises(ValueError):Planner(c,[],date.today())
 def test_invalid_config(self):
  c=config();c['min_days']=21
  with self.assertRaises(ValueError):Planner(c,[],date.today())

class FareTests(unittest.TestCase):
 def setUp(self):self.q=Search('GRU','MIA',date(2026,11,20),date(2026,12,4))
 def fare(self,price,airlines=['LA']):return N(price=price,airlines=airlines,flights=[N(from_airport=N(code='GRU'),to_airport=N(code='MIA'),departure=N(date=(2026,11,20)))])
 def test_cheapest_real_positive_fare_any_airline(self):
  values=[self.fare(None),self.fare(0),self.fare(1500,['AA']),self.fare(1200,['LA','BA']),self.fare(float('nan')),self.fare(3500),self.fare(3200)]
  o=normalize_cheapest(values,self.q,{'city':'Miami'},'https://www.google.com/travel/flights')
  self.assertEqual(o['price_brl'],1200)
  self.assertEqual(o['airlines'],['BA','LA'])
  self.assertEqual(o['return_date'],'2026-12-04')
  self.assertNotIn('miles',o)
  self.assertEqual(o['fare_scope'],'round_trip_search')
 def test_reject_wrong_route_and_date(self):
  item=self.fare(1000);item.flights[0].to_airport.code='JFK'
  self.assertIsNone(normalize_cheapest([item],self.q,{},''))
  item=self.fare(1000);item.flights[0].departure.date=(2026,11,21)
  self.assertIsNone(normalize_cheapest([item],self.q,{},''))
 def test_no_results_does_not_create_offer(self):self.assertIsNone(normalize_cheapest([],self.q,{},''))
 def test_pypi_airline_names_and_mixed_carriers(self):
  values=[self.fare(3000,['LATAM']),self.fare(1000,['LATAM','American Airlines'])]
  o=normalize_cheapest(values,self.q,{},'')
  self.assertEqual(o['price_brl'],1000)
  self.assertEqual(o['airlines'],['AA','LA'])
  self.assertEqual(o['airline_names'],['LATAM','American Airlines'])
if __name__=='__main__':unittest.main()
