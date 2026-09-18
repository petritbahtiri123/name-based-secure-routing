import pytest


def test_three_counterbalanced_pairs_are_required():
    from scripts.performance.linux_b5_campaign import run_cohort
    calls, kept = [], []

    def run(path, repeat):
        calls.append((path, repeat))
        return dict(path=path, valid=True, gbps=1, window_p99_median_ns=100)

    assert run_cohort(("direct", "nbsr"), run, kept.append, diagnostic=False) == 3
    assert calls == [("direct", 1), ("nbsr", 1), ("nbsr", 2), ("direct", 2), ("direct", 3), ("nbsr", 3)]
    assert len(kept) == 6


def test_latency_dispersion_expands_both_paths_to_five():
    from scripts.performance.linux_b5_campaign import run_cohort
    kept = []

    def run(path, repeat):
        return dict(path=path, valid=True, gbps=1,
                    window_p99_median_ns=200 if path == "nbsr" and repeat == 1 else 100)

    assert run_cohort(("direct", "nbsr"), run, kept.append, diagnostic=False) == 5
    assert len(kept) == 10


def test_invalid_prefix_is_retained_without_replacement():
    from scripts.performance.linux_b5_campaign import run_cohort
    kept = []

    def run(path, repeat):
        return dict(path=path, valid=path == "direct", gbps=1)

    with pytest.raises(RuntimeError, match="no replacement"):
        run_cohort(("direct", "nbsr"), run, kept.append, diagnostic=False)
    assert len(kept) == 2 and kept[-1]["valid"] is False


def test_diagnostic_one_repeat_cannot_become_qualified():
    from scripts.performance.linux_b5_campaign import run_cohort
    kept = []
    assert run_cohort(("nbsr",), lambda *args: dict(valid=True, gbps=1), kept.append, diagnostic=True) == 1
    assert len(kept) == 1


def test_dirty_source_is_rejected_before_output_or_execution(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts.performance import linux_b5_campaign as campaign
    monkeypatch.setattr(campaign, "git_state", lambda: ("a" * 40, " M source.py"))
    args = SimpleNamespace(diagnostic=True, reference=None, rate=(1, 1), paths=["nbsr"],
        streams=1, payload=1024, depth=1, warmup=3, duration=30, progress=10,
        output=tmp_path / "never-created")
    with pytest.raises(ValueError, match="clean checkout"):
        campaign.execute(args)
    assert not args.output.exists()


def test_manual_rate_cannot_bypass_reference_binding(tmp_path):
    from types import SimpleNamespace
    from scripts.performance import linux_b5_campaign as campaign
    args = SimpleNamespace(diagnostic=False, reference=tmp_path, rate=(1, 1))
    with pytest.raises(ValueError, match="ceiling"):
        campaign.execute(args)


def test_split_placement_cannot_reuse_shared_ceiling_reference(tmp_path):
    from types import SimpleNamespace
    from scripts.performance import linux_b5_campaign as campaign
    args = SimpleNamespace(diagnostic=False, reference=tmp_path, rate=None, placement='split')
    with pytest.raises(ValueError, match='split placement requires diagnostic'):
        campaign.execute(args)
