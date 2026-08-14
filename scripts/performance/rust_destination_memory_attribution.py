from __future__ import annotations

from typing import Any


def classify_destination_runs(runs: list[dict[str, Any]]) -> str:
    valid = [run for run in runs if run.get("valid")]
    if len(valid) < 3:
        return "E"
    growing = [run for run in valid if float(run["full_window_working_set_slope"]) > 1024.0]
    if len(growing) < 2:
        return "D"
    if sum(int(run.get("post_drain_nonbaseline_live", 0)) > 0 for run in growing) >= 2:
        return "A"
    if not all(bool(run.get("all_instrumented_layers_visible")) for run in growing):
        return "E"
    capacity_owned = [
        run
        for run in growing
        if float(run.get("replay_capacity_working_set_correlation", 0.0)) >= 0.95
        and float(run.get("replay_capacity_private_bytes_correlation", 0.0)) >= 0.95
        and bool(run.get("replay_insertions_equal_completed_streams"))
        and bool(run.get("replay_entries_and_capacity_clear_post_drain"))
        and bool(run.get("process_memory_returns_to_baseline_post_drain"))
    ]
    if len(capacity_owned) >= 2:
        return "B"
    return "C"
