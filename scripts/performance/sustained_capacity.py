"""Strict B5 sustained-capacity evidence analysis."""

from __future__ import annotations

import math
import statistics
from typing import Any


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _slope(values: list[tuple[float, float]]) -> tuple[float, float]:
    if len(values) < 4:
        return 0.0, 0.0
    xs = [item[0] for item in values]
    ys = [item[1] for item in values]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator == 0:
        return 0.0, 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in values) / denominator
    intercept = mean_y - slope * mean_x
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in values)
    total = sum((y - mean_y) ** 2 for y in ys)
    return slope, 1.0 - residual / total if total else 1.0


def _cleanup(diagnostics: dict[str, Any]) -> str:
    if set(diagnostics) != {"source", "destination"}:
        return "INCONCLUSIVE"
    fields = (
        "transport_sessions_current_live", "service_channels_current_live", "application_streams_current_live",
        "nbsr_tasks_current_live", "quic_connections_current_live", "quic_streams_current_live",
        "audit_queue_current_entries", "replay_state_current_entries",
    )
    if any(field not in diagnostics[role] for role in diagnostics for field in fields):
        return "INCONCLUSIVE"
    return "PASS" if all(int(diagnostics[role][field]) == 0 for role in diagnostics for field in fields) else "FAIL"


def analyze_soak_run(
    progress: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    *,
    expected_duration_seconds: int,
    payload_bytes: int,
    streams: int,
) -> dict[str, Any]:
    if expected_duration_seconds <= 0 or payload_bytes <= 0 or streams <= 0:
        raise ValueError("duration, payload, and streams must be positive")
    ordered = sorted(progress, key=lambda item: int(item.get("window_index", -1)))
    invalid: list[str] = []
    required = {
        "window_index", "elapsed_ns", "interval_ns", "completed_operations", "completed_total",
        "goodput_bytes_per_second", "p50_latency_ns", "p95_latency_ns", "p99_latency_ns", "errors", "timeouts",
    }
    for item in ordered:
        missing = sorted(required - item.keys())
        if missing:
            invalid.append(f"progress record missing: {','.join(missing)}")
    if ordered:
        indices = [int(item["window_index"]) for item in ordered if required <= item.keys()]
        if indices != list(range(1, len(indices) + 1)):
            invalid.append("progress window cadence is incomplete or duplicated")
        cumulative = 0
        for item in ordered:
            if not required <= item.keys():
                continue
            cumulative += int(item["completed_operations"])
            if int(item["completed_total"]) != cumulative:
                invalid.append("completed operation accounting does not reconcile")
                break
        observed_ns = sum(int(item["interval_ns"]) for item in ordered if "interval_ns" in item)
        if observed_ns < expected_duration_seconds * 1_000_000_000 * 0.99:
            invalid.append("progress duration is shorter than requested")
    else:
        invalid.append("no progress records")

    completed = sum(int(item.get("completed_operations", 0)) for item in ordered)
    errors = sum(int(item.get("errors", 0)) for item in ordered)
    timeouts = sum(int(item.get("timeouts", 0)) for item in ordered)
    usable = [item for item in ordered if required <= item.keys()]
    third = max(1, len(usable) // 3)
    early = usable[:third]
    late = usable[-third:]
    early_goodput = _median([float(item["goodput_bytes_per_second"]) for item in early]) if early else 0.0
    late_goodput = _median([float(item["goodput_bytes_per_second"]) for item in late]) if late else 0.0
    goodput_drift = (late_goodput / early_goodput - 1.0) * 100 if early_goodput else 0.0
    p95_early = _median([float(item["p95_latency_ns"]) for item in early]) if early else 0.0
    p95_late = _median([float(item["p95_latency_ns"]) for item in late]) if late else 0.0
    p99_early = _median([float(item["p99_latency_ns"]) for item in early]) if early else 0.0
    p99_late = _median([float(item["p99_latency_ns"]) for item in late]) if late else 0.0

    memory: dict[str, Any] = {}
    growth = False
    resource_roles = {str(item.get("role")) for item in resources if item.get("phase") == "steady"}
    if resource_roles != {"source", "destination"}:
        invalid.append("resource series must contain source and destination steady-state samples")
    for role in sorted(resource_roles):
        role_values = sorted(
            (item for item in resources if item.get("role") == role),
            key=lambda item: int(item["timestamp_ns"]),
        )
        values = sorted(
            (item for item in resources if item.get("role") == role and item.get("phase") == "steady"),
            key=lambda item: int(item["timestamp_ns"]),
        )
        points = [(int(item["timestamp_ns"]) / 1e9, float(item["private_bytes"])) for item in values]
        slope, r_squared = _slope(points)
        working_slope, working_r_squared = _slope(
            [(int(item["timestamp_ns"]) / 1e9, float(item["working_set_bytes"])) for item in values]
        )
        delta = (points[-1][1] - points[0][1]) if len(points) >= 2 else 0.0
        end = points[-1][1] if points else 0.0
        role_growth = len(points) >= 4 and slope > 0 and r_squared >= 0.8 and delta > max(1.0, end * 0.02)
        growth = growth or role_growth
        cooldown = [item for item in role_values if item.get("phase") == "cooldown"]
        if not cooldown:
            invalid.append(f"{role} resource series has no cooldown sample")
        cpu_start = int(values[0]["user_cpu_ns"]) + int(values[0]["kernel_cpu_ns"]) if values else 0
        cpu_end = int(values[-1]["user_cpu_ns"]) + int(values[-1]["kernel_cpu_ns"]) if values else 0
        memory[role] = {
            "sample_count": len(values),
            "initial_private_bytes": int(points[0][1]) if points else None,
            "final_private_bytes": int(end) if points else None,
            "initial_working_set_bytes": int(values[0]["working_set_bytes"]) if values else None,
            "final_working_set_bytes": int(values[-1]["working_set_bytes"]) if values else None,
            "post_load_private_bytes": int(cooldown[-1]["private_bytes"]) if cooldown else None,
            "post_load_working_set_bytes": int(cooldown[-1]["working_set_bytes"]) if cooldown else None,
            "peak_private_bytes": max((int(item["private_bytes"]) for item in values), default=None),
            "peak_working_set_bytes": max((int(item["working_set_bytes"]) for item in values), default=None),
            "steady_private_slope_bytes_per_second": slope,
            "steady_private_slope_r_squared": r_squared,
            "steady_working_set_slope_bytes_per_second": working_slope,
            "steady_working_set_slope_r_squared": working_r_squared,
            "continuous_growth": role_growth,
            "median_cpu_percent_assigned": _median([float(item["cpu_percent_assigned"]) for item in values]) if values else None,
            "max_cpu_percent_assigned": max((float(item["cpu_percent_assigned"]) for item in values), default=None),
            "cpu_time_ns": cpu_end - cpu_start if values else None,
            "max_threads": max((int(item["thread_count"]) for item in values), default=None),
            "final_threads": int(cooldown[-1]["thread_count"]) if cooldown else None,
            "max_handles": max((int(item["handle_count"]) for item in values), default=None),
            "final_handles": int(cooldown[-1]["handle_count"]) if cooldown else None,
        }
    cleanup = _cleanup(diagnostics)
    if cleanup == "INCONCLUSIVE":
        invalid.append("cleanup diagnostics are incomplete")
    evidence_status = "INCONCLUSIVE" if invalid else "PASS"
    if evidence_status != "PASS":
        system_result = "UNSTABLE"
    elif growth:
        system_result = "RESOURCE-GROWTH"
    elif errors or timeouts or cleanup == "FAIL":
        system_result = "UNSTABLE"
    else:
        system_result = "STABLE"
    return {
        "schema": "nbsr-b5-soak-analysis-v1",
        "evidence_status": evidence_status,
        "system_result": system_result,
        "invalid_reasons": invalid,
        "duration_seconds": expected_duration_seconds,
        "payload_bytes": payload_bytes,
        "streams": streams,
        "valid_samples": len(usable),
        "completed_operations": completed,
        "median_goodput_bytes_per_second": _median([float(item["goodput_bytes_per_second"]) for item in usable]) if usable else 0.0,
        "early_goodput_bytes_per_second": early_goodput,
        "late_goodput_bytes_per_second": late_goodput,
        "goodput_drift_percent": goodput_drift,
        "median_p50_latency_ns": _median([float(item["p50_latency_ns"]) for item in usable]) if usable else 0.0,
        "median_p95_latency_ns": _median([float(item["p95_latency_ns"]) for item in usable]) if usable else 0.0,
        "median_p99_latency_ns": _median([float(item["p99_latency_ns"]) for item in usable]) if usable else 0.0,
        "p95_drift_percent": (p95_late / p95_early - 1.0) * 100 if p95_early else 0.0,
        "p99_drift_percent": (p99_late / p99_early - 1.0) * 100 if p99_early else 0.0,
        "errors": errors,
        "timeouts": timeouts,
        "cleanup_result": cleanup,
        "memory": memory,
    }
