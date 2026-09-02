from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_max_throughput_v2_stage4 as stage4
import scripts.run_max_throughput_v2_stage5 as stage5
import scripts.run_p2a_established as p2a
from scripts.performance.authority import write_loopback_authority
from scripts.profile_b2_v2 import windows_processor_topology


ROOT = Path(__file__).resolve().parents[1]
GROUPS = (1, 2)
MODES = ("physical", "smt")


def stage6_cells() -> list[dict[str, int | str]]:
    return [
        {
            "path": "nbsr",
            "payload_bytes": 16384,
            "streams_per_group": 1,
            "outstanding_per_stream": 4,
            "endpoint_groups": groups,
            "runtime_workers": 1,
            "affinity_mode": mode,
        }
        for mode in MODES
        for groups in GROUPS
    ]


def required_repeats(throughputs: list[float]) -> int:
    if len(throughputs) >= 10:
        return 10
    if len(throughputs) < 5:
        return 5
    cv = statistics.stdev(throughputs) / statistics.mean(throughputs)
    return 5 if cv <= 0.05 else 10


def is_strict_stable(candidate: dict, baseline: dict) -> bool:
    return (
        candidate["valid"]
        and candidate["cleanup_pass"]
        and candidate["errors"] == 0
        and candidate["timeouts"] == 0
        and candidate["throughput_cv"] <= 0.05
        and candidate["median_p99_latency_ns"]
        <= 1.25 * baseline["median_p99_latency_ns"]
        and candidate["achieved_offered_ratio"] >= 0.95
        and candidate["backlog_drained"]
    )


def summarize(records: list[dict]) -> list[dict]:
    cells = []
    for mode in MODES:
        for groups in GROUPS:
            values = [
                record
                for record in records
                if record["affinity_mode"] == mode
                and record["endpoint_groups"] == groups
            ]
            throughputs = [float(value["aggregate_application_gbps"]) for value in values]
            achieved = [
                min(
                    1.0,
                    float(value["max_observed_total_outstanding"])
                    / float(value["configured_total_outstanding"]),
                )
                for value in values
            ]
            cells.append(
                {
                    "affinity_mode": mode,
                    "path": "nbsr",
                    "endpoint_groups": groups,
                    "repeat_count": len(values),
                    "median_gbps": statistics.median(throughputs),
                    "max_gbps": max(throughputs),
                    "throughput_cv": statistics.stdev(throughputs)
                    / statistics.mean(throughputs),
                    "median_ops_per_second": statistics.median(
                        float(value["operations_per_second"]) for value in values
                    ),
                    "median_effective_cores": statistics.median(
                        float(value["resources"]["total_cpu_ns"])
                        / int(value["measured_ns"])
                        for value in values
                    ),
                    "median_p50_latency_ns": statistics.median(
                        int(value["p50_latency_ns"]) for value in values
                    ),
                    "median_p95_latency_ns": statistics.median(
                        int(value["p95_latency_ns"]) for value in values
                    ),
                    "median_p99_latency_ns": statistics.median(
                        int(value["p99_latency_ns"]) for value in values
                    ),
                    "peak_working_set_bytes": max(
                        sum(
                            role["peak_working_set_bytes"]
                            for role in value["resources"]["roles"].values()
                        )
                        for value in values
                    ),
                    "achieved_offered_ratio": min(achieved),
                    "backlog_drained": all(value["cleanup_pass"] for value in values),
                    "errors": sum(int(value["errors"]) for value in values),
                    "timeouts": sum(int(value["timeouts"]) for value in values),
                    "valid": all(value["valid"] for value in values),
                    "cleanup_pass": all(value["cleanup_pass"] for value in values),
                    "host_counters": {
                        key: statistics.median(
                            float(value["host_counters"][key]) for value in values
                        )
                        for key in (
                            "processor_utility_percent_median",
                            "processor_performance_percent_median",
                            "processor_frequency_mhz_median",
                        )
                        if all(
                            value["host_counters"].get("status") == "MEASURED"
                            for value in values
                        )
                    },
                }
            )
    by_key = {(cell["affinity_mode"], cell["endpoint_groups"]): cell for cell in cells}
    for mode in MODES:
        baseline = by_key[(mode, 1)]
        for groups in GROUPS:
            cell = by_key[(mode, groups)]
            cell["strict_stable"] = is_strict_stable(cell, baseline)
            cell["p99_ratio_to_lowest_load"] = (
                cell["median_p99_latency_ns"] / baseline["median_p99_latency_ns"]
            )
    return cells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=3)
    parser.add_argument("--duration-seconds", type=float, default=20)
    parser.add_argument("--initial-repeats", type=int, default=5)
    parser.add_argument("--maximum-repeats", type=int, default=10)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    if args.initial_repeats != 5 or args.maximum_repeats != 10:
        raise ValueError("Stage 6 requires exactly five initial and at most ten repeats")

    raw = args.output / "raw"
    raw.mkdir(parents=True)
    topology = windows_processor_topology()
    binaries = p2a.build(
        Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\max-throughput-v2-stage6"))
    )
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-stage6-") as temporary:
        authority = Path(temporary) / "authority"
        write_loopback_authority(authority)
        for cell in stage6_cells():
            mode_raw = raw / str(cell["affinity_mode"])
            mode_raw.mkdir(exist_ok=True)
            plan = stage5.affinity_plan(
                topology, int(cell["endpoint_groups"]), str(cell["affinity_mode"])
            )
            cell_records = []
            for repeat in range(1, args.initial_repeats + 1):
                counter_path = mode_raw / (
                    f"nbsr-eg{cell['endpoint_groups']}-r{repeat}-host.csv"
                )
                record = stage4.run_repeat(
                    cell,
                    repeat,
                    binaries,
                    authority,
                    args.warmup_seconds,
                    args.duration_seconds,
                    mode_raw,
                    topology,
                    placement=plan,
                    host_counter_path=counter_path,
                )
                record["schema"] = "nbsr-max-throughput-v2-stage6-repeat-v1"
                record["affinity_mode"] = cell["affinity_mode"]
                record["host_counters"] = stage5.read_host_counters(counter_path)
                output = mode_raw / (
                    f"nbsr-p16384-s1-o4-eg{cell['endpoint_groups']}-r{repeat}.json"
                )
                output.write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
                )
                records.append(record)
                cell_records.append(record)
            target_repeats = required_repeats(
                [float(value["aggregate_application_gbps"]) for value in cell_records]
            )
            for repeat in range(args.initial_repeats + 1, target_repeats + 1):
                counter_path = mode_raw / (
                    f"nbsr-eg{cell['endpoint_groups']}-r{repeat}-host.csv"
                )
                record = stage4.run_repeat(
                    cell,
                    repeat,
                    binaries,
                    authority,
                    args.warmup_seconds,
                    args.duration_seconds,
                    mode_raw,
                    topology,
                    placement=plan,
                    host_counter_path=counter_path,
                )
                record["schema"] = "nbsr-max-throughput-v2-stage6-repeat-v1"
                record["affinity_mode"] = cell["affinity_mode"]
                record["host_counters"] = stage5.read_host_counters(counter_path)
                output = mode_raw / (
                    f"nbsr-p16384-s1-o4-eg{cell['endpoint_groups']}-r{repeat}.json"
                )
                output.write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
                )
                records.append(record)
                cell_records.append(record)

    cells = summarize(records)
    strict = [cell for cell in cells if cell["strict_stable"]]
    repeatable = [cell for cell in cells if cell["throughput_cv"] <= 0.05]
    manifest = {
        "schema": "nbsr-max-throughput-v2-stage6-v1",
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, *sys.argv],
        "warmup_seconds": args.warmup_seconds,
        "duration_seconds": args.duration_seconds,
        "processor_topology": topology,
        "cells": cells,
        "highest_single_nbsr_gbps": max(
            float(record["aggregate_application_gbps"]) for record in records
        ),
        "highest_repeatable_nbsr_gbps": (
            max(cell["median_gbps"] for cell in repeatable) if repeatable else None
        ),
        "highest_strict_stable_nbsr_gbps": (
            max(cell["median_gbps"] for cell in strict) if strict else None
        ),
        "all_valid": all(record["valid"] for record in records),
        "all_cleanup_pass": all(record["cleanup_pass"] for record in records),
        "errors": sum(int(record["errors"]) for record in records),
        "timeouts": sum(int(record["timeouts"]) for record in records),
        "binaries": {
            name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in binaries.items()
        },
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
