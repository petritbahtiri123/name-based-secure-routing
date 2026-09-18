from pathlib import Path
from types import SimpleNamespace
import signal

import pytest


def test_signal_cancellation_is_deferred_until_owned_child_is_registered():
    from scripts.performance.linux_native_peer import Cancellation
    previous = signal.getsignal(signal.SIGTERM)
    with Cancellation() as cancellation:
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)  # Must not raise in the middle of Popen assignment.
        with pytest.raises(InterruptedError, match='SIGTERM'):
            cancellation.check()
        handler(signal.SIGTERM, None)  # Repeated requests cannot interrupt finally cleanup.
    assert signal.getsignal(signal.SIGTERM) == previous


def test_observer_checks_pending_cancel_before_sampling_or_reaping(tmp_path, monkeypatch):
    from scripts.performance import linux_native_peer as peer
    monkeypatch.setattr(peer, 'sample_process', lambda *a, **k: pytest.fail('sample after cancellation'))
    child = SimpleNamespace(pid=123, wait=lambda **k: pytest.fail('reap belongs to owner cleanup'))
    def cancelled():
        raise InterruptedError('SIGTERM')
    with pytest.raises(InterruptedError, match='SIGTERM'):
        peer.observe_child(child, [0], tmp_path, deadline=peer.time.monotonic() + 1,
                           check_cancelled=cancelled)


def test_native_commands_keep_equivalent_shape_and_explicit_addresses(tmp_path):
    from scripts.performance.linux_native_peer import native_command
    cell = dict(path='direct', cores=1, payload_bytes=16384, streams=8, outstanding=2)
    for mode in ('direct', 'nbsr'):
        value = cell | {'path': mode}
        source, env = native_command(value, 'source', Path('/bins'), Path('/private'), tmp_path,
                                     bind='192.0.2.10:0', endpoint='192.0.2.11:4444')
        assert not env
        assert source[source.index('--benchmark-client-bind') + 1] == '192.0.2.10:0'
        assert source[source.index('--endpoint') + 1] == '192.0.2.11:4444'
        assert source[source.index('--p2a-outstanding-per-stream') + 1] == '2'
        destination, env = native_command(value, 'destination', Path('/bins'), Path('/private'), tmp_path,
                                          bind='192.0.2.11:0', endpoint=None)
        assert destination[destination.index('--benchmark-listen') + 1] == '192.0.2.11:0'
        assert destination[destination.index('--p2a-runtime-workers') + 1] == '1'
        assert env == ({'NBSR_P2A_STREAMS': '8'} if mode == 'nbsr' else {})


@pytest.mark.parametrize('endpoint', ['0.0.0.0:123', '224.0.0.1:123', '255.255.255.255:123',
    '[::1]:123', '192.0.2.1:0', '192.0.2.1:65536', 'name.example:123'])
def test_native_remote_endpoint_refuses_ambiguous_or_unroutable_forms(endpoint):
    from scripts.performance.linux_native_peer import validate_endpoint
    with pytest.raises(ValueError):
        validate_endpoint(endpoint, allow_zero=False)


def test_finite_observer_retains_terminal_before_reap_and_exiting_transition(tmp_path, monkeypatch):
    from scripts.performance import linux_native_peer as peer
    events = []
    samples = iter([dict(pid=123, start_ticks=9, state='S', flags=4, cpu_ns=10,
                         fd_count=None, fd_count_state='UNAVAILABLE_EXITING'),
                    dict(pid=123, start_ticks=9, state='Z', flags=4, cpu_ns=20,
                         fd_count=None, fd_count_state='UNAVAILABLE_ZOMBIE')])
    def sample(pid, cpus, *, allow_exiting):
        assert allow_exiting is True
        return next(samples)
    class Child:
        pid = 123
        def wait(self, timeout):
            assert '"state": "Z"' in (tmp_path / 'resources.ndjson').read_text()
            events.append('reaped')
            return 0
    monkeypatch.setattr(peer, 'sample_process', sample)
    monkeypatch.setattr(peer.time, 'sleep', lambda _: None)
    result = peer.observe_child(Child(), [0], tmp_path, deadline=peer.time.monotonic() + 1)
    assert result['final_sample']['cpu_ns'] == 20
    assert events == ['reaped']


def test_finite_observer_rejects_pid_reuse_before_reaping(tmp_path, monkeypatch):
    from scripts.performance import linux_native_peer as peer
    samples = iter([dict(pid=123, start_ticks=9, state='S'), dict(pid=123, start_ticks=10, state='Z')])
    monkeypatch.setattr(peer, 'sample_process', lambda *a, **k: next(samples))
    monkeypatch.setattr(peer.time, 'sleep', lambda _: None)
    child = SimpleNamespace(pid=123, wait=lambda **k: pytest.fail('must not reap reused identity as success'))
    with pytest.raises(RuntimeError, match='identity'):
        peer.observe_child(child, [0], tmp_path, deadline=peer.time.monotonic() + 1)


def test_readiness_checks_alpn_and_exact_destination_address(tmp_path):
    from scripts.performance.linux_native_peer import readiness_endpoint
    p = tmp_path / 'ready.json'
    p.write_text('{"endpoint":"192.0.2.11:4444","alpn":"nbsr-quic-1"}')
    assert readiness_endpoint(p, '192.0.2.11') == '192.0.2.11:4444'
    with pytest.raises(ValueError):
        readiness_endpoint(p, '192.0.2.12')
    p.write_text('{"endpoint":"192.0.2.11:4444","alpn":"other"}')
    with pytest.raises(ValueError):
        readiness_endpoint(p, '192.0.2.11')


def test_failed_source_validation_cannot_produce_ack_authorization(tmp_path):
    from scripts.performance.linux_native_peer import validate_source
    (tmp_path / 'stdout').write_text('{"errors":1,"measured_ns":1000}\n')
    with pytest.raises(ValueError):
        validate_source(tmp_path)
    assert not (tmp_path / 'validated-result.json').exists()


@pytest.mark.parametrize('failure_kind', ['sampler', 'cancel-after-spawn'])
def test_failure_kills_only_owned_group_and_seals_rejected_attempt(tmp_path, monkeypatch, failure_kind):
    import json
    from scripts.performance import linux_native_peer as peer
    binaries = tmp_path / 'bins'
    authority = tmp_path / 'private'
    binaries.mkdir()
    authority.mkdir()
    for name in peer.NAMES.values():
        (binaries / name).write_bytes(b'fixture executable')
    for name in ('ca.der', 'destination.der', 'destination-key.der'):
        (authority / name).write_bytes(b'private fixture stays outside evidence')
    manifest = tmp_path / 'build.json'
    manifest.write_text(json.dumps(dict(source_sha='a' * 40, build_profile='release',
        binary_sha256={n: peer.digest(binaries / n) for n in peer.NAMES.values()},
        build_commands=['fixture'], toolchains={'fixture': True})))
    events = []
    class Child:
        pid = 123
        returncode = None
        def wait(self, timeout):
            events.append('wait')
            self.returncode = -9
            return -9
    def launch(*args, **kwargs):
        assert kwargs['start_new_session'] is True
        return Child()
    monkeypatch.setattr(peer.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(peer, 'git_state', lambda: ('a' * 40, ''))
    monkeypatch.setattr(peer, 'environment', lambda _: dict(selected_cpus=[0], taskset='taskset'))
    monkeypatch.setattr(peer.os, 'environ', {})
    monkeypatch.setattr(peer.os, 'getuid', lambda: 1000, raising=False)
    monkeypatch.setattr(peer.os, 'killpg', lambda pid, sig: events.append(('kill_group', pid)), raising=False)
    monkeypatch.setattr(peer.signal, 'SIGKILL', 9, raising=False)
    monkeypatch.setattr(peer.subprocess, 'Popen', launch)
    monkeypatch.setattr(peer, 'wait_target_exec', lambda *a, **k: None)
    def fail(*args, **kwargs):
        raise RuntimeError('sampler failure fixture')
    monkeypatch.setattr(peer, 'observe_child', fail)
    args = SimpleNamespace(output=tmp_path / 'out', authority=authority, binaries=binaries,
        bind='127.0.0.1:0', role='destination', path='direct', ready_input=None,
        destination_address=None, build_manifest=manifest, cores=1, payload=1024, streams=1, depth=1)
    calls = 0
    def check_cancelled():
        nonlocal calls
        calls += 1
        if failure_kind == 'cancel-after-spawn' and calls == 2:
            assert (args.output / 'pid.json').is_file()
            raise InterruptedError('cancelled fixture')
    expected = RuntimeError if failure_kind == 'sampler' else InterruptedError
    with pytest.raises(expected, match='fixture'):
        peer.execute(args, check_cancelled=check_cancelled)
    assert events == [('kill_group', 123), 'wait']
    assert json.loads((args.output / 'forced-cleanup.json').read_text())['valid'] is False
    assert (args.output / 'failure.json').exists() and (args.output / 'checksums.sha256').exists()
    assert not (args.output / 'result.json').exists()
    assert not any('key.der' in p.name for p in args.output.rglob('*'))
