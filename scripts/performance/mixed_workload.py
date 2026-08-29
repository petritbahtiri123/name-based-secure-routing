"""B4 mixed established-forwarding and admission analysis."""

from __future__ import annotations

from collections import defaultdict
import math
import statistics
from typing import Any


def workload_cells(*, smoke: bool) -> list[dict[str, float | int]]:
    rates = [0.0, 5.0] if smoke else [0.0, 25.0, 100.0, 400.0]
    duration = 2.0 if smoke else 10.0
    return [
        {
            "payload_bytes": 1024,
            "streams": 8,
            "duration_seconds": duration,
            "admission_rate_per_second": rate,
        }
        for rate in rates
    ]


def scheduled_admission_count(rate: float, duration: float) -> int:
    if rate < 0 or duration <= 0:
        raise ValueError("rate must be non-negative and duration must be positive")
    return int(math.floor(rate * duration + 0.5))


def _median(records: list[dict[str, Any]], field: str) -> float:
    return float(statistics.median(float(record[field]) for record in records))


def _resource_value(record: dict[str, Any], field: str) -> float:
    resources = record.get("resources", {})
    if field in resources:
        return float(resources[field])
    roles = resources.get("roles", {})
    return float(sum(float(role.get(field, 0)) for role in roles.values()))


def _optional_median(records: list[dict[str, Any]], field: str) -> float | None:
    values = [float(record[field]) for record in records if record.get(field) is not None]
    return float(statistics.median(values)) if values else None


def analyze_mixed_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    required = {
        "repeat",
        "payload_bytes",
        "streams",
        "duration_seconds",
        "admission_rate_per_second",
        "scheduled_admissions",
        "successful_admissions",
        "failed_admissions",
        "timeouts",
        "errors",
        "established_goodput_bytes_per_second",
        "p99_latency_ns",
        "planned_admission_rates",
    }
    for record in records:
        missing = sorted(required - record.keys())
        if missing:
            invalid.append({"record": record, "reason": f"missing fields: {', '.join(missing)}"})
        else:
            valid.append(record)

    grouped: dict[tuple[int, int, float, float], list[dict[str, Any]]] = defaultdict(list)
    for record in valid:
        grouped[
            (
                int(record["payload_bytes"]),
                int(record["streams"]),
                float(record["duration_seconds"]),
                float(record["admission_rate_per_second"]),
            )
        ].append(record)
    workload_shapes = {(key[0], key[1], key[2]) for key in grouped}
    if len(workload_shapes) != 1:
        invalid.extend({"record": record, "reason": "mismatched workload shape"} for record in valid)

    planned_sets = {tuple(float(rate) for rate in record["planned_admission_rates"]) for record in valid}
    observed_rates = {key[3] for key in grouped}
    planned_rates = set(next(iter(planned_sets), ()))
    if len(planned_sets) != 1 or observed_rates != planned_rates or 0.0 not in observed_rates:
        invalid.extend({"record": record, "reason": "planned cells, observed cells, or baseline do not match"} for record in valid)
    for key, values in grouped.items():
        repeats = [int(value["repeat"]) for value in values]
        expected_admissions = scheduled_admission_count(key[3], key[2])
        if len(repeats) != len(set(repeats)):
            invalid.extend({"record": value, "reason": "duplicate repeat identifier"} for value in values)
        if any(int(value["scheduled_admissions"]) != expected_admissions for value in values):
            invalid.extend({"record": value, "reason": "scheduled admission count does not match rate and duration"} for value in values)

    baseline_records = next((values for key, values in grouped.items() if key[3] == 0.0), [])
    baseline_goodput = _median(baseline_records, "established_goodput_bytes_per_second") if baseline_records else 0.0
    baseline_p99 = _median(baseline_records, "p99_latency_ns") if baseline_records else 0.0
    cells: list[dict[str, Any]] = []
    first_saturation = None
    for (_, _, _, rate), values in sorted(grouped.items()):
        goodput = _median(values, "established_goodput_bytes_per_second")
        p99 = _median(values, "p99_latency_ns")
        scheduled = _median(values, "scheduled_admissions")
        successful = _median(values, "successful_admissions")
        failed = sum(int(value["failed_admissions"]) for value in values)
        errors = sum(int(value["errors"]) for value in values)
        timeouts = sum(int(value["timeouts"]) for value in values)
        achieved_ratio = successful / scheduled if scheduled else 1.0
        goodput_ratio = goodput / baseline_goodput if baseline_goodput else (1.0 if rate == 0 else 0.0)
        p99_ratio = p99 / baseline_p99 if baseline_p99 else (1.0 if rate == 0 else float("inf"))
        reasons = []
        if failed or errors:
            reasons.append("admission failures")
        if timeouts:
            reasons.append("timeouts")
        if achieved_ratio < 0.9:
            reasons.append("achieved admission rate below 90%")
        if goodput_ratio < 0.9:
            reasons.append("established goodput below 90%")
        if p99_ratio > 2.0:
            reasons.append("p99 latency above 2x baseline")
        status = "BASELINE" if rate == 0 else ("SATURATED" if reasons else "STABLE")
        if status == "SATURATED" and first_saturation is None:
            first_saturation = {"admission_rate_per_second": rate, "reason": "; ".join(reasons)}
        cells.append(
            {
                "payload_bytes": int(values[0]["payload_bytes"]),
                "streams": int(values[0]["streams"]),
                "duration_seconds": float(values[0]["duration_seconds"]),
                "admission_rate_per_second": rate,
                "valid_repeats": len(values),
                "median_established_goodput_bytes_per_second": goodput,
                "median_p99_latency_ns": p99,
                "median_successful_admissions": successful,
                "median_scheduled_admissions": scheduled,
                "median_achieved_admissions_per_second": successful / float(values[0]["duration_seconds"]),
                "median_admission_p50_latency_ns": _optional_median(values, "admission_p50_latency_ns"),
                "median_admission_p95_latency_ns": _optional_median(values, "admission_p95_latency_ns"),
                "median_admission_p99_latency_ns": _optional_median(values, "admission_p99_latency_ns"),
                "median_max_admission_start_lateness_ns": _median(values, "max_admission_start_lateness_ns"),
                "median_total_cpu_seconds": statistics.median(
                    _resource_value(value, "total_cpu_ns") / 1e9 for value in values
                ),
                "median_peak_working_set_bytes": statistics.median(
                    _resource_value(value, "peak_working_set_bytes") for value in values
                ),
                "median_peak_private_bytes": statistics.median(
                    _resource_value(value, "peak_private_bytes") for value in values
                ),
                "median_achieved_admission_ratio": achieved_ratio,
                "median_goodput_ratio_to_baseline": goodput_ratio,
                "median_p99_ratio_to_baseline": p99_ratio,
                "failed_admissions": failed,
                "errors": errors,
                "timeouts": timeouts,
                "status": status,
            }
        )
    enough = bool(cells) and all(cell["valid_repeats"] >= 3 for cell in cells)
    classification = "INCONCLUSIVE" if invalid or not enough else ("PARTIAL" if first_saturation else "PASS")
    return {
        "schema": "nbsr-b4-mixed-analysis-v1",
        "classification": classification,
        "stability_limits": {"minimum_goodput_ratio": 0.9, "maximum_p99_ratio": 2.0, "minimum_achieved_admission_ratio": 0.9},
        "cells": cells,
        "first_saturation": first_saturation,
        "invalid_records": invalid,
    }
