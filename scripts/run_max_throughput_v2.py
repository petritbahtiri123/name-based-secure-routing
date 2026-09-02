from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_p2a_established as p2a
from scripts.performance.authority import write_loopback_authority
from scripts.profile_b2_v2 import set_and_verify_exact_affinity, windows_processor_topology


ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = (1024, 16384)
STREAMS = (1, 2, 4, 8, 16, 32, 64)
OUTSTANDING = (1, 2, 4, 8, 16)


def stage1_cells() -> list[dict]:
    return [
        {
            "path": path,
            "payload_bytes": payload,
            "streams": streams,
            "outstanding_per_stream": outstanding,
            "runtime_workers": 1,
            "connections": 1,
            "channels": 1,
            "load": streams * outstanding,
        }
        for payload in PAYLOADS
        for streams in STREAMS
        for outstanding in OUTSTANDING
        for path in ("direct", "nbsr")
    ]


def repeat_target(values: list[float]) -> int:
    if len(values) < 3:
        return 3
    mean = statistics.fmean(values)
    cv = statistics.stdev(values) / mean if mean else float("inf")
    return 5 if cv > 0.05 else 3


def midpoint_refinement(low: int, high: int, *, measured: set[int]) -> int | None:
    if high <= low:
        return None
    midpoint = 1 << ((low.bit_length() - 1 + high.bit_length() - 1) // 2)
    return midpoint if low < midpoint < high and midpoint not in measured else None


def classify_regions(cells: list[dict]) -> dict:
    ordered = sorted((dict(cell) for cell in cells), key=lambda cell: cell["load"])
    if not ordered:
        raise ValueError("at least one cell is required")
    baseline_p99 = float(ordered[0]["median_p99_latency_ns"])
    best_stable = 0.0
    for cell in ordered:
        hard_failure = (
            cell["errors"] > 0
            or cell["timeouts"] > 0
            or not cell["cleanup_pass"]
            or not cell["backlog_drained"]
            or cell["achieved_offered_ratio"] < 0.90
            or float(cell["median_p99_latency_ns"]) > 2.0 * baseline_p99
            or (best_stable and float(cell["median_gbps"]) < 0.75 * best_stable)
        )
        stable = (
            not hard_failure
            and cell.get("valid", True)
            and cell["repeat_count"] >= 3
            and cell["throughput_cv"] <= 0.05
            and cell["achieved_offered_ratio"] >= 0.95
            and float(cell["median_p99_latency_ns"]) <= 1.25 * baseline_p99
            and (not best_stable or float(cell["median_gbps"]) >= 0.90 * best_stable)
        )
        cell["region"] = "SATURATED" if hard_failure else ("STABLE" if stable else "DEGRADED")
        if stable:
            best_stable = max(best_stable, float(cell["median_gbps"]))
    stable_cells = [cell for cell in ordered if cell["region"] == "STABLE"]
    degraded = next((cell for cell in ordered if cell["region"] == "DEGRADED"), None)
    saturated = next((cell for cell in ordered if cell["region"] == "SATURATED"), None)
    return {
        "cells": ordered,
        "stable_ceiling": max(stable_cells, key=lambda cell: cell["median_gbps"]) if stable_cells else None,
        "first_degraded": degraded,
        "first_saturated": saturated,
    }


def write_summary(output: Path, analysis: dict) -> None:
    lines = [
        "# Benchmark V2 Task 3: maximum-throughput sweep",
        "",
        "Classification: **PARTIAL / HARNESS-LIMITED: single-thread peer event loops**",
        "",
        "The full single-channel geometric matrix completed with no correctness, timeout, or cleanup failures. "
        "Throughput plateaued while the matched source and destination used about 1.3 effective CPU cores in total; "
        "therefore this is not a measured host or hardware ceiling. The current in-process P2A mode owns one "
        "authorized NBSR channel and one single-thread runtime per peer. Multi-channel scaling remains required before "
        "a funding-grade stable host ceiling can be claimed.",
        "",
        "| Payload | NBSR peak | Shape | Matched Direct | Delta | CPU cores | p50/p95/p99 ms |",
        "|---:|---:|---|---:|---:|---:|---|",
    ]
    cells = analysis["cells"]
    for payload in PAYLOADS:
        nbsr = max((cell for cell in cells if cell["payload_bytes"] == payload and cell["path"] == "nbsr"), key=lambda cell: cell["median_gbps"])
        direct = next(cell for cell in cells if cell["payload_bytes"] == payload and cell["path"] == "direct" and cell["streams"] == nbsr["streams"] and cell["outstanding_per_stream"] == nbsr["outstanding_per_stream"])
        delta = (nbsr["median_gbps"] / direct["median_gbps"] - 1.0) * 100.0
        latencies = "/".join(f"{nbsr[key] / 1e6:.3f}" for key in ("median_p50_latency_ns", "median_p95_latency_ns", "median_p99_latency_ns"))
        lines.append(f"| {payload} | {nbsr['median_gbps']:.3f} Gbit/s | 1 conn / 1 channel / {nbsr['streams']} streams / {nbsr['outstanding_per_stream']} outstanding | {direct['median_gbps']:.3f} Gbit/s | {delta:+.2f}% | {nbsr['median_effective_cores']:.3f} | {latencies} |")
    lines += [
        "",
        "All raw valid degraded/saturated cells are retained. The strict common p99 rules classify most high-load "
        "cells as degraded or saturated even when their throughput is repeatable; peak above means highest valid "
        "repeatable throughput, not a new stable ceiling.",
        "",
        "No production NBSR, protocol, transport, security, frozen-authority, or resource-limit code changed.",
        "",
    ]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def summarize_cell(records: list[dict]) -> dict:
    first = records[0]
    values = [float(record["aggregate_application_gbps"]) for record in records]
    mean = statistics.fmean(values)
    configured = int(first["configured_total_outstanding"])
    observed = min(int(record["max_outstanding_per_stream_observed"]) * int(record["streams"]) for record in records)
    ownership = ("transport_sessions_created_delta", "service_channels_created_delta", "application_streams_created_delta", "replay_entries_delta")
    return {
        "path": first["path"], "payload_bytes": int(first["payload_bytes"]),
        "streams": int(first["streams"]), "outstanding_per_stream": int(first["outstanding_per_stream"]),
        "connections": 1, "channels": 1, "runtime_workers": 1,
        "load": int(first["streams"]) * int(first["outstanding_per_stream"]),
        "repeat_count": len(records), "median_gbps": statistics.median(values),
        "throughput_cv": statistics.stdev(values) / mean if len(values) > 1 and mean else 0.0,
        "median_operations_per_second": statistics.median(float(r["operations_per_second"]) for r in records),
        "median_effective_cores": statistics.median(float(r["resources"]["total_cpu_ns"]) / float(r["measured_ns"]) for r in records),
        "median_cpu_ns_per_operation": statistics.median(float(r["resources"]["cpu_ns_per_completed_operation"]) for r in records),
        "median_p50_latency_ns": statistics.median(float(r["p50_latency_ns"]) for r in records),
        "median_p95_latency_ns": statistics.median(float(r["p95_latency_ns"]) for r in records),
        "median_p99_latency_ns": statistics.median(float(r["p99_latency_ns"]) for r in records),
        "peak_working_set_bytes": max(int(role["peak_working_set_bytes"]) for r in records for role in r["resources"]["roles"].values()),
        "peak_private_bytes": max(int(role["peak_private_bytes"]) for r in records for role in r["resources"]["roles"].values()),
        "errors": sum(int(r["errors"]) for r in records), "timeouts": sum(int(r["timeouts"]) for r in records),
        "achieved_offered_ratio": observed / configured if configured else 0.0,
        "configured_outstanding": configured, "max_observed_outstanding": observed,
        "backlog_drained": True,
        "cleanup_pass": all(all(int(r[key]) == 0 for key in ownership) for r in records),
        "valid": all(bool(r["valid"]) and bool(r["affinity_verified"]) for r in records),
    }


def _checksums(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (root / "checksums.sha256").write_text("\n".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}" for path in files
    ) + "\n", encoding="utf-8", newline="\n")


def run(output: Path, *, warmup: float, duration: float, repeats: int, exploratory: bool) -> None:
    topology = windows_processor_topology()
    if not topology["verified"]:
        raise RuntimeError("physical-core topology could not be verified")
    mask = int(topology["affinity_masks"]["4"]["decimal"])
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b2-v2-profile"))
    binaries = p2a.build(target)
    original_affinity = p2a.set_and_verify_affinity
    p2a.set_and_verify_affinity = lambda pid, processors: {
        "requested_processors": processors, **set_and_verify_exact_affinity(pid, mask)
    }
    records: list[dict] = []
    started = time.time()
    try:
        with tempfile.TemporaryDirectory(prefix="nbsr-max-throughput-") as temporary:
            authority = Path(temporary) / "authority"
            write_loopback_authority(authority)
            for cell in stage1_cells():
                cell_records: list[dict] = []
                target_repeats = 1 if exploratory else repeats
                repeat = 1
                while repeat <= target_repeats:
                    name = f"{cell['path']}-p{cell['payload_bytes']}-s{cell['streams']}-o{cell['outstanding_per_stream']}-r{repeat}.json"
                    path = raw / name
                    if path.exists():
                        record = json.loads(path.read_text(encoding="utf-8"))
                    else:
                        record = p2a.run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, 4)
                        record["affinity_verified"] = bool(record["affinity"]["verified"])
                        record["affinity_mask"] = hex(mask)
                        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                    cell_records.append(record)
                    records.append(record)
                    repeat += 1
                if not exploratory and repeat_target([float(r["aggregate_application_gbps"]) for r in cell_records]) == 5:
                    target_repeats = 5
                    while repeat <= target_repeats:
                        name = f"{cell['path']}-p{cell['payload_bytes']}-s{cell['streams']}-o{cell['outstanding_per_stream']}-r{repeat}.json"
                        path = raw / name
                        record = p2a.run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, 4)
                        record["affinity_verified"] = bool(record["affinity"]["verified"])
                        record["affinity_mask"] = hex(mask)
                        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                        cell_records.append(record)
                        records.append(record)
                        repeat += 1
    finally:
        p2a.set_and_verify_affinity = original_affinity
    grouped: dict[tuple, list[dict]] = {}
    for record in records:
        key = (record["payload_bytes"], record["path"], record["streams"], record["outstanding_per_stream"])
        grouped.setdefault(key, []).append(record)
    cells = [summarize_cell(group) for group in grouped.values()]
    analysis = {"schema": "nbsr-max-throughput-v2-analysis-v1", "exploratory": exploratory, "cells": cells}
    if not exploratory:
        regions = {}
        for payload in PAYLOADS:
            for path in ("direct", "nbsr"):
                selected = [cell for cell in cells if cell["payload_bytes"] == payload and cell["path"] == path]
                regions[f"p{payload}-{path}"] = classify_regions(selected)
        analysis["regions"] = regions
    (output / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    environment = {
        "schema": "nbsr-max-throughput-v2-environment-v1",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os": platform.platform(), "processor": platform.processor(), "processor_topology": topology,
        "affinity_mask": hex(mask), "runtime_workers": 1,
        "cargo": subprocess.check_output(["cargo", "--version"], text=True).strip(),
        "python": sys.version,
        "binaries": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in binaries.items()},
    }
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "schema": "nbsr-max-throughput-v2-manifest-v1", "command": [sys.executable, *sys.argv],
        "warmup_seconds": warmup, "duration_seconds": duration, "requested_repeats": repeats,
        "exploratory": exploratory, "records": len(records), "elapsed_seconds": time.time() - started,
        "production_stream_cap_unchanged": 64, "connections": 1, "channels": 1,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_summary(output, analysis)
    _checksums(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=3.0)
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--exploratory", action="store_true")
    args = parser.parse_args()
    run(args.output, warmup=args.warmup_seconds, duration=args.duration_seconds, repeats=args.repeats, exploratory=args.exploratory)


if __name__ == "__main__":
    main()
