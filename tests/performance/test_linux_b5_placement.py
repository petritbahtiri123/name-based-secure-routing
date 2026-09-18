from copy import deepcopy

import pytest


def row(placement, repeat, *, p99=100, failed=False):
    return dict(placement=placement, repeat=repeat, valid=not failed,
        classification='FAIL_DIAGNOSTIC_RETAINED' if failed else 'DIAGNOSTIC',
        diagnostic_continue_on_performance_failure=True,
        diagnostic_gate_failures=[{'reason': 'live p99 drift'}] if failed else [],
        gbps=1, window_p99_median_ns=p99,
        final=dict(errors=0, timeouts=0, all_groups_joined=True, evidence_valid=True))


def test_counterbalanced_pairs_retain_failed_gates_without_acceptance_claim():
    from scripts.performance.linux_b5_placement import run_pairs
    calls, kept = [], []

    def run(placement, repeat):
        calls.append((placement, repeat))
        return row(placement, repeat, failed=True)

    report = run_pairs(run, kept.append)
    assert calls == [('shared', 1), ('split', 1), ('split', 2),
                     ('shared', 2), ('shared', 3), ('split', 3)]
    assert len(kept) == 6 and all(not r['valid'] for r in kept)
    assert report['repeats_per_placement'] == 3
    assert report['failed_gate_runs'] == 6
    assert report['sustained_stability'] == 'NOT_PROVEN'


def test_high_latency_cv_extends_both_arms_to_five_without_replacing_rows():
    from scripts.performance.linux_b5_placement import run_pairs
    kept = []
    report = run_pairs(lambda p, n: row(p, n, p99=200 if n == 1 else 100), kept.append)
    assert report['repeats_per_placement'] == 5 and len(kept) == 10
    assert report['dispersion_unresolved'] is True
    assert kept[0]['window_p99_median_ns'] == 200


@pytest.mark.parametrize('change', [dict(classification='FAIL'), dict(cleanup_errors=['lost peer']),
    dict(final={'errors': 1, 'timeouts': 0, 'all_groups_joined': True, 'evidence_valid': True}),
    dict(final={'errors': 0, 'timeouts': 0, 'all_groups_joined': False, 'evidence_valid': True}),
    dict(window_p99_median_ns=float('nan')), dict(diagnostic_gate_failures=[])])
def test_correctness_or_incomplete_failure_is_retained_then_stops(change):
    from scripts.performance.linux_b5_placement import run_pairs
    kept = []

    def run(p, n):
        result = row(p, n, failed=True)
        if p == 'split':
            result.update(deepcopy(change))
        return result

    with pytest.raises(ValueError):
        run_pairs(run, kept.append)
    assert len(kept) == 2


def test_repeated_identity_cannot_be_substituted():
    from scripts.performance.linux_b5_placement import run_pairs
    kept = []
    with pytest.raises(ValueError, match='identity'):
        run_pairs(lambda p, n: row('shared', 1), kept.append)
    assert len(kept) == 2


@pytest.mark.parametrize('expected_failure', [True, False])
def test_child_exception_is_only_tolerated_for_retained_performance_failure(tmp_path, monkeypatch, expected_failure):
    import json
    from types import SimpleNamespace
    from scripts.performance import linux_b5_placement as module
    args = SimpleNamespace(binaries=tmp_path, build_manifest=tmp_path / 'build.json',
        path='nbsr', rate=[1, 1], payload=16384, streams=8, depth=1,
        warmup=3, duration=300, progress=30)

    def child(options):
        options.output.mkdir()
        (options.output / 'records.json').write_text(json.dumps([row('shared', 1, failed=True)]))
        raise RuntimeError('invalid partial run retained; no replacement' if expected_failure else 'source changed')

    monkeypatch.setattr(module.campaign, 'execute', child)
    result = module.execute_cell(args, 'shared', 1, tmp_path / 'new')
    if expected_failure:
        assert result['classification'] == 'FAIL_DIAGNOSTIC_RETAINED'
    else:
        assert result['classification'] == 'FAIL' and result['controller_error'] == 'source changed'


def test_parent_index_covers_nested_indexes(tmp_path):
    from scripts.performance.linux_b5_placement import seal_output
    child = tmp_path / 'child'
    child.mkdir()
    (child / 'checksums.sha256').write_text('child index')
    seal_output(tmp_path)
    assert '  child/checksums.sha256\n' in (tmp_path / 'checksums.sha256').read_text()
