"""Small, serializable diagnostics. Never persist response bodies or secrets."""
import re

def safe_message(value,limit=350):
    text=str(value)
    if re.search(r'<!doctype|<html',text,re.I):return 'Resposta HTML não interpretável.'
    text=re.sub(r'https?://\S+','[URL removida]',text,flags=re.I)
    text=re.sub(r'(?i)\bbearer\s+\S+','Bearer [removido]',text)
    text=re.sub(r'''(?i)(["']?(?:token|password|secret|cookie|api[_-]?key|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''',r'\1[removido]',text)
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[e-mail removido]',text)
    text=re.sub(r'/(?:Users|home|private|tmp)/\S+','[caminho removido]',text)
    text=re.sub(r'[A-Za-z0-9_+/=-]{60,}','[valor removido]',text)
    return ' '.join(text.split())[:limit]

class SearchFailure(RuntimeError):
    def __init__(self,code,cause_type,message,http_status=None,retryable=False):
        self.code=code;self.cause_type=cause_type;self.message=safe_message(message)
        self.http_status=http_status;self.retryable=retryable
        super().__init__(f'{code}: {cause_type}: {self.message}')
    def diagnostic(self):
        return {'code':self.code,'cause_type':self.cause_type,'message':self.message,'http_status':self.http_status,'retryable':self.retryable}
    @classmethod
    def from_diagnostic(cls,value):return cls(**value)

def diagnose(error):
    if isinstance(error,SearchFailure):return error.diagnostic()
    if isinstance(getattr(error,'diagnostic',None),dict):return error.diagnostic
    cause=error
    for _ in range(8):
        nested=cause.__cause__ or cause.__context__
        if nested is None or nested is cause:break
        cause=nested
    name=type(cause).__name__;message=safe_message(cause)
    status=getattr(cause,'status_code',None) or getattr(cause,'code',None)
    if not isinstance(status,int) or not 100<=status<=599:status=None
    if status==429:code,retryable='rate_limited',False
    elif status==403:code,retryable='access_denied',False
    elif name=='CalendarBlocked':code,retryable='challenge',False
    elif 'timeout' in name.lower() or isinstance(cause,TimeoutError):code,retryable='timeout',True
    elif any(v in name.lower() for v in ('connection','connecterror','dns','urlerror')):code,retryable='network_error',True
    elif isinstance(cause,(ValueError,TypeError,KeyError,IndexError,AttributeError)):code,retryable='parse_error',False
    else:code,retryable='provider_error',False
    return {'code':code,'cause_type':name,'message':message,'http_status':status,'retryable':retryable}
