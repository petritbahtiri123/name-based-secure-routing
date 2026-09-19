from pathlib import Path

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance.post_close_cleanup import FIELDS as RUST_CLEANUP_FIELDS


def fixture(role='source', count=16, **overrides):
    args = dict(role=role, count=count, shards=2, rate=100,
                binaries=Path('/bin'), authority=Path('/private/authority'),
                lifecycle=Path('/private/lifecycle'), output=Path('/evidence'),
                bind='192.0.2.1:0', endpoint='192.0.2.2:4444' if role == 'source' else None)
    return native.command(**(args | overrides))


def test_command_preserves_materialized_workload_and_explicit_bind():
    source, env = fixture()
    assert not env
    for flag, value in {'--lifecycle-clients': '16', '--lifecycle-source-shards': '2',
                        '--lifecycle-offered-rate': '100', '--payload-bytes': '1024',
                        '--benchmark-client-bind': '192.0.2.1:0',
                        '--b3-materialized-streams': '1'}.items():
        assert source[source.index(flag) + 1] == value
    assert '--hold-for-release' in source
    dest, env = fixture('destination')
    assert env['NBSR_PERF_LIFECYCLE_CONNECTIONS'] == '16'
    assert env['NBSR_PERF_LIFECYCLE_SERIAL_ACCEPT'] == '1'
    assert dest[dest.index('--b3-report-gate') + 1] == str(Path('/private/lifecycle'))
    assert dest[dest.index('--benchmark-listen') + 1] == '192.0.2.1:0'
    assert not any('timeout' in arg or 'keepalive' in arg for arg in source + dest)


@pytest.mark.parametrize('change', [dict(count=0), dict(count=1024), dict(count=True),
                                  dict(shards=3), dict(rate=0), dict(role='other'),
                                  dict(bind='0.0.0.0:0'), dict(bind='192.0.2.1:4444'),
                                  dict(endpoint='192.0.2.2:0')])
def test_invalid_workloads_reject(change):
    with pytest.raises(ValueError):
        fixture(**change)


def source_rows():
    return [dict(success=True, logical_client_id=i, bytes_transmitted=1024,
                 bytes_received=1024) for i in range(16)] + [
        dict(phase='lifecycle_cleanup', **dict.fromkeys(RUST_CLEANUP_FIELDS, 0))]


def test_source_requires_exact_unique_clients_and_all_cleanup_fields():
    rows = source_rows()
    result = native.validate_result('source', 16, rows, None)
    assert result['successful'] == 16 and result['ownership_all_zero']
    for corrupted in [rows[:-1], rows + [rows[0]],
                      [rows[0]] * 16 + [rows[-1]],
                      rows[:-1] + [rows[-1] | {RUST_CLEANUP_FIELDS[0]: 1}],
                      [rows[0] | {'bytes_received': 0}] + rows[1:],
                      rows + [dict(success=False, error='HandshakeTimeout')]]:
        with pytest.raises(ValueError):
            native.validate_result('source', 16, corrupted, None)


def test_destination_requires_result_cardinality_and_explicit_final_cleanup():
    final = dict.fromkeys(RUST_CLEANUP_FIELDS, 0)
    server = dict(status='PASS', connections=16, samples=[{} for _ in range(16)])
    assert native.validate_result('destination', 16, [final], server)['ownership_all_zero']
    for rows, result in [([], server), ([{}], server), ([final], server | {'connections': 15}),
                         ([final], server | {'samples': [{}]}),
                         ([final | {RUST_CLEANUP_FIELDS[0]: True}], server)]:
        with pytest.raises(ValueError):
            native.validate_result('destination', 16, rows, result)


@pytest.mark.parametrize('cancel', [False, True])
def test_failed_owned_child_is_killed_reaped_and_failure_sealed(tmp_path, monkeypatch, cancel):
    import json
    from types import SimpleNamespace

    bins, authority, lifecycle = (tmp_path / n for n in ('bins', 'authority', 'lifecycle'))
    for p in (bins, authority, lifecycle):
        p.mkdir()
    for name in native.NAMES.values():
        (bins / name).write_bytes(b'executable fixture')
    build = tmp_path / 'build.json'
    build.write_text(json.dumps(dict(source_sha='a' * 40, build_profile='release',
        binary_sha256={n: native.digest(bins / n) for n in native.NAMES.values()},
        build_commands=['fixture'], toolchains={'fixture': True})))
    output = tmp_path / 'output'
    args = SimpleNamespace(output=output, authority=authority, lifecycle=lifecycle, binaries=bins,
        build_manifest=build, bind='127.0.0.1:0', role='destination', count=16, shards=2, rate=100,
        cores=1, ready_input=None, destination_address=None)
    events = []

    class Child:
        pid = 123
        returncode = None

        def wait(self, timeout):
            events.append('wait')
            self.returncode = -9
            return -9

    def launch(*a, **kw):
        assert kw['start_new_session']
        events.append('spawn')
        return Child()

    def fail(*a, **kw):
        raise RuntimeError('sampler failure fixture')

    def cancellation():
        if cancel and 'spawn' in events:
            raise InterruptedError('cancel fixture')

    monkeypatch.setattr(native.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(native, 'git_state', lambda: ('a' * 40, ''))
    monkeypatch.setattr(native, 'environment', lambda _: dict(selected_cpus=[0], taskset='taskset'))
    monkeypatch.setattr(native, 'immutable_fixture', lambda *a: {'fixture': True})
    monkeypatch.setattr(native.os, 'environ', {})
    monkeypatch.setattr(native.os, 'getuid', lambda: 1000, raising=False)
    monkeypatch.setattr(native.os, 'killpg', lambda pid, sig: events.append(('kill', pid)), raising=False)
    monkeypatch.setattr(native.signal, 'SIGKILL', 9, raising=False)
    monkeypatch.setattr(native.subprocess, 'Popen', launch)
    monkeypatch.setattr(native, 'wait_target_exec', lambda *a, **kw: None)
    monkeypatch.setattr(native, 'observe_child', fail)
    with pytest.raises((RuntimeError, InterruptedError)):
        native.execute(args, check_cancelled=cancellation)
    assert events == ['spawn', ('kill', 123), 'wait']
    assert (output / 'failure.json').is_file() and (output / 'checksums.sha256').is_file()
    assert not (output / 'result.json').exists()
    assert json.loads((output / 'forced-cleanup.json').read_text())['valid'] is False
