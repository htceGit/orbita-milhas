"""Private synchronous API: uvicorn calendar_service.api:app --host 127.0.0.1."""
from datetime import date
from threading import Lock
from time import monotonic
from secrets import compare_digest
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import asyncio
import os
from fastapi import FastAPI,Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel,ConfigDict,StrictInt
from .browser import BrowserCalendarEngine
from .domain import CalendarQuery,CalendarUnavailable

class CalendarRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    origin:str
    destination:str
    departure_start:date
    departure_end:date
    min_days:StrictInt=7
    max_days:StrictInt=20
    max_stops:StrictInt=2

bearer=HTTPBearer(auto_error=False)
def authorize(credentials:HTTPAuthorizationCredentials=Depends(bearer)):
    token=os.environ.get('CALENDAR_API_TOKEN','')
    if len(token)<32:raise HTTPException(503,'Configure CALENDAR_API_TOKEN com pelo menos 32 caracteres.')
    if not credentials or not compare_digest(credentials.credentials,token):raise HTTPException(401,'Credencial inválida.',headers={'WWW-Authenticate':'Bearer'})


def create_app(engine_factory=BrowserCalendarEngine):
    # Playwright objects must be created, used and closed on the same thread.
    # HTTP request threads only submit work; one dedicated thread owns Chromium.
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='orbita-browser');holder=[];last_used=[monotonic()]
    busy=Lock();cache={}
    def close_engine():
        if holder:holder.pop().close()
    def capture(q):
        if not holder:holder.append(engine_factory())
        try:return holder[0].capture(q)
        except Exception:
            close_engine();raise
        finally:last_used[0]=monotonic()
    async def release_idle_browser():
        while True:
            await asyncio.sleep(30)
            if monotonic()-last_used[0]<300 or not busy.acquire(blocking=False):continue
            try:await asyncio.wrap_future(executor.submit(close_engine))
            finally:busy.release()
    @asynccontextmanager
    async def lifespan(app):
        cleanup=asyncio.create_task(release_idle_browser())
        try:yield
        finally:
            cleanup.cancel()
            try:await cleanup
            except asyncio.CancelledError:pass
            executor.submit(close_engine).result();executor.shutdown(wait=True)
    app=FastAPI(title='Órbita Calendar API',version='2.0.0',lifespan=lifespan,description='Captura própria do calendário público do Google Flights. Os preços não confirmam companhia ou resgate com milhas.')
    @app.get('/health')
    def health():return {'status':'ok','service':'orbita-calendar','version':'2.0.0'}
    @app.post('/v1/calendar',dependencies=[Depends(authorize)])
    def calendar(payload:CalendarRequest):
        try:q=CalendarQuery.from_dict(payload.model_dump(mode='json'))
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        key=tuple(q.json().values())
        if not busy.acquire(blocking=False):raise HTTPException(429,'Captura em andamento. Tente novamente depois.',headers={'Retry-After':'60'})
        try:
            cached=cache.get(key)
            if cached and monotonic()-cached[0]<14400:return {**cached[1],'cached':True}
            result=executor.submit(capture,q).result()
            body=result.json()
            if result.status=='completed':
                cache[key]=(monotonic(),body)
                while len(cache)>32:cache.pop(next(iter(cache)))
            return {**body,'cached':False}
        except CalendarUnavailable as exc:raise HTTPException(503,str(exc)) from None
        finally:busy.release()
    return app

app=create_app()
