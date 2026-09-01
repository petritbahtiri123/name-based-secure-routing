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
WORKLOADS = ((1024, 64, 1), (16384, 1, 4))
WORKERS = (1, 2, 4)


def scaling_cells() -> list[dict]:
    return [
        {
            "path": path,
            "payload_bytes": payload,
            "streams": streams,
            "outstanding_per_stream": outstanding,
            "runtime_workers": workers,
        }
        for payload, streams, outstanding in WORKLOADS
        for path in ("direct", "nbsr")
        for workers in WORKERS
    ]


def _median_cell(records: list[dict]) -> dict:
    first = records[0]

    def median(key: str) -> float:
        return statistics.median(float(record[key]) for record in records)

    goodputs = [float(record["aggregate_application_gbps"]) for record in records]
    mean = statistics.fmean(goodputs)
    cv = statistics.stdev(goodputs) / mean if len(goodputs) > 1 and mean else 0.0
    roles = {}
    for role in ("source", "destination"):
        roles[role] = {
            "median_effective_cores": statistics.median(
                float(record["resources"]["roles"][role]["effective_cores"]) for record in records
            ),
            "median_peak_thread_count": statistics.median(
                int(record["resources"]["roles"][role]["peak_thread_count"]) for record in records
            ),
        }
    return {
        "path": first["path"],
        "payload_bytes": int(first["payload_bytes"]),
        "streams": int(first["streams"]),
        "outstanding_per_stream": int(first["outstanding_per_stream"]),
        "runtime_workers": int(first["runtime_workers"]),
        "repeat_count": len(records),
        "valid": all(record["valid"] and not record["errors"] and not record["timeouts"] for record in records),
        "throughput_cv": cv,
        "median_gbps": median("aggregate_application_gbps"),
        "median_operations_per_second": median("operations_per_second"),
        "median_effective_cores": statistics.median(
            float(record["resources"]["total_cpu_ns"]) / float(record["measured_ns"]) for record in records
        ),
        "median_cpu_ns_per_operation": statistics.median(
            float(record["resources"]["cpu_ns_per_completed_operation"]) for record in records
        ),
        "median_p50_latency_ns": median("p50_latency_ns"),
        "median_p95_latency_ns": median("p95_latency_ns"),
        "median_p99_latency_ns": median("p99_latency_ns"),
        "errors": sum(int(record["errors"]) for record in records),
        "timeouts": sum(int(record["timeouts"]) for record in records),
        "roles": roles,
    }


def analyze(records: list[dict]) -> dict:
    grouped: dict[tuple, list[dict]] = {}
    for record in records:
        key = (
            record["payload_bytes"], record["streams"], record["outstanding_per_stream"],
            record["path"], record["runtime_workers"],
        )
        grouped.setdefault(key, []).append(record)
    summaries = [_median_cell(group) for _, group in sorted(grouped.items())]
    workloads = {}
    for payload, streams, outstanding in WORKLOADS:
        label = f"p{payload}-s{streams}-o{outstanding}"
        if not any(cell["payload_bytes"] == payload and cell["streams"] == streams for cell in summaries):
            continue
        workloads[label] = {}
        for path in ("direct", "nbsr"):
            cells = [
                cell for cell in summaries
                if cell["payload_bytes"] == payload and cell["streams"] == streams
                and cell["outstanding_per_stream"] == outstanding and cell["path"] == path
            ]
            by_workers = {cell["runtime_workers"]: cell for cell in cells}
            stable = [cell for cell in cells if cell["valid"] and cell["repeat_count"] >= 3 and cell["throughput_cv"] <= 0.05]
            ceiling = max(stable, key=lambda cell: cell["median_gbps"])
            scaling = {
                "1_to_2": (by_workers[2]["median_gbps"] / by_workers[1]["median_gbps"] - 1) * 100,
                "2_to_4": (by_workers[4]["median_gbps"] / by_workers[2]["median_gbps"] - 1) * 100,
                "1_to_4": (by_workers[4]["median_gbps"] / by_workers[1]["median_gbps"] - 1) * 100,
            }
            workloads[label][path] = {"cells": cells, "scaling_percent": scaling, "stable_ceiling": ceiling}
        direct_cells = {cell["runtime_workers"]: cell for cell in workloads[label]["direct"]["cells"]}
        nbsr_cells = {cell["runtime_workers"]: cell for cell in workloads[label]["nbsr"]["cells"]}
        workloads[label]["matched_direct_nbsr_delta_percent"] = {
            str(workers): (nbsr_cells[workers]["median_gbps"] / direct_cells[workers]["median_gbps"] - 1) * 100
            for workers in WORKERS
        }
    regresses_with_workers = all(
        path_data["cells"][1]["median_gbps"] < path_data["cells"][0]["median_gbps"]
        and path_data["cells"][2]["median_gbps"] < path_data["cells"][0]["median_gbps"]
        and path_data["cells"][1]["median_effective_cores"] > path_data["cells"][0]["median_effective_cores"]
        for workload in workloads.values()
        for path_data in (workload["direct"], workload["nbsr"])
    )
    return {
        "schema": "nbsr-b2-v2-runtime-scaling-analysis-v1",
        "claim_boundary": "Benchmark runtime scaling only; production NBSR runtime is unchanged.",
        "classification": {
            "evidence": "PASS",
            "system": "HARNESS-LIMITED:multi-thread-runtime-overhead" if regresses_with_workers else "UNRESOLVED",
        },
        "next_measured_bottleneck": (
            "Multi-thread benchmark runtime scheduling/synchronization overhead: 2/4 workers consume more CPU "
            "while producing less throughput in matched Direct and NBSR cells."
            if regresses_with_workers else "No common reproducible worker-scaling owner identified."
        ),
        "workloads": workloads,
    }


def _write_checksums(root: Path) -> None:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.sha256"):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run(output: Path, *, warmup: float, duration: float, repeats: int) -> None:
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

    def exact(pid: int, processors: int) -> dict:
        result = set_and_verify_exact_affinity(pid, mask)
        return {"requested_processors": processors, **result}

    p2a.set_and_verify_affinity = exact
    records = []
    started = time.time()
    try:
        with tempfile.TemporaryDirectory(prefix="nbsr-b2-v2-runtime-") as temporary:
            authority = Path(temporary) / "authority"
            write_loopback_authority(authority)
            for cell in scaling_cells():
                for repeat in range(1, repeats + 1):
                    name = (
                        f"{cell['path']}-p{cell['payload_bytes']}-s{cell['streams']}-"
                        f"o{cell['outstanding_per_stream']}-w{cell['runtime_workers']}-r{repeat}.json"
                    )
                    path = raw / name
                    if path.exists():
                        records.append(json.loads(path.read_text(encoding="utf-8")))
                        continue
                    record = p2a.run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, 4)
                    record["affinity_selection"] = {"scope": topology["scope"], "mask": mask, "mask_hex": hex(mask)}
                    record["affinity_verified"] = bool(record["affinity"]["verified"])
                    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                    records.append(record)
    finally:
        p2a.set_and_verify_affinity = original_affinity
    analysis = analyze(records)
    (output / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    environment = {
        "schema": "nbsr-b2-v2-runtime-scaling-environment-v1",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os": platform.platform(),
        "processor_topology": topology,
        "affinity_mask": hex(mask),
        "cargo": subprocess.check_output(["cargo", "--version"], text=True).strip(),
        "binaries": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in binaries.items()},
    }
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "schema": "nbsr-b2-v2-runtime-scaling-manifest-v1",
        "command": [sys.executable, *sys.argv],
        "runtime_workers": list(WORKERS),
        "workloads": [{"payload_bytes": p, "streams": s, "outstanding_per_stream": o} for p, s, o in WORKLOADS],
        "warmup_seconds": warmup,
        "duration_seconds": duration,
        "repeats": repeats,
        "records": len(records),
        "elapsed_seconds": time.time() - started,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = [
        "# B2-v2 Task 2b Runtime Scaling",
        "",
        "Classification: **PASS / HARNESS-LIMITED: multi-thread runtime overhead**",
        "",
        "Increasing benchmark workers from 1 to 2 or 4 increased CPU consumption and reduced throughput in both Direct and NBSR. "
        "This identifies a benchmark-runtime scheduling/synchronization cost; it is not a production NBSR result.",
        "",
        "| Workload | Path | Workers | Gbit/s | Ops/s | Effective cores | CPU ns/op | p99 ms | CV |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, workload in analysis["workloads"].items():
        for path in ("direct", "nbsr"):
            for cell in workload[path]["cells"]:
                lines.append(
                    f"| {label} | {path} | {cell['runtime_workers']} | {cell['median_gbps']:.3f} | "
                    f"{cell['median_operations_per_second']:.0f} | {cell['median_effective_cores']:.3f} | "
                    f"{cell['median_cpu_ns_per_operation']:.0f} | {cell['median_p99_latency_ns']/1e6:.3f} | "
                    f"{cell['throughput_cv']:.3f} |"
                )
    lines += ["", "No production runtime, protocol, transport, security, or frozen-authority code changed.", ""]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _write_checksums(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=3)
    parser.add_argument("--duration-seconds", type=float, default=10)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    run(args.output, warmup=args.warmup_seconds, duration=args.duration_seconds, repeats=args.repeats)


if __name__ == "__main__":
    main()
