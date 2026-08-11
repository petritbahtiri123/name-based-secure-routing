from __future__ import annotations

import argparse
from dataclasses import asdict
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
from scripts.performance.p2b_profile import LOADS, profile_manifest, shard_plan
from scripts.run_performance_validation import measured_client, wait_ready

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "crates" / "nbsr-transport"


def reset_markers(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def build(target: Path) -> dict[str, Path]:
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    result = subprocess.run([
        "cargo", "build", "--release", "--manifest-path", str(TRANSPORT / "Cargo.toml"),
        "--features", "benchmark-harness", "--bin", "perf_direct_peer", "--bin", "perf_rust_source",
        "--bin", "wp8_interop_server",
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError(result.stderr)
    suffix = ".exe" if os.name == "nt" else ""
    return {name: target / "release" / f"{binary}{suffix}" for name, binary in {
        "direct": "perf_direct_peer", "nbsr": "perf_rust_source", "server": "wp8_interop_server"}.items()}


def parse_output(text: str) -> tuple[list[dict], dict | None]:
    documents = [json.loads(line) for line in text.splitlines() if line.strip()]
    profile = next((document for document in documents if document.get("event") == "p2b_profile"), None)
    return [document for document in documents if "sample_id" in document], profile


def measured_resources(samples: list[dict], duration_ns: int, completed: int) -> dict:
    cutoff = max(sample["timestamp_ns"] for sample in samples) - duration_ns
    measured = [sample for sample in samples if sample["timestamp_ns"] >= cutoff]
    roles = {}
    total_cpu = 0
    for role in sorted({sample["role"] for sample in measured}):
        values = sorted((sample for sample in measured if sample["role"] == role), key=lambda item: item["timestamp_ns"])
        cpu = 0 if len(values) < 2 else (
            values[-1]["user_cpu_ns"] + values[-1]["kernel_cpu_ns"]
            - values[0]["user_cpu_ns"] - values[0]["kernel_cpu_ns"])
        total_cpu += cpu
        roles[role] = {"cpu_ns": cpu, "cpu_percent_assigned_mean": statistics.fmean(v["cpu_percent_assigned"] for v in values),
                       "peak_working_set_bytes": max(v["peak_working_set_bytes"] for v in values),
                       "peak_private_bytes": max(v["private_bytes"] for v in values)}
    return {"roles": roles, "total_cpu_ns": total_cpu,
            "cpu_ns_per_completed_operation": total_cpu / completed if completed else None}


def run_shard(path: str, samples: int, rate: float, instrumentation: bool, binaries: dict[str, Path],
              authority: Path, temporary: Path, ordinal: int) -> dict:
    prefix = f"{path}-{ordinal}"
    ready, result, ack = temporary / f"{prefix}.ready.json", temporary / f"{prefix}.result.json", temporary / f"{prefix}.ack"
    reset_markers(ready, result, ack)
    env = os.environ.copy()
    if instrumentation:
        env["NBSR_P2B_PROFILE"] = "1"
    if path == "direct":
        server_argv = [str(binaries["direct"]), "--role", "server", "--ready", str(ready),
                       "--authority-dir", str(authority), "--connections", "1", "--requests-per-connection", str(samples)]
        client_binary = binaries["direct"]
    else:
        env["NBSR_PERF_STREAM_SAMPLES"] = str(samples)
        server_argv = [str(binaries["server"]), "--ready", str(ready), "--result", str(result),
                       "--authority-dir", str(authority), "--completion-ack", str(ack)]
        client_binary = binaries["nbsr"]
    server = subprocess.Popen(server_argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        if path == "direct":
            client_argv = [str(client_binary), "--role", "client", "--authority-dir", str(authority),
                           "--endpoint", endpoint, "--samples", str(samples), "--payload-bytes", "1024",
                           "--lifecycle", "warm", "--offered-rate", str(rate)]
        else:
            client_argv = [str(client_binary), "--authority-dir", str(authority), "--endpoint", endpoint,
                           "--samples", str(samples), "--payload-bytes", "1024", "--offered-rate", str(rate)]
        client_env = os.environ.copy()
        if instrumentation:
            client_env["NBSR_P2B_PROFILE"] = "1"
        # measured_client inherits os.environ, so scope the feature flag around launch.
        previous = os.environ.get("NBSR_P2B_PROFILE")
        if instrumentation: os.environ["NBSR_P2B_PROFILE"] = "1"
        else: os.environ.pop("NBSR_P2B_PROFILE", None)
        try:
            stdout, resources = measured_client(client_argv, cwd=ROOT, server=server, timeout=600)
        finally:
            if previous is None: os.environ.pop("NBSR_P2B_PROFILE", None)
            else: os.environ["NBSR_P2B_PROFILE"] = previous
        if path == "nbsr": ack.touch()
        server.wait(timeout=30)
        server_stdout = server.stdout.read() if server.stdout else ""
        server_stderr = server.stderr.read() if server.stderr else ""
        if server.returncode:
            raise RuntimeError(server_stderr)
        records, source_profile = parse_output(stdout)
        _, destination_profile = parse_output(server_stdout)
        if len(records) != samples:
            raise RuntimeError(f"sample loss: expected {samples}, observed {len(records)}")
        errors = sum(record.get("success") is not True for record in records)
        latencies = sorted(int(record["request_latency_ns"]) for record in records if record.get("success") is True)
        duration_ns = max(int(record.get("completed_ns", record["request_latency_ns"])) for record in records)
        percentile = lambda p: latencies[max(0, (len(latencies) * p + 99) // 100 - 1)]
        return {"samples": samples, "completed": len(latencies), "errors": errors, "over_capacity": 0,
                "duration_ns": duration_ns, "throughput": len(latencies) / (duration_ns / 1e9),
                "mean_lifecycle_ns": statistics.fmean(latencies),
                "p50_ns": percentile(50), "p95_ns": percentile(95), "p99_ns": percentile(99),
                "source_profile": source_profile, "destination_profile": destination_profile,
                "resources": measured_resources(resources, duration_ns, len(latencies))}
    finally:
        if server.poll() is None:
            server.kill(); server.wait(timeout=5)


def aggregate(path: str, load: int, repeat: int, instrumentation: bool, duration: int,
              binaries: dict[str, Path], authority: Path, temporary: Path) -> dict:
    rate = LOADS[path][load]
    counts = [round(rate * duration)] if path == "direct" else shard_plan(rate, duration)
    shards = [run_shard(path, count, rate, instrumentation, binaries, authority, temporary, ordinal)
              for ordinal, count in enumerate(counts, 1)]
    completed = sum(shard["completed"] for shard in shards)
    elapsed = sum(shard["duration_ns"] for shard in shards)
    all_phase: dict[tuple[str, str], list[dict]] = {}
    for shard in shards:
        for profile in (shard["source_profile"], shard["destination_profile"]):
            if profile:
                for phase in profile["phases"]:
                    all_phase.setdefault((profile["role"], phase["phase"]), []).append(phase)
    phases = []
    for (role, name), values in sorted(all_phase.items()):
        calls = sum(value["calls"] for value in values)
        phases.append({"role": role, "phase": name, "calls": calls,
                       "successes": sum(value["successes"] for value in values),
                       "failures": sum(value["failures"] for value in values),
                       "total_ns": sum(value["total_ns"] for value in values),
                       "mean_ns": sum(value["total_ns"] for value in values) / calls if calls else 0,
                       "p50_ns": statistics.median(value["p50_ns"] for value in values if value["calls"]) if calls else 0,
                       "p95_ns": statistics.median(value["p95_ns"] for value in values if value["calls"]) if calls else 0,
                       "p99_ns": statistics.median(value["p99_ns"] for value in values if value["calls"]) if calls else 0})
    latency_values = {name: [shard[name] for shard in shards] for name in ("p50_ns", "p95_ns", "p99_ns")}
    return {"schema": "nbsr-p2b-logical-profile-v1", "path": path, "load_percent": load,
            "repeat": repeat, "instrumentation_enabled": instrumentation, "offered_rate": rate,
            "duration_seconds_requested": duration, "shard_count": len(shards),
            "max_operations_per_session": max(shard["samples"] for shard in shards),
            "completed_operations": completed, "errors": sum(shard["errors"] for shard in shards),
            "over_capacity": sum(shard["over_capacity"] for shard in shards),
            "throughput": completed / (elapsed / 1e9),
            "mean_lifecycle_ns": sum(shard["mean_lifecycle_ns"] * shard["completed"] for shard in shards) / completed,
            "p50_ns": statistics.median(latency_values["p50_ns"]),
            "p95_ns": statistics.median(latency_values["p95_ns"]),
            "p99_ns": statistics.median(latency_values["p99_ns"]),
            "cpu_ns_per_operation": sum(shard["resources"]["total_cpu_ns"] for shard in shards) / completed,
            "phases": phases, "shards": shards}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["smoke", "observer", "profile"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw, manifests = args.output / "raw", args.output / "manifests"
    raw.mkdir(exist_ok=True); manifests.mkdir(exist_ok=True)
    binaries = build(Path(os.environ.get("CARGO_TARGET_DIR", r"C:\codex-target\nbsr-p2b")))
    with tempfile.TemporaryDirectory(prefix="nbsr-p2b-") as temporary_name:
        temporary = Path(temporary_name); authority = temporary / "authority"; write_loopback_authority(authority)
        if args.suite == "smoke": jobs = [(path, 50, 1, True, 5) for path in ("direct", "nbsr")]
        elif args.suite == "observer": jobs = [(path, 50, repeat, enabled, 30) for path in ("direct", "nbsr") for repeat in range(1, 4) for enabled in (False, True)]
        else: jobs = [(path, load, repeat, True, 180) for path in ("direct", "nbsr") for load in (50, 90) for repeat in range(1, 4)]
        for path, load, repeat, enabled, duration in jobs:
            suffix = "enabled" if enabled else "disabled"
            run = aggregate(path, load, repeat, enabled, duration, binaries, authority, temporary)
            name = f"{args.suite}-{path}-{load}pct-r{repeat}-{suffix}"
            (raw / f"{name}.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")
            manifest = profile_manifest(path, load, repeat, duration, enabled)
            (manifests / f"{name}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps({"run": name, "throughput": run["throughput"], "p99_ns": run["p99_ns"], "errors": run["errors"]}), flush=True)


if __name__ == "__main__": main()
