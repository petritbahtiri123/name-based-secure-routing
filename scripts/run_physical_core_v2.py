"""Matched Windows forwarding on a shared verified physical-core CPU pool."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_max_throughput_v2_stage4 as stage4
from scripts import run_p2a_established as p2a
from scripts.performance.authority import write_loopback_authority
from scripts.profile_b2_v2 import windows_processor_topology
from scripts.run_b4b_task4k import checksums


def placement(topology, cores, groups):
    masks = stage4.endpoint_masks(topology, cores)
    if not 1 <= groups <= cores:
        raise ValueError("endpoint groups must fit the physical-core pool")
    pool = sum(masks)
    return {"source_mask": pool, "endpoint_masks": [pool] * groups,
            "logical_processors_available": cores}


def repeat_requirement(values):
    if len(values) < 3:
        return 3
    return 5 if statistics.stdev(values) / statistics.mean(values) > 0.05 else 3


def summarize(rows):
    goodput = [r["aggregate_application_gbps"] for r in rows]
    return {"repeats": len(rows), "median_gbps": statistics.median(goodput),
            "cv": statistics.stdev(goodput) / statistics.mean(goodput),
            "median_ops_per_second": statistics.median(r["operations_per_second"] for r in rows),
            "median_cpu_ns_per_op": statistics.median(r["resources"]["cpu_ns_per_completed_operation"] for r in rows),
            "median_effective_cores": statistics.median(r["resources"]["total_cpu_ns"] / r["measured_ns"] for r in rows),
            "median_p50_ns": statistics.median(r["p50_latency_ns"] for r in rows),
            "median_p95_ns": statistics.median(r["p95_latency_ns"] for r in rows),
            "median_p99_ns": statistics.median(r["p99_latency_ns"] for r in rows),
            "valid": all(r["valid"] and r["cleanup_pass"] and r["errors"] == 0 for r in rows)}


def execute(args):
    args.output.mkdir(parents=True, exist_ok=False)
    topology = windows_processor_topology()
    plan = placement(topology, args.cores, args.groups)
    binaries = p2a.build(args.target)
    (args.output / "binaries").mkdir()
    for role, binary in list(binaries.items()):
        retained = args.output / "binaries" / binary.name
        shutil.copy2(binary, retained)
        binaries[role] = retained
    meta = {"schema": "nbsr-physical-core-forwarding-v1", "topology": topology,
            "placement": plan, "physical_cores": args.cores, "smt_siblings_used": False,
            "scope": "Windows loopback; both roles share one total physical-core pool",
            "repository_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "git_status": subprocess.check_output(["git", "status", "--porcelain"], text=True),
            "binary_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in binaries.items()},
            "warmup_seconds": args.warmup, "duration_seconds": args.duration,
            "cpu_accounting": "Process CPU sampled every 0.5s over final measured-duration window; excludes boundary fragments and host interrupt work. CPU ns/op is a sampled estimate.",
            "allocation_accounting": "NOT_MEASURED", "context_switches": "NOT_MEASURED",
            "syscalls": "NOT_MEASURED"}
    (args.output / "environment.json").write_text(json.dumps(meta, indent=2), newline="\n")
    (args.output / "source.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"]))
    for relative in ("scripts/run_physical_core_v2.py", "scripts/run_max_throughput_v2_stage4.py"):
        dest = args.output / "source" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(relative, dest)
    all_rows, summaries = [], []
    try:
        with tempfile.TemporaryDirectory(prefix="nbsr-physical-") as temp:
            authority = Path(temp) / "authority"
            write_loopback_authority(authority)
            for outstanding in args.outstanding:
                modes = {"direct": [], "nbsr": []}
                required = 3
                for repeat in range(1, 6):
                    if repeat > required:
                        break
                    for mode in (("direct", "nbsr") if repeat % 2 else ("nbsr", "direct")):
                        cell = dict(path=mode, payload_bytes=args.payload, streams_per_group=args.streams,
                                    outstanding_per_stream=outstanding, endpoint_groups=args.groups, runtime_workers=1)
                        print(f"cores={args.cores} groups={args.groups} payload={args.payload} streams={args.streams} outstanding={outstanding} path={mode} repeat={repeat}", flush=True)
                        row = stage4.run_repeat(cell, repeat, binaries, authority, args.warmup,
                                                args.duration, args.output, topology, placement=plan)
                        all_rows.append(row)
                        modes[mode].append(row)
                        (args.output / "records.json").write_text(json.dumps(all_rows, indent=2), newline="\n")
                        if not row["valid"] or not row["cleanup_pass"]:
                            raise RuntimeError("invalid run retained; investigate before continuing")
                    if repeat == 3:
                        required = max(repeat_requirement([r["aggregate_application_gbps"] for r in rows]) for rows in modes.values())
                for mode, rows in modes.items():
                    summaries.append({"path": mode, "outstanding": outstanding, **summarize(rows)})
                (args.output / "summary.json").write_text(json.dumps(summaries, indent=2), newline="\n")
    finally:
        checksums(args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path(r"C:\NBSR-build\b4b-task4k"))
    parser.add_argument("--cores", type=int, required=True)
    parser.add_argument("--groups", type=int, default=1)
    parser.add_argument("--payload", type=int, default=16384)
    parser.add_argument("--streams", type=int, default=1)
    parser.add_argument("--outstanding", type=int, nargs="+", default=[1, 4, 8, 16])
    parser.add_argument("--warmup", type=float, default=3)
    parser.add_argument("--duration", type=float, default=20)
    execute(parser.parse_args())
