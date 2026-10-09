from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_run as run
from scripts.performance import linux_socket_ownership as sockets
from scripts.performance import linux_udp_failure as udp
from scripts.performance.linux_native_archive import archive_root
from scripts.performance.linux_native_lifecycle_control import LifecycleBarrier
from scripts.performance.linux_native_lifecycle_coordinator import EventLedger, endpoint_arguments, validate_config
from scripts.performance.linux_native_lifecycle_remote import extract_public_archive
from tests.performance.test_linux_native_lifecycle import fixture
from tests.performance.test_linux_native_lifecycle_coordinator import config
from tests.performance.test_linux_native_lifecycle_remote import archive
from tests.performance.test_linux_socket_ownership import fixture as proc_fixture
from tests.performance.test_linux_udp_failure import HEADER, ROW


@pytest.mark.parametrize('count', [6144, 8192])
def test_large_count_requires_explicit_live_mode_and_preserves_workload(count):
    value = config() | dict(count=count, bundle_mode='live-bundles')
    assert validate_config(value) == value
    args = native.argument_parser().parse_args(endpoint_arguments(value, 'source')[4:])
    assert (args.count, args.rate, args.shards) == (count, 100, 2)
    argv, overrides = fixture(count=count, bundle_mode='live-bundles')
    assert argv[argv.index('--lifecycle-clients') + 1] == str(count)
    assert argv[argv.index('--payload-bytes') + 1] == '1024'
    assert argv[-2:] == ['--b3-keep-alive-seconds', '1'] and not overrides
    with pytest.raises(ValueError):
        fixture(count=count)
    with pytest.raises(ValueError):
        validate_config(value | dict(bundle_mode='idle-bundles'))


@pytest.mark.parametrize('count', [True, 6143, 6145, 8191, 8193, 16384])
def test_unsupported_counts_still_rejected(count):
    with pytest.raises(ValueError):
        fixture(count=count, bundle_mode='live-bundles')


def test_8192_barrier_keeps_exact_cardinality_and_hold(tmp_path):
    root, output = tmp_path / 'private', tmp_path / 'output'
    root.mkdir()
    output.mkdir()
    barrier = LifecycleBarrier(role='source', count=8192, root=root, output=output, capture=lambda: {})
    assert len(barrier.expected_active) == 8192
    assert EventLedger(8192).count == 8192
    with pytest.raises(ValueError, match='all active'):
        barrier.request('release')


@pytest.mark.parametrize('reader', ['memory', 'extract'])
def test_extended_archive_bound_is_opt_in_and_still_enforced(tmp_path, reader):
    path = archive(tmp_path, [(f'file{i}', 'file', b'x') for i in range(3)])
    def read(bound):
        if reader == 'memory':
            return archive_root(path, maximum_entries=bound)
        return extract_public_archive(path, tmp_path / 'out', maximum_entries=bound)
    for bad in (True, 0, 40001, None):
        with pytest.raises(ValueError, match='entry bound'):
            read(bad)
    with pytest.raises(ValueError, match='count'):
        read(2)
    read(40000)


@pytest.mark.parametrize('count', [6144, 8192])
@pytest.mark.parametrize('role,expected', [('source', 40000), ('destination', 20000)])
def test_large_collection_bound_is_role_scoped(tmp_path, monkeypatch, count, role, expected):
    observed = []
    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = {role: object()}
            self.ledger = SimpleNamespace(positions={role: 1})
        def start_command(self, *args):
            raise InterruptedError('stop before launch')
        wait = send = finish = sleep = lambda *args: None
        def close(self):
            return {}
    monkeypatch.setattr(run, 'Manager', Manager)
    monkeypatch.setattr(run, 'collect_reports', lambda *args, **kwargs: None)
    monkeypatch.setattr(run, 'collect', lambda *args, **kwargs: observed.append(kwargs.get('maximum_entries', 10000)))
    with pytest.raises(InterruptedError):
        run.execute(config() | dict(count=count, bundle_mode='live-bundles'), tmp_path / 'out')
    assert observed == [expected if count == 8192 else expected * 3 // 4]


@pytest.mark.parametrize('fd_count,accepted', [(8193, True), (16384, True), (16385, False)])
@pytest.mark.parametrize('failure_snapshot', [False, True])
def test_owned_fd_observers_have_bounded_overhead_allowance(tmp_path, monkeypatch, fd_count, accepted, failure_snapshot):
    base, _ = proc_fixture(tmp_path, monkeypatch)
    original_iterdir = Path.iterdir
    original_readlink = udp.os.readlink
    monkeypatch.setattr(Path, 'iterdir', lambda p: (base / 'fd' / str(i) for i in range(fd_count)) if p == base / 'fd' else original_iterdir(p))
    monkeypatch.setattr(udp.os, 'readlink', lambda p: 'socket:[99]' if p.parent == base / 'fd' and p.name == '3' else '/dev/null' if p.parent == base / 'fd' else original_readlink(p))
    (base / 'net' / 'udp6').write_text(HEADER.replace('rem_address', 'remote_address'))
    if failure_snapshot:
        child = SimpleNamespace(pid=11, poll=lambda: None)
        value = udp.capture_owned_udp({'source': child}, {11: 3}, proc_root=tmp_path)['roles']['source']
        expected = 'MEASURED_FAILURE_SNAPSHOT'
    else:
        value = sockets.snapshot(11, 3, '/tmp/peer', '127.0.0.1', proc_root=tmp_path)
        expected = 'MEASURED_LIVE_SOCKET_SNAPSHOT'
    assert (value['status'] == expected) is accepted
    if not accepted:
        assert 'FD observation bound' in value.get('error', value.get('reason', ''))


@pytest.mark.parametrize('rows,accepted', [(8193, True), (16384, True), (16385, False)])
def test_udp_table_allows_extra_sockets_but_remains_bounded(rows, accepted):
    text = HEADER + ''.join(ROW.replace(' 99 ', f' {i + 99} ') for i in range(rows))
    if accepted:
        result = udp.parse_udp(text, {99}, family='udp')
        assert len(result) == 1 and result[0]['inode'] == 99
    else:
        with pytest.raises(ValueError, match='UDP table'):
            udp.parse_udp(text, {99}, family='udp')
