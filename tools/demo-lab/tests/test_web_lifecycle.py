"""Dashboard resource ownership with fakes and loopback sockets; no browser or NBSR run."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import web


@pytest.mark.parametrize('failure', ['browser', 'expiry_start', 'serve', 'close', None])
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
    assert events[-2:] == ['coordinator_closed', 'socket_closed']
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
