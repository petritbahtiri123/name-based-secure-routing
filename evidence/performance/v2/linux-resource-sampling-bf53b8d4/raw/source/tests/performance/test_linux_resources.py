from pathlib import Path
import threading

import pytest

from scripts.performance import linux_resources as resources


ROLLUP = ('00400000-7fffffffffff ---p 00000000 00:00 0 [rollup]\n'
          'Rss: 100 kB\nPss: 80 kB\nPrivate_Clean: 20 kB\n'
          'Private_Dirty: 30 kB\nPrivate_Hugetlb: 4 kB\nUnknown: 1 kB\n')


def stat(state='S', start=99, pid=123):
    fields = [state] + ['0'] * 49
    fields[11], fields[19], fields[21] = '10', str(start), '25'
    return f'{pid} (peer) ' + ' '.join(fields)


def proc(root, state='S'):
    base = root / '123'
    task = base / 'task' / '123'
    task.mkdir(parents=True)
    (task / 'status').write_text('Cpus_allowed_list:\t0\n')
    (task / 'children').write_text('')
    (base / 'stat').write_text(stat(state))
    (base / 'fd').mkdir()
    (base / 'smaps_rollup').write_text(ROLLUP)
    return base


def sample(root):
    return resources.sample_linux_process(123, [0], proc_root=root, ticks=100, page_size=4096)


def test_private_memory_is_not_rss():
    value = resources.parse_smaps_rollup(ROLLUP)
    assert value == dict(rss_bytes=102400, pss_bytes=81920, private_resident_bytes=51200,
                         private_hugetlb_bytes=4096, memory_basis='linux_smaps_rollup')


@pytest.mark.parametrize('text', [ROLLUP.replace('Rss: 100 kB\n', ''),
    ROLLUP + 'Rss: 1 kB\n', ROLLUP.replace('100 kB', '100 MB'),
    ROLLUP.replace('100 kB', '-1 kB'), ROLLUP.replace('100 kB', '1.2 kB'),
    ROLLUP.replace('Rss:', 'Rss '), ROLLUP.replace('100 kB', '+1 kB')])
def test_required_memory_fields_fail_closed(text):
    with pytest.raises(ValueError):
        resources.parse_smaps_rollup(text)


def test_live_sample_preserves_identity_cpu_affinity(tmp_path):
    proc(tmp_path)
    value = sample(tmp_path)
    assert value['pid'] == 123 and value['start_ticks'] == 99
    assert value['cpu_ns'] == 100_000_000 and value['affinity'] == [0]
    assert value['thread_ids'] == [123] and value['memory_state'] == 'MEASURED'
    assert value['private_resident_bytes'] == 51200
    assert 'private_bytes' not in value and 'handle_count' not in value


@pytest.mark.parametrize('state,start,pid', [('S', 99, 123), ('Z', 99, 123),
                                          ('Z', 100, 123), ('Z', 99, 124)])
def test_memory_permission_race(tmp_path, monkeypatch, state, start, pid):
    base = proc(tmp_path)
    read = Path.read_text

    def denied(path, *args, **kwargs):
        if path == base / 'smaps_rollup':
            (base / 'stat').write_text(stat(state, start, pid))
            raise PermissionError('memory denied')
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', denied)
    if (state, start, pid) == ('Z', 99, 123):
        value = sample(tmp_path)
        assert value['memory_state'] == 'UNAVAILABLE_ZOMBIE'
        assert value['private_resident_bytes'] is None and value['rss_bytes'] is None
    else:
        with pytest.raises((RuntimeError, PermissionError)):
            sample(tmp_path)


def test_identity_change_after_successful_memory_read(tmp_path, monkeypatch):
    base = proc(tmp_path)
    read = Path.read_text

    def changed(path, *args, **kwargs):
        value = read(path, *args, **kwargs)
        if path == base / 'smaps_rollup':
            (base / 'stat').write_text(stat(start=100))
        return value

    monkeypatch.setattr(Path, 'read_text', changed)
    with pytest.raises(RuntimeError, match='identity'):
        sample(tmp_path)


def test_known_zombie_memory_unavailable(tmp_path):
    base = proc(tmp_path, 'Z')
    (base / 'smaps_rollup').unlink()
    value = sample(tmp_path)
    assert value['memory_state'] == 'UNAVAILABLE_ZOMBIE'
    assert value['private_resident_bytes'] is None and value['fd_count'] is None


@pytest.mark.parametrize('filename,text', [('status', 'Cpus_allowed_list: 1\n'), ('children', '456')])
def test_preserves_affinity_and_child_rejection(tmp_path, filename, text):
    base = proc(tmp_path)
    (base / 'task' / '123' / filename).write_text(text)
    with pytest.raises(RuntimeError):
        sample(tmp_path)


def test_missing_live_memory_fails(tmp_path):
    base = proc(tmp_path)
    (base / 'smaps_rollup').unlink()
    with pytest.raises(FileNotFoundError):
        sample(tmp_path)


def record(**changes):
    return dict(pid=123, start_ticks=99, cpu_ns=100, timestamp_ns=1000,
                state='S', memory_state='MEASURED', affinity=[0], thread_ids=[123],
                rss_bytes=100, pss_bytes=80, private_resident_bytes=50,
                private_hugetlb_bytes=0, fd_count=1, **changes)


def sampler(**kwargs):
    return resources.LinuxResourceSampler(**(dict(processes={'source': 123}, cpus=[0],
        interval_seconds=1, max_records=8, sample_fn=lambda *_: record()) | kwargs))


@pytest.mark.parametrize('changes', [dict(max_records=0), dict(max_records=True),
    dict(max_records=1.5), dict(interval_seconds=float('nan')),
    dict(interval_seconds=float('inf')), dict(interval_seconds=0),
    dict(processes={}), dict(processes={'source': True}), dict(processes={'': 123}),
    dict(cpus=[]), dict(cpus=[-1]), dict(cpus=[True]), dict(cpus=[0, 0])])
def test_invalid_sampler_bounds(changes):
    with pytest.raises(ValueError):
        sampler(**changes)


def test_start_once_stop_and_snapshot_isolation():
    emitted = threading.Event()
    value = record()

    def sink(row):
        row['affinity'].append(7)
        emitted.set()

    instance = sampler(sample_fn=lambda *_: value, record_sink=sink)
    with pytest.raises(RuntimeError):
        instance.check_health(require_running=True)
    instance.start()
    assert emitted.wait(2)
    with pytest.raises(RuntimeError):
        instance.start()
    rows = instance.stop()
    assert len(rows) == 1 and rows[0]['role'] == 'source'
    assert rows[0]['affinity'] == [0]
    rows[0]['affinity'].append(2)
    value['affinity'].append(3)
    assert instance.records_snapshot()[0]['affinity'] == [0]
    with pytest.raises(RuntimeError):
        instance.check_health(require_running=True)
    with pytest.raises(RuntimeError):
        instance.start()


def test_sink_failure_preserves_prefix_and_latches():
    seen = threading.Event()

    def sink(row):
        seen.set()
        raise OSError('disk full')

    instance = sampler(record_sink=sink)
    instance.start()
    assert seen.wait(2)
    with pytest.raises(RuntimeError):
        instance.stop()
    assert len(instance.records_snapshot()) == 1
    with pytest.raises(RuntimeError):
        instance.check_health()


def test_record_cap_preserves_exact_prefix():
    seen = threading.Event()
    instance = sampler(max_records=1, interval_seconds=.001,
                       record_sink=lambda row: seen.set())
    instance.start()
    assert seen.wait(2)
    instance._thread.join(2)
    with pytest.raises(RuntimeError, match='failed'):
        instance.stop()
    assert len(instance.records_snapshot()) == 1


@pytest.mark.parametrize('change', [dict(pid=124), dict(start_ticks=100),
    dict(cpu_ns=99), dict(timestamp_ns=999), dict(timestamp_ns=1000),
    dict(cpu_ns=True), dict(state='Z', memory_state='UNAVAILABLE_ZOMBIE'),
    dict(affinity=[1])])
def test_discontinuous_or_lost_live_sampling_fails(change):
    values = iter([record(), record() | dict(timestamp_ns=1001) | change])
    instance = sampler(sample_fn=lambda *_: next(values), interval_seconds=.001)
    instance.start()
    instance._thread.join(2)
    with pytest.raises(RuntimeError):
        instance.stop()
    assert len(instance.records_snapshot()) == 1


def test_empty_sampling_fails_and_preserves_empty_prefix():
    def unavailable(*_):
        raise ProcessLookupError('gone')

    instance = sampler(sample_fn=unavailable)
    with pytest.raises(RuntimeError):
        instance.stop()
    instance.start()
    instance._thread.join(2)
    with pytest.raises(RuntimeError):
        instance.stop()
    assert instance.records_snapshot() == []
