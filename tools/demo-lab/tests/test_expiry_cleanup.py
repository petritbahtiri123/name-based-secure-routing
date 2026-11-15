"""Owned expiry cleanup and shared wait budget; no NBSR processes."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import web
from nbsr_demo_lab.coordinator import Coordinator


@pytest.mark.parametrize('close_error', [False, True])
@pytest.mark.parametrize('elapsed,remaining', [(0, 1), (119.75, .25), (125, 0)])
def test_expiry_join_uses_remaining_cleanup_budget(monkeypatch, elapsed, remaining, close_error):
    clock = [100.0]
    waits = []
    deadlines = []
    class Server:
        server_port = 12345
        def serve_forever(self, **kwargs): pass
        def server_close(self): pass
    class Owner:
        def close(self, *, deadline=None):
            deadlines.append(deadline)
            clock[0] += elapsed
            if close_error:
                raise RuntimeError("fixture coordinator failure")
    class Thread:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def join(self, timeout): waits.append(timeout)
        def is_alive(self): return False
    monkeypatch.setattr(web, 'HTTPServer', lambda *args: Server())
    monkeypatch.setattr(web.threading, 'Thread', Thread)
    monkeypatch.setattr(web.webbrowser, 'open', lambda url: True)
    monkeypatch.setattr(web.time, 'monotonic', lambda: clock[0])
    if close_error:
        with pytest.raises(RuntimeError, match="fixture coordinator failure"):
            web.serve(Owner())
    else:
        web.serve(Owner())
    assert deadlines == [220]
    assert waits == [remaining]


@pytest.mark.parametrize('owner_error', [False, True])
@pytest.mark.parametrize('failure', ['alive', 'join', 'inspect', 'interrupt'])
def test_expiry_uncertainty_retains_ui_lock(tmp_path, monkeypatch, failure, owner_error):
    import demo
    from nbsr_demo_lab import coordinator
    class Server:
        server_port = 12345
        def serve_forever(self, **kwargs): pass
        def server_close(self): pass
    class Owner:
        closed = False
        def close(self, **kwargs):
            self.closed = True
            if owner_error:
                raise RuntimeError('fixture coordinator failure')
    class Thread:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def join(self, timeout):
            if failure == 'join':
                raise RuntimeError('fixture join')
            if failure == 'interrupt':
                raise KeyboardInterrupt()
        def is_alive(self):
            if failure == 'inspect':
                raise OSError('fixture inspect')
            return True
    owner = Owner()
    monkeypatch.setattr(coordinator, 'Coordinator', lambda *args: owner)
    monkeypatch.setattr(web, 'HTTPServer', lambda *args: Server())
    monkeypatch.setattr(web.threading, 'Thread', Thread)
    monkeypatch.setattr(web.webbrowser, 'open', lambda url: True)
    monkeypatch.setattr(demo, '__file__', str(tmp_path / 'tools/demo-lab/demo.py'))
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'serve'])
    try:
        result = demo.main()
    except BaseException as exc:
        result = type(exc).__name__
    assert result == 2
    assert owner.closed
    assert (tmp_path / 'tools/demo-lab/.state/ui.lock').exists()


@pytest.mark.parametrize('deadline,expected', [(105, 5), (90, 0), (500, 120)])
def test_coordinator_honors_remaining_wait_without_extending_cap(tmp_path, monkeypatch, deadline, expected):
    waits = []
    class Thread:
        def join(self, timeout): waits.append(timeout)
        def is_alive(self): return False
    lab = Coordinator(tmp_path, tmp_path / 'state')
    lab.thread = Thread()
    import time
    monkeypatch.setattr(time, 'monotonic', lambda: 100)
    lab.close(deadline=deadline)
    assert waits == [expected]


def test_actual_expiry_thread_has_exited_before_serve_returns(monkeypatch):
    import threading

    threads = []
    real_thread = threading.Thread
    class Server:
        server_port = 12345
        def serve_forever(self, **kwargs): pass
        def server_close(self): pass
    class Owner:
        def close(self, **kwargs): pass
    def tracked_thread(**kwargs):
        thread = real_thread(**kwargs)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, 'HTTPServer', lambda *args: Server())
    monkeypatch.setattr(web.threading, 'Thread', tracked_thread)
    monkeypatch.setattr(web.webbrowser, 'open', lambda url: True)
    try:
        web.serve(Owner())
        assert len(threads) == 1
        assert not threads[0].is_alive()
    finally:
        for thread in threads:
            thread.join(timeout=2)


def test_unstarted_expiry_thread_is_uncertain_not_silently_ignored():
    import threading
    import time
    from nbsr_demo_lab.coordinator import CleanupUnconfirmed

    thread = threading.Thread(target=lambda: None, daemon=True)
    with pytest.raises(CleanupUnconfirmed) as caught:
        web._join_expiry(thread, time.monotonic() + 120)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert thread.ident is None
