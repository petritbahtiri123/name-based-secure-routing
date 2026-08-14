from __future__ import annotations

from scripts.performance.rust_memory_attribution import classify_attribution, reconcile_snapshot
from scripts.run_rust_memory_attribution import attribution_specs


def test_frozen_attribution_plan_has_one_control_three_repeats_and_explicit_drain() -> None:
    specs = attribution_specs()

    assert [(item.percent, item.rate, item.ordinal) for item in specs] == [
        (50, 843.75, 1),
        (75, 1265.625, 1),
        (75, 1265.625, 2),
        (75, 1265.625, 3),
    ]
    assert {(item.warmup_seconds, item.steady_seconds, item.drain_seconds) for item in specs} == {(60, 1800, 20)}


def test_snapshot_reconciliation_uses_mutually_exclusive_terminals() -> None:
    snapshot = {
        "application_streams_created": 11,
        "application_streams_completed": 9,
        "application_streams_failed_or_cancelled": 1,
        "application_streams_current_live": 1,
    }

    assert reconcile_snapshot(snapshot, "application_streams") == {
        "created": 11,
        "terminal_success": 9,
        "terminal_failure_or_cancel": 1,
        "current_live": 1,
        "reconciled": True,
    }


def run(*, slope: float, post_live: int = 0, post_capacity: int = 0, replay_growth: int = 0) -> dict:
    return {
        "valid": True,
        "final_quarter_working_set_slope": slope,
        "post_drain_nonbaseline_live": post_live,
        "post_drain_retained_capacity": post_capacity,
        "replay_entry_growth": replay_growth,
        "all_instrumented_layers_visible": True,
    }


def test_classification_requires_two_of_three_reproducible_75_percent_runs() -> None:
    assert classify_attribution([run(slope=60_000, post_live=4), run(slope=55_000, post_live=3), run(slope=0)]) == "A"
    assert classify_attribution([run(slope=60_000, post_capacity=1_000), run(slope=55_000, post_capacity=900), run(slope=0)]) == "B"
    assert classify_attribution([run(slope=60_000), run(slope=55_000), run(slope=0)]) == "C"
    assert classify_attribution([run(slope=0), run(slope=10), run(slope=-5)]) == "D"


def test_single_correlated_run_is_not_attribution() -> None:
    assert classify_attribution([run(slope=60_000, replay_growth=10_000), run(slope=0), run(slope=0)]) == "D"
