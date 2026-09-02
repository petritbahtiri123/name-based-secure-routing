from __future__ import annotations

import argparse
from dataclasses import asdict
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

import scripts.run_max_throughput_v2_stage2 as stage2
import scripts.run_p2a_established as p2a
from scripts.performance.authority import write_loopback_authority
from scripts.performance.resources import ProcessResourceSampler
from scripts.profile_b2_v2 import set_and_verify_exact_affinity, windows_processor_topology
from scripts.run_performance_validation import wait_ready


ROOT = Path(__file__).resolve().parents[1]
GROUPS = (1, 2, 4)


def stage4_cells() -> list[dict[str, int | str]]:
    return [
        {
            "path": path,
            "payload_bytes": 16384,
            "streams_per_group": 1,
            "outstanding_per_stream": 4,
            "endpoint_groups": groups,
            "runtime_workers": 1,
        }
        for groups in GROUPS
        for path in ("direct", "nbsr")
    ]


def endpoint_masks(topology: dict, groups: int) -> list[int]:
    if not topology.get("verified"):
        raise RuntimeError("verified Windows physical-core topology required")
    cores = topology.get("cores", [])
    if groups > len(cores):
        raise RuntimeError("not enough verified physical cores for endpoint groups")
    masks = []
    for core in cores[:groups]:
        logical_mask = int(core["logical_mask"])
        masks.append(logical_mask & -logical_mask)
    if len(set(masks)) != groups or any(mask == 0 for mask in masks):
        raise RuntimeError("endpoint masks are not distinct physical-core representatives")
    return masks


def _server_command(cell: dict, binaries: dict[str, Path], authority: Path, ready: Path,
                    result: Path, ack: Path) -> tuple[list[str], dict[str, str]]:
    streams = str(cell["streams_per_group"])
    if cell["path"] == "direct":
        return ([str(binaries["direct"]), "--role", "server", "--ready", str(ready),
                 "--authority-dir", str(authority), "--connections", "1",
                 "--requests-per-connection", "1", "--p2a-streams", streams,
                 "--p2a-groups", "1", "--completion-ack", str(ack),
                 "--p2a-runtime-workers", "1"], os.environ.copy())
    return ([str(binaries["server"]), "--ready", str(ready), "--result", str(result),
             "--authority-dir", str(authority), "--completion-ack", str(ack),
             "--p2a-runtime-workers", "1"], {**os.environ, "NBSR_P2A_STREAMS": streams})


def run_repeat(cell: dict, repeat: int, binaries: dict[str, Path], authority: Path,
               warmup: float, duration: float, raw: Path, topology: dict) -> dict:
    groups = int(cell["endpoint_groups"])
    masks = endpoint_masks(topology, groups)
    prefix = f"{cell['path']}-p16384-s1-o4-eg{groups}-r{repeat}"
    ack = raw / f"{prefix}.ack"
    ack.unlink(missing_ok=True)
    servers: list[subprocess.Popen[str]] = []
    server_affinity = []
    endpoints = []
    try:
        for ordinal, mask in enumerate(masks):
            ready = raw / f"{prefix}-d{ordinal}.ready.json"
            result = raw / f"{prefix}-d{ordinal}.result.json"
            p2a.clear_run_markers(ready, result)
            argv, env = _server_command(cell, binaries, authority, ready, result, ack)
            server = subprocess.Popen(
                argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            servers.append(server)
            server_affinity.append(set_and_verify_exact_affinity(server.pid, mask))
            endpoints.append(wait_ready(ready, server)["endpoint"])

        common = ["--authority-dir", str(authority), "--endpoint", endpoints[0],
                  "--p2a-endpoints", ",".join(endpoints), "--payload-bytes", "16384",
                  "--p2a-streams", "1", "--p2a-groups", str(groups),
                  "--p2a-runtime-workers", "1", "--p2a-outstanding-per-stream", "4",
                  "--p2a-warmup-seconds", str(warmup), "--p2a-duration-seconds", str(duration)]
        argv = ([str(binaries["direct"]), "--role", "client", "--samples", "1",
                 "--lifecycle", "warm", *common]
                if cell["path"] == "direct"
                else [str(binaries["nbsr"]), "--samples", "1", *common])
        client = subprocess.Popen(
            argv, cwd=ROOT, env=os.environ.copy(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True
        )
        client_affinity = set_and_verify_exact_affinity(client.pid, 0x55)
        processes = {"source": client.pid}
        processes.update({f"destination_{ordinal}": server.pid for ordinal, server in enumerate(servers)})
        sampler = ProcessResourceSampler(
            processes, interval_seconds=0.5, assigned_logical_processors=4
        )
        sampler.start()
        stdout, stderr = client.communicate(timeout=int(warmup + duration + 90))
        samples = [asdict(sample) for sample in sampler.stop()]
        if client.returncode:
            raise RuntimeError(stderr)
        records = [json.loads(line) for line in stdout.splitlines()
                   if line.startswith("{") and '"schema":"nbsr-p2a-repeat-v2"' in line]
        diagnostics = [json.loads(line) for line in stdout.splitlines()
                       if line.startswith("{") and '"phase":"group_cleanup"' in line]
        if len(records) != groups:
            raise RuntimeError(f"expected {groups} group records, got {len(records)}")
        ack.write_text("client resource sampling complete\n", encoding="ascii")
        for server in servers:
            server.wait(timeout=30)
            if server.returncode:
                raise RuntimeError(server.stderr.read())

        aggregate = stage2.aggregate_group_records(
            records, payload_bytes=16384, streams_per_group=1, outstanding_per_stream=4
        )
        seconds = aggregate["measured_ns"] / 1e9
        cleanup_pass = (
            stage2.cleanup_from_diagnostic(diagnostics[-1])
            if cell["path"] == "nbsr" and groups > 1
            else all(all(int(record[key]) == 0 for key in (
                "transport_sessions_created_delta", "service_channels_created_delta",
                "application_streams_created_delta", "replay_entries_delta"
            )) for record in records)
        )
        resources = p2a.summarize_resources(samples, aggregate["completed_operations"], seconds, 1)
        aggregate.update({
            "schema": "nbsr-max-throughput-v2-stage4-repeat-v1",
            "path": cell["path"], "repeat": repeat, "endpoint_groups": groups,
            "runtime_workers": 1, "errors": sum(int(record["errors"]) for record in records),
            "timeouts": 0,
            "valid": stage2.validate_group_records(records, process_cleanup_pass=cleanup_pass),
            "cleanup_pass": cleanup_pass,
            "cleanup_diagnostic": diagnostics[-1] if diagnostics else None,
            "resources": resources,
            "affinity": {
                "endpoint_masks": [hex(mask) for mask in masks],
                "server": server_affinity,
                "source_process_mask": "0x55", "source": client_affinity,
                "source_group_thread_masks_enforced": False,
                "placement": "each destination endpoint process pinned to a distinct verified physical-core representative; source process constrained to 0x55",
            },
        })
        return aggregate
    finally:
        for server in servers:
            if server.poll() is None:
                server.kill()
                server.wait(timeout=5)


def summarize(records: list[dict]) -> list[dict]:
    cells = []
    for path in ("direct", "nbsr"):
        for groups in GROUPS:
            values = [record for record in records
                      if record["path"] == path and record["endpoint_groups"] == groups]
            throughputs = [float(record["aggregate_application_gbps"]) for record in values]
            median = statistics.median(throughputs)
            cells.append({
                "path": path, "endpoint_groups": groups, "repeat_count": len(values),
                "median_gbps": median,
                "throughput_cv": statistics.stdev(throughputs) / statistics.mean(throughputs)
                if len(throughputs) > 1 else 0.0,
                "median_ops_per_second": statistics.median(float(v["operations_per_second"]) for v in values),
                "median_p50_latency_ns": statistics.median(int(v["p50_latency_ns"]) for v in values),
                "median_p95_latency_ns": statistics.median(int(v["p95_latency_ns"]) for v in values),
                "median_p99_latency_ns": statistics.median(int(v["p99_latency_ns"]) for v in values),
                "median_effective_cores": statistics.median(float(v["resources"]["total_cpu_ns"]) / int(v["measured_ns"]) for v in values),
                "errors": sum(int(v["errors"]) for v in values),
                "timeouts": sum(int(v["timeouts"]) for v in values),
                "cleanup_pass": all(v["cleanup_pass"] for v in values),
                "valid": all(v["valid"] for v in values),
                "peak_working_set_bytes": max(sum(role["peak_working_set_bytes"] for role in v["resources"]["roles"].values()) for v in values),
                "per_group_median_gbps": [statistics.median(float(v["per_group"][i]["gbps"]) for v in values) for i in range(groups)],
            })
    return cells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=2)
    parser.add_argument("--duration-seconds", type=float, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    raw = args.output / "raw"
    raw.mkdir(parents=True)
    topology = windows_processor_topology()
    binaries = p2a.build(Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\max-throughput-v2-stage4")))
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-stage4-") as temporary:
        authority = Path(temporary) / "authority"
        write_loopback_authority(authority)
        for cell in stage4_cells():
            cell_records = []
            for repeat in range(1, args.repeats + 1):
                record = run_repeat(cell, repeat, binaries, authority, args.warmup_seconds,
                                    args.duration_seconds, raw, topology)
                (raw / f"{cell['path']}-p16384-s1-o4-eg{cell['endpoint_groups']}-r{repeat}.json").write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
                )
                records.append(record)
                cell_records.append(record)
            throughputs = [float(record["aggregate_application_gbps"]) for record in cell_records]
            if len(throughputs) >= 3 and statistics.stdev(throughputs) / statistics.mean(throughputs) > 0.05:
                for repeat in range(args.repeats + 1, 6):
                    record = run_repeat(cell, repeat, binaries, authority, args.warmup_seconds,
                                        args.duration_seconds, raw, topology)
                    (raw / f"{cell['path']}-p16384-s1-o4-eg{cell['endpoint_groups']}-r{repeat}.json").write_text(
                        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
                    )
                    records.append(record)

    cells = summarize(records)
    manifest = {
        "schema": "nbsr-max-throughput-v2-stage4-v1",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, *sys.argv],
        "warmup_seconds": args.warmup_seconds, "duration_seconds": args.duration_seconds,
        "processor_topology": topology, "cells": cells,
        "all_valid": all(record["valid"] for record in records),
        "all_cleanup_pass": all(record["cleanup_pass"] for record in records),
        "errors": sum(int(record["errors"]) for record in records),
        "timeouts": sum(int(record["timeouts"]) for record in records),
        "binaries": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in binaries.items()},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
