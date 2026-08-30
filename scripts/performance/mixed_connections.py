"""B4b established forwarding with new connection and route-admission analysis."""

from __future__ import annotations

from collections import defaultdict
import statistics
from typing import Any


def load_levels(*, validation: bool) -> list[tuple[int, int]]:
    if validation:
        return [(0, 0), (1, 2), (2, 2)]
    return [(0, 0), *((clients, 4) for clients in (1, 2, 4, 8, 16, 32, 64))]


def admission_server_specs(clients: int, connections_per_client: int) -> list[tuple[int, int]]:
    if clients < 0 or connections_per_client < 0:
        raise ValueError("client and connection counts must be non-negative")
    return [(index, index * connections_per_client) for index in range(clients)]


def remember_completion(previous: float | None, *, pending: int, now: float) -> float | None:
    if previous is not None:
        return previous
    return now if pending == 0 else None


def _median(records: list[dict[str, Any]], field: str) -> float:
    return float(statistics.median(float(record[field]) for record in records))


def _optional_median(records: list[dict[str, Any]], field: str) -> float | None:
    values = [float(record[field]) for record in records if record.get(field) is not None]
    return float(statistics.median(values)) if values else None


def analyze_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        "repeat",
        "clients",
        "connections_per_client",
        "planned_clients",
        "scheduled_admissions",
        "successful_admissions",
        "failed_admissions",
        "errors",
        "timeouts",
        "established_goodput_bytes_per_second",
        "established_p95_latency_ns",
        "established_p99_latency_ns",
        "admission_elapsed_seconds",
        "peak_pending_clients",
        "resources",
        "cleanup",
    }
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    cleanup_failure = False
    partial_saturation = False
    for record in records:
        missing = sorted(required - record.keys())
        if missing:
            invalid.append({"record": record, "reason": f"missing fields: {', '.join(missing)}"})
            continue
        cleanup = record["cleanup"]
        if not cleanup.get("processes_exited"):
            invalid.append({"record": record, "reason": "cleanup did not return owned resources and processes to zero"})
            cleanup_failure = True
            continue
        if not cleanup.get("all_zero"):
            if record.get("saturation_failure"):
                partial_saturation = True
            else:
                invalid.append({"record": record, "reason": "cleanup did not return owned resources and processes to zero"})
                cleanup_failure = True
                continue
        valid.append(record)

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in valid:
        grouped[int(record["clients"])].append(record)
    planned_sets = {tuple(int(value) for value in record["planned_clients"]) for record in valid}
    planned = set(next(iter(planned_sets), ()))
    if len(planned_sets) != 1 or set(grouped) != planned or 0 not in grouped:
        invalid.append({"record": {}, "reason": "planned client levels, observed levels, or baseline do not match"})
    for clients, values in grouped.items():
        repeats = [int(value["repeat"]) for value in values]
        if len(repeats) != len(set(repeats)):
            invalid.append({"record": {}, "reason": f"duplicate repeat identifier at clients={clients}"})
        for value in values:
            expected = int(value["clients"]) * int(value["connections_per_client"])
            if int(value["scheduled_admissions"]) != expected:
                invalid.append({"record": value, "reason": "scheduled admissions do not match clients times connections"})

    baseline = grouped.get(0, [])
    baseline_goodput = _median(baseline, "established_goodput_bytes_per_second") if baseline else 0.0
    baseline_p99 = _median(baseline, "established_p99_latency_ns") if baseline else 0.0
    cells: list[dict[str, Any]] = []
    for clients, values in sorted(grouped.items()):
        scheduled = _median(values, "scheduled_admissions")
        successful = _median(values, "successful_admissions")
        goodput = _median(values, "established_goodput_bytes_per_second")
        p99 = _median(values, "established_p99_latency_ns")
        completion_ratio = successful / scheduled if scheduled else 1.0
        goodput_ratio = goodput / baseline_goodput if baseline_goodput else 0.0
        p99_ratio = p99 / baseline_p99 if baseline_p99 else float("inf")
        failed = sum(int(value["failed_admissions"]) for value in values)
        errors = sum(int(value["errors"]) for value in values)
        timeouts = sum(int(value["timeouts"]) for value in values)
        reasons = []
        if failed or errors:
            reasons.append("admission failures")
        if timeouts:
            reasons.append("timeouts")
        if completion_ratio < 0.9:
            reasons.append("admission completion below 90%")
        if goodput_ratio < 0.75:
            reasons.append("established goodput below 75%")
        if p99_ratio > 3.0:
            reasons.append("established p99 above 3x baseline")
        if clients == 0:
            status = "BASELINE"
        elif reasons:
            status = "SATURATED"
        elif goodput_ratio < 0.9 or p99_ratio > 2.0:
            status = "DEGRADED"
        else:
            status = "STABLE"
        elapsed = _median(values, "admission_elapsed_seconds")
        cells.append(
            {
                "clients": clients,
                "connections_per_client": int(values[0]["connections_per_client"]),
                "valid_repeats": len(values),
                "median_scheduled_admissions": scheduled,
                "median_successful_admissions": successful,
                "median_achieved_admissions_per_second": successful / elapsed if elapsed else 0.0,
                "median_established_goodput_bytes_per_second": goodput,
                "median_established_p95_latency_ns": _median(values, "established_p95_latency_ns"),
                "median_established_p99_latency_ns": p99,
                "median_goodput_ratio_to_baseline": goodput_ratio,
                "median_p99_ratio_to_baseline": p99_ratio,
                "median_admission_p50_latency_ns": _optional_median(values, "admission_p50_latency_ns"),
                "median_admission_p95_latency_ns": _optional_median(values, "admission_p95_latency_ns"),
                "median_admission_p99_latency_ns": _optional_median(values, "admission_p99_latency_ns"),
                "median_peak_pending_clients": _median(values, "peak_pending_clients"),
                "median_cpu_seconds": statistics.median(float(value["resources"]["cpu_seconds"]) for value in values),
                "median_peak_working_set_bytes": statistics.median(float(value["resources"]["peak_working_set_bytes"]) for value in values),
                "median_peak_private_bytes": statistics.median(float(value["resources"]["peak_private_bytes"]) for value in values),
                "failed_admissions": failed,
                "errors": errors,
                "timeouts": timeouts,
                "status": status,
            }
        )

    enough = bool(cells) and all(cell["valid_repeats"] >= 3 for cell in cells)
    evidence = ("PARTIAL" if partial_saturation else "PASS") if enough and not invalid else "INCONCLUSIVE"
    load_cells = [cell for cell in cells if cell["status"] != "BASELINE"]
    terminal_status = load_cells[-1]["status"] if load_cells else "STABLE"
    first_saturation = None
    if terminal_status == "SATURATED":
        saturation_suffix = []
        for cell in reversed(load_cells):
            if cell["status"] != "SATURATED":
                break
            saturation_suffix.append(cell)
        first = saturation_suffix[-1]
        reasons = []
        if first["failed_admissions"] or first["errors"]:
            reasons.append("admission failures")
        if first["timeouts"]:
            reasons.append("timeouts")
        if first["median_successful_admissions"] / first["median_scheduled_admissions"] < 0.9:
            reasons.append("admission completion below 90%")
        if first["median_goodput_ratio_to_baseline"] < 0.75:
            reasons.append("established goodput below 75%")
        if first["median_p99_ratio_to_baseline"] > 3.0:
            reasons.append("established p99 above 3x baseline")
        first_saturation = {"clients": first["clients"], "reason": "; ".join(reasons)}
    if cleanup_failure:
        system = "UNSTABLE"
    elif cells and not invalid:
        system = terminal_status
    else:
        system = "UNSTABLE"
    return {
        "schema": "nbsr-b4b-mixed-connections-analysis-v1",
        "evidence": evidence,
        "system": system,
        "thresholds": {
            "stable_minimum_goodput_ratio": 0.9,
            "stable_maximum_p99_ratio": 2.0,
            "saturation_minimum_goodput_ratio": 0.75,
            "saturation_maximum_p99_ratio": 3.0,
            "minimum_completion_ratio": 0.9,
        },
        "cells": cells,
        "first_saturation": first_saturation,
        "invalid_records": invalid,
    }
