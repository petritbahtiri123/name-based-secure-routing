"""Real loopback HTTP boundaries with a fake coordinator; no NBSR processes."""
import http.client
import json
import queue
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import web


def test_http_session_and_cross_origin_boundary(monkeypatch):
    urls = queue.Queue()
    monkeypatch.setattr(web.webbrowser, 'open', lambda url: urls.put(url) or True)
    class Fake:
        running = False
        closed = False
        starts = 0
        def status(self): return {'current': None}
        def start(self, *args):
            self.starts += 1
            return {'run_id': 'fake'}
        def cancel(self): pass
        def close(self): self.closed = True
    coordinator = Fake()
    thread = threading.Thread(target=web.serve, args=(coordinator,), daemon=True)
    thread.start()
    url = urlsplit(urls.get(timeout=5))
    origin = f'http://{url.netloc}'
    token = None
    def call(method, path, body=None, **overrides):
        connection = http.client.HTTPConnection('127.0.0.1', url.port, timeout=5)
        headers = {'Host': url.netloc, 'Origin': origin, 'Content-Type': 'application/json', 'X-NBSR-Action': 'demo'}
        if token: headers['Authorization'] = 'Bearer ' + token
        headers.update(overrides)
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse()
        answer = response.status, json.loads(response.read())
        connection.close()
        return answer
    try:
        assert call('GET', '/api/status')[0] == 401
        assert call('POST', '/api/start', {'scenario': 'unknown_service', 'request_id': 'one'}, Origin='https://evil.test')[0] == 403
        assert call('GET', '/api/status', Host='evil.test')[0] == 403
        status, result = call('POST', '/api/bootstrap', {'secret': url.fragment})
        assert status == 200
        token = result['token']
        assert call('POST', '/api/bootstrap', {'secret': url.fragment})[0] == 401
        assert call('GET', '/api/status') == (200, {'current': None})
        assert call('POST', '/api/start', {'scenario': 'unknown_service', 'request_id': 'one'}, **{'X-NBSR-Action': ''})[0] == 401
        assert coordinator.starts == 0
        assert call('POST', '/api/start', {'scenario': 'unknown_service', 'request_id': 'one'})[0] == 202
        assert coordinator.starts == 1
    finally:
        call('POST', '/api/shutdown', {})
        thread.join(5)
    assert not thread.is_alive()
    assert coordinator.closed
