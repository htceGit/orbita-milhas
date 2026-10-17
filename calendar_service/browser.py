"""Capture native Google Flights calendar responses in an isolated browser.
No saved Google account, stealth scripts, header forgery or CAPTCHA solver.
"""
from datetime import timedelta
from dataclasses import replace
from math import ceil
from time import monotonic,sleep
from urllib.parse import parse_qs,urlparse
import json
import os
from .domain import CalendarQuery,CalendarCapture,CalendarUnavailable,CalendarBlocked,parse_calendar
from worker.diagnostics import SearchFailure,diagnose
from worker.telemetry import TelemetryFailure


def calendar_rpc(url):
    parsed=urlparse(url)
    return parsed.hostname=='www.google.com' and 'FlightsFrontendService/GetCalendar' in parsed.path


def ensure_calendar_response(response):
    if not response:return
    if response.status in (403,429):raise CalendarBlocked('O Google limitou a captura. Aguarde a próxima rodada.',response.status)
    if response.status>=400:raise SearchFailure('upstream_http','HTTPError',f'Calendário HTTP {response.status}',response.status,response.status in (500,502,503,504))


def rpc_range(request,expected=None):
    try:
        form=parse_qs(request.post_data or '');outer=json.loads(form['f.req'][0]);inner=json.loads(outer[1])
        if expected:
            settings=inner[1];legs=settings[13]
            source=lambda leg:leg[0][0][0][0]
            destination=lambda leg:leg[1][0][0][0]
            if settings[2]!=1 or settings[5]!=1 or settings[6]!=[1,0,0,0] or len(legs)!=2 or source(legs[0])!=expected.origin or destination(legs[0])!=expected.destination or source(legs[1])!=expected.destination or destination(legs[1])!=expected.origin or any(leg[3]!=expected.max_stops+1 for leg in legs):
                raise ValueError('Contexto da pesquisa divergente')
        from datetime import date
        return date.fromisoformat(inner[2][0]),date.fromisoformat(inner[2][1]),inner[4]
    except (ValueError,KeyError,IndexError,TypeError):raise CalendarUnavailable('Formato de requisição do calendário mudou.') from None


def search_url(query,anchor):
    from fast_flights import FlightQuery,Passengers,create_query
    q=create_query(flights=[FlightQuery(date=str(anchor),from_airport=query.origin,to_airport=query.destination),
        FlightQuery(date=str(anchor+timedelta(days=query.min_days)),from_airport=query.destination,to_airport=query.origin)],
        seat='economy',trip='round-trip',passengers=Passengers(adults=1),currency='BRL',language='en',max_stops=query.max_stops,hide_separate_and_self_transfer=True)
    return q.url()+'&gl=BR'

class BrowserCalendarEngine:
    def __init__(self):self.playwright=self.browser=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        try:
            if self.browser:self.browser.close()
        finally:
            if self.playwright:self.playwright.stop()
            self.browser=self.playwright=None
    def _start(self,proxy=None):
        if self.browser:return
        from playwright.sync_api import sync_playwright
        self.playwright=sync_playwright().start()
        options={'headless':os.environ.get('CALENDAR_HEADLESS','true').lower()!='false'}
        if os.environ.get('CALENDAR_BROWSER_CHANNEL'):options['channel']=os.environ['CALENDAR_BROWSER_CHANNEL']
        if proxy:
            parts=urlparse(proxy)
            if parts.scheme not in ('http','https','socks5') or not parts.hostname:raise ValueError('Proxy inválido')
            options['proxy']={'server':f'{parts.scheme}://{parts.hostname}:{parts.port or 8080}'}
            if parts.username:options['proxy'].update(username=parts.username,password=parts.password or '')
        self.browser=self.playwright.chromium.launch(**options)

    def capture(self,query:CalendarQuery,max_search_calls=None,proxy=None,timeout_seconds=None,progress=None):
        query.validate();self._start(proxy)
        timeout_seconds=timeout_seconds if timeout_seconds is not None else max(240,min(900,query.estimated_calls*8))
        capture=CalendarCapture(query);values={};started=monotonic()
        budget=max_search_calls or query.estimated_calls+2*ceil(query.days/60)
        context=self.browser.new_context(locale='en-US',timezone_id='America/Sao_Paulo',viewport={'width':1280,'height':900})
        page=context.new_page();page.set_default_timeout(20000)
        current={'origin':query.origin,'destination':query.destination,'min_days':query.min_days,'max_days':query.max_days}
        def report():
            if progress:progress({'search_calls':capture.search_calls,'calendar_requests':capture.calendar_requests,'prices':tuple(values.values()),'current':dict(current)})
        def guard():
            if 'consent.google.com' in page.url:raise SearchFailure('consent_required','ConsentRequired','A pesquisa direcionou para uma página de consentimento.')
            if '/sorry/' in page.url or page.locator('iframe[src*="recaptcha"]').count():raise CalendarBlocked('O Google solicitou verificação humana. A captura foi interrompida.')
            if monotonic()-started>timeout_seconds:raise CalendarUnavailable('Limite de tempo da captura atingido.')
            if capture.search_calls>=budget:raise CalendarUnavailable('Orçamento de consultas atingido durante a captura.')
        def step(action,stay):
            guard();capture.search_calls+=1;capture.calendar_requests+=1
            current['stay_days']=stay;report()
            with page.expect_response(lambda r:calendar_rpc(r.url),timeout=25000) as waiting:action()
            response=waiting.value
            ensure_calendar_response(response)
            if response.status!=200:raise CalendarUnavailable(f'Calendário HTTP {response.status}')
            first,last,durations=rpc_range(response.request,query)
            if durations!=[stay,stay]:raise CalendarUnavailable('A duração retornada difere da duração solicitada.')
            for entry in parse_calendar(response.text(),query.origin,query.destination,query.departure_start,query.departure_end,stay):
                values[entry.query]=entry
            report()
            return first,last
        try:
            guard();capture.search_calls+=1
            report()
            # The native graph starts seven days before the selected departure.
            anchor=min(query.departure_start+timedelta(days=7),query.departure_end)
            response=page.goto(search_url(query,anchor),wait_until='domcontentloaded',timeout=45000)
            ensure_calendar_response(response)
            guard()
            # SSR buttons can be replaced during hydration. The currency control
            # gets its accessible name after the page is interactive.
            page.get_by_role('button',name='Currency BRL',exact=True).wait_for(timeout=25000)
            windows=[(query.departure_start+timedelta(days=i),min(query.departure_end,query.departure_start+timedelta(days=i+59))) for i in range(0,query.days,60)]
            finished={stay:0 for stay in range(query.min_days,query.max_days+1)}
            # Reloading each 60-day window is more predictable than the native
            # arrows, which request small, overlapping tails of the chart.
            for index,(window_start,window_end) in enumerate(windows):
                current.update(departure_start=str(window_start),departure_end=str(window_end))
                if index:
                    guard();capture.search_calls+=1
                    report()
                    anchor=min(window_start+timedelta(days=7),window_end)
                    ensure_calendar_response(page.goto(search_url(query,anchor),wait_until='domcontentloaded',timeout=45000))
                    page.get_by_role('button',name='Currency BRL',exact=True).wait_for(timeout=25000)
                try:page.wait_for_load_state('networkidle',timeout=10000)
                except Exception:pass
                sleep(float(os.environ.get('CALENDAR_DELAY_SECONDS','2')))
                retried=False
                for stay in range(query.min_days,query.max_days+1):
                    if stay==query.min_days:action=lambda:page.get_by_role('button',name='Price graph',exact=True).click()
                    else:action=lambda:page.get_by_role('button',name='Extend your stay by one day',exact=True).click()
                    try:first,last=step(action,stay)
                    except (CalendarBlocked,TelemetryFailure):raise
                    except Exception:
                        if retried or budget-capture.search_calls<2:raise
                        # One fresh native page per window, after a pause. A
                        # repeated failure remains partial; no retry loop.
                        retried=True;sleep(3);guard();capture.search_calls+=1
                        report()
                        ensure_calendar_response(page.goto(search_url(replace(query,min_days=stay,max_days=stay),anchor),wait_until='domcontentloaded',timeout=45000))
                        page.get_by_role('button',name='Currency BRL',exact=True).wait_for(timeout=25000)
                        try:page.wait_for_load_state('networkidle',timeout=10000)
                        except Exception:pass
                        sleep(float(os.environ.get('CALENDAR_DELAY_SECONDS','2')))
                        first,last=step(lambda:page.get_by_role('button',name='Price graph',exact=True).click(),stay)
                    if first>window_start or last<window_end:raise CalendarUnavailable('A janela retornada não cobre as datas solicitadas.')
                    finished[stay]+=1
                    capture.completed_sweeps=sum(count==len(windows) for count in finished.values())
                    sleep(float(os.environ.get('CALENDAR_DELAY_SECONDS','2')))
        except TelemetryFailure:raise
        except Exception as exc:
            capture.status='partial' if values else 'failed'
            capture.diagnostic=diagnose(exc)
            capture.note=str(exc) if isinstance(exc,CalendarUnavailable) else f'Falha de captura: {type(exc).__name__}'
            if not values:
                error=(CalendarBlocked if isinstance(exc,CalendarBlocked) else CalendarUnavailable)(capture.note);error.search_calls=capture.search_calls;error.diagnostic=capture.diagnostic;raise error from exc
        finally:context.close()
        capture.entries=list(values.values())
        return capture
