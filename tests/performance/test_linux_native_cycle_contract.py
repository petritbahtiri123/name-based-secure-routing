from pathlib import PurePosixPath as Path

import pytest

from scripts.performance import linux_native_lifecycle as native


def command(role, cycles=4):
    return native.cycle_command(role=role, cycles=cycles, binaries=Path('/bin'),
        authority=Path('/private/auth'), lifecycle=Path('/private/cycles'),
        output=Path('/evidence'), bind='192.0.2.1:0',
        endpoint='192.0.2.2:4000' if role == 'source' else None)


def test_source_sequential_cycles_keep_one_process_and_final_cooldown_gate():
    argv, env = command('source')
    assert argv[argv.index('--connections') + 1] == '4'
    assert argv[argv.index('--services') + 1] == '1'
    assert argv[argv.index('--streams-per-service') + 1] == '1'
    assert argv[argv.index('--lifecycle-final-release') + 1] == '/private/cycles/source.final-release'
    assert '--hold-for-release' in argv and '--b3-materialized-streams' in argv
    assert not any(flag in argv for flag in ('--lifecycle-clients', '--lifecycle-source-shards', '--lifecycle-offered-rate'))
    assert env == {}


def test_destination_sequential_cycles_preserve_report_gate_without_fanout():
    argv, env = command('destination')
    assert env['NBSR_PERF_LIFECYCLE_CONNECTIONS'] == '4'
    assert env['NBSR_PERF_LIFECYCLE_SERVICES'] == env['NBSR_PERF_STREAMS_PER_SERVICE'] == '1'
    assert not any(key in env for key in ('NBSR_PERF_CONCURRENT_SESSIONS', 'NBSR_PERF_LIFECYCLE_SERIAL_ACCEPT', 'NBSR_PERF_LIFECYCLE_OFFERED_RATE'))
    assert argv[argv.index('--b3-report-gate') + 1] == '/private/cycles'
    assert argv[argv.index('--diagnostic-drain-seconds') + 1] == '2'


@pytest.mark.parametrize('cycles', [0, 3, 32, True, 4.0, '4'])
def test_invalid_cycle_count_rejects(cycles):
    with pytest.raises(ValueError, match='cycle count'):
        command('source', cycles)


def test_concurrent_bundle_contract_is_unchanged():
    argv, env = native.command(role='source', count=16, shards=2, rate=100,
        binaries=Path('/bin'), authority=Path('/private/auth'),
        lifecycle=Path('/private/cycles'), output=Path('/evidence'),
        bind='192.0.2.1:0', endpoint='192.0.2.2:4000')
    assert argv[argv.index('--connections') + 1] == '1'
    assert argv[argv.index('--lifecycle-clients') + 1] == '16'
    assert '--lifecycle-final-release' not in argv and env == {}
