from types import SimpleNamespace

import pytest

from scripts import run_b3_session_lifecycle as b3
from scripts.performance.b3_linux import LinuxCapture


def reading(pid, cpus):
    return dict(pid=pid, start_ticks=pid * 10, state='S', memory_state='MEASURED',
                memory_basis='linux_smaps_rollup', timestamp_ns=100, cpu_ns=10,
                affinity=list(cpus), thread_ids=[pid], fd_count=3, rss_bytes=100,
                pss_bytes=80, private_resident_bytes=50, private_hugetlb_bytes=4)


def process(pid):
    return SimpleNamespace(pid=pid, poll=lambda: None)


def backend(sample_fn=reading):
    return LinuxCapture([2], '/usr/bin/taskset', sample_fn=sample_fn)


def test_prefix_places_both_roles_before_launch():
    capture = backend()
    assert capture.command(['server', '--ready', 'r']) == ['/usr/bin/taskset', '-c', '2', 'server', '--ready', 'r']
    assert capture.command(['source']) == ['/usr/bin/taskset', '-c', '2', 'source']


def test_role_sums_keep_original_processes_and_linux_names():
    capture = backend()
    rows = []
    capture.capture_once(rows, process(1), [process(2), process(3)], phase='active', cycle=0)
    source = rows[1]
    assert source['process_count'] == 2 and len(source['processes']) == 2
    assert source['private_resident_bytes'] == 100 and source['rss_bytes'] == 200
    assert source['private_hugetlb_bytes'] == 8 and source['fd_count'] == 6
    assert source['thread_count'] == 2 and source['platform'] == 'linux'
    assert not {'private_bytes', 'working_set_bytes', 'handle_count'} & source.keys()


@pytest.mark.parametrize('change', ['start', 'pid', 'count', 'missing', 'zombie', 'affinity', 'clock', 'cpu'])
def test_identity_count_and_live_sampling_required_across_cycles(change):
    values = {1: reading(1, [2]), 2: reading(2, [2])}
    capture = backend(lambda pid, cpus: values[pid].copy())
    rows = []
    capture.capture_once(rows, process(1), [process(2)], phase='idle', cycle=0)
    for value in values.values():
        value['timestamp_ns'] += 1
    clients = [process(2)]
    if change == 'start':
        values[2]['start_ticks'] += 1
    elif change == 'pid':
        clients = [process(3)]
    elif change == 'count':
        clients = []
    elif change == 'missing':
        values[2]['private_resident_bytes'] = None
    elif change == 'zombie':
        values[2]['state'] = 'Z'
    elif change == 'affinity':
        values[2]['affinity'] = [3]
    elif change == 'clock':
        values[2]['timestamp_ns'] = 100
    else:
        values[2]['cpu_ns'] = 9
    with pytest.raises(RuntimeError):
        capture.capture_once(rows, process(1), clients, phase='cooldown', cycle=1)


def test_failed_linux_final_capture_forbids_report_release(tmp_path, monkeypatch):
    monkeypatch.setattr(b3, 'wait_paths', lambda *args: None)

    class Failed:
        def capture(self, *args, **kwargs):
            raise RuntimeError('live data missing')

    with pytest.raises(RuntimeError, match='live data missing'):
        b3.capture_final_cooldown([], process(1), [process(2)], tmp_path,
            cycle=0, seconds=2, cadence=.5, report_gate=True, capture_backend=Failed())
    assert not (tmp_path / 'destination.report-release').exists()


def test_expected_bundle_exit_only_final_after_report_ready(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(b3, 'wait_paths', lambda *args: events.append('ready'))

    class Capture:
        def capture(self, *args, **kwargs):
            assert events == ['ready']
            assert kwargs['allow_exited_sources'] is True
            events.append('captured')

    b3.capture_final_cooldown([], process(1), [process(2)], tmp_path,
        cycle=0, seconds=2, cadence=.5, report_gate=True, capture_backend=Capture(),
        allow_exited_sources=True)
    assert events == ['ready', 'captured']
    assert (tmp_path / 'destination.report-release').exists()


def test_expected_exited_source_is_unavailable_not_zero():
    tick = 100

    def read(pid, cpus):
        return reading(pid, cpus) | {'timestamp_ns': tick}

    capture = backend(read)
    rows = []
    capture.capture_once(rows, process(1), [process(2)], phase='active', cycle=0)
    tick += 1
    exited = SimpleNamespace(pid=2, poll=lambda: 0)
    capture.capture_once(rows, process(1), [exited], phase='cooldown', cycle=0,
                         allow_exited_sources=True)
    row = rows[-1]
    assert row['memory_state'] == 'UNAVAILABLE_EXPECTED_EXIT'
    assert row['private_resident_bytes'] is None and row['cpu_ns'] is None
    assert row['processes'][0]['start_ticks'] == 20
    assert row['processes'][0]['exit_code'] == 0


@pytest.mark.parametrize('phase,code', [('active', 0), ('cooldown', 1)])
def test_exit_exception_never_masks_active_exit_or_failed_exit(phase, code):
    capture = backend()
    rows = []
    capture.capture_once(rows, process(1), [process(2)], phase='idle', cycle=0)
    with pytest.raises(RuntimeError):
        capture.capture_once(rows, process(1), [SimpleNamespace(pid=2, poll=lambda: code)],
            phase=phase, cycle=0, allow_exited_sources=True)
