import json
import shutil

import pytest

from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_pair import SHA, fixture, put


def cohort(tmp_path, counts=(100, 100, 100)):
    entries = []
    for repeat, count in enumerate(counts, 1):
        for mode in ('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct'):
            root = tmp_path / f'{mode}-{repeat}'
            root.mkdir()
            source, destination = fixture(root, mode)
            row = json.loads((source / 'validated-result.json').read_bytes())
            row['completed_operations'] = count
            put(source, 'validated-result.json', row)
            put(source, 'stdout', row)
            result = json.loads((source / 'result.json').read_bytes())
            result.update(completed_operations=count, application_gbps=16 * 1024 * count / row['measured_ns'])
            put(source, 'result.json', result)
            for role_index, peer in enumerate((source, destination)):
                sample = json.loads((peer / 'resources.ndjson').read_text())
                sample.update(pid=1000 + 2 * len(entries) + role_index, start_ticks=100 + len(entries))
                put(peer, 'resources.ndjson', sample)
                put(peer, 'pid.json', dict(pid=sample['pid'], owns_process_group=True))
                put(peer, 'exit.json', dict(exit_code=0, final_sample=sample))
                peer_result = json.loads((peer / 'result.json').read_bytes())
                peer_result['final_sample'] = sample
                put(peer, 'result.json', peer_result)
                seal_output(peer)
            entries.append(dict(path=mode, repeat=repeat, source=str(source.relative_to(tmp_path)),
                                destination=str(destination.relative_to(tmp_path))))
    path = tmp_path / 'cohort.json'
    put(tmp_path, path.name, dict(schema='nbsr-native-cohort-v1', attempts=entries))
    return path


def test_complete_counterbalanced_cohort_is_not_capacity(tmp_path):
    from scripts.performance.linux_native_cohort import analyze_cohort
    result = analyze_cohort(cohort(tmp_path), source_sha=SHA)
    assert result['status'] == 'PASS_FINITE_COHORT_INTEGRITY'
    assert result['repeats_per_path'] == 3 and len(result['attempts']) == 6
    assert result['strict_stable_capacity'] == result['external_hardware'] == 'NOT_PROVEN'
    assert result['paired_goodput_delta_percent'] == [0, 0, 0]


@pytest.mark.parametrize('counts,expected', [((94, 100, 106), 'requires five'),
    ((100, 100), 'three or five')])
def test_incomplete_or_under_repeated_cohort_is_rejected(tmp_path, counts, expected):
    from scripts.performance.linux_native_cohort import analyze_cohort
    with pytest.raises(ValueError, match=expected):
        analyze_cohort(cohort(tmp_path, counts), source_sha=SHA)


@pytest.mark.parametrize('counts,unresolved', [((94, 100, 106, 100, 100), False),
                                           ((50, 100, 100, 100, 100), True)])
def test_five_retains_unfavorable_valid_results_and_residual_dispersion(tmp_path, counts, unresolved):
    from scripts.performance.linux_native_cohort import analyze_cohort
    result = analyze_cohort(cohort(tmp_path, counts), source_sha=SHA)
    assert result['dispersion_unresolved'] is unresolved
    assert len(result['attempts']) == 10 and result['repeats_per_path'] == 5
    assert result['first_three_cv']['direct'] > .05


@pytest.mark.parametrize('fault', ['order', 'repeat', 'duplicate-root', 'duplicate-bytes', 'authority', 'invalid-peer'])
def test_mixed_or_reused_or_invalid_evidence_is_never_silently_dropped(tmp_path, fault):
    from scripts.performance.linux_native_cohort import analyze_cohort
    path = cohort(tmp_path)
    manifest = json.loads(path.read_bytes())
    entries = manifest['attempts']
    if fault == 'order':
        entries[:2] = entries[1::-1]
    elif fault == 'repeat':
        entries[2]['repeat'] = 1
    elif fault == 'duplicate-root':
        entries[3]['source'] = entries[0]['source']
    elif fault == 'duplicate-bytes':
        for role in ('source', 'destination'):
            target = tmp_path / ('copied-' + role)
            shutil.copytree(tmp_path / entries[0][role], target)
            entries[3][role] = target.name
    elif fault == 'authority':
        for role in ('source', 'destination'):
            root = tmp_path / entries[3][role]
            env = json.loads((root / 'environment.json').read_bytes())
            env['certificates_sha256']['ca.der'] = 'd' * 64
            put(root, 'environment.json', env)
            seal_output(root)
    else:
        (tmp_path / entries[0]['source'] / 'stdout').write_text('invalid')
    put(tmp_path, path.name, manifest)
    with pytest.raises(ValueError):
        analyze_cohort(path, source_sha=SHA)
