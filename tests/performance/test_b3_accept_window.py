import pytest

from scripts import run_b3_v2 as runner
from scripts import run_b3_session_lifecycle as lifecycle


def test_diagnostic_accept_window_is_explicit_without_changing_arrivals():
    original = runner.spec_for('live-bundles', 2048, 1)
    diagnostic = runner.spec_for('live-bundles', 2048, 1, accept_window=2)
    assert diagnostic.get('accept_window', 1) == 2
    assert {k: v for k, v in diagnostic.items() if k != 'accept_window'} == original
    assert original['start_rate'] == diagnostic['start_rate'] == 100


@pytest.mark.parametrize('window', [0, 3, 64, True, '2'])
def test_invalid_diagnostic_accept_windows_fail_closed(window):
    with pytest.raises(ValueError, match='accept window'):
        runner.spec_for('live-bundles', 2048, 1, accept_window=window)


@pytest.mark.parametrize('axis,count', [('cycles', 2), ('channels', 2), ('streams', 8), ('live-bundles', 1)])
def test_accept_window_cannot_apply_to_unrelated_or_single_connection_workloads(axis, count):
    with pytest.raises(ValueError, match='accept window'):
        runner.spec_for(axis, count, 1, accept_window=2)


def test_only_recorded_window_is_forwarded_to_destination(monkeypatch):
    monkeypatch.delenv('NBSR_PERF_LIFECYCLE_ACCEPT_WINDOW', raising=False)
    spec = runner.spec_for('live-bundles', 2048, 1, accept_window=2)
    assert lifecycle.diagnostic_accept_environment('rust-rust', spec) == {'NBSR_PERF_LIFECYCLE_ACCEPT_WINDOW': '2'}
    assert lifecycle.diagnostic_accept_environment('rust-rust', runner.spec_for('live-bundles', 2048, 1)) == {}
    for invalid in [dict(spec, start_rate=0), dict(spec, start_rate=float('nan'))]:
        with pytest.raises(ValueError, match='accept window'):
            lifecycle.diagnostic_accept_environment('rust-rust', invalid)
    with pytest.raises(ValueError, match='accept window'):
        lifecycle.diagnostic_accept_environment('go-rust', spec)
    monkeypatch.setenv('NBSR_PERF_LIFECYCLE_ACCEPT_WINDOW', '32')
    with pytest.raises(ValueError, match='recorded'):
        lifecycle.diagnostic_accept_environment('rust-rust', spec)
