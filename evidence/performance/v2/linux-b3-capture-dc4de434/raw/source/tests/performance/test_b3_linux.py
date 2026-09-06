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
