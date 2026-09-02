from __future__ import annotations

import argparse
import csv
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
import scripts.run_p2a_established as p2a
from scripts.performance.authority import write_loopback_authority
from scripts.profile_b2_v2 import windows_processor_topology


ROOT = Path(__file__).resolve().parents[1]
GROUPS = (2, 4)
MODES = ("physical", "smt")


def stage5_cells() -> list[dict[str, int | str]]:
    return [
        {
            "path": path,
            "payload_bytes": 16384,
            "streams_per_group": 1,
            "outstanding_per_stream": 4,
            "endpoint_groups": groups,
            "runtime_workers": 1,
            "affinity_mode": mode,
        }
        for groups in GROUPS
        for mode in MODES
        for path in ("direct", "nbsr")
    ]


def affinity_plan(topology: dict, groups: int, mode: str) -> dict:
    if not topology.get("verified") or int(topology.get("logical_processors", 0)) != 8:
        raise RuntimeError("verified 4-core/8-LP Windows topology required")
    cores = topology.get("cores", [])
    if groups > len(cores) or mode not in MODES:
        raise ValueError("unsupported Stage 5 affinity plan")
    if mode == "physical":
        return {
            "source_mask": 0x55,
            "endpoint_masks": [int(core["logical_mask"]) & -int(core["logical_mask"])
                               for core in cores[:groups]],
            "logical_processors_available": 4,
        }
    return {
        "source_mask": 0xFF,
        "endpoint_masks": [int(core["logical_mask"]) for core in cores[:groups]],
        "logical_processors_available": 8,
    }


def read_host_counters(path: Path) -> dict:
    if not path.exists():
        return {"status": "UNAVAILABLE", "reason": "typeperf output missing"}
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    values = []
    for row in rows[1:]:
        if len(row) != 4:
            continue
        try:
            values.append(tuple(float(value) for value in row[1:]))
        except ValueError:
            continue
    if len(values) < 2:
        return {"status": "UNAVAILABLE", "reason": "insufficient typeperf samples"}
    return {
        "status": "MEASURED",
        "sample_count": len(values),
        "processor_utility_percent_median": statistics.median(value[0] for value in values),
        "processor_performance_percent_median": statistics.median(value[1] for value in values),
        "processor_frequency_mhz_median": statistics.median(value[2] for value in values),
        "thermal_temperature": "UNAVAILABLE: ACPI thermal zone not exposed on host",
    }


def summarize(records: list[dict]) -> list[dict]:
    cells = []
    for mode in MODES:
        for path in ("direct", "nbsr"):
            for groups in GROUPS:
                values = [record for record in records if record["affinity_mode"] == mode
                          and record["path"] == path and record["endpoint_groups"] == groups]
                throughputs = [float(record["aggregate_application_gbps"]) for record in values]
                cells.append({
                    "affinity_mode": mode, "path": path, "endpoint_groups": groups,
                    "repeat_count": len(values), "median_gbps": statistics.median(throughputs),
                    "max_gbps": max(throughputs),
                    "throughput_cv": statistics.stdev(throughputs) / statistics.mean(throughputs),
                    "median_ops_per_second": statistics.median(float(v["operations_per_second"]) for v in values),
                    "median_effective_cores": statistics.median(float(v["resources"]["total_cpu_ns"]) / int(v["measured_ns"]) for v in values),
                    "median_p50_latency_ns": statistics.median(int(v["p50_latency_ns"]) for v in values),
                    "median_p95_latency_ns": statistics.median(int(v["p95_latency_ns"]) for v in values),
                    "median_p99_latency_ns": statistics.median(int(v["p99_latency_ns"]) for v in values),
                    "peak_working_set_bytes": max(sum(role["peak_working_set_bytes"] for role in v["resources"]["roles"].values()) for v in values),
                    "errors": sum(int(v["errors"]) for v in values),
                    "timeouts": sum(int(v["timeouts"]) for v in values),
                    "valid": all(v["valid"] for v in values),
                    "cleanup_pass": all(v["cleanup_pass"] for v in values),
                    "host_counters": {
                        key: statistics.median(float(v["host_counters"][key]) for v in values)
                        for key in ("processor_utility_percent_median",
                                    "processor_performance_percent_median",
                                    "processor_frequency_mhz_median")
                        if all(v["host_counters"].get("status") == "MEASURED" for v in values)
                    },
                })
    return cells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=2)
    parser.add_argument("--duration-seconds", type=float, default=8)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    if args.repeats < 5:
        raise ValueError("Stage 5 authoritative runs require at least five repeats")
    raw = args.output / "raw"
    raw.mkdir(parents=True)
    topology = windows_processor_topology()
    binaries = p2a.build(Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\max-throughput-v2-stage5")))
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-stage5-") as temporary:
        authority = Path(temporary) / "authority"
        write_loopback_authority(authority)
        for cell in stage5_cells():
            mode_raw = raw / str(cell["affinity_mode"])
            mode_raw.mkdir(exist_ok=True)
            plan = affinity_plan(topology, int(cell["endpoint_groups"]), str(cell["affinity_mode"]))
            for repeat in range(1, args.repeats + 1):
                counter_path = mode_raw / f"{cell['path']}-eg{cell['endpoint_groups']}-r{repeat}-host.csv"
                record = stage4.run_repeat(
                    cell, repeat, binaries, authority, args.warmup_seconds,
                    args.duration_seconds, mode_raw, topology, placement=plan,
                    host_counter_path=counter_path,
                )
                record["schema"] = "nbsr-max-throughput-v2-stage5-repeat-v1"
                record["affinity_mode"] = cell["affinity_mode"]
                record["host_counters"] = read_host_counters(counter_path)
                (mode_raw / f"{cell['path']}-p16384-s1-o4-eg{cell['endpoint_groups']}-r{repeat}.json").write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
                )
                records.append(record)

    manifest = {
        "schema": "nbsr-max-throughput-v2-stage5-v1",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, *sys.argv],
        "warmup_seconds": args.warmup_seconds, "duration_seconds": args.duration_seconds,
        "processor_topology": topology, "cells": summarize(records),
        "all_valid": all(record["valid"] for record in records),
        "all_cleanup_pass": all(record["cleanup_pass"] for record in records),
        "errors": sum(int(record["errors"]) for record in records),
        "timeouts": sum(int(record["timeouts"]) for record in records),
        "binaries": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in binaries.items()},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
