"""Dashboard resource ownership with fakes and loopback sockets; no browser or NBSR run."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import web


@pytest.mark.parametrize('failure', ['browser', 'expiry_start', 'serve', 'close', 'socket_close', None])
def test_dashboard_releases_resources_on_startup_and_shutdown(monkeypatch, failure):
    events = []
    class Server:
        server_port = 12345
        def serve_forever(self, **kwargs):
            events.append('serve')
            if failure == 'serve':
                raise KeyboardInterrupt()
        def server_close(self):
            events.append('socket_closed')
            if failure == 'socket_close':
                raise RuntimeError('fixture socket close failure')
    class Coordinator:
        def close(self):
            events.append('coordinator_closed')
            if failure == 'close':
                raise RuntimeError('fixture close failure')
    class Thread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            if failure == 'expiry_start':
                raise RuntimeError('fixture expiry_start failure')
    def browser(url):
        if failure == 'browser':
            raise RuntimeError('fixture browser failure')
        return True
    monkeypatch.setattr(web, 'HTTPServer', lambda *args: Server())
    monkeypatch.setattr(web.threading, 'Thread', Thread)
    monkeypatch.setattr(web.webbrowser, 'open', browser)
    if failure:
        expected = KeyboardInterrupt if failure == 'serve' else RuntimeError
        with pytest.raises(expected):
            web.serve(Coordinator())
    else:
        web.serve(Coordinator())
    assert events[-2:] == ['socket_closed', 'coordinator_closed']
    assert events.count('socket_closed') == 1
    if failure in ('browser', 'expiry_start'):
        assert 'serve' not in events

@pytest.mark.parametrize('failure', ['browser', 'expiry_start', 'close'])
def test_startup_failure_closes_actual_loopback_socket(monkeypatch, failure):
    import socket

    servers = []
    closed = []
    real_server = web.HTTPServer
    def capture_server(*args):
        server = real_server(*args)
        servers.append(server)
        return server
    class Coordinator:
        def close(self):
            closed.append(True)
            if failure == 'close':
                raise RuntimeError('fixture close failure')
    class Thread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            raise RuntimeError('fixture expiry_start failure')
    def browser(url):
        if failure != 'expiry_start':
            raise RuntimeError('fixture browser failure')
        return True
    monkeypatch.setattr(web, 'HTTPServer', capture_server)
    monkeypatch.setattr(web.threading, 'Thread', Thread)
    monkeypatch.setattr(web.webbrowser, 'open', browser)
    try:
        with pytest.raises(RuntimeError, match='fixture'):
            web.serve(Coordinator())
        assert len(servers) == 1
        assert servers[0].socket.fileno() == -1
        assert closed == [True]
        # Actual reuse after closure, with no outbound connection or listener loop.
        with socket.socket() as probe:
            probe.bind(servers[0].server_address)
    finally:
        for server in servers:
            server.server_close()


def test_listener_closed_while_coordinator_cleanup_is_blocked(monkeypatch):
    import threading

    entered = threading.Event()
    release = threading.Event()
    servers = []
    errors = []
    class Server(web.HTTPServer):
        def serve_forever(self, **kwargs):
            pass  # exercise real bound socket without a request loop
    def capture(*args):
        server = Server(*args)
        servers.append(server)
        return server
    class Coordinator:
        def close(self):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test cleanup release deadline expired')
    def run():
        try:
            web.serve(Coordinator())
        except BaseException as exc:
            errors.append(exc)
    monkeypatch.setattr(web, 'HTTPServer', capture)
    monkeypatch.setattr(web.webbrowser, 'open', lambda url: True)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert entered.wait(1), 'coordinator cleanup was not reached'
        assert thread.is_alive(), 'cleanup must still be waiting for release'
        assert servers[0].socket.fileno() == -1
    finally:
        release.set()
        thread.join(2)
        for server in servers:
            server.server_close()
    assert not thread.is_alive()
    assert errors == []
