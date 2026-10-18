"""One reusable HTTP session in a killable process, with a deadline per query."""
from multiprocessing import get_context
from .provider import FastFlightsProvider
from .diagnostics import SearchFailure,diagnose


def serve(connection,max_stops,proxy):
    provider=FastFlightsProvider(max_stops,proxy)
    try:
        while True:
            try:message=connection.recv()
            except EOFError:break
            if message is None:break
            query,metadata=message
            try:connection.send(('ok',provider.search(query,metadata)))
            except Exception as exc:connection.send(('error',diagnose(exc)))
    finally:
        provider.close();connection.close()


class DetailWorker:
    def __init__(self,timeout=40):
        self.timeout=timeout;self.process=self.connection=None;self.key=None

    def close(self):
        if self.connection:
            try:self.connection.send(None)
            except (OSError,EOFError):pass
        if self.process:
            self.process.join(.25)
            if self.process.is_alive():self.process.terminate();self.process.join(3)
            if self.process.is_alive():self.process.kill();self.process.join()
        if self.connection:self.connection.close()
        self.process=self.connection=None;self.key=None

    def __call__(self,query,metadata,max_stops,proxy):
        key=(max_stops,proxy)
        if self.process is None or not self.process.is_alive() or key!=self.key:
            self.close();context=get_context('spawn');parent,child=context.Pipe()
            self.process=context.Process(target=serve,args=(child,max_stops,proxy),daemon=True)
            self.process.start();child.close();self.connection=parent;self.key=key
        try:
            self.connection.send((query,metadata))
            if not self.connection.poll(self.timeout):
                raise SearchFailure('timeout','TimeoutError',f'A consulta detalhada excedeu {self.timeout:g} segundos.',retryable=True)
            kind,payload=self.connection.recv()
        except SearchFailure:
            self.close();raise
        except (EOFError,OSError) as exc:
            self.close()
            raise SearchFailure('worker_crash',type(exc).__name__,'O processo de detalhes encerrou sem devolver resultado.',retryable=True) from exc
        if kind!='ok':raise SearchFailure.from_diagnostic(payload)
        return payload
