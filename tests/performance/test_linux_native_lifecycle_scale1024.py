from pathlib import Path

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance.linux_native_lifecycle_control import LifecycleBarrier
from scripts.performance.linux_native_lifecycle_coordinator import EventLedger, validate_config
from scripts.performance.post_close_cleanup import FIELDS
from tests.performance.test_linux_native_lifecycle import fixture
from tests.performance.test_linux_native_lifecycle_coordinator import config


def test_1024_command_preserves_payload_shards_gates_and_rate():
    source, overrides = fixture(count=1024, rate=200)
    assert not overrides
    for flag, expected in [('--lifecycle-clients', '1024'), ('--lifecycle-offered-rate', '200'),
                           ('--lifecycle-source-shards', '2'), ('--payload-bytes', '1024'),
                           ('--b3-materialized-streams', '1')]:
        assert source[source.index(flag)+1] == expected
    assert '--hold-for-release' in source
    destination, overrides = fixture('destination', count=1024, rate=200)
    assert overrides['NBSR_PERF_LIFECYCLE_CONNECTIONS'] == '1024'
    assert overrides['NBSR_PERF_LIFECYCLE_OFFERED_RATE'] == '200'
    assert '--b3-report-gate' in destination
    assert not any('keep-alive' in arg or 'timeout' in arg for arg in source+destination)


def test_1024_configuration_and_parser_accept_with_existing_bounds():
    value = config() | dict(count=1024, rate=200)
    assert validate_config(value) == value
    assert EventLedger(1024).count == 1024
    arguments = ['--role', 'source', '--bind', '192.0.2.1:0', '--count', '1024', '--rate', '200']
    for name in ('binaries', 'build-manifest', 'authority', 'lifecycle', 'output'):
        arguments += ['--'+name, '/'+name]
    assert native.argument_parser().parse_args(arguments).count == 1024


def test_1024_barrier_never_accepts_1023_clients(tmp_path):
    root, output = tmp_path/'markers', tmp_path/'output'
    root.mkdir()
    output.mkdir()
    now = [0]
    state = LifecycleBarrier(role='source', count=1024, root=root, output=output,
        capture=lambda: dict(status='MEASURED_LIVE_SOCKET_SNAPSHOT', sockets=[{}]*1024), clock=lambda: now[0])
    for i in range(1023):
        (root/f'connection-{i}.active').touch()
    assert state.poll() == []
    with pytest.raises(ValueError, match='all active'):
        state.request('release')
    (root/'connection-1023.active').touch()
    assert state.poll() == [dict(event='active', count=1024)]
    now[0] = 2_000_000_000
    assert state.request('release') == [dict(event='released', count=1024)]
    assert len(list(root.glob('*.release'))) == 1024


def test_1024_raw_results_still_require_every_client_and_zero_ownership():
    rows = [dict(success=True, logical_client_id=i, bytes_transmitted=1024, bytes_received=1024) for i in range(1024)]
    rows.append(dict(phase='lifecycle_cleanup', **dict.fromkeys(FIELDS, 0)))
    assert native.validate_result('source', 1024, rows, None)['successful'] == 1024
    with pytest.raises(ValueError, match='cardinality'):
        native.validate_result('source', 1024, rows[1:], None)
    rows[-1][FIELDS[0]] = 1
    with pytest.raises(ValueError, match='eleven'):
        native.validate_result('source', 1024, rows, None)


def test_no_implicit_extension_to_2048():
    with pytest.raises(ValueError):
        fixture(count=2048)
    with pytest.raises(ValueError):
        validate_config(config() | dict(count=2048))
    with pytest.raises(ValueError):
        LifecycleBarrier(role='source', count=2048, root=Path('/unused'), output=Path('/unused'), capture=lambda: None)
