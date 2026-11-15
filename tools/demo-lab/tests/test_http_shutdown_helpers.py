"""HTTP helper ownership without sockets, browsers, or NBSR workers."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import web


@pytest.mark.parametrize('request_count', [2, 128])
@pytest.mark.parametrize('expiry_alive', [False, True])
@pytest.mark.parametrize('failure', [None, 'alive', 'join', 'inspect', 'start', 'interrupt'])
def test_shutdown_attempt_is_bounded_and_uncertainty_retains_lock(tmp_path, monkeypatch, failure, expiry_alive, request_count):
    import demo
    from nbsr_demo_lab import coordinator

    joined = []
    joined_threads = []
    created = []
    started = []
    replies = []
    class Owner:
        def cancel(self): pass
        def close(self, **kwargs): pass
    class Server:
        server_port = 12345
        def __init__(self, address, handler): self.handler = handler
        def shutdown(self): pass
        def server_close(self): pass
        def serve_forever(self, **kwargs):
            for _ in range(request_count):
                handler = object.__new__(self.handler)
                handler.server = self
                handler.path = '/api/shutdown'
                handler.headers = {'Host': '127.0.0.1:12345', 'Origin': 'http://127.0.0.1:12345',
                                   'Content-Type': 'application/json', 'Content-Length': '2', 'X-NBSR-Action': 'demo'}
                handler.rfile = io.BytesIO(b'{}')
                handler.auth_ok = lambda: True  # Existing HTTP suite covers authentication.
                handler.reply = lambda status, value: replies.append(status)
                handler.do_POST()
    class Thread:
        def __init__(self, target, **kwargs):
            self.http = target.__name__ == 'shutdown'
            if self.http:
                created.append(self)
        def start(self):
            if self.http:
                started.append(self)
            if self.http and failure == 'start':
                raise RuntimeError('fixture startup failure')
        def join(self, timeout):
            if self.http:
                joined.append(timeout)
                joined_threads.append(self)
                if failure in ('join', 'start'):
                    raise RuntimeError('fixture join failure')
                if failure == 'interrupt':
                    raise KeyboardInterrupt()
        def is_alive(self):
            if self.http and failure == 'inspect':
                raise OSError('fixture inspection failure')
            return (self.http and failure == 'alive') or (not self.http and expiry_alive)
    monkeypatch.setattr(coordinator, 'Coordinator', lambda *args: Owner())
    monkeypatch.setattr(web, 'HTTPServer', Server)
    monkeypatch.setattr(web.threading, 'Thread', Thread)
    monkeypatch.setattr(web.webbrowser, 'open', lambda url: True)
    monkeypatch.setattr(demo, '__file__', str(tmp_path / 'tools/demo-lab/demo.py'))
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'serve'])
    assert demo.main() == (2 if failure or expiry_alive else 0)
    assert len(created) == len(started) == len(joined) == 1
    assert created[0] is started[0] is joined_threads[0]
    assert all(0 <= timeout <= 1 for timeout in joined)
    assert replies == ([409] if failure == 'start' else [202]) + [409] * (request_count - 1)
    assert (tmp_path / 'tools/demo-lab/.state/ui.lock').exists() == bool(failure or expiry_alive)


def test_all_helpers_attempted_under_same_deadline_and_failures_retained(monkeypatch):
    from nbsr_demo_lab.coordinator import CleanupUnconfirmed

    clock = [100.0]
    waits = []
    class Thread:
        def join(self, timeout):
            waits.append(timeout)
            clock[0] += .75
        def is_alive(self): return True
    monkeypatch.setattr(web.time, 'monotonic', lambda: clock[0])
    with pytest.raises(CleanupUnconfirmed) as caught:
        web._join_shutdown_helpers([Thread(), Thread()], 100.5)
    assert waits == [.5, 0]
    assert len(caught.value.__cause__.exceptions) == 2
