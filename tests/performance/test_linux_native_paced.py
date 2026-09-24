import json
from pathlib import Path

import pytest

from scripts.performance.linux_native_peer import native_command
from tests.performance.test_b5_stream import records


def cell():
    return dict(path='nbsr', cores=1, payload_bytes=1024, streams=1, outstanding=1,
                diagnostic_rate=[100, 1])


def transcript():
    progress, final = records()
    values = []
    for index in range(1, 5):
        counters = dict(offered=index * 500, reserved=index * 500, issued=index * 500,
                        completed=index * 500, missed=0, unreserved_current=0)
        values.append(progress | counters | dict(window_index=index,
            elapsed_ns=index * 5_000_000_000, interval_start_ns=(index-1)*5_000_000_000,
            interval_end_ns=index*5_000_000_000, issue_deadline_ns=20_000_000_000,
            group_counters=[dict(group_id=0, **counters)], goodput_bytes_per_second=204800,
            sample_count=500, sample_stride=1, sample_capacity=1024,
            p50_latency_ns=100, p95_latency_ns=200, p99_latency_ns=300))
    values.append(final | counters | dict(measurement_duration_ns=20_000_000_000,
        group_counters=[dict(group_id=0, **counters)], max_outstanding_observed=1))
    return values


@pytest.mark.parametrize('mode', ['direct', 'nbsr'])
def test_paced_native_command_binds_existing_pacer_and_keeps_native_address(tmp_path, mode):
    shape = cell() | {'path': mode}
    argv, _ = native_command(shape, 'source', Path('/bins'), Path('/private'), tmp_path,
        bind='192.0.2.1:0', endpoint='192.0.2.2:443', post_close_reports=True)
    for flag, value in (('--b5-rate-numerator', '100'), ('--b5-rate-denominator', '1'),
                        ('--p2a-progress-seconds', '5'), ('--p2a-groups', '1'),
                        ('--benchmark-client-bind', '192.0.2.1:0')):
        assert argv[argv.index(flag)+1] == value


@pytest.mark.parametrize('rate', [None, True, [0, 1], [1, 0], [1.0, 1], [True, 1], [1], [2**64, 1]])
def test_invalid_paced_rate_rejected(tmp_path, rate):
    with pytest.raises(ValueError):
        native_command(cell() | {'diagnostic_rate': rate}, 'source', Path('/bins'), Path('/private'),
            tmp_path, bind='192.0.2.1:0', endpoint='192.0.2.2:443', post_close_reports=True)


@pytest.mark.parametrize('fault', ['no-report', 'fixed-work', 'phase'])
def test_paced_mode_does_not_mix_measurement_contracts(tmp_path, fault):
    shape = cell() | ({'operations_per_stream': 1} if fault == 'fixed-work' else {})
    with pytest.raises(ValueError):
        native_command(shape, 'source', Path('/bins'), Path('/private'), tmp_path,
            bind='192.0.2.1:0', endpoint='192.0.2.2:443', post_close_reports=fault != 'no-report',
            phase_control='127.0.0.1:1000' if fault == 'phase' else None)


def test_paced_transcript_remains_diagnostic(tmp_path):
    from scripts.performance.linux_native_paced import read_paced
    path = tmp_path / 'stdout'
    path.write_text(''.join(json.dumps(row)+'\n' for row in transcript()))
    result = read_paced(path, cell())
    assert result['schema'] == 'nbsr-native-paced-diagnostic-v1'
    assert result['completed_operations'] == 2000
    assert result['achieved_offered_ratio'] == 1
    assert result['strict_stable_capacity'] == 'NOT_ESTABLISHED'
    assert result['drift_failures'] == []


@pytest.mark.parametrize('fault', ['partial', 'counter', 'duration', 'shape', 'after-final', 'missing-final', 'duplicate-key', 'errors', 'timeouts'])
def test_paced_transcript_fails_closed(tmp_path, fault):
    from scripts.performance.linux_native_paced import read_paced
    rows = transcript()
    if fault == 'counter':
        rows[0]['completed'] += 1
    elif fault == 'duration':
        rows[-1]['measurement_duration_ns'] += 1
    elif fault == 'shape':
        rows[-1]['streams_per_group'] = 2
    elif fault == 'after-final':
        rows.append({'event': 'diagnostic'})
    elif fault == 'missing-final':
        rows.pop()
    elif fault in ('errors', 'timeouts'):
        rows[0][fault] = 1
    wire = ''.join(json.dumps(row)+'\n' for row in rows)
    if fault == 'partial':
        wire = wire[:-1]
    elif fault == 'duplicate-key':
        wire = '{"event":"diagnostic","event":"diagnostic"}\n' + wire
    path = tmp_path / 'stdout'
    path.write_text(wire)
    with pytest.raises(ValueError):
        read_paced(path, cell())


def test_valid_degraded_paced_trajectory_preserves_failed_drift(tmp_path):
    from scripts.performance.linux_native_paced import read_paced
    rows = transcript()
    rows[-2]['p99_latency_ns'] = 1000
    path = tmp_path / 'stdout'
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    result = read_paced(path, cell())
    assert result['drift_failures'] == [dict(window=4, reason='p99')]
    assert result['strict_stable_capacity'] == 'NOT_ESTABLISHED'


def test_coordinator_declares_same_diagnostic_rate_on_both_roles():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments
    from tests.performance.test_linux_native_finite_run import config
    value = config() | dict(diagnostic_rate=[100, 1], post_close_reports=True)
    validate_config(value)
    for role in ('source', 'destination'):
        argv = endpoint_arguments(value, role)
        index = argv.index('--diagnostic-rate')
        assert argv[index + 1:index + 3] == ['100', '1']
    with pytest.raises(ValueError):
        validate_config(value | {'post_close_reports': False})


@pytest.mark.parametrize('fault', [None, 'command', 'summary', 'asymmetric', 'undeclared'])
@pytest.mark.parametrize('observed', [False, True])
def test_collected_paced_pair_validates_raw_accounting_and_executed_rate(tmp_path, fault, observed):
    from scripts.performance.linux_b5_placement import seal_output
    from scripts.performance.linux_native_paced import read_paced
    from scripts.performance.linux_native_pair import analyze_pair
    from tests.performance.test_linux_native_pair import fixture, SHA, put
    roots = fixture(tmp_path, 'direct')
    for role, root in zip(('source', 'destination'), roots):
        env = json.loads((root / 'environment.json').read_text())
        env['cell']['diagnostic_rate'] = [100, 1]
        env['post_close_reports'] = True
        put(root, 'environment.json', env)
        result = json.loads((root / 'result.json').read_text())
        result['runtime_ownership_cleanup'] = 'NOT_APPLICABLE_DIRECT'
        if role == 'source':
            rows = transcript()
            rows[-1]['streams_per_group'] = 64
            (root / 'stdout').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            summary = read_paced(root / 'stdout', env['cell'])
            put(root, 'validated-result.json', summary)
            result.update(completed_operations=2000, application_gbps=16 * 1024 * 2000 / summary['measured_ns'])
            command = json.loads((root / 'command.json').read_text())
            command['argv'] += ['--p2a-groups', '1', '--p2a-progress-seconds', '5',
                                '--b5-rate-numerator', '99' if fault == 'command' else '100',
                                '--b5-rate-denominator', '1']
            put(root, 'command.json', command)
            if observed:
                from scripts.performance.linux_native_source_observer import SourceObserver
                from tests.performance.test_linux_native_source_observer import Sampler
                env['source_live_guard'] = True
                put(root, 'environment.json', env)
                with SourceObserver(root, pid=123, cpus=[0], payload_bytes=1024,
                    deadline_ns=100_000_000_000, sampler_factory=Sampler, clock=lambda: 25_000_000_000) as live:
                    live.poll()
                    live.stop()
                    result['source_live_guard'] = live.finish(0)
            if fault == 'summary':
                put(root, 'validated-result.json', summary | {'achieved_offered_ratio': .5})
        if fault == 'undeclared' or (fault == 'asymmetric' and role == 'destination'):
            env['cell'].pop('diagnostic_rate')
            put(root, 'environment.json', env)
        put(root, 'result.json', result)
        seal_output(root)
    if fault:
        with pytest.raises(ValueError):
            analyze_pair(*roots, source_sha=SHA)
    else:
        result = analyze_pair(*roots, source_sha=SHA)
        assert result['workload_mode'] == 'PACED_DIAGNOSTIC'
        assert result['achieved_offered_ratio'] == 1
        assert result['strict_stable_capacity'] == 'NOT_PROVEN'
        if observed:
            assert result['live_private_growth'] == 'SOURCE_ONLY_DIAGNOSTIC'
            assert result['destination_private_growth'] == 'NOT_MEASURED'
