"""Failure-only context must survive without accepting inaccessible live resources."""
import json
from pathlib import Path

import pytest

from scripts.performance import b4_linux, linux_resources
from scripts.performance.linux_loopback import sample_process
from tests.performance.test_linux_sampler_zombie import fixture, stat


def test_live_fd_denial_retains_existing_stat_observations(tmp_path, monkeypatch):
    base = fixture(tmp_path)
    original = Path.iterdir
    failure = PermissionError(13, 'FD unavailable', '/proc/123/fd')

    def denied(path):
        if path == base / 'fd':
            (base / 'stat').write_text(stat('R', cpu=20))
            raise failure
        return original(path)

    monkeypatch.setattr(Path, 'iterdir', denied)
    with pytest.raises(PermissionError) as caught:
        sample_process(123, [0], tmp_path, 100, 4096)
    assert caught.value is failure
    note = json.loads(failure.__notes__[0])
    assert note['phase'] == 'fd_permission_recheck'
    assert note['pid'] == 123
    assert note['initial_stat']['state'] == 'S'
    assert note['recheck_stat']['state'] == 'R'
    assert note['initial_stat']['start_ticks'] == note['recheck_stat']['start_ticks'] == 99
    assert note['recheck_stat']['cpu_ns'] == 200_000_000


@pytest.mark.parametrize('failed_call,phase', [(1, 'before_smaps'), (2, 'after_smaps')])
def test_memory_sampler_labels_denied_subphase_without_retry(tmp_path, monkeypatch, failed_call, phase):
    base = fixture(tmp_path)
    (base / 'smaps_rollup').write_text('Rss: 1 kB\nPss: 1 kB\nPrivate_Clean: 0 kB\nPrivate_Dirty: 1 kB\nPrivate_Hugetlb: 0 kB\n')
    failure = PermissionError(13, 'FD unavailable')
    calls = []

    def sampled(*args):
        calls.append(args)
        if len(calls) == failed_call:
            raise failure
        return dict(state='S', start_ticks=99)

    monkeypatch.setattr(linux_resources, 'sample_process', sampled)
    with pytest.raises(PermissionError) as caught:
        linux_resources.sample_linux_process(123, [0], proc_root=tmp_path, ticks=100, page_size=4096)
    assert caught.value is failure
    assert len(calls) == failed_call
    assert f'sample_linux_process phase={phase}' in failure.__notes__


def test_failure_metadata_preserves_traceback_and_notes():
    try:
        error = PermissionError(13, 'FD unavailable')
        error.add_note('sample_linux_process phase=after_smaps')
        raise error
    except PermissionError as caught:
        value = b4_linux.failure_details(caught)
    assert value['error_type'] == 'PermissionError'
    assert 'FD unavailable' in value['error']
    assert 'test_failure_metadata_preserves_traceback_and_notes' in value['traceback']
    assert 'sample_linux_process phase=after_smaps' in value['traceback']
    assert value['traceback_truncated'] is False


def test_failure_metadata_is_bounded_and_keeps_terminal_notes():
    error = PermissionError('x' * 100_000)
    error.add_note('terminal observation')
    value = b4_linux.failure_details(error)
    assert len(value['error']) == 4096
    assert len(value['traceback']) == 65536
    assert value['traceback_truncated'] is True
    assert value['traceback'].endswith('terminal observation\n')
