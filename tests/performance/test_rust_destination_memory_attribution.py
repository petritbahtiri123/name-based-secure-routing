from __future__ import annotations

from pathlib import Path

from scripts.run_rust_destination_memory_attribution import (
    attribution_specs,
    load_command,
    observer_spec,
    summarize_observer,
)


def test_p1b_plan_uses_short_frozen_control_and_three_attribution_runs() -> None:
    specs = attribution_specs()
    assert [(item.percent, item.rate, item.ordinal) for item in specs] == [
        (50, 843.75, 1),
        (75, 1265.625, 1),
        (75, 1265.625, 2),
        (75, 1265.625, 3),
    ]
    assert [(item.warmup_seconds, item.steady_seconds, item.drain_seconds) for item in specs] == [
        (60, 600, 20),
        (60, 900, 20),
        (60, 900, 20),
        (60, 900, 20),
    ]


def test_observer_plan_uses_exact_count_short_window() -> None:
    spec = observer_spec()
    assert (spec.warmup_seconds, spec.steady_seconds, spec.drain_seconds) == (32, 60, 5)


def test_p1b_short_attribution_windows_use_explicit_validation_profile(tmp_path: Path) -> None:
    command = load_command(
        rate=843.75,
        warmup_seconds=60,
        steady_seconds=600,
        drain_seconds=20,
        run_id="control",
        finalized=tmp_path / "finalized",
        durable_root=tmp_path,
        enabled=True,
    )
    assert "--validation-profile" in command


def test_observer_summary_applies_all_three_guardrails() -> None:
    rows = [
        {"pair": pair, "diagnostics_enabled": False, "achieved_rate": 100.0, "p99_ns": 1000, "errors": 0}
        for pair in range(1, 6)
    ] + [
        {"pair": pair, "diagnostics_enabled": True, "achieved_rate": 98.0, "p99_ns": 1040, "errors": 0}
        for pair in range(1, 6)
    ]
    assert summarize_observer(rows)["pass"] is True
    rows[-1]["errors"] = 1
    assert summarize_observer(rows)["pass"] is False
