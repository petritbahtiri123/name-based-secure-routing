import json
from pathlib import Path

import pytest

from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_pair import SHA, fixture, put


@pytest.mark.parametrize('mode', ['direct', 'nbsr'])
def test_fixed_work_replaces_duration_and_warmup_symmetrically(tmp_path, mode):
    from scripts.performance.linux_native_peer import native_command
    cell = dict(path=mode, cores=1, payload_bytes=1024, streams=64, outstanding=1, operations_per_stream=1000)
    argv, _ = native_command(cell, 'source', Path('/bins'), Path('/authority'), tmp_path,
                             bind='192.0.2.10:0', endpoint='192.0.2.11:4444')
    assert '--p2a-duration-seconds' not in argv
    assert argv[argv.index('--p2a-operations-per-stream') + 1] == '1000'
    assert argv[argv.index('--p2a-warmup-seconds') + 1] == '0'


@pytest.mark.parametrize('operations,depth', [(0, 1), (-1, 1), (10001, 1), (True, 1), (10, 2)])
def test_fixed_work_invalid_bounds_or_depth_rejected(tmp_path, operations, depth):
    from scripts.performance.linux_native_peer import native_command
    with pytest.raises(ValueError):
        native_command(dict(path='direct', cores=1, payload_bytes=1024, streams=64,
                            outstanding=depth, operations_per_stream=operations),
                       'source', Path('/bins'), Path('/authority'), tmp_path,
                       bind='192.0.2.10:0', endpoint='192.0.2.11:4444')


def fixed_fixture(tmp_path, mode='nbsr', count=128):
    source, destination = fixture(tmp_path, mode)
    for root in (source, destination):
        env = json.loads((root / 'environment.json').read_text())
        env['cell']['operations_per_stream'] = 2
        env.update(warmup_seconds=0, duration_seconds=None)
        put(root, 'environment.json', env)
    cmd = json.loads((source / 'command.json').read_text())
    argv = cmd['argv']
    argv[argv.index('--p2a-warmup-seconds') + 1] = '0'
    pos = argv.index('--p2a-duration-seconds')
    argv[pos:pos + 2] = ['--p2a-operations-per-stream', '2']
    put(source, 'command.json', cmd)
    row = json.loads((source / 'validated-result.json').read_text())
    row['completed_operations'] = count
    put(source, 'validated-result.json', row)
    put(source, 'stdout', row)
    result = json.loads((source / 'result.json').read_text())
    result.update(completed_operations=count, application_gbps=16 * 1024 * count / row['measured_ns'])
    put(source, 'result.json', result)
    for root in (source, destination):
        seal_output(root)
    return source, destination


@pytest.mark.parametrize('mode', ['direct', 'nbsr'])
def test_fixed_pair_requires_exact_work_but_not_capacity(tmp_path, mode):
    from scripts.performance.linux_native_pair import analyze_pair
    roots = fixed_fixture(tmp_path, mode)
    result = analyze_pair(*roots, source_sha=SHA)
    assert result['cell']['operations_per_stream'] == 2
    assert result['strict_stable_capacity'] == 'NOT_PROVEN'


def test_live_source_validation_rejects_incomplete_fixed_work(tmp_path):
    from scripts.performance.linux_native_peer import validate_source
    source, _ = fixed_fixture(tmp_path, count=127)
    cell = json.loads((source / 'environment.json').read_text())['cell']
    with pytest.raises(ValueError, match='fixed'):
        validate_source(source, cell)


@pytest.mark.parametrize('fault', ['short', 'extra', 'duration', 'warmup', 'peer-mode'])
def test_fixed_pair_rejects_incomplete_or_mismatched_bound(tmp_path, fault):
    from scripts.performance.linux_native_pair import analyze_pair
    source, destination = fixed_fixture(tmp_path, count=127 if fault == 'short' else 129 if fault == 'extra' else 128)
    if fault == 'duration':
        cmd = json.loads((source / 'command.json').read_text())
        cmd['argv'] += ['--p2a-duration-seconds', '20']
        put(source, 'command.json', cmd)
    elif fault in ('warmup', 'peer-mode'):
        env = json.loads((destination / 'environment.json').read_text())
        if fault == 'warmup':
            env['warmup_seconds'] = 3
        else:
            env['cell'].pop('operations_per_stream')
        put(destination, 'environment.json', env)
    for root in (source, destination):
        seal_output(root)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)


@pytest.mark.parametrize('repeats', [3, 5])
def test_packet_fixed_work_cohort_requires_five_pairs(tmp_path, repeats):
    from scripts.performance.linux_native_cohort import analyze_cohort
    from tests.performance.test_linux_native_cohort import cohort
    path = cohort(tmp_path, counts=(128,) * repeats)
    for entry in json.loads(path.read_text())['attempts']:
        for role in ('source', 'destination'):
            root = tmp_path / entry[role]
            env = json.loads((root / 'environment.json').read_text())
            env['cell']['operations_per_stream'] = 2
            env.update(warmup_seconds=0, duration_seconds=None)
            put(root, 'environment.json', env)
            if role == 'source':
                command = json.loads((root / 'command.json').read_text())
                argv = command['argv']
                argv[argv.index('--p2a-warmup-seconds') + 1] = '0'
                pos = argv.index('--p2a-duration-seconds')
                argv[pos:pos + 2] = ['--p2a-operations-per-stream', '2']
                put(root, 'command.json', command)
            seal_output(root)
    if repeats == 3:
        with pytest.raises(ValueError, match='five'):
            analyze_cohort(path, source_sha=SHA)
    else:
        assert analyze_cohort(path, source_sha=SHA)['repeats_per_path'] == 5
