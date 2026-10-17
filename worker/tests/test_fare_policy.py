import unittest
from unittest.mock import Mock
from worker.fare_policy import fare_cap,offer_allowed
from worker.storage import Store

class FarePolicyTests(unittest.TestCase):
 def test_caps_apply_to_cash_for_all_carriers_including_latam(self):
  for destination,cap in [('MIA',3000),('JFK',3000),('LIS',3500),('CDG',3500)]:
   for airlines in [['LA'],['AA'],['LA','AA'],['UNKNOWN']]:
    offer={'destination':destination,'airlines':airlines}
    self.assertTrue(offer_allowed({**offer,'price_brl':cap}))
    self.assertFalse(offer_allowed({**offer,'price_brl':cap+.01}))
  self.assertFalse(offer_allowed({'destination':'MIA','price_brl':4000,'airlines':['LA']}))

 def test_custom_destinations_use_country_or_region_and_other_regions_keep_behavior(self):
  self.assertEqual(fare_cap({'destination':'SFO','country':'Estados Unidos'}),3000)
  self.assertEqual(fare_cap({'destination':'AMS','region':'Europa'}),3500)
  self.assertEqual(fare_cap({'destination':'MIA','region':'Ásia'}),3000)
  self.assertEqual(fare_cap({'destination':' lis ','region':'EUA'}),3500)
  self.assertTrue(offer_allowed({'destination':'NRT','region':'Ásia','price_brl':9000}))
  for price in [None,True,0,-1,float('nan'),float('inf'),'2500']:
   self.assertFalse(offer_allowed({'destination':'MIA','price_brl':price}))

 def test_storage_does_not_write_rejected_offers_or_price_history(self):
  store=Store.__new__(Store);store.request=Mock(return_value=[{'id':'fare'}])
  self.assertFalse(store.save_offer({'destination':'MIA','price_brl':3000.01}))
  store.request.assert_not_called()
  self.assertTrue(store.save_offer({'destination':'MIA','price_brl':3000}))
  self.assertEqual([c.args[0] for c in store.request.call_args_list],['offers','fare_history'])
