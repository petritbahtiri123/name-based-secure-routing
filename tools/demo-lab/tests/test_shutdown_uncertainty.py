"""Shutdown timeout semantics; no NBSR subprocess or 120-second wait."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab.coordinator import Coordinator


class Worker:
    def __init__(self, alive):
        self.alive = alive
        self.waits = []
    def join(self, timeout):
        self.waits.append(timeout)
    def is_alive(self):
        return self.alive


def test_surviving_worker_reports_uncertainty_without_changing_marker(tmp_path):
    lab = Coordinator(tmp_path, tmp_path / 'state')
    marker = lab.state / 'active.json'
    marker.write_bytes(b'{"run_id":"fixture-retained"}')
    lab.blocked = True
    lab.thread = Worker(True)
    with pytest.raises(RuntimeError, match='cleanup is unconfirmed'):
        lab.close()
    assert lab.cancel_event.is_set()
    assert lab.thread.waits == [120]
    assert lab.blocked
    assert marker.read_bytes() == b'{"run_id":"fixture-retained"}'


@pytest.mark.parametrize('worker', [None, Worker(False)])
def test_completed_or_absent_worker_closes_normally(tmp_path, worker):
    lab = Coordinator(tmp_path, tmp_path / 'state')
    lab.thread = worker
    lab.close()
    assert lab.cancel_event.is_set()


def test_cli_retains_owner_and_refuses_restart_after_join_timeout(tmp_path, monkeypatch, capsys):
    import demo
    from nbsr_demo_lab import coordinator, web
    lab = Coordinator(tmp_path, tmp_path / 'tools/demo-lab/.state')
    marker = lab.state / 'active.json'
    marker.write_text('{"run_id":"fixture-retained"}', encoding='utf-8')
    lab.thread = Worker(True)
    monkeypatch.setattr(coordinator, 'Coordinator', lambda *args: lab)
    monkeypatch.setattr(web, 'serve', lambda owner, **kwargs: owner.close())
    monkeypatch.setattr(demo, '__file__', str(tmp_path / 'tools/demo-lab/demo.py'))
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'serve', '--no-browser'])
    assert demo.main() == 2
    assert 'cleanup is unconfirmed' in capsys.readouterr().err
    lock = lab.state / 'ui.lock'
    owner = lock.read_bytes()
    assert json.loads(owner)['purpose'] == 'demo-ui'
    assert marker.exists()
    # A worker may finish later, but that cannot erase the earlier UI uncertainty.
    lab.thread.alive = False
    assert demo.main() == 2
    assert lock.read_bytes() == owner
    assert marker.exists()


def test_real_non_daemon_worker_is_not_killed_or_detached(tmp_path, monkeypatch):
    import threading
    from nbsr_demo_lab.coordinator import CleanupUnconfirmed

    release = threading.Event()
    lab = Coordinator(tmp_path, tmp_path / 'state')
    worker = threading.Thread(target=lambda: release.wait(2), daemon=False)
    lab.thread = worker
    worker.start()
    real_join = worker.join
    # Expire only the join wait, without spending the production 120-second budget.
    monkeypatch.setattr(worker, 'join', lambda timeout: real_join(timeout=0))
    try:
        with pytest.raises(CleanupUnconfirmed):
            lab.close()
        assert worker.is_alive()
        assert not worker.daemon
        assert lab.cancel_event.is_set()
    finally:
        release.set()
        real_join(timeout=2)
    assert not worker.is_alive()


@pytest.mark.parametrize('failure', [False, True])
def test_cli_releases_ui_lock_for_normal_or_ordinary_startup_exit(tmp_path, monkeypatch, failure):
    import demo
    from nbsr_demo_lab import web

    def serve(*args, **kwargs):
        if failure:
            raise RuntimeError('fixture startup failure')
    monkeypatch.setattr(web, 'serve', serve)
    monkeypatch.setattr(demo, '__file__', str(tmp_path / 'tools/demo-lab/demo.py'))
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'serve'])
    assert demo.main() == (2 if failure else 0)
    assert not (tmp_path / 'tools/demo-lab/.state/ui.lock').exists()


@pytest.mark.parametrize('stage', ['join', 'is_alive'])
@pytest.mark.parametrize('error_type', [RuntimeError, OSError, KeyboardInterrupt])
def test_failed_shutdown_observation_preserves_ui_owner(tmp_path, monkeypatch, capsys, stage, error_type):
    import demo
    from nbsr_demo_lab import coordinator, web

    failure = error_type('fixture private error detail')
    class BrokenWorker(Worker):
        def join(self, timeout):
            if stage == 'join':
                raise failure
            super().join(timeout)
        def is_alive(self):
            if stage == 'is_alive':
                raise failure
            return super().is_alive()
    lab = Coordinator(tmp_path, tmp_path / 'tools/demo-lab/.state')
    marker = lab.state / 'active.json'
    marker.write_bytes(b'{"run_id":"retained-fixture"}')
    lab.thread = BrokenWorker(True)
    monkeypatch.setattr(coordinator, 'Coordinator', lambda *args: lab)
    observed = []
    def serve(owner, **kwargs):
        try:
            owner.close()
        except BaseException as exc:
            observed.append(exc)
            raise
    monkeypatch.setattr(web, 'serve', serve)
    monkeypatch.setattr(demo, '__file__', str(tmp_path / 'tools/demo-lab/demo.py'))
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'serve'])
    # Catch injected Ctrl+C locally so an unfixed baseline does not abort pytest.
    try:
        result = demo.main()
    except BaseException as exc:
        result = type(exc).__name__
    assert result == 2
    assert isinstance(observed[0], coordinator.CleanupUnconfirmed)
    assert observed[0].__cause__ is failure
    assert lab.cancel_event.is_set()
    assert (lab.state / 'ui.lock').exists()
    assert marker.read_bytes() == b'{"run_id":"retained-fixture"}'
    stderr = capsys.readouterr().err
    assert 'cleanup is unconfirmed' in stderr
    assert 'private error detail' not in stderr
