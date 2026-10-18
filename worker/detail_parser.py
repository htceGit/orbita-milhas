"""Read essential public SSR fare fields without requiring optional emissions/time data."""
from datetime import date
from types import SimpleNamespace as N
import json
import math
import re
from .diagnostics import SearchFailure
from calendar_service.domain import price_currency


class DetailResults(list):
    metadata = None


def at(value,index,default=None):
    return value[index] if isinstance(value,list) and len(value)>index else default


def rows(value):return value if isinstance(value,list) else []


def parse_detail_html(html):
    from selectolax.lexbor import LexborHTMLParser
    tree=LexborHTMLParser(html)
    script=tree.css_first(r'script.ds\:1')
    if script is None:
        raise SearchFailure('parse_error','MissingFareData','A página não contém o bloco público de tarifas.')
    return parse_detail_script(script.text())


def parse_detail_script(script):
    if re.search(r'errorHasStatus\s*:\s*true',script):
        raise SearchFailure('upstream_error','FlightsNotFound','O Google retornou um erro de pesquisa.',retryable=True)
    marker=re.search(r'\bdata\s*:',script)
    if not marker:
        raise SearchFailure('parse_error','MissingFareData','Bloco de tarifas não identificado.')
    try:payload,_=json.JSONDecoder().raw_decode(script[marker.end():].lstrip())
    except (ValueError,TypeError) as exc:
        raise SearchFailure('parse_error','InvalidFareData','O bloco de tarifas não contém JSON válido.') from exc
    if not isinstance(payload,list) or len(payload)<4:
        raise SearchFailure('parse_error','ChangedFareData','A estrutura do bloco de tarifas mudou.')
    results=DetailResults();metadata=at(at(payload,7),1)
    results.metadata=N(airlines=[N(code=row[0],name=row[1]) for row in rows(at(metadata,1))
        if isinstance(row,list) and len(row)>1 and all(isinstance(v,str) for v in row[:2])])
    # Google separates recommended fares (2) and other options (3). Both matter.
    for index in (2,3):
        block=at(payload,index);options=at(block,0)
        if block is not None and not isinstance(block,list) or options is not None and not isinstance(options,list):
            raise SearchFailure('parse_error','ChangedFareData','A estrutura das opções de tarifas mudou.')
        for item in rows(options):
            flight=at(item,0);pricing=at(item,1);price=at(at(pricing,0),1)
            if isinstance(price,bool) or not isinstance(price,(float,int)) or not math.isfinite(price) or price<=0:continue
            if price_currency(at(pricing,1))!='BRL':continue
            airlines=at(flight,1);raw_segments=at(flight,2)
            if not isinstance(airlines,list) or not airlines or not all(isinstance(v,str) and v.strip() for v in airlines):continue
            if not isinstance(raw_segments,list) or not raw_segments:continue
            segments=[]
            for segment in raw_segments:
                origin,destination,day=at(segment,3),at(segment,6),at(segment,20)
                if not all(isinstance(v,str) and re.fullmatch('[A-Z]{3}',v) for v in (origin,destination)):break
                try:
                    if not isinstance(day,list) or len(day)!=3 or any(type(v) is not int for v in day):break
                    date(*day)
                except (TypeError,ValueError):break
                segments.append(N(from_airport=N(code=origin),to_airport=N(code=destination),departure=N(date=tuple(day))))
            if len(segments)!=len(raw_segments):continue
            if any(a.to_airport.code!=b.from_airport.code for a,b in zip(segments,segments[1:])):continue
            results.append(N(price=price,airlines=airlines,flights=segments))
    return results
