import copy
import json

import pytest

from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_b5_ceiling import LINUX
from tests.performance.test_linux_native_pair import SHA, fixture, put
from tests.performance.test_linux_native_post_close import enable_reports


def manifest(tmp_path, *, effect=1, counts=None):
    attempts = []
    for repeat in range(1, 6):
        for observer in (('off', 'on') if repeat % 2 else ('on', 'off')):
            parent = tmp_path / f'{observer}-{repeat}'
            parent.mkdir()
            roots = fixture(parent)
            count = (counts or [100] * 5)[repeat-1]
            count = int(count * effect) if observer == 'on' else count
            for role, root in zip(('source', 'destination'), roots):
                env = json.loads((root / 'environment.json').read_text())
                env['linux_environment'] = copy.deepcopy(LINUX)
                put(root, 'environment.json', env)
                if observer == 'on':
                    enable_reports(root, role)
                if role == 'source':
                    row = json.loads((root / 'validated-result.json').read_text())
                    row.update(completed_operations=count, p50_latency_ns=100,
                               p95_latency_ns=500, p99_latency_ns=1000,
                               schema='nbsr-p2a-repeat-v2', configured_total_outstanding=64,
                               max_outstanding_per_stream_observed=1)
                    put(root, 'validated-result.json', row)
                    put(root, 'stdout', row)
                    result = json.loads((root / 'result.json').read_text())
                    result.update(completed_operations=count, application_gbps=16*1024*count/row['measured_ns'])
                    put(root, 'result.json', result)
                sample = json.loads((root / 'resources.ndjson').read_text())
                sample.update(pid=1000 + 2 * len(attempts) + (role == 'destination'), start_ticks=100+len(attempts))
                put(root, 'resources.ndjson', sample)
                put(root, 'pid.json', dict(pid=sample['pid'], owns_process_group=True))
                put(root, 'exit.json', dict(exit_code=0, final_sample=sample))
                result = json.loads((root / 'result.json').read_text())
                put(root, 'result.json', result | {'final_sample': sample})
                if observer == 'on':
                    report = json.loads((root / 'cleanup.json').read_text())
                    put(root, 'cleanup.json', report | {'pid': sample['pid']})
                seal_output(root)
            attempts.append(dict(repeat=repeat, observer=observer,
                source=str(roots[0].relative_to(tmp_path)), destination=str(roots[1].relative_to(tmp_path))))
    path = tmp_path / 'observer.json'
    put(tmp_path, path.name, dict(schema='nbsr-native-observer-v1', attempts=attempts, interruptions=[]))
    return path


def test_valid_observer_gate_is_not_capacity_or_hardware(tmp_path):
    from scripts.performance.linux_native_observer import qualify
    result = qualify(manifest(tmp_path), source_sha=SHA)
    assert result['qualified'] is True
    assert result['pairs'] == 5
    assert result['strict_stable_capacity'] == result['external_hardware'] == 'NOT_PROVEN'


def test_resealed_fractional_operation_count_cannot_qualify(tmp_path):
    from scripts.performance.linux_native_observer import qualify
    path = manifest(tmp_path)
    root = tmp_path / 'on-1/source'
    row = json.loads((root / 'validated-result.json').read_text())
    row['completed_operations'] = 100.5
    put(root, 'validated-result.json', row)
    put(root, 'stdout', row)
    result = json.loads((root / 'result.json').read_text())
    result.update(completed_operations=100.5, application_gbps=16*1024*100.5/row['measured_ns'])
    put(root, 'result.json', result)
    seal_output(root)
    with pytest.raises(ValueError, match='exact operation'):
        qualify(path, source_sha=SHA)


@pytest.mark.parametrize('kind', ['effect', 'variance', 'interruption'])
def test_valid_unfavorable_runs_remain_retained_without_qualification(tmp_path, kind):
    from scripts.performance.linux_native_observer import qualify
    path = manifest(tmp_path, effect=.8 if kind == 'effect' else 1,
                    counts=[50, 100, 100, 100, 100] if kind == 'variance' else None)
    if kind == 'interruption':
        value = json.loads(path.read_text())
        value['interruptions'] = ['retained disk-reserve stop between cells']
        put(tmp_path, path.name, value)
    result = qualify(path, source_sha=SHA)
    assert result['qualified'] is False
    assert len(result['attempts']) == 10


@pytest.mark.parametrize('fault', ['duplicate', 'order', 'under-repeat', 'mode', 'authority', 'placement', 'other-observer', 'rate'])
def test_invalid_observer_join_is_rejected(tmp_path, fault):
    from scripts.performance.linux_native_observer import qualify
    path = manifest(tmp_path)
    value = json.loads(path.read_text())
    if fault == 'duplicate':
        value['attempts'][2]['source'] = value['attempts'][1]['source']
        value['attempts'][2]['destination'] = value['attempts'][1]['destination']
    elif fault == 'order':
        value['attempts'][0], value['attempts'][1] = value['attempts'][1], value['attempts'][0]
    elif fault == 'under-repeat':
        value['attempts'] = value['attempts'][:8]
    else:
        root = tmp_path / value['attempts'][1]['source']
        env = json.loads((root / 'environment.json').read_text())
        if fault == 'mode':
            value['attempts'][1]['observer'] = 'off'
        elif fault == 'authority':
            env['certificates_sha256']['source.der'] = 'd' * 64
        elif fault == 'placement':
            env['linux_environment']['kernel'] = 'other kernel'
        elif fault == 'other-observer':
            env['phase_control_endpoint'] = '127.0.0.1:9000'
        elif fault == 'rate':
            env['cell']['diagnostic_rate'] = [100, 1]
        put(root, 'environment.json', env)
        seal_output(root)
    put(tmp_path, path.name, value)
    with pytest.raises(ValueError):
        qualify(path, source_sha=SHA)
