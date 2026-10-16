"""Offline clocks/process handles only; no process creation, signals or network."""

import pytest
from types import SimpleNamespace

from scripts.performance import linux_native_lifecycle_coordinator as coordinator
from tests.performance.test_linux_native_cleanup_failures import Child, Clock, Reader, Stream


def test_raw_manager_cleanup_does_not_supply_whole_trial_bound(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(coordinator.time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(coordinator.time, 'sleep', clock.sleep)
    manager = coordinator.Manager(16, tmp_path)
    manager.children = {role: Child() for role in ('source', 'destination')}
    manager.readers = {role: Reader() for role in manager.children}
    manager.errors = {role: Stream() for role in manager.children}
    clock.now = 120
    manager.close()
    # Historical characterization: raw manager is unchanged; use the outer owner.
    assert 135 <= clock.now < 135.1


class OwnedWorker:
    def __init__(self, clock, *, finish=None, code=0, descendants=False,
                 stuck=False, start_fails=False, signal_fails=False):
        self.clock, self.finish, self.code = clock, finish, code
        self.descendants, self.stuck = descendants, stuck
        self.start_fails, self.signal_fails = start_fails, signal_fails
        self.owned = False
        self.signals = []
        self.reaped = False

    def start(self):
        self.owned = True
        if self.start_fails:
            raise OSError('partial startup')

    def observe(self):
        code = self.code if self.finish is not None and self.clock.now >= self.finish else None
        return code, code is None or self.descendants

    def signal(self, name):
        assert self.owned and not self.reaped
        self.signals.append((name, self.clock.now))
        if self.signal_fails:
            raise OSError('signal failed')
        if name == 'KILL' and not self.stuck:
            self.finish, self.code, self.descendants = self.clock.now, -9, False

    def reap(self):
        assert self.observe()[0] is not None
        self.reaped = True


def run(worker, clock, **kwargs):
    from scripts.performance.linux_native_watchdog import supervise
    return supervise(worker, clock=clock.monotonic, sleep=clock.sleep, **kwargs)


def test_stalled_worker_is_contained_by_one_deadline():
    clock = Clock()
    worker = OwnedWorker(clock)  # No completion in any worker phase.
    result = run(worker, clock)
    assert result['reason'] == 'deadline'
    assert result['status'] == 'INVALID_PARTIAL'
    assert [name for name, _ in worker.signals] == ['INT', 'TERM', 'KILL']
    assert worker.signals[0][1] <= 100.1
    assert clock.now <= 120
    assert worker.reaped
    assert result['remote_cleanup'] == 'UNCONFIRMED'


@pytest.mark.parametrize('cause', ['disconnect', 'cancel', 'partial-start', 'resource'])
def test_early_failure_cleans_owned_group_without_restarting_budget(cause):
    clock = Clock()
    worker = OwnedWorker(clock, finish=1 if cause == 'disconnect' else None,
                         code=255, start_fails=cause == 'partial-start')

    def cancelled():
        if cause == 'cancel' and clock.now >= 1:
            raise InterruptedError('repeated cancellation')

    def guard():
        if cause == 'resource' and clock.now >= 1:
            raise OSError('resource guard')

    result = run(worker, clock, check_cancelled=cancelled, guard=guard)
    assert result['status'] == 'INVALID_PARTIAL'
    assert worker.reaped
    assert clock.now < 12


def test_exited_leader_with_surviving_descendant_is_signalled_before_reap():
    clock = Clock()
    worker = OwnedWorker(clock, finish=1, descendants=True)
    result = run(worker, clock)
    assert worker.signals and worker.signals[0][1] < 2
    assert worker.reaped and result['status'] == 'INVALID_PARTIAL'


def test_deadline_exhaustion_retains_unconfirmed_ownership():
    clock = Clock()
    worker = OwnedWorker(clock, stuck=True, signal_fails=True)
    result = run(worker, clock)
    assert clock.now == 120
    assert not worker.reaped and worker.owned
    assert not result['group_exit_observed']
    assert not result['leader_reaped']
    assert result['errors'] and result['status'] == 'INVALID_PARTIAL'


def test_clean_exit_is_only_local_completion():
    clock = Clock()
    worker = OwnedWorker(clock, finish=2)
    result = run(worker, clock)
    assert result['status'] == 'LOCAL_WORKER_COMPLETED'
    assert result['remote_cleanup'] == 'UNCONFIRMED'
    assert result['local_cleanup'] == 'UNCONFIRMED'  # /proc snapshot is not atomic proof.
    assert worker.reaped and not worker.signals


def test_observation_failure_never_claims_group_release():
    clock = Clock()
    worker = OwnedWorker(clock)

    def broken():
        raise PermissionError('private detail')

    worker.observe = broken
    result = run(worker, clock)
    assert clock.now == 120 and not worker.reaped
    assert not result['group_exit_observed']
    assert result['errors'] == [dict(stage='observe', type='PermissionError')]


def test_start_failure_before_creation_never_signals_an_unowned_pid():
    clock = Clock()
    worker = OwnedWorker(clock)

    def broken():
        raise OSError('no child')

    worker.start = broken
    result = run(worker, clock)
    assert result['status'] == 'INVALID_PARTIAL'
    assert not worker.owned and not worker.signals and not worker.reaped


def test_backward_clock_kills_once_without_restarting_wait_budget():
    clock = Clock()
    worker = OwnedWorker(clock)

    def sleep(seconds):
        clock.now -= seconds

    from scripts.performance.linux_native_watchdog import supervise
    result = supervise(worker, clock=clock.monotonic, sleep=sleep)
    assert result['reason'] == 'clock' and result['status'] == 'INVALID_PARTIAL'
    assert [name for name, _ in worker.signals] == ['KILL']


@pytest.mark.parametrize('overrun', ['start', 'sleep', 'observe'])
def test_deadline_overrun_still_attempts_owned_kill_without_a_new_wait(overrun):
    clock = Clock()
    worker = OwnedWorker(clock)
    original_start, original_observe = worker.start, worker.observe

    def start():
        original_start()
        if overrun == 'start':
            clock.now = 121

    def observe():
        if overrun == 'observe':
            clock.now = 121
        return original_observe()

    def sleep(seconds):
        clock.now = 121

    worker.start, worker.observe = start, observe
    from scripts.performance.linux_native_watchdog import supervise
    result = supervise(worker, clock=clock.monotonic, sleep=sleep)
    assert [name for name, _ in worker.signals] == ['KILL']
    assert result['status'] == 'INVALID_PARTIAL' and not worker.reaped
    assert clock.now == 121


@pytest.fixture
def linux_adapter(monkeypatch):
    from scripts.performance import linux_native_watchdog as watchdog
    monkeypatch.setattr(watchdog.sys, 'platform', 'linux')
    calls = []
    child = SimpleNamespace(pid=731, returncode=None)

    def popen(argv, **kwargs):
        calls.append(('start', argv, kwargs))
        return child

    monkeypatch.setattr(watchdog.subprocess, 'Popen', popen)
    for name, value in [('P_PID', 1), ('WEXITED', 4), ('WNOHANG', 1), ('WNOWAIT', 16), ('CLD_EXITED', 1)]:
        monkeypatch.setattr(watchdog.os, name, value, raising=False)
    monkeypatch.setattr(watchdog.os, 'waitid', lambda *args: calls.append(('observe', args)) or
                        SimpleNamespace(si_pid=731, si_status=0, si_code=1), raising=False)
    monkeypatch.setattr(watchdog.os, 'killpg', lambda *args: calls.append(('signal', args)), raising=False)
    monkeypatch.setattr(watchdog.os, 'waitpid', lambda *args: calls.append(('reap', args)) or (731, 0))
    monkeypatch.setattr(watchdog.os, 'waitstatus_to_exitcode', lambda status: status, raising=False)
    monkeypatch.setattr(watchdog.signal, 'SIGKILL', 9, raising=False)

    class Entry:
        def __init__(self, pid, pgid, state='Z'):
            self.name, self.pgid, self.state = str(pid), pgid, state

        def __truediv__(self, name):
            assert name == 'stat'
            return self

        def read_text(self):
            return f'{self.name} (name with ) parentheses) {self.state} 1 {self.pgid} 731 0'

    entries = [Entry(731, 731), Entry(732, 731), Entry(990, 990)]
    monkeypatch.setattr(watchdog, 'Path', lambda value: SimpleNamespace(iterdir=lambda: iter(entries)))
    return watchdog, child, calls, entries


def test_linux_group_pins_exited_leader_until_last_descendant_is_absent(linux_adapter):
    watchdog, child, calls, entries = linux_adapter
    owner = watchdog.LinuxGroup(['worker'], 'out', 'err')
    owner.start()
    assert calls[0][2]['start_new_session'] is True
    assert calls[0][2]['stdin'] == watchdog.subprocess.DEVNULL
    assert owner.observe() == (0, True)  # Zombie descendant is still ownership.
    assert calls[-1][1][-1] & watchdog.os.WNOWAIT
    assert child.returncode is None
    owner.signal('KILL')
    assert calls[-1] == ('signal', (731, 9))
    entries.pop(1)
    assert owner.observe() == (0, False)
    owner.reap()
    assert child.returncode == 0
    with pytest.raises(RuntimeError, match='unreaped'):
        owner.signal('KILL')


def test_linux_group_reap_failure_preserves_unreaped_identity(linux_adapter, monkeypatch):
    watchdog, child, _, _ = linux_adapter
    owner = watchdog.LinuxGroup(['worker'], 'out', 'err')
    owner.start()
    monkeypatch.setattr(watchdog.os, 'waitpid', lambda *args: (0, 0))
    with pytest.raises(RuntimeError, match='not ready'):
        owner.reap()
    assert child.returncode is None and owner.owned


def test_worker_command_cannot_select_arbitrary_module():
    from scripts.performance.linux_native_watchdog import worker_command
    for mode in ('finite', 'lifecycle'):
        command = worker_command(mode, 'config', 'output')
        assert command[1:] == ['-B', '-m', f'scripts.performance.linux_native_{mode}_run',
                               '--config', 'config', '--output', 'output']
    with pytest.raises(ValueError):
        worker_command('shell', 'config', 'output')


@pytest.mark.parametrize('free,ram,baseline,starting', [
    (7, 3, 7, True), (5, 3, 6, False), (9, 1, 9, False), (9, 3, 12, False),
])
def test_resource_guard_preserves_start_stop_and_original_growth_bounds(monkeypatch, free, ram, baseline, starting):
    from scripts.performance import linux_native_watchdog as watchdog
    monkeypatch.setattr(watchdog.shutil, 'disk_usage', lambda path: SimpleNamespace(free=free * 2**30))
    monkeypatch.setattr(watchdog, 'Path', lambda path: SimpleNamespace(read_text=lambda: f'MemAvailable: {ram * 2**20} kB'))
    with pytest.raises(OSError, match='resource guard'):
        watchdog.resource_guard('owned', baseline * 2**30, starting=starting)


@pytest.mark.parametrize('case', ['windows', 'long-profile', 'invalid-config'])
def test_cli_rejects_unsupported_execution_before_creating_owner(tmp_path, monkeypatch, case):
    import json
    from scripts.performance import linux_native_watchdog as watchdog
    from tests.performance.test_linux_native_finite_run import config
    value = config()
    if case == 'long-profile':
        value['diagnostic_seconds'] = 60
        value['diagnostic_rate'] = [1000, 1]
        value['post_close_reports'] = True
    if case == 'invalid-config':
        value['unknown'] = True
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    output = tmp_path / 'out'
    monkeypatch.setattr(watchdog.sys, 'platform', 'win32' if case == 'windows' else 'linux')
    monkeypatch.setattr(watchdog.sys, 'argv', ['watchdog', '--mode', 'finite', '--config', str(path),
                                            '--output', str(output), '--original-disk-free-bytes', '14247788544'])

    def forbidden(*args, **kwargs):
        pytest.fail('must reject before creating a process owner')

    monkeypatch.setattr(watchdog, 'LinuxGroup', forbidden)
    with pytest.raises((SystemExit, ValueError)):
        watchdog.main()
    assert not output.exists()
