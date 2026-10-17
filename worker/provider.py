"""Detailed Google Flights adapter pinned to fast-flights 3.1.0 (MIT)."""
from datetime import datetime, timedelta, timezone
import math
from .planner import Search

class ProviderError(RuntimeError):
    pass

AIRLINES = {'LA':'LATAM','AA':'American Airlines','UA':'United Airlines','DL':'Delta Air Lines',
            'TP':'TAP Air Portugal','AF':'Air France','KL':'KLM','IB':'Iberia','BA':'British Airways',
            'LH':'Lufthansa','LX':'SWISS','CM':'Copa Airlines','AV':'Avianca','AD':'Azul',
            'G3':'GOL','TK':'Turkish Airlines','QR':'Qatar Airways','EK':'Emirates','ET':'Ethiopian Airlines'}

def normalize_cheapest(results, query: Search, metadata:dict, url:str, now=None, airline_metadata=()):
    names = dict(AIRLINES)
    names.update({a.code:a.name for a in airline_metadata if a.code and a.name})
    codes = {name.casefold():code for code,name in names.items()}
    codes.update({'latam airlines':'LA','latam':'LA'})
    candidates=[]
    for item in results:
        if not item.airlines or any(not isinstance(a,str) or not a.strip() for a in item.airlines):continue
        if not isinstance(item.price,(int,float)) or isinstance(item.price,bool) or not math.isfinite(item.price) or item.price<=0:continue
        if not item.flights:continue
        if item.flights[0].from_airport.code!=query.origin or item.flights[-1].to_airport.code!=query.destination:continue
        if tuple(item.flights[0].departure.date)!=(query.departure.year,query.departure.month,query.departure.day):continue
        candidates.append(item)
    if not candidates:return None
    best=min(candidates,key=lambda x:x.price)
    carriers=sorted({a if a in names else codes.get(a.casefold(),'UNKNOWN') for a in best.airlines})
    labels=list(dict.fromkeys(names.get(a,a) for a in best.airlines))
    now=now or datetime.now(timezone.utc)
    return {
        'origin':query.origin,'destination':query.destination,
        'city':metadata.get('city',query.destination),'country':metadata.get('country','Internacional'),
        'region':metadata.get('region','Outros'),'departure_date':query.departure.isoformat(),
        'return_date':query.returning.isoformat(),'price_brl':round(float(best.price),2),
        'airlines':carriers,'airline_names':labels,'stops':len(best.flights)-1,'booking_url':url,
        'provider':'fast_flights','source':'google_flights','fare_scope':'round_trip_search',
        # Outbound carriers only; return segments and awards need confirmation.
        'carrier_validation':'outbound_only',
        'collected_at':now.isoformat(),'expires_at':(now+timedelta(hours=8)).isoformat(),
    }

class FastFlightsProvider:
    def __init__(self,max_stops=2,proxy=None):
        self.max_stops=max_stops;self.proxy=proxy

    def search(self,query:Search,metadata:dict):
        from fast_flights import FlightQuery,Passengers,create_query,get_flights,FlightsNotFound
        q=create_query(flights=[
            FlightQuery(date=query.departure.isoformat(),from_airport=query.origin,to_airport=query.destination),
            FlightQuery(date=query.returning.isoformat(),from_airport=query.destination,to_airport=query.origin)
        ],seat='economy',trip='round-trip',passengers=Passengers(adults=1),currency='BRL',language='pt-BR',max_stops=self.max_stops,hide_separate_and_self_transfer=True)
        try:results=get_flights(q,proxy=self.proxy)
        except FlightsNotFound:return None
        except Exception as exc:raise ProviderError(type(exc).__name__) from None
        return normalize_cheapest(results,query,metadata,q.url(),airline_metadata=getattr(getattr(results,'metadata',None),'airlines',[]))
