"""Adapter pinned to fast-flights v3.1.0 (AWeirdDev/flights, MIT)."""
from datetime import datetime, timedelta, timezone
import math
from .planner import Search

class ProviderError(RuntimeError):
    pass

def normalize_cheapest(results, query: Search, metadata:dict, url:str, now=None):
    candidates=[]
    for item in results:
        # Never convert missing, unpriced or mixed-carrier results into a bargain.
        if not item.airlines or any(code!='LA' for code in item.airlines):
            continue
        if not isinstance(item.price,(int,float)) or isinstance(item.price,bool) or not math.isfinite(item.price) or item.price<=0:
            continue
        if not item.flights:
            continue
        if item.flights[0].from_airport.code!=query.origin or item.flights[-1].to_airport.code!=query.destination:
            continue
        if tuple(item.flights[0].departure.date)!=(query.departure.year,query.departure.month,query.departure.day):
            continue
        candidates.append(item)
    if not candidates:
        return None
    best=min(candidates,key=lambda x:x.price)
    now=now or datetime.now(timezone.utc)
    return {
        'origin':query.origin,'destination':query.destination,
        'city':metadata.get('city',query.destination),'country':metadata.get('country','Internacional'),
        'region':metadata.get('region','Outros'),'departure_date':query.departure.isoformat(),
        'return_date':query.returning.isoformat(),'price_brl':round(float(best.price),2),
        'airlines':['LA'],'stops':len(best.flights)-1,'booking_url':url,
        'provider':'fast_flights','source':'google_flights','fare_scope':'round_trip_search',
        # Google exposes outbound choices in this step with a ROUND-TRIP fare.
        # This does not attest the operating carrier of every return segment.
        'carrier_validation':'search_filter_and_outbound',
        'collected_at':now.isoformat(),'expires_at':(now+timedelta(hours=8)).isoformat(),
    }

class FastFlightsProvider:
    def __init__(self,max_stops=2,proxy=None):
        self.max_stops=max_stops
        self.proxy=proxy

    def search(self,query:Search,metadata:dict):
        from fast_flights import FlightQuery,Passengers,create_query,get_flights,FlightsNotFound
        q=create_query(flights=[
            FlightQuery(date=query.departure.isoformat(),from_airport=query.origin,to_airport=query.destination,airlines=['LA']),
            FlightQuery(date=query.returning.isoformat(),from_airport=query.destination,to_airport=query.origin,airlines=['LA'])
        ],seat='economy',trip='round-trip',passengers=Passengers(adults=1),currency='BRL',language='pt-BR',max_stops=self.max_stops,hide_separate_and_self_transfer=True)
        try:
            results=get_flights(q,proxy=self.proxy)
        except FlightsNotFound:
            return None
        except Exception as exc:
            # Do not include proxy credentials or request contents in logs.
            raise ProviderError(type(exc).__name__) from None
        return normalize_cheapest(results,query,metadata,q.url())

