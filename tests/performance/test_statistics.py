from __future__ import annotations

import pytest

from scripts.performance.statistics import Cell, bootstrap_run_ci, matched_overhead, summarize


def cell(**changes: object) -> Cell:
    values: dict[str, object] = {
        "environment_digest": "a" * 64,
        "topology": "windows-loopback",
        "build_profile": "release",
        "payload_bytes": 1024,
        "load_level": "idle",
        "connection_lifecycle": "warm",
        "run_ordinal": 1,
        "implementation": "direct-quic",
        "scenario": "direct-warm",
    }
    values.update(changes)
    return Cell(**values)  # type: ignore[arg-type]


def test_percentiles_use_literal_nearest_rank_values() -> None:
    result = summarize(list(range(1, 101)))
    assert result == {
        "count": 100,
        "min": 1,
        "max": 100,
        "p50": 50,
        "p95": 95,
        "p99": 99,
        "p99_9": None,
    }


def test_p999_requires_one_hundred_thousand_successes() -> None:
    values = list(range(1, 100_001))
    assert summarize(values)["p99_9"] == 99_900


@pytest.mark.parametrize(
    "changed",
    [
        {"payload_bytes": 1},
        {"load_level": "50pct"},
        {"environment_digest": "b" * 64},
        {"topology": "same-region"},
        {"build_profile": "debug"},
        {"connection_lifecycle": "cold"},
        {"run_ordinal": 2},
    ],
)
def test_overhead_rejects_non_equivalent_cells(changed: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="unmatched benchmark cells"):
        matched_overhead(cell(implementation="rust-rust", scenario="nbsr-warm-existing-service"), cell(**changed), 15, 10)


def test_overhead_requires_the_approved_scenario_pair() -> None:
    with pytest.raises(ValueError, match="invalid overhead scenario pair"):
        matched_overhead(cell(implementation="go-rust", scenario="nbsr-cold", connection_lifecycle="warm"), cell(), 15, 10)


def test_matched_warm_existing_overhead_is_nbsr_minus_direct() -> None:
    value = matched_overhead(
        cell(implementation="rust-rust", scenario="nbsr-warm-existing-service"),
        cell(),
        15_000_000,
        9_000_000,
    )
    assert value == 6_000_000


def test_run_level_bootstrap_ci_is_deterministic_and_machine_readable() -> None:
    first = bootstrap_run_ci([100, 110, 120, 130, 140], resamples=2_000, seed=75)
    second = bootstrap_run_ci([100, 110, 120, 130, 140], resamples=2_000, seed=75)
    assert first == second
    assert first["method"] == "independent-run-bootstrap-mean-v1"
    assert first["run_count"] == 5
    assert first["resamples"] == 2_000
    assert first["lower"] <= first["estimate"] <= first["upper"]


def test_bootstrap_constant_runs_do_not_invent_uncertainty() -> None:
    result = bootstrap_run_ci([7, 7, 7, 7, 7], resamples=100, seed=1)
    assert (result["lower"], result["estimate"], result["upper"]) == (7, 7, 7)
