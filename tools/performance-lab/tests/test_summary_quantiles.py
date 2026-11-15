"""Synthetic percentile contradictions must not become displayed measurements."""
import json

import pytest

from lab.adapters import normalize
from lab.store import Store


def artifact(kind, values):
    if kind == 'repeat':
        return {'schema': 'nbsr-p2a-repeat-v2', 'path': 'direct',
                **{q + '_latency_ns': value for q, value in values.items()}}
    if kind == 'legacy':
        measurement = {'latency_median_of_window_quantiles_us':
                       {q + '_latency_ns': value for q, value in values.items()}}
    else:
        measurement = {'median_window_quantiles_us': values}
    return {'schema': 'nbsr-sphere-controlled-load-summary-v1',
            'measurement': measurement}


@pytest.mark.parametrize('kind', ['summary', 'legacy', 'repeat'])
@pytest.mark.parametrize('values', [
    {'p50': 3000, 'p95': 2000, 'p99': 4000},
    {'p50': 1000, 'p95': 3000, 'p99': 2000},
    {'p50': 3000, 'p99': 2000},
])
def test_contradictory_percentiles_rejected(kind, values):
    with pytest.raises(ValueError, match='quantiles'):
        normalize(artifact(kind, values))


@pytest.mark.parametrize('kind', ['summary', 'legacy', 'repeat'])
@pytest.mark.parametrize('values', [
    {'p50': 3000, 'p95': 2000, 'p99': 4000},
    {'p50': 1000, 'p95': 3000, 'p99': 2000},
    {'p50': 3000, 'p99': 2000},
])
def test_contradictory_percentiles_quarantined_with_original_bytes(tmp_path, kind, values):
    raw = json.dumps(artifact(kind, values), indent=2).encode()
    store = Store(tmp_path)
    result = store.ingest(raw, 'synthetic-unordered.json')
    assert result['status'] == 'quarantined'
    assert store.runs() == []
    assert store.artifact(result['sha256']) == raw
    assert 'quantiles' in result['issue']


@pytest.mark.parametrize('kind', ['summary', 'legacy', 'repeat'])
@pytest.mark.parametrize('values,expected_summary,expected_repeat', [
    ({}, [None, None, None], [None, None, None]),
    ({'p99': 2000}, [None, None, 2000], [None, None, 2]),
    ({'p50': 0, 'p95': 0, 'p99': 0}, [0, 0, 0], [0, 0, 0]),
    ({'p50': 1000, 'p95': 1000, 'p99': 2000}, [1000, 1000, 2000], [1, 1, 2]),
])
def test_ordered_or_missing_quantiles_preserve_values_and_units(kind, values, expected_summary, expected_repeat):
    run = normalize(artifact(kind, values))[0]
    assert [run['latency'][q + '_us'] for q in ('p50', 'p95', 'p99')] == (
        expected_repeat if kind == 'repeat' else expected_summary)


@pytest.mark.parametrize('kind', ['summary', 'legacy'])
def test_summary_integer_quantiles_are_not_rounded_by_validation(kind):
    run = normalize(artifact(kind, {'p99': 9007199254740993}))[0]
    assert run['latency']['p99_us'] == 9007199254740993
