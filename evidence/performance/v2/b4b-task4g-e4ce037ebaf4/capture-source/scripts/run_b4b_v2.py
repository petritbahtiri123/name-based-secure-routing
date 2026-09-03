from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_b4b_mixed_connections import run_cell, write_json
from scripts.run_p2a_established import build
from scripts.run_performance_validation import ROOT, environment as host_environment


CLIENT_LEVELS = (8, 16, 32, 64, 128, 256, 512)
CONNECTIONS_PER_CLIENT = 1
HOST_COUNTERS = (
    r"\Processor(_Total)\% Processor Time",
    r"\System\Processor Queue Length",
    r"\System\Context Switches/sec",
    r"\Memory\Committed Bytes",
    r"\Memory\Available Bytes",
)


def coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2 or statistics.mean(values) == 0:
        return 0.0
    return statistics.stdev(values) / statistics.mean(values)


def required_repeats(records: list[dict[str, Any]]) -> int:
    if len(records) < 3:
        return 3
    goodput_cv = coefficient_of_variation(
        [float(record["established_goodput_bytes_per_second"]) for record in records]
    )
    rates = [float(record["admission_rate"]) for record in records]
    admission_cv = coefficient_of_variation(rates) if any(rates) else 0.0
    return 5 if goodput_cv > 0.05 or admission_cv > 0.05 else 3


def classify_cell(candidate: dict[str, Any], baseline: dict[str, Any]) -> str:
    scheduled = int(candidate["scheduled_admissions"])
    completion = (
        int(candidate["successful_admissions"]) / scheduled if scheduled else 1.0
    )
    goodput_ratio = (
        float(candidate["established_goodput_bytes_per_second"])
        / float(baseline["established_goodput_bytes_per_second"])
    )
    p99_ratio = (
        int(candidate["established_p99_latency_ns"])
        / int(baseline["established_p99_latency_ns"])
    )
    cleanup = candidate["cleanup"]
    if (
        int(candidate["errors"])
        or int(candidate["timeouts"])
        or completion < 0.90
        or goodput_ratio < 0.75
        or p99_ratio > 2.0
        or not cleanup.get("all_zero")
        or not cleanup.get("processes_exited")
    ):
        return "SATURATED"
    if completion < 0.95 or goodput_ratio < 0.90 or p99_ratio > 1.25:
        return "DEGRADED"
    return "STABLE"


def should_stop_after_saturation(records: list[dict[str, Any]]) -> bool:
    return (
        len(records) >= 3
        and all(record.get("valid") for record in records)
        and all(record.get("status") == "SATURATED" for record in records)
    )


def classify_evidence(cells: list[dict[str, Any]], invalid: list[dict[str, Any]]) -> str:
    if any(
        not cell["cleanup_pass"] or not cell["process_cleanup_pass"] for cell in cells
    ):
        return "FAIL"
    statuses = [cell["status"] for cell in cells if cell["status"] != "BASELINE"]
    if not invalid and all(status in statuses for status in ("STABLE", "DEGRADED", "SATURATED")):
        return "PASS"
    return "PARTIAL"


def start_host_counters(path: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["typeperf", *HOST_COUNTERS, "-si", "1", "-f", "CSV", "-o", str(path), "-y"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def stop_host_counters(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def read_host_counters(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "UNAVAILABLE", "reason": "typeperf output missing"}
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    samples: list[list[float]] = []
    for row in rows[1:]:
        if len(row) != len(HOST_COUNTERS) + 1:
            continue
        try:
            samples.append([float(value) for value in row[1:]])
        except ValueError:
            continue
    if len(samples) < 2:
        return {"status": "UNAVAILABLE", "reason": "insufficient typeperf samples"}
    names = (
        "processor_time_percent",
        "processor_queue_length",
        "context_switches_per_second",
        "committed_bytes",
        "available_bytes",
    )
    return {
        "status": "MEASURED",
        "sample_count": len(samples),
        **{
            f"{name}_median": statistics.median(sample[index] for sample in samples)
            for index, name in enumerate(names)
        },
        **{
            f"{name}_max": max(sample[index] for sample in samples)
            for index, name in enumerate(names)
        },
    }


def valid_record(record: dict[str, Any]) -> bool:
    required = {
        "successful_admissions",
        "failed_admissions",
        "established_goodput_bytes_per_second",
        "established_p99_latency_ns",
        "admission_elapsed_seconds",
        "resources",
        "cleanup",
    }
    return (required <= record.keys() and record["cleanup"].get("processes_exited", False)
            and record.get("stderr_capture", {}).get("valid", True)
            and record.get("timeline_capture", {}).get("valid", True))


def run_measured_cell(*args: Any, counter_path: Path, **kwargs: Any) -> dict[str, Any]:
    counter = start_host_counters(counter_path)
    started = time.monotonic()
    try:
        record = run_cell(*args, **kwargs)
    finally:
        stop_host_counters(counter)
    record["observed_elapsed_seconds"] = time.monotonic() - started
    record["host_counters"] = read_host_counters(counter_path)
    record["admission_rate"] = (
        int(record["successful_admissions"]) / float(record["admission_elapsed_seconds"])
    )
    record["effective_cores"] = (
        float(record["resources"]["cpu_seconds"]) / record["observed_elapsed_seconds"]
    )
    record["valid"] = valid_record(record)
    return record


def summarize_cell(records: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    representative = {
        "scheduled_admissions": statistics.median(
            int(record["scheduled_admissions"]) for record in records
        ),
        "successful_admissions": statistics.median(
            int(record["successful_admissions"]) for record in records
        ),
        "errors": sum(int(record["errors"]) for record in records),
        "timeouts": sum(int(record["timeouts"]) for record in records),
        "established_goodput_bytes_per_second": statistics.median(
            float(record["established_goodput_bytes_per_second"]) for record in records
        ),
        "established_p99_latency_ns": statistics.median(
            int(record["established_p99_latency_ns"]) for record in records
        ),
        "cleanup": {
            "all_zero": all(record["cleanup"].get("all_zero") for record in records),
            "processes_exited": all(
                record["cleanup"].get("processes_exited") for record in records
            ),
        },
    }
    scheduled = float(representative["scheduled_admissions"])
    successful = float(representative["successful_admissions"])
    goodputs = [float(record["established_goodput_bytes_per_second"]) for record in records]
    rates = [float(record["admission_rate"]) for record in records]
    status = "BASELINE" if int(records[0]["clients"]) == 0 else classify_cell(
        representative, baseline
    )
    return {
        "clients": int(records[0]["clients"]),
        "connections_per_client": int(records[0]["connections_per_client"]),
        "repeat_count": len(records),
        "status": status,
        "median_requested_admissions": scheduled,
        "median_successful_admissions": successful,
        "admission_completion_ratio": successful / scheduled if scheduled else 1.0,
        "median_admissions_per_second": statistics.median(rates),
        "admission_rate_cv": coefficient_of_variation(rates) if any(rates) else 0.0,
        "median_established_gbps": statistics.median(goodputs) * 8 / 1e9,
        "established_goodput_cv": coefficient_of_variation(goodputs),
        "median_established_p50_latency_ns": statistics.median(
            int(record["established_p50_latency_ns"]) for record in records
        ),
        "median_established_p95_latency_ns": statistics.median(
            int(record["established_p95_latency_ns"]) for record in records
        ),
        "median_established_p99_latency_ns": representative[
            "established_p99_latency_ns"
        ],
        "goodput_ratio_to_baseline": representative[
            "established_goodput_bytes_per_second"
        ]
        / float(baseline["established_goodput_bytes_per_second"]),
        "p99_ratio_to_baseline": representative["established_p99_latency_ns"]
        / int(baseline["established_p99_latency_ns"]),
        "median_admission_p50_latency_ns": statistics.median(
            int(record["admission_p50_latency_ns"]) for record in records
            if record["admission_p50_latency_ns"] is not None
        )
        if scheduled
        else None,
        "median_admission_p95_latency_ns": statistics.median(
            int(record["admission_p95_latency_ns"]) for record in records
            if record["admission_p95_latency_ns"] is not None
        )
        if scheduled
        else None,
        "median_admission_p99_latency_ns": statistics.median(
            int(record["admission_p99_latency_ns"]) for record in records
            if record["admission_p99_latency_ns"] is not None
        )
        if scheduled
        else None,
        "median_effective_cores": statistics.median(
            float(record["effective_cores"]) for record in records
        ),
        "median_peak_working_set_bytes": statistics.median(
            int(record["resources"]["peak_working_set_bytes"]) for record in records
        ),
        "median_peak_private_bytes": statistics.median(
            int(record["resources"]["peak_private_bytes"]) for record in records
        ),
        "median_peak_handles": statistics.median(
            int(record["resources"]["peak_handles"]) for record in records
        ),
        "median_peak_threads": statistics.median(
            int(record["resources"]["peak_threads"]) for record in records
        ),
        "median_peak_processes": statistics.median(
            int(record["resources"]["peak_processes"]) for record in records
        ),
        "median_peak_pending_clients": statistics.median(
            int(record["peak_pending_clients"]) for record in records
        ),
        "errors": representative["errors"],
        "timeouts": representative["timeouts"],
        "cleanup_pass": representative["cleanup"]["all_zero"],
        "process_cleanup_pass": representative["cleanup"]["processes_exited"],
        "host_counters": {
            key: statistics.median(float(record["host_counters"][key]) for record in records)
            for key in records[0]["host_counters"]
            if key.endswith("_median")
            and all(record["host_counters"].get("status") == "MEASURED" for record in records)
        },
    }


def render_summary(analysis: dict[str, Any], command: str) -> str:
    lines = [
        "# B4b-v2 Multi-client Connection and Route Scaling",
        "",
        f"Evidence: **{analysis['evidence']}**",
        f"System: **{analysis['system']}**",
        "",
        "| Clients | Repeats | Admissions | Admissions/s | Established Gbit/s | Goodput CV | p99 ms | p99/base | Cores | Private MiB | Pending | Errors/timeouts | Status |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for cell in analysis["cells"]:
        lines.append(
            f"| {cell['clients']} | {cell['repeat_count']} | "
            f"{cell['median_successful_admissions']:.0f}/{cell['median_requested_admissions']:.0f} | "
            f"{cell['median_admissions_per_second']:.2f} | {cell['median_established_gbps']:.3f} | "
            f"{cell['established_goodput_cv']:.2%} | {cell['median_established_p99_latency_ns']/1e6:.3f} | "
            f"{cell['p99_ratio_to_baseline']:.3f} | {cell['median_effective_cores']:.2f} | "
            f"{cell['median_peak_private_bytes']/1048576:.1f} | {cell['median_peak_pending_clients']:.0f} | "
            f"{cell['errors']}/{cell['timeouts']} | {cell['status']} |"
        )
    lines.extend(
        [
            "",
            f"First degraded cell: {analysis['first_degraded_clients']}",
            f"First saturated cell: {analysis['first_saturated_clients']}",
            f"Stop reason: {analysis['stop_reason']}",
            "",
            "Each requested logical client is an independent task within one bounded source driver, creating one fresh QUIC transport connection, control session, route/channel admission, and application stream while established forwarding remains active. One concurrent admission destination and the unchanged established-forwarding pair are included in owned-resource telemetry.",
            "",
            "The classification uses the Funding-Grade V2 thresholds. A hardware limit is not inferred from throughput alone.",
            "",
            f"Command: `{command}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=20.0)
    parser.add_argument("--warmup-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    if args.duration_seconds <= 0 or args.warmup_seconds <= 0:
        raise ValueError("durations must be positive")
    args.output.mkdir(parents=True)
    raw = args.output / "raw"
    raw.mkdir()
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b4b-v2"))
    binaries = build(target)
    planned = [0, *CLIENT_LEVELS]
    all_records: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    baseline_record: dict[str, Any] | None = None
    stop_reason = "upper requested level reached without saturation"
    for clients in planned:
        cell_records: list[dict[str, Any]] = []
        connections = 0 if clients == 0 else CONNECTIONS_PER_CLIENT
        target_repeats = 3
        repeat = 1
        while repeat <= target_repeats:
            print(f"running clients={clients} repeat={repeat}/{target_repeats}", flush=True)
            counter_path = raw / f"clients-{clients}-r{repeat}-host.csv"
            try:
                record = run_measured_cell(
                    clients,
                    connections,
                    repeat,
                    binaries,
                    raw,
                    duration=args.duration_seconds,
                    warmup=args.warmup_seconds,
                    planned_clients=planned,
                    counter_path=counter_path,
                )
            except Exception as error:
                record = {
                    "schema": "nbsr-b4b-v2-failed-repeat-v1",
                    "clients": clients,
                    "connections_per_client": connections,
                    "repeat": repeat,
                    "failure": f"{type(error).__name__}: {error}",
                    "valid": False,
                }
            write_json(raw / f"clients-{clients}-connections-{connections}-r{repeat}.json", record)
            all_records.append(record)
            cell_records.append(record)
            if not record.get("valid"):
                stop_reason = f"invalid run at {clients} clients"
                break
            if repeat == 3:
                target_repeats = required_repeats(cell_records)
            repeat += 1
        if not all(record.get("valid") for record in cell_records):
            break
        if baseline_record is None:
            baseline_record = {
                "established_goodput_bytes_per_second": statistics.median(
                    float(record["established_goodput_bytes_per_second"])
                    for record in cell_records
                ),
                "established_p99_latency_ns": statistics.median(
                    int(record["established_p99_latency_ns"]) for record in cell_records
                ),
            }
        cell = summarize_cell(cell_records, baseline_record)
        cells.append(cell)
        if clients and cell["status"] == "SATURATED":
            stop_reason = f"requested progression completed after SATURATED cell at {clients} clients"

    observed = [cell["clients"] for cell in cells]
    invalid = [record for record in all_records if not record.get("valid")]
    statuses = [cell["status"] for cell in cells if cell["status"] != "BASELINE"]
    evidence = classify_evidence(cells, invalid)
    analysis = {
        "schema": "nbsr-b4b-v2-analysis-v1",
        "evidence": evidence,
        "system": statuses[-1] if statuses else "UNRESOLVED",
        "cells": cells,
        "first_degraded_clients": next(
            (cell["clients"] for cell in cells if cell["status"] == "DEGRADED"), None
        ),
        "first_saturated_clients": next(
            (cell["clients"] for cell in cells if cell["status"] == "SATURATED"), None
        ),
        "stop_reason": stop_reason,
        "invalid_runs": invalid,
        "thresholds": {
            "stable_minimum_goodput_ratio": 0.90,
            "stable_maximum_p99_ratio": 1.25,
            "stable_minimum_admission_completion": 0.95,
            "saturated_maximum_p99_ratio": 2.0,
            "saturated_minimum_goodput_ratio": 0.75,
            "saturated_minimum_admission_completion": 0.90,
            "repeat_cv": 0.05,
        },
    }
    environment = host_environment()
    environment.update(
        {
            "schema": "nbsr-b4b-v2-environment-v1",
            "base_git_sha": environment.pop("repository_sha"),
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=ROOT, text=True
            ).strip(),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "build": "release",
            "connections_per_client": CONNECTIONS_PER_CLIENT,
            "planned_progression": list(CLIENT_LEVELS),
            "observed_progression": observed,
            "binary_sha256": {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in binaries.items()
            },
        }
    )
    write_json(args.output / "environment.json", environment)
    write_json(args.output / "analysis.json", analysis)
    command = shlex.join(sys.argv)
    (args.output / "summary.md").write_text(
        render_summary(analysis, command), encoding="utf-8", newline="\n"
    )
    (args.output / "commands.txt").write_text(command + "\n", encoding="utf-8")
    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    (args.output / "checksums.sha256").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(args.output).as_posix()}\n"
            for path in files
            if path.name != "checksums.sha256"
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"evidence": evidence, "system": analysis["system"], "records": len(all_records)}))


if __name__ == "__main__":
    main()
