import os
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import unquote
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .store import Store
from .adapters import MAX_BYTES
from .feed import Inbox

ROOT = Path(__file__).resolve().parent.parent


def create_app(data_dir=None, inbox_dir=None):
    store = Store(data_dir or os.environ.get('NBSR_LAB_DATA',ROOT/'data'))
    inbox_path = inbox_dir or os.environ.get('NBSR_LAB_INBOX')
    inbox = Inbox(store,inbox_path) if inbox_path else None
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(inbox.watch()) if inbox else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError): await task
    app = FastAPI(title='NBSR Performance Lab',version='0.3.0',docs_url='/api/docs',lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

    @app.middleware('http')
    async def boundaries(request, call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin = request.headers.get('origin')
            if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
                return Response('Cross-origin writes are disabled',status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get('/api/v1/health')
    def health(): return dict(status='ok',mode='passive-inbox' if inbox else 'offline-evidence',active_benchmark='not_controlled',version='0.3.0')

    @app.get('/api/v1/feed')
    def feed(): return inbox.status() if inbox else dict(configured=False,feeds=[],error=None)

    @app.get('/api/v1/export-contract')
    def export_contract():
        return FileResponse(ROOT/'docs'/'export-contract.json',media_type='application/json')

    @app.get('/api/v1/runs')
    def runs(): return dict(runs=store.runs(),mode='offline-evidence')

    @app.get('/api/v1/artifacts')
    def artifacts(): return dict(artifacts=store.artifacts())

    @app.get('/api/v1/artifacts/{sha}')
    def artifact(sha):
        try: raw = store.artifact(sha)
        except FileNotFoundError: raise HTTPException(404,'Artifact not found')
        except ValueError as e: raise HTTPException(409,str(e))
        return Response(raw,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{sha}.artifact"'})

    @app.post('/api/v1/ingestions')
    async def ingest(request: Request):
        if request.headers.get('content-type','').split(';')[0] not in ('application/json','application/x-ndjson'):
            raise HTTPException(415,'Upload a JSON or NDJSON artifact')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_BYTES: raise HTTPException(413,'Maximum upload is 4 MiB')
        try: return store.ingest(bytes(raw),unquote(request.headers.get('x-artifact-name','upload.json')))
        except ValueError as e: raise HTTPException(422,str(e))

    @app.get('/')
    def index(): return FileResponse(ROOT/'static'/'index.html')

    if (ROOT/'static').exists(): app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
    return app
