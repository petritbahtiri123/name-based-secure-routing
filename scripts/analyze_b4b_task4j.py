from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path


PREFIXES = ("quic_connections", "transport_sessions", "service_channels", "application_streams")
SOURCE_REPOSITORY_SHA = "fa46af05db7923a4aa7bb6e4d9c5af8dcb17e5b7"


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("empty percentile input")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def analyze_diagnostic_rows(rows: list[dict]) -> dict:
    if len(rows) < 2:
        raise ValueError("at least two diagnostic rows required")
    ordered = sorted(rows, key=lambda row: int(row["timestamp_ns"]))
    for prefix in PREFIXES:
        completed = [int(row[f"{prefix}_completed"]) for row in ordered]
        if completed != sorted(completed):
            raise ValueError(f"non-monotonic {prefix}_completed")

    occupancy = {
        key: []
        for key in (
            "transport_establishment",
            "control_and_route_admission",
            "channel_and_application_activation",
            "application_and_close",
        )
    }
    for row in ordered:
        live = [int(row[f"{prefix}_current_live"]) for prefix in PREFIXES]
        if not (live[0] >= live[1] >= live[2] >= live[3] >= 0):
            raise ValueError(f"stage ordering violated at timestamp {row['timestamp_ns']}")
        occupancy["transport_establishment"].append(live[0] - live[1])
        occupancy["control_and_route_admission"].append(live[1] - live[2])
        occupancy["channel_and_application_activation"].append(live[2] - live[3])
        occupancy["application_and_close"].append(live[3])

    duration = (int(ordered[-1]["timestamp_ns"]) - int(ordered[0]["timestamp_ns"])) / 1e9
    if duration <= 0:
        raise ValueError("non-positive diagnostic duration")
    rates = {}
    for prefix in PREFIXES:
        rates[prefix] = (int(ordered[-1][f"{prefix}_completed"]) - int(ordered[0][f"{prefix}_completed"])) / duration
    return {
        "duration_seconds": duration,
        "occupancy_peak": {key: max(values) for key, values in occupancy.items()},
        "occupancy_mean": {key: statistics.fmean(values) for key, values in occupancy.items()},
        "completion_rate_per_second": rates,
        "queue_peak": {
            "pending_routes": max(int(row["pending_routes_current_entries"]) for row in ordered),
            "audit": max(int(row["audit_queue_current_entries"]) for row in ordered),
        },
        "final_live": {prefix: int(ordered[-1][f"{prefix}_current_live"]) for prefix in PREFIXES},
    }


def read_ndjson(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_source_manifest(source: Path) -> set[str]:
    manifest = source / "checksums.sha256"
    if not manifest.is_file():
        raise ValueError("source checksum manifest missing")
    verified = set()
    for line in manifest.read_text(encoding="ascii").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64:
            raise ValueError(f"malformed source checksum line: {line!r}")
        path = source / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"source checksum mismatch: {relative}")
        verified.add(relative.replace("\\", "/"))
    return verified


def latency_summary(values: list[float]) -> dict:
    return {"p50_ms": percentile(values, 0.50) / 1e6, "p95_ms": percentile(values, 0.95) / 1e6, "p99_ms": percentile(values, 0.99) / 1e6}


def resource_roles(samples: list[dict]) -> dict:
    result = {}
    for role in sorted({row["role"] for row in samples}):
        rows = sorted((row for row in samples if row["role"] == role), key=lambda row: row["timestamp_ns"])
        elapsed = (rows[-1]["timestamp_ns"] - rows[0]["timestamp_ns"]) / 1e9
        cpu = ((rows[-1]["user_cpu_ns"] + rows[-1]["kernel_cpu_ns"]) - (rows[0]["user_cpu_ns"] + rows[0]["kernel_cpu_ns"])) / 1e9
        result[role] = {
            "effective_cores": cpu / elapsed if elapsed > 0 else 0.0,
            "peak_threads": max(row["thread_count"] for row in rows),
            "peak_handles": max(row["handle_count"] for row in rows),
            "peak_private_bytes": max(row["private_bytes"] for row in rows),
        }
    return result


def analyze_repeat(run_json: Path, rate: int, verified: set[str], source: Path) -> dict:
    record = json.loads(run_json.read_text(encoding="utf-8"))
    run_dir = run_json.parent / run_json.stem.replace("r", "clients-512-connections-1-r", 1)
    inputs = [
        run_json,
        run_dir / "lifecycle-diagnostics.ndjson",
        run_dir / "admission-source.stdout",
        run_dir / "lifecycle-server-result.json",
    ]
    for path in inputs:
        relative = path.relative_to(source).as_posix()
        if relative not in verified:
            raise ValueError(f"input absent from accepted source manifest: {relative}")
    if record.get("schema") != "nbsr-b4b-mixed-connections-repeat-v2":
        raise ValueError(f"unexpected repeat schema: {run_json}")
    if int(record["offered_admission_rate"]) != rate or int(record["requested_clients"]) != 512:
        raise ValueError(f"workload mismatch: {run_json}")
    if (
        record["errors"]
        or int(record["timeouts"])
        or int(record["failed_admissions"])
        or not record["cleanup"]["processes_exited"]
        or not record["cleanup"]["terminal_evidence_exact"]
    ):
        raise ValueError(f"failed lifecycle evidence: {run_json}")
    diagnostics = analyze_diagnostic_rows(read_ndjson(run_dir / "lifecycle-diagnostics.ndjson"))
    clients = read_ndjson(run_dir / "admission-source.stdout")
    successful = [row for row in clients if row["success"]]
    if len(successful) != int(record["successful_admissions"]):
        raise ValueError(f"client evidence count mismatch: {run_json}")
    if any(diagnostics["final_live"].values()) or not record["cleanup"]["all_zero"]:
        raise ValueError(f"cleanup not zero: {run_json}")
    stage_values = {
        "transport_handshake": [row["transport_handshake_ns"] for row in successful],
        "control_hello": [row["hello_rtt_ns"] for row in successful],
        "source_admission": [row["source_admission_ns"] for row in successful],
        "route_open": [row["route_open_rtt_ns"] for row in successful],
        "channel_binding": [row["channel_binding_ns"] for row in successful],
        "stream_open": [row["stream_open_rtt_ns"] for row in successful],
        "total_scenario": [row["total_scenario_ns"] for row in successful],
    }
    server = json.loads((run_dir / "lifecycle-server-result.json").read_text(encoding="utf-8"))
    if server.get("status") != "PASS" or len(server["samples"]) != len(successful):
        raise ValueError(f"destination evidence count mismatch: {run_json}")
    stage_values["destination_admission"] = [row["destination_admission_ns"] for row in server["samples"]]
    stage_values["application_processing"] = [row["application_processing_ns"] for row in server["samples"]]
    return {
        "repeat": int(record["repeat"]),
        "valid": bool(record["valid"]),
        "offered_rate": float(record["offered_admission_rate"]),
        "completion_rate": float(record["admission_rate"]),
        "successful": int(record["successful_admissions"]),
        "requested": int(record["requested_clients"]),
        "peak_pending_clients": int(record["peak_pending_clients"]),
        "effective_cores": float(record["effective_cores"]),
        "host_cpu_percent": float(record["host_counters"]["processor_time_percent_median"]),
        "memory_private_bytes_peak": float(record["resources"]["peak_private_bytes"]),
        "thread_count_peak": int(record["resources"]["peak_threads"]),
        "handle_count_peak": int(record["resources"]["peak_handles"]),
        "resource_roles": resource_roles(record["resource_samples"]),
        "stage_latency": {key: latency_summary(values) for key, values in stage_values.items()},
        "diagnostics": diagnostics,
    }


def median_tree(rows: list[dict], path: tuple[str, ...]) -> float:
    values = []
    for row in rows:
        value = row
        for key in path:
            value = value[key]
        values.append(float(value))
    return statistics.median(values)


def analyze(source: Path) -> dict:
    verified = verify_source_manifest(source)
    environment = json.loads((source / "environment.json").read_text(encoding="utf-8"))
    if environment.get("repository_sha") != SOURCE_REPOSITORY_SHA or environment.get("total_clients") != 512:
        raise ValueError("unexpected Task 4i source provenance")
    cells = []
    for rate in (125, 150, 200):
        repeats = [analyze_repeat(path, rate, verified, source) for path in sorted((source / "raw" / f"rate-{rate}").glob("r*.json"))]
        expected_repeats = 5 if rate == 200 else 3
        if len(repeats) != expected_repeats:
            raise ValueError(f"expected {expected_repeats} repeats at {rate}/s, found {len(repeats)}")
        if not repeats or not all(row["valid"] for row in repeats):
            raise ValueError(f"missing or invalid repeat at {rate}/s")
        stages = repeats[0]["stage_latency"].keys()
        occupancy = repeats[0]["diagnostics"]["occupancy_peak"].keys()
        roles = repeats[0]["resource_roles"].keys()
        cells.append(
            {
                "offered_rate": rate,
                "repeat_count": len(repeats),
                "completion_rate_median": median_tree(repeats, ("completion_rate",)),
                "achieved_percent": 100 * median_tree(repeats, ("completion_rate",)) / rate,
                "successful_median": median_tree(repeats, ("successful",)),
                "peak_pending_clients_median": median_tree(repeats, ("peak_pending_clients",)),
                "effective_cores_median": median_tree(repeats, ("effective_cores",)),
                "host_cpu_percent_median": median_tree(repeats, ("host_cpu_percent",)),
                "memory_private_bytes_peak_median": median_tree(repeats, ("memory_private_bytes_peak",)),
                "threads_peak_median": median_tree(repeats, ("thread_count_peak",)),
                "handles_peak_median": median_tree(repeats, ("handle_count_peak",)),
                "role_effective_cores_median": {role: median_tree(repeats, ("resource_roles", role, "effective_cores")) for role in roles},
                "occupancy_peak_median": {key: median_tree(repeats, ("diagnostics", "occupancy_peak", key)) for key in occupancy},
                "queue_peak_median": {key: median_tree(repeats, ("diagnostics", "queue_peak", key)) for key in ("pending_routes", "audit")},
                "stage_latency_median": {
                    stage: {p: median_tree(repeats, ("stage_latency", stage, p)) for p in ("p50_ms", "p95_ms", "p99_ms")}
                    for stage in stages
                },
                "repeats": repeats,
            }
        )
    stable, degraded, saturated = cells
    completion_plateau_percent = 100 * (saturated["completion_rate_median"] / degraded["completion_rate_median"] - 1)
    source_core_peak = max(cell["role_effective_cores_median"]["admission-source"] for cell in cells)
    destination_core_peak = max(cell["role_effective_cores_median"]["admission-destination"] for cell in cells)
    local_validation_growth = (
        saturated["stage_latency_median"]["destination_admission"]["p99_ms"]
        / stable["stage_latency_median"]["destination_admission"]["p99_ms"]
    )
    network_progress_growth = (
        saturated["stage_latency_median"]["control_hello"]["p99_ms"] / stable["stage_latency_median"]["control_hello"]["p99_ms"]
    )
    attribution_supported = (
        abs(completion_plateau_percent) <= 2.0
        and source_core_peak >= 0.90
        and destination_core_peak < 0.75
        and local_validation_growth < 1.25
        and network_progress_growth >= 10.0
    )
    return {
        "schema": "nbsr-b4b-task4j-analysis-v1",
        "source": str(source).replace("\\", "/"),
        "classification": "HARNESS-LIMITED:admission-source-current-thread-runtime" if attribution_supported else "UNRESOLVED",
        "attribution": {
            "supported": attribution_supported,
            "completion_change_150_to_200_percent": completion_plateau_percent,
            "admission_source_effective_core_peak": source_core_peak,
            "admission_destination_effective_core_peak": destination_core_peak,
            "destination_validation_p99_growth_ratio_125_to_200": local_validation_growth,
            "control_hello_p99_growth_ratio_125_to_200": network_progress_growth,
            "scope": "benchmark admission-source process scheduling; not production NBSR capacity",
        },
        "cells": cells,
    }


def write_outputs(result: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    source = Path(result["source"])
    source_lines = []
    for rate in (125, 150, 200):
        for pattern in ("r*.json", "*/admission-source.stdout", "*/lifecycle-server-result.json", "*/lifecycle-diagnostics.ndjson"):
            for path in sorted((source / "raw" / f"rate-{rate}").glob(pattern)):
                relative = path.as_posix()
                source_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
    (output / "source-checksums.sha256").write_text("\n".join(source_lines) + "\n", encoding="ascii")
    with (output / "stage-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "offered_rate",
                "completion_rate",
                "achieved_percent",
                "transport_peak",
                "control_route_peak",
                "channel_app_peak",
                "app_close_peak",
                "handshake_p99_ms",
                "route_open_p99_ms",
                "host_cpu_percent",
            ]
        )
        for cell in result["cells"]:
            occ = cell["occupancy_peak_median"]
            lat = cell["stage_latency_median"]
            writer.writerow(
                [
                    cell["offered_rate"],
                    cell["completion_rate_median"],
                    cell["achieved_percent"],
                    occ["transport_establishment"],
                    occ["control_and_route_admission"],
                    occ["channel_and_application_activation"],
                    occ["application_and_close"],
                    lat["transport_handshake"]["p99_ms"],
                    lat["route_open"]["p99_ms"],
                    cell["host_cpu_percent_median"],
                ]
            )
    hashes = []
    for path in sorted(output.glob("*")):
        if path.name != "checksums.sha256":
            hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (output / "checksums.sha256").write_text("\n".join(hashes) + "\n", encoding="ascii")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.source)
    if args.output:
        write_outputs(result, args.output)
    else:
        print(json.dumps(result, indent=2))
