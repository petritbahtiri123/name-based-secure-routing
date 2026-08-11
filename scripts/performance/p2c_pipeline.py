"""P2C window selection and immutable KEEP-gate calculations."""

from __future__ import annotations

import statistics

ALLOWED_WINDOWS = (1, 2, 4, 8, 16)


def validate_windows(values: list[int]) -> list[int]:
    if len(values) != len(set(values)) or any(value not in ALLOWED_WINDOWS for value in values):
        raise ValueError("admission windows must be unique members of 1,2,4,8,16")
    return values


def select_window(cells: list[dict]) -> int:
    ordered = sorted(cells, key=lambda cell: cell["window"])
    validate_windows([cell["window"] for cell in ordered])
    maximum = max(cell["throughput"] for cell in ordered)
    threshold = maximum * 0.98
    return next(cell["window"] for cell in ordered if cell["throughput"] >= threshold)


def acceptance(
    before: list[dict],
    after: list[dict],
    *,
    security_pass: bool,
    quality_pass: bool,
    soak_pass: bool,
) -> dict:
    before_throughput = statistics.median(cell["throughput"] for cell in before)
    after_throughput = statistics.median(cell["throughput"] for cell in after)
    before_p99 = statistics.median(cell["p99_ns"] for cell in before)
    after_p99 = statistics.median(cell["p99_ns"] for cell in after)
    throughput_improvement = after_throughput / before_throughput - 1
    p99_change = after_p99 / before_p99 - 1
    errors = sum(cell["errors"] for cell in before + after)
    pending_bounded = all(cell["pending_high_water"] <= cell["window"] for cell in before + after)
    keep = (
        throughput_improvement >= 0.10
        and p99_change <= 0.05
        and errors == 0
        and pending_bounded
        and security_pass
        and quality_pass
        and soak_pass
    )
    return {
        "before_median_throughput": before_throughput,
        "after_median_throughput": after_throughput,
        "throughput_improvement": throughput_improvement,
        "before_median_p99_ns": before_p99,
        "after_median_p99_ns": after_p99,
        "p99_change": p99_change,
        "errors": errors,
        "pending_bounded": pending_bounded,
        "security_pass": security_pass,
        "quality_pass": quality_pass,
        "soak_pass": soak_pass,
        "keep": keep,
    }
