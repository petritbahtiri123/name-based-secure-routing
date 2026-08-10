from __future__ import annotations

from typing import Any


def reconcile_snapshot(snapshot: dict[str, Any], prefix: str) -> dict[str, Any]:
    created = int(snapshot[f"{prefix}_created"])
    success = int(snapshot[f"{prefix}_completed"])
    failure = int(snapshot[f"{prefix}_failed_or_cancelled"])
    live = int(snapshot[f"{prefix}_current_live"])
    return {
        "created": created,
        "terminal_success": success,
        "terminal_failure_or_cancel": failure,
        "current_live": live,
        "reconciled": created - success - failure == live,
    }


def classify_attribution(runs: list[dict[str, Any]]) -> str:
    valid = [run for run in runs if run.get("valid")]
    if len(valid) < 3:
        return "E"
    growing = [run for run in valid if float(run["final_quarter_working_set_slope"]) > 1024.0]
    if len(growing) < 2:
        return "D"
    if sum(int(run.get("post_drain_nonbaseline_live", 0)) > 0 for run in growing) >= 2:
        return "A"
    if sum(int(run.get("post_drain_retained_capacity", 0)) > 0 for run in growing) >= 2:
        return "B"
    if all(bool(run.get("all_instrumented_layers_visible")) for run in growing):
        return "C"
    return "E"
