"""Loopback-only, session-authenticated UI. No command or filesystem API."""
import hmac
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Session:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.created = clock()
        self.bootstrap = secrets.token_urlsafe(32)
        self.token = None

    def exchange(self, value):
        if (self.token is not None or self.clock() - self.created > 120
                or not isinstance(value, str) or not hmac.compare_digest(value, self.bootstrap)):
            return None
        self.token = secrets.token_urlsafe(32)
        self.bootstrap = ''
        return self.token

    def authorized(self, value):
        return (self.token is not None and isinstance(value, str)
                and self.clock() - self.created < 3600 and hmac.compare_digest(value, self.token))


def check_origin(host, origin, port):
    return host == f'127.0.0.1:{port}' and origin == f'http://127.0.0.1:{port}'


def serve(coordinator, *, open_browser=True):
    session = Session()
    static = Path(__file__).resolve().parents[1] / 'static'
    last_request = [time.monotonic()]

    class Handler(BaseHTTPRequestHandler):
        server_version = 'NBSRDemoLab'
        protocol_version = 'HTTP/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *_args):
            pass  # tokens/request contents never enter logs

        def reply(self, status, value, content_type='application/json'):
            raw = json.dumps(value, allow_nan=False).encode() if content_type == 'application/json' else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def host_ok(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def auth_ok(self):
            value = self.headers.get('Authorization', '')
            return value.startswith('Bearer ') and session.authorized(value[7:])

        def do_GET(self):
            if not self.host_ok():
                return self.reply(403, {'error': 'Host rejected'})
            if self.path in ('/', '/app.js', '/style.css'):
                name, mime = {'/': ('index.html', 'text/html; charset=utf-8'),
                              '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                              '/style.css': ('style.css', 'text/css; charset=utf-8')}[self.path]
                return self.reply(200, (static / name).read_bytes(), mime)
            if self.path == '/api/health':
                return self.reply(200, {'mode': 'local-demo', 'benchmark_control': False})
            if not self.auth_ok():
                return self.reply(401, {'error': 'Session required'})
            last_request[0] = time.monotonic()
            if self.path == '/api/status':
                return self.reply(200, coordinator.status())
            return self.reply(404, {'error': 'Unknown resource'})

        def do_POST(self):
            if not check_origin(self.headers.get('Host'), self.headers.get('Origin'), self.server.server_port):
                return self.reply(403, {'error': 'Origin rejected'})
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                return self.reply(415, {'error': 'JSON required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 4096:
                    raise ValueError()
                def pairs(items):
                    obj = {}
                    for k, v in items:
                        if k in obj:
                            raise ValueError('duplicate key')
                        obj[k] = v
                    return obj
                body = json.loads(self.rfile.read(length), object_pairs_hook=pairs)
                if not isinstance(body, dict):
                    raise ValueError()
            except (ValueError, UnicodeError, TimeoutError, RecursionError):
                return self.reply(400, {'error': 'Invalid bounded JSON'})
            if self.path == '/api/bootstrap':
                token = session.exchange(body.get('secret')) if set(body) == {'secret'} else None
                return self.reply(200 if token else 401, {'token': token} if token else {'error': 'Bootstrap expired or used'})
            if not self.auth_ok() or self.headers.get('X-NBSR-Action') != 'demo':
                return self.reply(401, {'error': 'Session and action header required'})
            last_request[0] = time.monotonic()
            try:
                if self.path == '/api/start' and set(body) == {'scenario', 'request_id'}:
                    return self.reply(202, coordinator.start(body['scenario'], body['request_id']))
                if self.path == '/api/cancel' and not body:
                    coordinator.cancel()
                    return self.reply(202, {'status': 'cancellation_requested'})
                if self.path == '/api/shutdown' and not body:
                    coordinator.cancel()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return self.reply(202, {'status': 'stopping'})
            except (ValueError, RuntimeError) as exc:
                return self.reply(409, {'error': str(exc)})
            return self.reply(400, {'error': 'Unknown action or fields'})

    server = HTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'NBSR Demo Lab: {url} (loopback only; no benchmark control)', flush=True)
    bootstrap_url = url + '/#' + session.bootstrap
    if open_browser:
        opened = webbrowser.open(bootstrap_url)
        if not opened:
            print('Browser unavailable. Restart with --no-browser to obtain a local one-use URL.', flush=True)
    else:
        print(f'Private one-use browser URL (do not share): {bootstrap_url}', flush=True)

    def expiry():
        while not stop.wait(1):
            now = time.monotonic()
            if now - session.created >= 3600 or (now - last_request[0] >= 900 and not coordinator.running):
                server.shutdown()
                return
    stop = threading.Event()
    threading.Thread(target=expiry, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        stop.set()
        coordinator.close()
        server.server_close()
