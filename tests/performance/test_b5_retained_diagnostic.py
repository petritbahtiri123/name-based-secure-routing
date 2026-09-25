import pytest

from scripts import run_b5_v2 as b5


def progress(index, p99=100):
    return dict(phase='steady', elapsed_ns=index * 1_000_000_000,
                goodput_bytes_per_second=100, p99_latency_ns=p99)


def diagnostic_guard(**kwargs):
    assert hasattr(b5, 'DiagnosticLiveGuards'), 'bounded diagnostic guard missing'
    return b5.DiagnosticLiveGuards(groups=1, max_progress=kwargs.get('max_progress', 8),
                                  max_resources=8, resource_basis='linux_private_resident')


def test_drift_is_retained_and_can_never_be_reported_as_pass():
    guard = diagnostic_guard()
    for i, p99 in enumerate((100, 100, 200, 200), 1):
        guard.progress(progress(i, p99), received_ns=i * 1_000_000_000)
    assert len(guard.steady) == 4
    result = {'valid': True, 'classification': 'DIAGNOSTIC', 'final': {'completed': 42}}
    guard.annotate_result(result)
    assert result['valid'] is False
    assert result['classification'] == 'FAIL_DIAGNOSTIC_RETAINED'
    assert result['diagnostic_gate_failures'][0]['elapsed_ns'] == 3_000_000_000
    assert result['diagnostic_gate_failures'][0]['reason'] == 'live p99 drift'
    assert result['final']['completed'] == 42


def test_strict_guard_still_aborts_at_first_drift():
    guard = b5.LiveGuards(groups=1, max_progress=8, max_resources=8)
    guard.progress(progress(1))
    guard.progress(progress(2))
    with pytest.raises(RuntimeError, match='live p99 drift'):
        guard.progress(progress(3, 200))


def test_diagnostic_does_not_suppress_bounds_or_invalid_resources():
    guard = diagnostic_guard(max_progress=1)
    guard.progress(progress(1))
    with pytest.raises(RuntimeError, match='progress bound'):
        guard.progress(progress(2))
    with pytest.raises(RuntimeError, match='memory'):
        guard.resource(dict(role='source', timestamp_ns=1, private_resident_bytes=None))


def test_existing_correctness_failure_is_not_overwritten():
    guard = diagnostic_guard()
    for i, p99 in enumerate((100, 100, 200), 1):
        guard.progress(progress(i, p99))
    result = dict(valid=False, classification='FAIL', error='owned-resource cleanup failed')
    guard.annotate_result(result)
    assert result['error'] == 'owned-resource cleanup failed'
    assert result['classification'] == 'FAIL'


def test_private_growth_is_preserved_as_failure():
    guard = diagnostic_guard()
    for i in range(4):
        guard.resource(dict(role='source', timestamp_ns=i * 1_000_000_000,
                            private_resident_bytes=1000 + i * 100))
    guard.progress(progress(3), received_ns=3_000_000_000)
    result = dict(valid=True)
    guard.annotate_result(result)
    assert result['valid'] is False
    assert result['error'].startswith('live private growth: source')


def test_retained_diagnostic_duration_is_bounded(tmp_path):
    with pytest.raises(ValueError, match='600'):
        b5.run_one(None, None, None, None, tmp_path / 'unused', warmup=3, duration=601,
                   progress=10, rate=(1, 1), diagnostic=True, retain_failed_diagnostic=True)
    assert not (tmp_path / 'unused').exists()


def test_retention_cannot_be_used_for_acceptance_run(tmp_path):
    with pytest.raises(ValueError, match='diagnostic'):
        b5.run_one(None, None, None, None, tmp_path / 'unused', warmup=3, duration=600,
                   progress=10, rate=(1, 1), diagnostic=False, retain_failed_diagnostic=True)
    assert not (tmp_path / 'unused').exists()


def test_linux_cli_records_explicit_diagnostic_retention(monkeypatch):
    import sys
    from scripts.performance import linux_b5_campaign
    captured = []
    monkeypatch.setattr(sys, 'argv', ['b5', '--binaries', 'bins', '--build-manifest', 'build.json',
        '--output', 'out', '--duration', '600', '--diagnostic', '--rate', '1', '1',
        '--retain-failed-diagnostic'])
    def execute(args, *, check_cancelled):
        check_cancelled()
        captured.append(args)
    monkeypatch.setattr(linux_b5_campaign, 'execute', execute)
    linux_b5_campaign.main()
    assert captured[0].retain_failed_diagnostic is True
