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

from scripts.performance.authority import write_loopback_authority
from scripts.performance.p2a_established import build_matrix, coefficient_of_variation, validate_repeat
from scripts.run_performance_validation import measured_client, wait_ready

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "crates" / "nbsr-transport"


def command(argv: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed: {argv!r}\n{result.stdout}\n{result.stderr}")
    return result


def build(target: Path) -> dict[str, Path]:
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    result = subprocess.run(
        ["cargo", "build", "--release", "--manifest-path", str(TRANSPORT / "Cargo.toml"),
         "--features", "benchmark-harness", "--bin", "perf_direct_peer", "--bin", "perf_rust_source",
         "--bin", "wp8_interop_server"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError(result.stderr)
    suffix = ".exe" if os.name == "nt" else ""
    return {name: target / "release" / f"{binary}{suffix}" for name, binary in {
        "direct": "perf_direct_peer", "nbsr": "perf_rust_source", "server": "wp8_interop_server"}.items()}


def summarize_resources(samples: list[dict], completed: int, measured_seconds: float) -> dict:
    cutoff = max(sample["timestamp_ns"] for sample in samples) - int(measured_seconds * 1e9)
    samples = [sample for sample in samples if sample["timestamp_ns"] >= cutoff]
    by_role: dict[str, list[dict]] = {}
    for sample in samples:
        by_role.setdefault(sample["role"], []).append(sample)
    roles = {}
    total_cpu = 0
    for role, values in by_role.items():
        values.sort(key=lambda item: item["timestamp_ns"])
        cpu = ((values[-1]["user_cpu_ns"] + values[-1]["kernel_cpu_ns"])
               - (values[0]["user_cpu_ns"] + values[0]["kernel_cpu_ns"])) if len(values) > 1 else 0
        total_cpu += cpu
        roles[role] = {
            "cpu_ns": cpu,
            "peak_working_set_bytes": max(v["peak_working_set_bytes"] for v in values),
            "peak_private_bytes": max(v["private_bytes"] for v in values),
        }
    return {"roles": roles, "total_cpu_ns": total_cpu,
            "cpu_ns_per_completed_operation": total_cpu / completed if completed else None}


def clear_run_markers(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def clear_cell_artifacts(raw_dir: Path, path: str, streams: int, payload_bytes: int) -> None:
    prefix = f"{path}-s{streams}-p{payload_bytes}-r"
    for artifact in raw_dir.glob(f"{prefix}*"):
        artifact.unlink()


def run_repeat(cell: dict, repeat: int, binaries: dict[str, Path], authority: Path,
               warmup: float, duration: float, raw_dir: Path) -> dict:
    ready = raw_dir / f"{cell['path']}-s{cell['streams']}-p{cell['payload_bytes']}-r{repeat}.ready.json"
    result = ready.with_suffix(".result.json")
    ack = ready.with_suffix(".ack")
    clear_run_markers(ready, result, ack)
    if cell["path"] == "direct":
        server_argv = [str(binaries["direct"]), "--role", "server", "--ready", str(ready),
                       "--authority-dir", str(authority), "--connections", "1", "--requests-per-connection", "1",
                       "--p2a-streams", str(cell["streams"])]
        server_env = os.environ.copy()
    else:
        server_argv = [str(binaries["server"]), "--ready", str(ready), "--result", str(result),
                       "--authority-dir", str(authority), "--completion-ack", str(ack)]
        server_env = {**os.environ, "NBSR_P2A_STREAMS": str(cell["streams"])}
    server = subprocess.Popen(server_argv, cwd=ROOT, env=server_env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        common = ["--authority-dir", str(authority), "--endpoint", endpoint, "--payload-bytes",
                  str(cell["payload_bytes"]), "--p2a-streams", str(cell["streams"]),
                  "--p2a-warmup-seconds", str(warmup), "--p2a-duration-seconds", str(duration)]
        client_argv = ([str(binaries["direct"]), "--role", "client", "--samples", "1", "--lifecycle", "warm", *common]
                       if cell["path"] == "direct" else [str(binaries["nbsr"]), "--samples", "1", *common])
        stdout, resources = measured_client(client_argv, cwd=ROOT, server=server,
                                            timeout=int(warmup + duration + 60))
        record = json.loads(stdout.strip().splitlines()[-1])
        server.wait(timeout=30)
        if server.returncode:
            raise RuntimeError(server.stderr.read())
        completed = int(record["completed_operations"])
        seconds = int(record["measured_ns"]) / 1e9
        payload = int(cell["payload_bytes"])
        record.update({
            "repeat": repeat, "valid": validate_repeat(record), "operations_per_second": completed / seconds,
            "request_messages_per_second": completed / seconds, "response_messages_per_second": completed / seconds,
            "payload_bytes_sent": completed * payload, "payload_bytes_received": completed * payload,
            "client_to_server_goodput_bytes_per_second": completed * payload / seconds,
            "server_to_client_goodput_bytes_per_second": completed * payload / seconds,
            "aggregate_goodput_bytes_per_second": 2 * completed * payload / seconds,
            "aggregate_application_gbps": 16 * completed * payload / seconds / 1e9,
            "timeouts": 0, "resources": summarize_resources(resources, completed, seconds),
            "allocations_per_operation": None, "allocated_bytes_per_operation": None,
        })
        return record
    except Exception as error:
        server_detail = ""
        if server.poll() is not None and server.stderr is not None:
            server_detail = server.stderr.read()
        raise RuntimeError(f"P2A peer failure; server stderr:\n{server_detail}") from error
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)


def write_checksums(root: Path) -> None:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}" for p in files]
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=10.0)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.output / "raw"
    manifests = args.output / "manifests"
    raw.mkdir(exist_ok=True); manifests.mkdir(exist_ok=True)
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\codex-target\nbsr-p2a"))
    binaries = build(target)
    with tempfile.TemporaryDirectory(prefix="nbsr-p2a-") as temp_name:
        authority = Path(temp_name) / "authority"
        write_loopback_authority(authority)
        matrix = build_matrix()
        if args.smoke:
            matrix = [c for c in matrix if c["streams"] == 1 and c["payload_bytes"] == 1]
        all_records = []
        for cell in matrix:
            clear_cell_artifacts(raw, str(cell["path"]), int(cell["streams"]), int(cell["payload_bytes"]))
            records = []
            repeat = 1
            while repeat <= args.repeats:
                record = run_repeat(cell, repeat, binaries, authority, args.warmup_seconds,
                                    args.duration_seconds, raw)
                (raw / f"{cell['path']}-s{cell['streams']}-p{cell['payload_bytes']}-r{repeat}.json").write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                records.append(record); all_records.append(record); repeat += 1
            cv = coefficient_of_variation([r["operations_per_second"] for r in records])
            while not args.smoke and cv > 0.05 and repeat <= 5:
                record = run_repeat(cell, repeat, binaries, authority, args.warmup_seconds,
                                    args.duration_seconds, raw)
                (raw / f"{cell['path']}-s{cell['streams']}-p{cell['payload_bytes']}-r{repeat}.json").write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                records.append(record); all_records.append(record); repeat += 1
                cv = coefficient_of_variation([r["operations_per_second"] for r in records])
            manifest = {**cell, "model": "one-outstanding-per-stream", "warmup_seconds": args.warmup_seconds,
                        "measured_seconds": args.duration_seconds, "repeat_count": len(records), "throughput_cv": cv}
            (manifests / f"{cell['path']}-s{cell['streams']}-p{cell['payload_bytes']}.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        grouped = {}
        for record in all_records:
            key = f"{record['path']}-s{record['streams']}-p{record['payload_bytes']}"
            grouped.setdefault(key, []).append(record)
        cells = []
        for key, records in grouped.items():
            med = lambda field: statistics.median(r[field] for r in records if r["valid"])
            cells.append({"cell": key, "path": records[0]["path"], "streams": records[0]["streams"],
                          "payload_bytes": records[0]["payload_bytes"], "valid_repeats": sum(r["valid"] for r in records),
                          "repeat_count": len(records), "throughput_cv": coefficient_of_variation([r["operations_per_second"] for r in records]),
                          "median_operations_per_second": med("operations_per_second"),
                          "median_aggregate_application_gbps": med("aggregate_application_gbps"),
                          "median_p50_latency_ns": med("p50_latency_ns"), "median_p95_latency_ns": med("p95_latency_ns"),
                          "median_p99_latency_ns": med("p99_latency_ns"), "errors": sum(r["errors"] for r in records)})
        analysis = {"schema": "nbsr-p2a-analysis-v1", "accepted": all(r["valid"] for r in all_records),
                    "allocation_telemetry": "unavailable; no invasive allocator profiler built", "cells": cells}
        (args.output / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
        write_checksums(args.output)
        print(json.dumps({"accepted": analysis["accepted"], "records": len(all_records), "cells": len(cells)}))


if __name__ == "__main__":
    main()
