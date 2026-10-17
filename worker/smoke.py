"""One live query, without persisting or inventing data. Manual integration QA."""
from datetime import date,timedelta
from .planner import Search
from .main import bounded_search
import json
if __name__=='__main__':
 day=date.today()+timedelta(days=35)
 q=Search('GRU','MIA',day,day+timedelta(days=14))
 try:
  result=bounded_search(q,{'city':'Miami','country':'Estados Unidos','region':'EUA'},2,None,45)
  print(json.dumps({'status':'fare_found' if result else'no_fares','offer':result},ensure_ascii=False))
 except Exception as exc:
  print(json.dumps({'status':'provider_error','kind':type(exc).__name__,'reason':str(exc)},ensure_ascii=False))
  raise SystemExit(1)
