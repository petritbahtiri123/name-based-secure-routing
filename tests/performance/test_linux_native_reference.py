import copy
import json

import pytest

from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_b5_ceiling import LINUX
from tests.performance.test_linux_native_observer import manifest as observer_manifest
from tests.performance.test_linux_native_pair import SHA, fixture, put


def reference(tmp_path, *, effect=1):
    observer = tmp_path / 'observer'
    observer.mkdir()
    observer_path = observer_manifest(observer, effect=effect)
    attempts = []
    for repeat in range(1, 6):
        parent = tmp_path / f'direct-{repeat}'
        parent.mkdir()
        direct = fixture(parent, 'direct')
        for role, root in zip(('source', 'destination'), direct):
            env = json.loads((root / 'environment.json').read_text())
            env.update(linux_environment=copy.deepcopy(LINUX), post_close_reports=True)
            put(root, 'environment.json', env)
            sample = json.loads((root / 'resources.ndjson').read_text())
            sample['pid'] = 10000 + repeat * 2 + (role == 'destination')
            put(root, 'resources.ndjson', sample)
            put(root, 'pid.json', dict(pid=sample['pid'], owns_process_group=True))
            put(root, 'exit.json', dict(exit_code=0, final_sample=sample))
            result = json.loads((root / 'result.json').read_text())
            result.update(final_sample=sample, runtime_ownership_cleanup='NOT_APPLICABLE_DIRECT')
            put(root, 'result.json', result)
            if role == 'source':
                row = json.loads((observer / f'off-{repeat}' / role / 'validated-result.json').read_text())
                row['path'] = 'direct'
                put(root, 'validated-result.json', row)
                put(root, 'stdout', row)
            seal_output(root)
        for mode in (('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct')):
            roots = direct if mode == 'direct' else [observer / f'on-{repeat}' / role for role in ('source', 'destination')]
            attempts.append(dict(path=mode, depth=1, repeat=repeat,
                source=str(roots[0].relative_to(tmp_path)), destination=str(roots[1].relative_to(tmp_path))))
    value = dict(schema='nbsr-native-reference-v1', depths=[1], attempts=attempts,
                 observers={'1': str(observer_path.relative_to(tmp_path))})
    put(tmp_path, 'reference.json', value)
    return tmp_path / 'reference.json'


def test_qualified_reference_derives_exact_load_but_not_hardware_claim(tmp_path):
    from scripts.performance.linux_native_reference import analyze_reference, load_reference
    path = reference(tmp_path)
    result = analyze_reference(path, source_sha=SHA)
    assert result['qualified'] is True
    load = load_reference(path, current_sha=SHA, identities=result['identities'],
                          shape=result['shape'], path='nbsr', depth=1, percent=75)
    assert (load['rate_numerator'], load['rate_denominator']) == (15, 4)
    assert load['external_hardware'] == 'NOT_PROVEN'


def test_rejected_observer_cannot_authorize_paced_reference(tmp_path):
    from scripts.performance.linux_native_reference import analyze_reference, load_reference
    path = reference(tmp_path, effect=.8)
    result = analyze_reference(path, source_sha=SHA)
    assert result['qualified'] is False
    assert len(result['rows']) == 10
    with pytest.raises(ValueError):
        load_reference(path, current_sha=SHA, identities=result['identities'],
                       shape=result['shape'], path='nbsr', depth=1, percent=75)


@pytest.mark.parametrize('fault', ['source', 'placement', 'shape', 'depth', 'percent'])
def test_reference_load_binds_current_execution(tmp_path, fault):
    from scripts.performance.linux_native_reference import analyze_reference, load_reference
    manifest = reference(tmp_path)
    result = analyze_reference(manifest, source_sha=SHA)
    args = dict(current_sha=SHA, identities=result['identities'], shape=result['shape'],
                path='nbsr', depth=1, percent=75)
    if fault == 'source':
        args['current_sha'] = 'b' * 40
    elif fault == 'placement':
        args['identities'] = {}
    elif fault == 'shape':
        args['shape'] = args['shape'] | {'streams': 1}
    elif fault == 'depth':
        args['depth'] = 2
    elif fault == 'percent':
        args['percent'] = 90
    with pytest.raises(ValueError):
        load_reference(manifest, **args)


@pytest.mark.parametrize('fault', ['duplicate', 'order', 'partial', 'cleanup'])
def test_reference_cannot_relabel_incomplete_or_failed_evidence(tmp_path, fault):
    from scripts.performance.linux_native_reference import analyze_reference
    manifest = reference(tmp_path)
    value = json.loads(manifest.read_text())
    if fault == 'duplicate':
        value['attempts'][2]['source'] = value['attempts'][1]['source']
    elif fault == 'order':
        value['attempts'][0], value['attempts'][1] = value['attempts'][1], value['attempts'][0]
    elif fault == 'partial':
        value['attempts'] = value['attempts'][:8]
    else:
        root = tmp_path / value['attempts'][1]['source']
        report = json.loads((root / 'cleanup.json').read_text())
        report['ownership']['transport_sessions_current_live'] = 1
        put(root, 'cleanup.json', report)
        seal_output(root)
    put(tmp_path, manifest.name, value)
    with pytest.raises(ValueError):
        analyze_reference(manifest, source_sha=SHA)
