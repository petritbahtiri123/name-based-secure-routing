import pytest

from scripts.performance.physical_core_analysis import classify_ladder


def row(depth=1, repeat=1, goodput=1.0, p99=100):
    return dict(outstanding_per_stream=depth, repeat=repeat, aggregate_application_gbps=goodput,
                p99_latency_ns=p99, valid=True, cleanup_pass=True, errors=0, timeouts=0,
                configured_total_outstanding=depth, max_observed_total_outstanding=depth)


def test_diagnostic_peak_does_not_replace_strict_stable_ceiling():
    rows = [row(repeat=i) for i in range(1, 4)]
    rows += [row(4, i, 2.0, 150) for i in range(1, 4)]
    rows += [row(8, i, 2.1, 250) for i in range(1, 4)]
    result = classify_ladder(rows)
    assert [c["classification"] for c in result["cells"]] == ["STABLE", "DEGRADED", "SATURATED"]
    assert result["strict_stable_gbps"] == 1.0
    assert result["observed_peak_diagnostic_gbps"] == 2.1


def test_dispersed_baseline_is_not_a_stable_capacity():
    result = classify_ladder([row(repeat=i, goodput=v) for i, v in enumerate((.7, 1, 1.3, 1, 1), 1)])
    assert result["strict_stable_gbps"] is None


def test_missing_repeats_and_duplicate_identity_are_rejected():
    with pytest.raises(ValueError, match="repeat"):
        classify_ladder([row(), row(repeat=2)])
    with pytest.raises(ValueError, match="repeat"):
        classify_ladder([row(), row(), row(repeat=3)])


def test_unfavorable_valid_latency_repeat_is_preserved():
    result = classify_ladder([row(), row(repeat=2), row(repeat=3, p99=130)])
    assert result["strict_stable_gbps"] is None
    assert result["cells"][0]["classification"] == "UNRESOLVED"
    assert result["cells"][0]["repeat_count"] == 3
