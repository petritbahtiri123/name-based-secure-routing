from types import SimpleNamespace
import time

import pytest

from scripts.performance.b4_linux import LinuxB4Backend, parse_host
from scripts import run_b4b_v2 as v2


def row(pid=11, ticks=3, stamp=1, cpu=10):
    return dict(pid=pid, start_ticks=ticks, timestamp_ns=stamp, cpu_ns=cpu,
                state='R', memory_state='MEASURED', affinity=[0], thread_ids=[pid],
                rss_bytes=100, pss_bytes=90, private_resident_bytes=80,
                private_hugetlb_bytes=0, fd_count=4)


def backend(sample_fn):
    return LinuxB4Backend([0], '/usr/bin/taskset', sample_fn=sample_fn,
                          host_fn=lambda: {'timestamp_ns': time.monotonic_ns(), 'status': 'MEASURED'}, max_records=20)


def test_linux_fields_and_pid_continuity():
    values = iter([row(), row(stamp=1_000_000_001, cpu=100_000_010)])
    b = backend(lambda *a: next(values))
    samples = []
    processes = {'source': SimpleNamespace(pid=11, poll=lambda: None)}
    b.sample(processes, samples)
    b.sample(processes, samples)
    result = b.summarize(samples)
    assert result['cpu_seconds'] == pytest.approx(.1)
    assert result['peak_private_resident_bytes'] == 80
    assert result['peak_fd_count'] == 4
    assert not {'peak_private_bytes', 'peak_handles', 'peak_working_set_bytes'} & result.keys()
    assert b.command(['peer', '--samples', '1']) == ['/usr/bin/taskset', '-c', '0', 'peer', '--samples', '1']


@pytest.mark.parametrize('problem', ['identity', 'affinity', 'permission', 'regression'])
def test_live_sampling_failure_is_not_suppressed(problem):
    calls = 0
    def sample(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return row()
        if problem == 'permission':
            raise PermissionError('denied')
        value = row(stamp=2, ticks=4 if problem == 'identity' else 3,
                    cpu=0 if problem == 'regression' else 11)
        if problem == 'affinity':
            value['affinity'] = [1]
        return value
    b = backend(sample)
    samples = []
    processes = {'source': SimpleNamespace(pid=11, poll=lambda: None)}
    b.sample(processes, samples)
    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        b.sample(processes, samples)
    assert len(samples) == 1


def test_linux_dispatch_does_not_launch_typeperf(monkeypatch, tmp_path):
    class Backend:
        def measure(self, run, args, kwargs, counter_path):
            assert run is v2.run_cell
            assert args == (512, 1, 1)
            assert kwargs == {'source_shards': 2}
            return {'linux': True}
    monkeypatch.setattr(v2, 'start_host_counters', lambda *a: pytest.fail('Windows counter dispatched'))
    assert v2.run_measured_cell(512, 1, 1, source_shards=2,
        counter_path=tmp_path/'host.json', backend=Backend()) == {'linux': True}


def test_host_native_fields_not_windows_aliases():
    result = parse_host('cpu 10 2 3 40 5 6 7 8 0 0\nctxt 50\nprocs_running 2\n',
                        'MemTotal: 100 kB\nMemAvailable: 30 kB\n', timestamp_ns=1)
    assert result['cpu_jiffies']['irq'] == 6
    assert result['mem_available_bytes'] == 30720
    assert 'processor_queue_length' not in result and 'committed_bytes' not in result
    with pytest.raises(ValueError):
        parse_host('cpu 0\n', '', timestamp_ns=1)


def test_shard_cpu_is_explicitly_unmeasured():
    assert backend(lambda *a: row()).shard_cpu({0: 0, 1: 0}) == {
        'status': 'NOT_MEASURED', 'reason': 'non-Windows shard OS thread IDs are zero',
        'shards': [0, 1]}


def test_build_binding_rejects_source_or_binary_substitution(tmp_path):
    import hashlib
    import json
    from scripts.run_b4b_linux import validate_build
    binary = tmp_path / 'perf_rust_source'
    binary.write_bytes(b'exact fixture')
    manifest = tmp_path / 'build.json'
    value = dict(source_sha='a' * 40, build_profile='release', build_commands=['cargo build'],
                 toolchains={'rustc': 'fixture'}, binary_sha256={binary.name: hashlib.sha256(binary.read_bytes()).hexdigest()})
    manifest.write_text(json.dumps(value))
    assert validate_build(manifest, {'nbsr': binary}, 'a' * 40)[0] == value
    with pytest.raises(ValueError, match='metadata'):
        validate_build(manifest, {'nbsr': binary}, 'b' * 40)
    binary.write_bytes(b'substitution')
    with pytest.raises(ValueError, match='digest'):
        validate_build(manifest, {'nbsr': binary}, 'a' * 40)


def test_partial_records_retained_and_count_cap(tmp_path):
    b = backend(lambda *a: row())
    b.cap = 1
    rows = []
    processes = {'source': SimpleNamespace(pid=11, poll=lambda: None)}
    b.sample(processes, rows)
    with pytest.raises(RuntimeError, match='cap'):
        b.sample(processes, rows)
    b.preserve(tmp_path, rows)
    assert len((tmp_path / 'linux-resources.ndjson').read_text().splitlines()) == 1
    assert (tmp_path / 'linux-host.ndjson').is_file()


def test_linux_measure_missing_role_invalidates_without_changing_admission(monkeypatch, tmp_path):
    b = backend(lambda *a: row())
    def run(*args, backend, **kwargs):
        backend.host = [{'timestamp_ns': 1}, {'timestamp_ns': 2}]
        return dict(successful_admissions=512, failed_admissions=0,
                    established_goodput_bytes_per_second=1, established_p99_latency_ns=1,
                    admission_elapsed_seconds=2, resources={'cpu_seconds': 1},
                    resource_samples=[{'role': 'established-source'}],
                    cleanup={'processes_exited': True})
    result = b.measure(run, (512, 1, 1), {'duration': 30, 'warmup': 2}, tmp_path/'host')
    assert result['admission_rate'] == 256
    assert not result['valid'] and not result['resource_capture']['valid']


def test_task4i_prepared_linux_preserves_batch_and_repeat_gates(monkeypatch, tmp_path):
    from scripts import run_b4b_task4i as task
    binary = tmp_path / 'binary'
    binary.write_bytes(b'fixture')
    selected = object()
    calls = []
    monkeypatch.setattr(task.v2, 'build', lambda *a: pytest.fail('unexpected build'))
    monkeypatch.setattr(task.v2, 'host_environment', lambda: pytest.fail('Windows environment'))
    def measured(*args, **kwargs):
        calls.append((args, kwargs))
        return dict(valid=True, requested_clients=512, started_clients=512, connected_clients=512,
                    successful_admissions=512, failed_admissions=0, errors=0, timeouts=0,
                    admission_rate=25, handshake_latency_ns={'50': 1, '95': 2, '99': 3},
                    admission_p50_latency_ns=1, admission_p95_latency_ns=2, admission_p99_latency_ns=3,
                    established_goodput_bytes_per_second=100, established_p99_latency_ns=4,
                    effective_cores=1, peak_pending_clients=512, resources={'peak_fd_count': 4},
                    cleanup={'all_zero': True, 'processes_exited': True})
    monkeypatch.setattr(task.v2, 'run_measured_cell', measured)
    result = task.execute(tmp_path/'run', source_shards=2, offered_rates=[25], backend=selected,
                          prepared_binaries={'nbsr': binary}, prepared_environment={'platform': 'linux'})
    assert len(calls) == 3
    assert all(args[:2] == (512, 1) and kw['source_shards'] == 2 and kw['backend'] is selected
               and kw['duration'] == 30 and kw['warmup'] == 2 and kw['release_rate'] == 25 for args, kw in calls)
    assert result['cells'][0]['status'] == 'STABLE'


def test_proc_exit_race_only_skipped_after_confirmed_exit():
    polls = iter([None, 0])
    def vanished(*a):
        raise FileNotFoundError('proc exited')
    b = backend(vanished)
    b.sample({'source': SimpleNamespace(pid=11, poll=lambda: next(polls))}, [])
    with pytest.raises(FileNotFoundError):
        b.sample({'source': SimpleNamespace(pid=11, poll=lambda: None)}, [])
