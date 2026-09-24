from copy import deepcopy

import pytest

from tests.performance.test_linux_native_paced import transcript


def guard(**kwargs):
    from scripts.performance.linux_native_live import LocalLiveGuard
    return LocalLiveGuard(role='source', payload_bytes=1024, max_progress=8,
                          max_resources=20, **kwargs)


def sample(clock, memory=1000, role='source'):
    return dict(role=role, timestamp_ns=clock, private_resident_bytes=memory)


def run(offset=0, growth=False):
    value = guard()
    for index, row in enumerate(transcript()[:-1], 1):
        value.resource(sample(offset + index * 5_000_000_000,
                              1000 + index * 100 if growth else 1000))
        value.progress(row, received_ns=offset + row['elapsed_ns'])
    value.finish(transcript()[-1])
    return value.qualification()


def test_independent_host_clock_offsets_preserve_decision():
    left, right = run(), run(10**15)
    for result in (left, right):
        assert result['resource_series_available'] is True
        assert result['latency_comparison_available'] is True
        assert result['failures'] == []
        assert result['sustained_capacity'] == 'NOT_ESTABLISHED'
    assert right['local_phase_origin_ns'] - left['local_phase_origin_ns'] == 10**15


def test_growth_preserved_with_same_existing_threshold():
    assert run(growth=True)['failures'][-1]['reason'] == 'private_growth'


def test_latency_failure_is_retained():
    value = guard()
    rows = transcript()
    rows[2]['p99_latency_ns'] = 900
    for row in rows[:-1]:
        value.progress(row, received_ns=row['elapsed_ns'])
    assert any(row['reason'] == 'p99' for row in value.qualification()['failures'])


def test_missing_samples_never_qualify():
    value = guard()
    value.progress(transcript()[0], received_ns=5_000_000_000)
    result = value.qualification()
    assert not result['resource_series_available']
    assert not result['latency_comparison_available']
    assert not result['final_received']


@pytest.mark.parametrize('fault', ['role', 'clock', 'memory', 'boolean'])
def test_invalid_resource_rejected(fault):
    value = guard()
    row = sample(10)
    row.update({'role': 'destination'} if fault == 'role' else
               {'timestamp_ns': -1} if fault == 'clock' else
               {'private_resident_bytes': None} if fault == 'memory' else
               {'timestamp_ns': True})
    with pytest.raises(ValueError):
        value.resource(row)


def test_local_clock_reversal_rejected():
    value = guard()
    value.resource(sample(10))
    with pytest.raises(ValueError):
        value.resource(sample(9))
    value.progress(transcript()[0], received_ns=10**10)
    with pytest.raises(ValueError):
        value.progress(transcript()[1], received_ns=10**10-1)


def test_resource_and_progress_bounds():
    value = guard()
    for index in range(20):
        value.resource(sample(index))
    with pytest.raises(ValueError):
        value.resource(sample(20))
    from scripts.performance.linux_native_live import LocalLiveGuard
    value = LocalLiveGuard(role='source', payload_bytes=1024, max_progress=1, max_resources=1)
    value.progress(transcript()[0], received_ns=5_000_000_000)
    with pytest.raises(ValueError):
        value.progress(transcript()[1], received_ns=10_000_000_000)


def test_malformed_progress_rejected():
    value = guard()
    row = transcript()[0]
    row['completed'] += 1
    with pytest.raises(ValueError):
        value.progress(row, received_ns=5_000_000_000)


def test_final_is_terminal_for_all_inputs():
    value = guard()
    for row in transcript()[:-1]:
        value.progress(row, received_ns=row['elapsed_ns'])
    value.finish(transcript()[-1])
    for action in (lambda: value.finish(transcript()[-1]),
                   lambda: value.resource(sample(30_000_000_000)),
                   lambda: value.progress(transcript()[0], received_ns=30_000_000_000)):
        with pytest.raises(ValueError):
            action()


def test_caller_cannot_mutate_retained_state():
    value = guard()
    row = transcript()[0]
    original = deepcopy(row)
    value.progress(row, received_ns=5_000_000_000)
    row['p99_latency_ns'] = 10**12
    assert value.steady == [original]
    result = value.qualification()
    result['failures'].append({'reason': 'invented'})
    assert value.qualification()['failures'] == []


def test_terminal_zombie_memory_is_missing_not_zero_or_coverage():
    value = guard()
    value.progress(transcript()[0], received_ns=5_000_000_000)
    for clock in range(1, 5):
        value.resource(sample(clock, None) | dict(state='Z', memory_state='UNAVAILABLE_ZOMBIE'))
    assert not value.qualification()['resource_series_available']


@pytest.mark.parametrize('limit', [0, -1, True, 1.5, 100001])
def test_invalid_storage_bounds_rejected(limit):
    from scripts.performance.linux_native_live import LocalLiveGuard
    with pytest.raises(ValueError):
        LocalLiveGuard(role='source', payload_bytes=1024, max_progress=limit, max_resources=20)


def test_destination_only_accepts_its_local_resources():
    from scripts.performance.linux_native_live import LocalLiveGuard
    value = LocalLiveGuard(role='destination', payload_bytes=1024, max_progress=8, max_resources=20)
    value.resource(sample(1, role='destination'))
    with pytest.raises(ValueError):
        value.resource(sample(2, role='source'))


def test_late_resource_delivery_cannot_claim_evaluated_series():
    value = guard()
    for row in transcript()[:-1]:
        value.progress(row, received_ns=row['elapsed_ns'])
    for clock in range(1, 5):
        value.resource(sample(clock * 1_000_000_000, clock * 1000))
    value.finish(transcript()[-1])
    assert not value.qualification()['resource_series_available']
