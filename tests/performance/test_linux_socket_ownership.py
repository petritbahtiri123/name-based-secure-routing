import os
import json

import pytest

from tests.performance.test_linux_udp_failure import HEADER, ROW, stat


def module():
    from scripts.performance import linux_socket_ownership
    return linux_socket_ownership


def fixture(tmp_path, monkeypatch):
    base = tmp_path / '11'
    (base / 'fd').mkdir(parents=True)
    (base / 'net').mkdir()
    (base / 'fd' / '3').touch()
    (base / 'stat').write_text(stat())
    (base / 'net' / 'udp').write_text(HEADER + ROW)
    links = {'exe': '/tmp/peer', 'net': 'net:[123]', '3': 'socket:[99]'}
    monkeypatch.setattr(os, 'readlink', lambda p: links[p.name])
    return base, links


def test_live_socket_binding_and_exact_join(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    row = module().snapshot(11, 3, '/tmp/peer', '127.0.0.1', proc_root=tmp_path)
    assert row['status'] == 'MEASURED_LIVE_SOCKET_SNAPSHOT'
    assert row['sockets'] == [{'fd': 3, 'inode': 99, 'local': ['127.0.0.1', 4660]}]
    module().validate_binding(row, pid=11, start_ticks=3, binary='/tmp/peer', local=['127.0.0.1', 4660])
    for change in ({'pid': 12}, {'start_ticks': 4}, {'binary': '/tmp/other'}, {'local': ['127.0.0.1', 4661]}):
        with pytest.raises(ValueError):
            module().validate_binding(row, **(dict(pid=11, start_ticks=3, binary='/tmp/peer', local=['127.0.0.1', 4660]) | change))


@pytest.mark.parametrize('change', ['pid', 'epoch', 'zombie', 'binary', 'fd', 'address', 'table'])
def test_unavailable_never_becomes_ownership_proof(tmp_path, monkeypatch, change):
    base, links = fixture(tmp_path, monkeypatch)
    if change == 'pid':
        (base / 'stat').write_text(stat().replace('11 (', '12 ('))
    elif change == 'epoch':
        (base / 'stat').write_text(stat(4))
    elif change == 'zombie':
        (base / 'stat').write_text(stat().replace(' S ', ' Z '))
    elif change == 'binary':
        links['exe'] = '/tmp/other'
    elif change == 'fd':
        links['3'] = 'socket:[100]'
    elif change == 'address':
        (base / 'net' / 'udp').write_text(HEADER + ROW.replace('0100007F', '00000000'))
    else:
        (base / 'net' / 'udp').write_text('unrecognized')
    row = module().snapshot(11, 3, '/tmp/peer', '127.0.0.1', proc_root=tmp_path)
    assert row['status'] == 'UNAVAILABLE'
    with pytest.raises(ValueError):
        module().validate_binding(row, pid=11, start_ticks=3, binary='/tmp/peer', local=['127.0.0.1', 4660])


def test_fd_change_during_snapshot_rejects(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    original = os.readlink
    count = 0
    def changing(path):
        nonlocal count
        if path.name == '3':
            count += 1
            if count > 1:
                return 'socket:[100]'
        return original(path)
    monkeypatch.setattr(os, 'readlink', changing)
    assert module().snapshot(11, 3, '/tmp/peer', '127.0.0.1', proc_root=tmp_path)['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('change', ['namespace', 'epoch', 'permission'])
def test_observation_race_or_access_denial_rejects(tmp_path, monkeypatch, change):
    base, _ = fixture(tmp_path, monkeypatch)
    original = os.readlink
    calls = 0
    def changing(path):
        nonlocal calls
        if change == 'permission':
            raise PermissionError('fixture')
        if path.name == 'net':
            calls += 1
            if calls == 2 and change == 'namespace':
                return 'net:[456]'
        if path.name == '3' and change == 'epoch':
            (base / 'stat').write_text(stat(4))
        return original(path)
    monkeypatch.setattr(os, 'readlink', changing)
    assert module().snapshot(11, 3, '/tmp/peer', '127.0.0.1', proc_root=tmp_path)['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('enabled,available', [(False, False), (True, False), (True, True)])
def test_peer_observer_is_opt_in_bounded_and_required_when_requested(tmp_path, monkeypatch, enabled, available):
    from types import SimpleNamespace
    from scripts.performance import linux_native_peer as peer
    samples = iter([dict(pid=11, start_ticks=3, state='S', cpu_ns=0)] * 25
                   + [dict(pid=11, start_ticks=3, state='Z', cpu_ns=1)])
    monkeypatch.setattr(peer, 'sample_process', lambda *a, **k: next(samples))
    monkeypatch.setattr(peer.time, 'sleep', lambda _: None)
    calls = []
    def observe(*args):
        calls.append(args)
        return dict(status='MEASURED_LIVE_SOCKET_SNAPSHOT' if available else 'UNAVAILABLE')
    monkeypatch.setattr(peer, 'snapshot', observe)
    child = SimpleNamespace(pid=11, wait=lambda **k: 0)
    args = dict(deadline=peer.time.monotonic() + 10,
                socket_identity=('/tmp/peer', '127.0.0.1') if enabled else None)
    if enabled and not available:
        with pytest.raises(ValueError, match='not observed'):
            peer.observe_child(child, [0], tmp_path, **args)
    else:
        peer.observe_child(child, [0], tmp_path, **args)
    assert len(calls) == (1 if available else 20) if enabled else not calls
    assert (tmp_path / 'socket-ownership.json').exists() == (enabled and available)


def test_comparison_identity_distinguishes_live_observer(tmp_path):
    from tests.performance.test_linux_native_pair import fixture
    from scripts.performance.linux_native_cohort import comparison_identity
    source, _ = fixture(tmp_path)
    env = json.loads((source / 'environment.json').read_text())
    assert comparison_identity(env) != comparison_identity(env | {'live_socket_observer': True})


def test_pair_rejects_claimed_observer_without_retained_socket_proof(tmp_path):
    from tests.performance.test_linux_native_pair import fixture, SHA, put
    from scripts.performance.linux_b5_placement import seal_output
    from scripts.performance.linux_native_pair import analyze_pair
    source, destination = fixture(tmp_path)
    for root in (source, destination):
        env = json.loads((root / 'environment.json').read_text())
        put(root, 'environment.json', env | {'live_socket_observer': True})
        seal_output(root)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)
