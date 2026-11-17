"""Synthetic failure reporting only. Peer/build/resource boundaries are mocked."""
import io
import json
from pathlib import Path

import pytest

from scripts import run_p2a_established as a
from scripts import run_p2b_profile as b


@pytest.mark.parametrize('validities', [[False], [False, True], [True], []])
def test_p2a_writes_analysis_for_invalid_or_empty_repeats(tmp_path, monkeypatch, validities):
    monkeypatch.setattr(a, 'build', lambda _: {})
    monkeypatch.setattr(a, 'write_loopback_authority', lambda _: None)
    monkeypatch.setattr(a, 'build_matrix', lambda: [{'path': 'direct', 'streams': 1, 'payload_bytes': 1}])
    def repeat(cell, number, *_):
        return {**cell, 'valid': validities[number-1], 'errors': int(not validities[number-1]),
                **{k: number*10 for k in ('operations_per_second', 'aggregate_application_gbps',
                    'p50_latency_ns', 'p95_latency_ns', 'p99_latency_ns')}}
    monkeypatch.setattr(a, 'run_repeat', repeat)
    monkeypatch.setattr(a.sys, 'argv', ['runner', '--output', str(tmp_path), '--smoke', '--repeats', str(len(validities))])
    a.main()
    report = json.loads((tmp_path / 'analysis.json').read_text())
    assert report['accepted'] is (bool(validities) and all(validities))
    assert len(list((tmp_path / 'raw').glob('*.json'))) == len(validities)
    if validities:
        cell = report['cells'][0]
        assert cell['valid_repeats'] == sum(validities)
        assert cell['errors'] == len(validities)-sum(validities)
        expected = 20 if validities == [False, True] else 10 if validities == [True] else None
        for field in ('median_operations_per_second', 'median_aggregate_application_gbps',
                      'median_p50_latency_ns', 'median_p95_latency_ns', 'median_p99_latency_ns'):
            assert cell[field] == expected
        manifest = json.loads(next((tmp_path / 'manifests').glob('*.json')).read_text())
        assert manifest['throughput_cv'] == cell['throughput_cv']
        if sum(validities) == 1:
            assert cell['throughput_cv'] == 0
        if not any(validities):
            assert cell['throughput_cv'] is None
    for i, valid in enumerate(validities, 1):
        raw = tmp_path / 'raw' / f'direct-s1-p1-r{i}.json'
        assert json.loads(raw.read_text())['valid'] is valid
        assert f'raw/{raw.name}' in (tmp_path / 'checksums.sha256').read_text()
    assert 'analysis.json' in (tmp_path / 'checksums.sha256').read_text()


@pytest.mark.parametrize('successes', [[False], [False, True], [True]])
def test_p2b_shard_preserves_failures_without_fabricating_latency(tmp_path, monkeypatch, successes):
    class Peer:
        returncode = 0
        stdout = io.StringIO('')
        stderr = io.StringIO('')
        def wait(self, timeout):
            return 0
        def poll(self):
            return 0
    monkeypatch.setattr(b.subprocess, 'Popen', lambda *args, **kwargs: Peer())
    monkeypatch.setattr(b, 'wait_ready', lambda *_: {'endpoint': 'mock-only'})
    records = [{'sample_id': i, 'success': success, 'request_latency_ns': 100,
                'completed_ns': 1000} for i, success in enumerate(successes)]
    monkeypatch.setattr(b, 'measured_client', lambda *args, **kwargs: ('\n'.join(map(json.dumps, records)), []))
    monkeypatch.setattr(b, 'measured_resources', lambda *_: {'total_cpu_ns': 20})
    shard = b.run_shard('direct', len(records), 1, False, {'direct': Path('never-executed')}, tmp_path, tmp_path, 1)
    assert shard['errors'] == len(successes)-sum(successes)
    assert shard['completed'] == sum(successes)
    for field in ('mean_lifecycle_ns', 'p50_ns', 'p95_ns', 'p99_ns'):
        assert shard[field] == (100 if any(successes) else None)


@pytest.mark.parametrize('completed', [[0], [0, 2], [2]])
def test_p2b_aggregate_preserves_partial_failed_shards(tmp_path, monkeypatch, completed):
    shards = [{'samples': 2, 'completed': n, 'errors': 2-n, 'over_capacity': 0,
        'duration_ns': 1000, 'mean_lifecycle_ns': 100 if n else None,
        'p50_ns': 100 if n else None, 'p95_ns': 100 if n else None,
        'p99_ns': 100 if n else None, 'resources': {'total_cpu_ns': 20},
        'source_profile': None, 'destination_profile': None} for n in completed]
    monkeypatch.setattr(b, 'shard_plan', lambda *_: [2]*len(shards))
    monkeypatch.setattr(b, 'run_shard', lambda *args: shards[args[-1]-1])
    report = b.aggregate('nbsr', 50, 1, False, 1, {}, tmp_path, tmp_path)
    assert report['shards'] == shards
    assert report['errors'] == sum(2-n for n in completed)
    assert report['completed_operations'] == sum(completed)
    for field in ('mean_lifecycle_ns', 'p50_ns', 'p95_ns', 'p99_ns'):
        assert report[field] == (100 if any(completed) else None)
    assert report['cpu_ns_per_operation'] == (20*len(shards)/sum(completed) if any(completed) else None)


def test_p2b_main_writes_all_failed_raw_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(b, 'build', lambda _: {})
    monkeypatch.setattr(b, 'write_loopback_authority', lambda _: None)
    def failed_shard(path, samples, *_):
        return {'samples': samples, 'completed': 0, 'errors': samples, 'over_capacity': 0,
                'duration_ns': 1000, 'mean_lifecycle_ns': None,
                'p50_ns': None, 'p95_ns': None, 'p99_ns': None,
                'resources': {'total_cpu_ns': 20}, 'source_profile': None,
                'destination_profile': None}
    monkeypatch.setattr(b, 'run_shard', failed_shard)
    monkeypatch.setattr(b.sys, 'argv', ['runner', '--suite', 'smoke', '--output', str(tmp_path)])
    b.main()
    reports = [json.loads(p.read_text()) for p in (tmp_path / 'raw').glob('*.json')]
    assert len(reports) == 2
    assert all(r['completed_operations'] == 0 and r['errors'] > 0 for r in reports)
    assert all(r['p99_ns'] is None and r['cpu_ns_per_operation'] is None for r in reports)


def test_ci_selects_reporting_regressions_and_existing_neighbors():
    from scripts.ci.check import command_groups
    core = next(c for c in command_groups('python-core') if c.name == 'python-core')
    for path in ('tests/ci', 'tests/test_p2a_established.py', 'tests/test_p2b_profile.py'):
        assert core.argv.count(path) == 1
