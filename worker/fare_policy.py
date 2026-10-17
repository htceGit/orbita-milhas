"""Cash round-trip caps, shared with the portal. LATAM estimates do not alter them."""
import json
import math
from pathlib import Path

POLICY = json.loads((Path(__file__).resolve().parent.parent / 'fare-policy.json').read_text())

def fare_cap(offer):
    region = (POLICY['destination_regions'].get(str(offer.get('destination', '')).strip().upper())
              or POLICY['country_regions'].get(str(offer.get('country', '')).strip().lower())
              or POLICY['region_names'].get(str(offer.get('region', '')).strip().lower()))
    return POLICY['caps'].get(region)

def offer_allowed(offer):
    price = offer.get('price_brl')
    cap = fare_cap(offer)
    return (isinstance(price, (float, int)) and not isinstance(price, bool)
            and math.isfinite(price) and price > 0 and (cap is None or price <= cap))
