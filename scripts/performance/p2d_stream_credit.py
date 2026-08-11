"""P2D stream-credit benchmark and evidence rules.

All calculations consume immutable live-cell JSON.  This module does not
simulate transport behavior or synthesize unavailable observations.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import statistics

CONCURRENCIES = (1, 2, 4, 8, 16, 32, 64)
OUTCOME_ACCEPTED = "Outcome A — ACCEPTED AND RETAINED"
OUTCOME_REVERTED = "Outcome B — IMPLEMENTED THEN REVERTED"
OUTCOME_INCONCLUSIVE = "Outcome B — INCONCLUSIVE"

_MATCHED_FIELDS = (
    "schema",
    "concurrency",
    "payload_bytes",
    "operation",
    "transport_session_model",
    "service_channel_model",
    "application_stream_model",
    "duration_seconds_requested",
    "build",
    "environment",
    "source",
)


def validate_matched_pair(before: dict, after: dict) -> None:
    if before.get("mode") != "before":
        raise ValueError("mode: BEFORE manifest must use before")
    if after.get("mode") != "after":
        raise ValueError("mode: AFTER manifest must use after")
    if before.get("profile") != "legacy-stream-open":
        raise ValueError("profile: BEFORE must be legacy STREAM_OPEN")
    if after.get("profile") != "nbsr-stream-credit-1":
        raise ValueError("profile: AFTER must be nbsr-stream-credit-1")
    for field in _MATCHED_FIELDS:
        if before.get(field) != after.get(field):
            raise ValueError(f"{field}: matched pair differs")
    if before["payload_bytes"] != 1024:
        raise ValueError("payload_bytes: matched P2D cells must use 1024")
    if not 60 <= before["duration_seconds_requested"] <= 120:
        raise ValueError("duration_seconds_requested: matched cells require 60-120 seconds")
    if before["concurrency"] not in CONCURRENCIES:
        raise ValueError("concurrency: not in the approved sweep")


def nearest_rank_percentile(values: list[int], percentile: int) -> int:
    if not values or not 1 <= percentile <= 100:
        raise ValueError("non-empty values and percentile 1..100 required")
    ordered = sorted(values)
    rank = math.ceil(percentile * len(ordered) / 100)
    return ordered[rank - 1]


def coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("at least two values are required for sample CV")
    mean = statistics.fmean(values)
    if mean == 0:
        raise ValueError("sample CV is undefined for a zero mean")
    return statistics.stdev(values) / mean


def summarize_pairs(before: list[dict], after: list[dict]) -> dict:
    if len(before) != len(after) or len(before) not in (3, 5):
        raise ValueError("matched evidence requires exactly three or five pairs")
    for before_cell, after_cell in zip(before, after, strict=True):
        if before_cell["concurrency"] != after_cell["concurrency"]:
            raise ValueError("concurrency: live pair differs")
    before_throughput = [float(value["operations_per_second"]) for value in before]
    after_throughput = [float(value["operations_per_second"]) for value in after]
    before_p99 = [int(value["p99_ns"]) for value in before]
    after_p99 = [int(value["p99_ns"]) for value in after]
    before_median = statistics.median(before_throughput)
    after_median = statistics.median(after_throughput)
    before_p99_median = statistics.median(before_p99)
    after_p99_median = statistics.median(after_p99)
    errors = sum(int(value["errors"]) for value in before + after)
    return {
        "pairs": len(before),
        "before_median_operations_per_second": before_median,
        "after_median_operations_per_second": after_median,
        "throughput_improvement": after_median / before_median - 1,
        "before_throughput_cv": coefficient_of_variation(before_throughput),
        "after_throughput_cv": coefficient_of_variation(after_throughput),
        "before_median_p99_ns": before_p99_median,
        "after_median_p99_ns": after_p99_median,
        "p99_change": after_p99_median / before_p99_median - 1,
        "errors": errors,
    }


def should_stop_after_three(before: list[dict], after: list[dict]) -> bool:
    if len(before) != 3 or len(after) != 3:
        return False
    summary = summarize_pairs(before, after)
    if summary["before_throughput_cv"] > 0.05 or summary["after_throughput_cv"] > 0.05:
        return False
    throughput_sides = [
        float(after_cell["operations_per_second"])
        >= 1.20 * float(before_cell["operations_per_second"])
        for before_cell, after_cell in zip(before, after, strict=True)
    ]
    p99_sides = [
        int(after_cell["p99_ns"]) <= 1.05 * int(before_cell["p99_ns"])
        for before_cell, after_cell in zip(before, after, strict=True)
    ]
    throughput_clear = all(throughput_sides) or not any(throughput_sides)
    p99_clear = all(p99_sides) or not any(p99_sides)
    return throughput_clear and p99_clear


def evaluate_acceptance(summary: dict, **gates: str) -> dict:
    required = ("security", "refill", "continuity", "soak", "resource")
    if set(gates) != set(required):
        raise ValueError("security/refill/continuity/soak/resource gates are required")
    for name, status in gates.items():
        if status not in ("PASS", "FAIL", "INCONCLUSIVE"):
            raise ValueError(f"{name}: invalid gate status")
    evaluated = {
        "errors": "PASS" if summary["errors"] == 0 else "FAIL",
        **{name: gates[name] for name in required},
        "throughput": (
            "PASS"
            if summary["after_median_operations_per_second"]
            >= 1.20 * summary["before_median_operations_per_second"]
            else "FAIL"
        ),
        "p99": (
            "PASS"
            if summary["after_median_p99_ns"] <= 1.05 * summary["before_median_p99_ns"]
            else "FAIL"
        ),
    }
    precedence = (
        "errors",
        "security",
        "refill",
        "continuity",
        "resource",
        "soak",
        "throughput",
        "p99",
    )
    blocking_gate = next((name for name in precedence if evaluated[name] != "PASS"), None)
    if any(status == "FAIL" for status in evaluated.values()):
        outcome = OUTCOME_REVERTED
    elif any(status == "INCONCLUSIVE" for status in evaluated.values()):
        outcome = OUTCOME_INCONCLUSIVE
    else:
        outcome = OUTCOME_ACCEPTED
    return {"gates": evaluated, "blocking_gate": blocking_gate, "outcome": outcome}


def validate_continuity(cell: dict) -> str:
    passed = (
        cell.get("mode") == "after"
        and cell.get("errors") == 0
        and cell.get("payload_correct") is True
        and cell.get("windows_crossed", 0) >= 10
        and cell.get("refill_count", 0) >= 10
        and 0 <= cell.get("remaining_credits", -1) <= 64
        and 1 <= cell.get("active_epochs", 0) <= 2
        and 0 <= cell.get("replay_entries", -1) <= cell.get("replay_limit", -1)
    )
    return "PASS" if passed else "FAIL"


def _nested_measured_endpoints(value: object):
    if isinstance(value, dict):
        for name, nested in value.items():
            if (
                name in ("source", "destination")
                and isinstance(nested, dict)
                and "completed_operations" in nested
            ):
                yield nested
            yield from _nested_measured_endpoints(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_measured_endpoints(nested)


def validate_replay_limits(cell: dict) -> str:
    measured = [cell, *_nested_measured_endpoints(cell)]
    for endpoint in measured:
        replay_entries = endpoint.get("replay_entries")
        replay_limit = endpoint.get("replay_limit")
        if replay_limit != 10_000:
            return "FAIL"
        if (
            not isinstance(replay_entries, int)
            or replay_entries < 0
            or replay_entries > replay_limit
        ):
            return "FAIL"
    return "PASS"


def validate_live_cell(cell: dict) -> None:
    required = {
        "schema",
        "mode",
        "profile",
        "concurrency",
        "payload_bytes",
        "payload_correct",
        "completed_operations",
        "duration_ns",
        "operations_per_second",
        "p50_ns",
        "p95_ns",
        "p99_ns",
        "cpu",
        "errors",
        "remaining_credits",
        "refill_count",
        "active_epochs",
        "replay_entries",
        "replay_limit",
        "build",
        "environment",
        "source",
    }
    missing = sorted(required - set(cell))
    if missing:
        raise ValueError(f"missing fields: {','.join(missing)}")
    if cell["schema"] != "nbsr-p2d-live-cell-v1":
        raise ValueError("schema: invalid")
    if cell["mode"] not in ("before", "after"):
        raise ValueError("mode: invalid")
    if cell["concurrency"] not in CONCURRENCIES:
        raise ValueError("concurrency: invalid")
    if cell["payload_bytes"] != 1024:
        raise ValueError("payload_bytes: must be 1024")
    if cell["payload_correct"] is not True:
        raise ValueError("payload_correct: must be observed true")
    if cell["errors"] != 0:
        raise ValueError("errors: mandatory zero-error gate failed")
    if cell["mode"] == "after":
        if not 0 <= cell["remaining_credits"] <= 64:
            raise ValueError("remaining_credits: outside 0..64")
        if not 1 <= cell["active_epochs"] <= 2:
            raise ValueError("active_epochs: outside 1..2")
    if not 0 <= cell["replay_entries"] <= cell["replay_limit"]:
        raise ValueError("replay_entries: exceeds exact replay limit")
    if cell["replay_limit"] != 10_000:
        raise ValueError("replay_limit: P2D requires the accepted exact 10000-entry P1F cap")
    if validate_replay_limits(cell) != "PASS":
        raise ValueError("replay_limit: nested measured endpoint violates the exact P1F cap")
    if cell["cpu"].get("status") == "MEASURED":
        if not isinstance(cell["cpu"].get("process_cpu_ns"), int):
            raise ValueError("cpu: measured CPU requires process_cpu_ns")
    elif cell["cpu"].get("status") != "UNAVAILABLE":
        raise ValueError("cpu: status must be MEASURED or UNAVAILABLE")


def select_saturation_concurrency(cells: list[dict]) -> int:
    by_concurrency = {int(cell["concurrency"]): cell for cell in cells}
    if tuple(sorted(by_concurrency)) != CONCURRENCIES:
        raise ValueError("concurrency: sweep is not the exact approved sequence")
    maximum = max(float(cell["operations_per_second"]) for cell in cells)
    threshold = maximum * 0.98
    return next(
        concurrency
        for concurrency in CONCURRENCIES
        if float(by_concurrency[concurrency]["operations_per_second"]) >= threshold
    )


def verify_closed_inventory(root: Path, checksum_file: Path) -> int:
    root = root.resolve()
    checksum_file = checksum_file.resolve()
    expected: dict[str, str] = {}
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, separator, relative = line.partition("  ")
        if separator != "  " or len(digest) != 64 or relative in expected:
            raise ValueError("checksum inventory has malformed or duplicate entries")
        if "\\" in relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("checksum inventory contains a non-canonical path")
        expected[relative] = digest
    observed: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path == checksum_file:
            continue
        if path.is_symlink():
            raise ValueError("checksum inventory rejects symlinks")
        if path.is_file():
            observed[path.relative_to(root).as_posix()] = path
    if set(observed) != set(expected):
        raise ValueError("checksum inventory is not closed")
    for relative, path in observed.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[relative]:
            raise ValueError(f"checksum digest mismatch: {relative}")
    return len(expected)
