"""B2 CPU-normalized efficiency derivation and conservative classification."""

from __future__ import annotations

import statistics
from typing import Any


def analyze_repeat(record: dict[str, Any]) -> dict[str, Any]:
    completed = int(record.get("completed_operations", 0))
    measured_ns = int(record.get("measured_ns", 0))
    cpu_ns = int(record.get("resources", {}).get("total_cpu_ns", 0))
    affinity = record.get("affinity", {})
    valid = (
        completed > 0
        and measured_ns > 0
        and cpu_ns > 0
        and bool(affinity.get("verified"))
        and int(record.get("errors", -1)) == 0
        and int(record.get("timeouts", -1)) == 0
    )
    operations_per_second = completed * 1e9 / measured_ns if measured_ns else None
    effective_cores = cpu_ns / measured_ns if measured_ns else None
    effective_cores_by_role = (
        {role: int(sample.get("cpu_ns", 0)) / measured_ns for role, sample in record.get("resources", {}).get("roles", {}).items()}
        if measured_ns
        else {}
    )
    goodput = float(record.get("aggregate_application_gbps", 0.0))
    return {
        **record,
        "valid": valid,
        "operations_per_second": operations_per_second,
        "cpu_ns_per_operation": cpu_ns / completed if completed else None,
        "effective_cores": effective_cores,
        "effective_cores_by_role": effective_cores_by_role,
        "gbit_per_second_per_effective_core": goodput / effective_cores if effective_cores else None,
    }


def summarize_cell(records: list[dict[str, Any]]) -> dict[str, Any]:
    derived = [analyze_repeat(record) for record in records]
    valid = [record for record in derived if record["valid"]]

    def median(field: str) -> float | None:
        values = [float(record[field]) for record in valid if record.get(field) is not None]
        return statistics.median(values) if values else None

    first = derived[0]
    role_names = sorted({role for record in valid for role in record["effective_cores_by_role"]})
    median_effective_cores_by_role = {
        role: statistics.median(record["effective_cores_by_role"][role] for record in valid if role in record["effective_cores_by_role"])
        for role in role_names
    }
    return {
        "path": first["path"],
        "payload_bytes": first["payload_bytes"],
        "streams": first["streams"],
        "processors": first["affinity"]["requested_processors"],
        "valid_repeats": len(valid),
        "repeat_count": len(derived),
        "median_operations_per_second": median("operations_per_second"),
        "median_aggregate_application_gbps": median("aggregate_application_gbps"),
        "median_p50_latency_ns": median("p50_latency_ns"),
        "median_p95_latency_ns": median("p95_latency_ns"),
        "median_p99_latency_ns": median("p99_latency_ns"),
        "median_cpu_ns_per_operation": median("cpu_ns_per_operation"),
        "median_effective_cores": median("effective_cores"),
        "median_effective_cores_by_role": median_effective_cores_by_role,
        "median_peak_role_effective_cores": max(median_effective_cores_by_role.values(), default=None),
        "median_gbit_per_second_per_effective_core": median("gbit_per_second_per_effective_core"),
        "peak_private_bytes": max(
            (int(role["peak_private_bytes"]) for record in valid for role in record["resources"]["roles"].values()), default=None
        ),
        "errors": sum(int(record.get("errors", 0)) for record in derived),
        "timeouts": sum(int(record.get("timeouts", 0)) for record in derived),
    }


def classify_cells(cells: list[dict[str, Any]]) -> dict[str, str]:
    complete = bool(cells) and all(cell["valid_repeats"] == cell["repeat_count"] >= 3 for cell in cells)
    nbsr = sorted((cell for cell in cells if cell["path"] == "nbsr"), key=lambda cell: cell["processors"])
    if not complete or not nbsr:
        return {"evidence": "INCONCLUSIVE", "system": "UNRESOLVED"}
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for cell in nbsr:
        grouped.setdefault((cell["payload_bytes"], cell["streams"]), []).append(cell)
    outcomes = []
    for series in grouped.values():
        series.sort(key=lambda cell: cell["processors"])
        if len(series) < 3:
            outcomes.append("UNRESOLVED")
            continue
        one, two, four = series[0], series[1], series[2]
        gain_1_2 = two["median_operations_per_second"] / one["median_operations_per_second"]
        gain_2_4 = four["median_operations_per_second"] / two["median_operations_per_second"]
        peak_role_effective = four["median_peak_role_effective_cores"]
        if gain_1_2 >= 1.5 and gain_2_4 >= 1.5:
            outcomes.append("SCALING")
        elif gain_2_4 < 1.2 and peak_role_effective >= 0.9 * four["processors"]:
            outcomes.append("CPU-LIMITED")
        elif gain_2_4 < 1.2 and peak_role_effective < 0.9 * four["processors"]:
            outcomes.append("SOFTWARE-LIMITED")
        else:
            outcomes.append("UNRESOLVED")
    system = outcomes[0] if len(set(outcomes)) == 1 else "UNRESOLVED"
    return {"evidence": "PASS", "system": system}
