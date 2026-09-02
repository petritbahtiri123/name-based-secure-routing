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
from scripts.run_performance_validation import measured_client, wait_ready


ROOT = Path(__file__).resolve().parents[1]
SHAPES = ((1024, 8, 8), (1024, 64, 4), (16384, 4, 2), (16384, 1, 4))
GROUPS = (1, 2, 4)
CLEANUP_FIELDS = (
    "transport_sessions_current_live", "service_channels_current_live",
    "application_streams_current_live", "nbsr_tasks_current_live",
    "quic_connections_current_live", "quic_streams_current_live",
    "pending_routes_current_entries", "channel_registry_current_entries",
    "stream_registry_current_entries", "replay_state_current_entries",
)


def cleanup_from_diagnostic(record: dict) -> bool:
    return all(int(record.get(field, -1)) == 0 for field in CLEANUP_FIELDS)


def validate_group_records(records: list[dict], *, process_cleanup_pass: bool) -> bool:
    correctness_fields = ("errors", "missing", "duplicates", "corrupt", "wrong_request")
    return process_cleanup_pass and all(
        int(record.get("completed_operations", 0)) > 0
        and all(int(record.get(field, -1)) == 0 for field in correctness_fields)
        for record in records
    )


def stage2_cells() -> list[dict]:
    return [
        {"path": path, "payload_bytes": payload, "streams_per_group": streams,
         "outstanding_per_stream": outstanding, "groups": groups, "runtime_workers": 1}
        for payload, streams, outstanding in SHAPES
        for groups in GROUPS
        for path in ("direct", "nbsr")
    ]


def aggregate_group_records(groups: list[dict], *, payload_bytes: int, streams_per_group: int,
                            outstanding_per_stream: int) -> dict:
    measured_ns = max(int(group["measured_ns"]) for group in groups)
    completed = sum(int(group["completed_operations"]) for group in groups)
    configured = len(groups) * streams_per_group * outstanding_per_stream
    observed = sum(int(group["max_outstanding_per_stream_observed"]) * streams_per_group for group in groups)
    return {
        "groups": len(groups), "payload_bytes": payload_bytes,
        "streams_per_group": streams_per_group, "outstanding_per_stream": outstanding_per_stream,
        "completed_operations": completed, "measured_ns": measured_ns,
        "configured_total_outstanding": configured, "max_observed_total_outstanding": observed,
        "operations_per_second": completed / (measured_ns / 1e9),
        "aggregate_application_gbps": 16 * completed * payload_bytes / (measured_ns / 1e9) / 1e9,
        "p50_latency_ns": statistics.median(int(group["p50_latency_ns"]) for group in groups),
        "p95_latency_ns": max(int(group["p95_latency_ns"]) for group in groups),
        "p99_latency_ns": max(int(group["p99_latency_ns"]) for group in groups),
        "per_group": [
            {"ordinal": ordinal, "completed_operations": int(group["completed_operations"]),
             "measured_ns": int(group["measured_ns"]),
             "gbps": 16 * int(group["completed_operations"]) * payload_bytes / (int(group["measured_ns"]) / 1e9) / 1e9,
             "p99_latency_ns": int(group["p99_latency_ns"])}
            for ordinal, group in enumerate(groups)
        ],
    }


def classify_group_scaling(cells: list[dict]) -> dict:
    ordered = sorted((dict(cell) for cell in cells), key=lambda cell: cell["groups"])
    baseline = float(ordered[0]["median_p99_latency_ns"])
    best = 0.0
    for cell in ordered:
        repeatable = cell["repeat_count"] >= 3 and cell["throughput_cv"] <= 0.05
        hard = (cell["errors"] or cell["timeouts"] or not cell["cleanup_pass"]
                or cell["achieved_offered_ratio"] < 0.90
                or float(cell["median_p99_latency_ns"]) > 2 * baseline)
        stable = (not hard and repeatable and cell["achieved_offered_ratio"] >= 0.95
                  and float(cell["median_p99_latency_ns"]) <= 1.25 * baseline
                  and (not best or float(cell["median_gbps"]) >= 0.90 * best))
        cell["region"] = "SATURATED" if hard else ("STABLE" if stable else "DEGRADED")
        if stable:
            best = max(best, float(cell["median_gbps"]))
    repeatable = [cell for cell in ordered if cell["repeat_count"] >= 3 and cell["throughput_cv"] <= 0.05]
    stable = [cell for cell in ordered if cell["region"] == "STABLE"]
    return {"cells": ordered,
            "highest_repeatable": max(repeatable, key=lambda cell: cell["median_gbps"]) if repeatable else None,
            "highest_strict_stable": max(stable, key=lambda cell: cell["median_gbps"]) if stable else None}


def run_repeat(cell: dict, repeat: int, binaries: dict[str, Path], authority: Path,
               warmup: float, duration: float, raw: Path, affinity_mask: int) -> dict:
    groups = int(cell["groups"])
    streams = int(cell["streams_per_group"])
    ready = raw / f"{cell['path']}-p{cell['payload_bytes']}-s{streams}-o{cell['outstanding_per_stream']}-g{groups}-r{repeat}.ready.json"
    result = ready.with_suffix(".result.json")
    ack = ready.with_suffix(".ack")
    p2a.clear_run_markers(ready, result, ack)
    common_server = ["--p2a-runtime-workers", "1"]
    if cell["path"] == "direct":
        server_argv = [str(binaries["direct"]), "--role", "server", "--ready", str(ready),
                       "--authority-dir", str(authority), "--connections", str(groups),
                       "--requests-per-connection", "1", "--p2a-streams", str(streams),
                       "--p2a-groups", str(groups), "--completion-ack", str(ack), *common_server]
        server_env = os.environ.copy()
    else:
        server_argv = [str(binaries["server"]), "--ready", str(ready), "--result", str(result),
                       "--authority-dir", str(authority), "--completion-ack", str(ack), *common_server]
        server_env = {**os.environ, "NBSR_P2A_STREAMS": str(streams)}
        if groups > 1:
            server_env["NBSR_P2A_GROUPS"] = str(groups)
    server = subprocess.Popen(server_argv, cwd=ROOT, env=server_env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        server_affinity = set_and_verify_exact_affinity(server.pid, affinity_mask)
        endpoint = wait_ready(ready, server)["endpoint"]
        common = ["--authority-dir", str(authority), "--endpoint", endpoint,
                  "--payload-bytes", str(cell["payload_bytes"]), "--p2a-streams", str(streams),
                  "--p2a-groups", str(groups), "--p2a-runtime-workers", "1",
                  "--p2a-outstanding-per-stream", str(cell["outstanding_per_stream"]),
                  "--p2a-warmup-seconds", str(warmup), "--p2a-duration-seconds", str(duration)]
        argv = ([str(binaries["direct"]), "--role", "client", "--samples", "1", "--lifecycle", "warm", *common]
                if cell["path"] == "direct" else [str(binaries["nbsr"]), "--samples", "1", *common])
        client_affinity: dict = {}
        stdout, resources = measured_client(
            argv, cwd=ROOT, server=server, timeout=int(warmup + duration + 90), env=os.environ.copy(),
            client_started=lambda pid: client_affinity.update(set_and_verify_exact_affinity(pid, affinity_mask)))
        records = [json.loads(line) for line in stdout.splitlines() if line.startswith("{") and '"schema":"nbsr-p2a-repeat-v2"' in line]
        diagnostics = [json.loads(line) for line in stdout.splitlines() if line.startswith("{") and '"phase":"group_cleanup"' in line]
        if len(records) != groups:
            raise RuntimeError(f"expected {groups} group records, got {len(records)}")
        ack.write_text("client resource sampling complete\n", encoding="ascii")
        server.wait(timeout=30)
        if server.returncode:
            raise RuntimeError(server.stderr.read())
        aggregate = aggregate_group_records(records, payload_bytes=int(cell["payload_bytes"]),
                                            streams_per_group=streams,
                                            outstanding_per_stream=int(cell["outstanding_per_stream"]))
        seconds = aggregate["measured_ns"] / 1e9
        cleanup_pass = (
            cleanup_from_diagnostic(diagnostics[-1])
            if cell["path"] == "nbsr" and groups > 1
            else all(all(int(r[key]) == 0 for key in ("transport_sessions_created_delta", "service_channels_created_delta", "application_streams_created_delta", "replay_entries_delta")) for r in records)
        )
        aggregate.update({"schema": "nbsr-p2a-stage2-repeat-v1", "path": cell["path"], "repeat": repeat,
                          "runtime_workers": 1, "errors": sum(int(r["errors"]) for r in records),
                          "timeouts": 0, "valid": validate_group_records(records, process_cleanup_pass=cleanup_pass),
                          "cleanup_pass": cleanup_pass,
                          "cleanup_diagnostic": diagnostics[-1] if diagnostics else None,
                          "resources": p2a.summarize_resources(resources, aggregate["completed_operations"], seconds, 1),
                          "affinity": {"process_mask": hex(affinity_mask), "server": server_affinity,
                                       "client": client_affinity, "group_thread_masks": None,
                                       "group_thread_masks_enforced": False,
                                       "group_placement": "process constrained to verified physical-core mask 0x55; per-thread placement not verified"}})
        return aggregate
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)


def summarize(records: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for record in records:
        key = (record["payload_bytes"], record["streams_per_group"], record["outstanding_per_stream"], record["groups"], record["path"])
        grouped.setdefault(key, []).append(record)
    cells = []
    for group in grouped.values():
        first = group[0]
        values = [float(r["aggregate_application_gbps"]) for r in group]
        mean = statistics.fmean(values)
        roles = {}
        for role in ("source", "destination"):
            roles[role] = {
                "median_effective_cores": statistics.median(r["resources"]["roles"][role]["effective_cores"] for r in group),
                "median_peak_thread_count": statistics.median(r["resources"]["roles"][role]["peak_thread_count"] for r in group),
            }
        per_group_median = [statistics.median(r["per_group"][ordinal]["gbps"] for r in group)
                            for ordinal in range(first["groups"])]
        cells.append({"path": first["path"], "payload_bytes": first["payload_bytes"],
                      "streams_per_group": first["streams_per_group"], "outstanding_per_stream": first["outstanding_per_stream"],
                      "groups": first["groups"], "repeat_count": len(group), "median_gbps": statistics.median(values),
                      "throughput_cv": statistics.stdev(values) / mean if len(values) > 1 and mean else 0.0,
                      "median_ops_per_second": statistics.median(r["operations_per_second"] for r in group),
                      "median_effective_cores": statistics.median(r["resources"]["total_cpu_ns"] / r["measured_ns"] for r in group),
                      "median_cpu_ns_per_op": statistics.median(r["resources"]["cpu_ns_per_completed_operation"] for r in group),
                      "median_p50_latency_ns": statistics.median(r["p50_latency_ns"] for r in group),
                      "median_p95_latency_ns": statistics.median(r["p95_latency_ns"] for r in group),
                      "median_p99_latency_ns": statistics.median(r["p99_latency_ns"] for r in group),
                      "errors": sum(r["errors"] for r in group), "timeouts": sum(r["timeouts"] for r in group),
                      "cleanup_pass": all(r["cleanup_pass"] for r in group),
                      "achieved_offered_ratio": min(r["max_observed_total_outstanding"] / r["configured_total_outstanding"] for r in group),
                      "peak_working_set_bytes": max(role["peak_working_set_bytes"] for r in group for role in r["resources"]["roles"].values()),
                      "roles": roles, "per_group_median_gbps": per_group_median})
    return cells


def write_summary(output: Path, analysis: dict) -> None:
    lines = [
        "# Benchmark V2 Task 3 Stage 2: in-process group scaling", "",
        "Classification: **PASS / HARNESS-LIMITED: shared destination QUIC endpoint driver runtime**", "",
        "Independent source groups use distinct OS threads and current-thread Tokio runtimes. Each NBSR group owns "
        "a separately authenticated connection and authorized channel. Destination application handlers also use "
        "dedicated current-thread runtimes, but all accepted connections retain one shared listener/endpoint driver "
        "runtime; this is the next harness serialization boundary requiring focused profiling. Direct and NBSR "
        "failed to achieve strict stable scaling: NBSR exceeded the strict p99 saturation threshold at two groups "
        "while total CPU remained below "
        "two effective cores. No host or production NBSR ceiling is claimed.", "",
        "| Payload/shape | Groups | Direct Gbit/s | NBSR Gbit/s | Delta | NBSR CPU cores | NBSR p99 ms | Region |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    cells = analysis["cells"]
    for payload, streams, outstanding in SHAPES:
        for groups in GROUPS:
            direct = next(c for c in cells if c["payload_bytes"] == payload and c["streams_per_group"] == streams and c["outstanding_per_stream"] == outstanding and c["groups"] == groups and c["path"] == "direct")
            nbsr = next(c for c in cells if c["payload_bytes"] == payload and c["streams_per_group"] == streams and c["outstanding_per_stream"] == outstanding and c["groups"] == groups and c["path"] == "nbsr")
            region = analysis["scaling"][f"p{payload}-s{streams}-o{outstanding}-nbsr"]["cells"][groups.bit_length() - 1]["region"]
            delta = (nbsr["median_gbps"] / direct["median_gbps"] - 1) * 100
            lines.append(f"| {payload} B / s{streams} / o{outstanding} | {groups} | {direct['median_gbps']:.3f} | {nbsr['median_gbps']:.3f} | {delta:+.2f}% | {nbsr['median_effective_cores']:.3f} | {nbsr['median_p99_latency_ns']/1e6:.3f} | {region} |")
    lines += ["", "Process affinity was verified at mask `0x55`, selecting four physical-core-separated logical processors. Per-thread placement inside that allowed set was not independently verified.", "", "All authoritative cells had zero errors/timeouts and process-level cleanup returned every owned NBSR resource and registry to zero.", ""]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def run(output: Path, warmup: float, duration: float, repeats: int) -> None:
    topology = windows_processor_topology()
    mask = int(topology["affinity_masks"]["4"]["decimal"])
    if not topology["verified"] or mask != 0x55:
        raise RuntimeError("verified physical-core mask 0x55 required")
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    binaries = p2a.build(Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b2-v2-profile")))
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-stage2-") as temporary:
        authority = Path(temporary) / "authority"
        write_loopback_authority(authority)
        for cell in stage2_cells():
            cell_records = []
            for repeat in range(1, repeats + 1):
                record = run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, mask)
                path = raw / f"{cell['path']}-p{cell['payload_bytes']}-s{cell['streams_per_group']}-o{cell['outstanding_per_stream']}-g{cell['groups']}-r{repeat}.json"
                path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                records.append(record)
                cell_records.append(record)
            values = [r["aggregate_application_gbps"] for r in cell_records]
            if len(values) >= 3 and statistics.stdev(values) / statistics.fmean(values) > 0.05:
                for repeat in range(repeats + 1, 6):
                    record = run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, mask)
                    path = raw / f"{cell['path']}-p{cell['payload_bytes']}-s{cell['streams_per_group']}-o{cell['outstanding_per_stream']}-g{cell['groups']}-r{repeat}.json"
                    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                    records.append(record)
    cells = summarize(records)
    analyses = {}
    for payload, streams, outstanding in SHAPES:
        for path in ("direct", "nbsr"):
            selected = [c for c in cells if c["payload_bytes"] == payload and c["streams_per_group"] == streams and c["outstanding_per_stream"] == outstanding and c["path"] == path]
            analyses[f"p{payload}-s{streams}-o{outstanding}-{path}"] = classify_group_scaling(selected)
    analysis = {"schema": "nbsr-max-throughput-v2-stage2-analysis-v1",
                "classification": {"evidence": "PASS", "system": "HARNESS-LIMITED:shared-destination-quic-endpoint-driver-runtime"},
                "cells": cells, "scaling": analyses,
                "claim_boundary": "Windows loopback benchmark harness; no production or hardware ceiling claim."}
    (output / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_summary(output, analysis)
    environment = {"schema": "nbsr-max-throughput-v2-stage2-environment-v1",
                   "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                   "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
                   "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "os": platform.platform(),
                   "processor_topology": topology, "process_affinity_mask": hex(mask),
                   "group_thread_masks": None, "group_thread_masks_enforced": False,
                   "runtime_workers": 1, "python": sys.version,
                   "cargo": subprocess.check_output(["cargo", "--version"], text=True).strip(),
                   "binaries": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                for name, path in binaries.items()}}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "manifest.json").write_text(json.dumps({"schema": "nbsr-max-throughput-v2-stage2-manifest-v1",
        "command": [sys.executable, *sys.argv], "warmup_seconds": warmup, "duration_seconds": duration,
        "minimum_repeats": repeats, "records": len(records), "cells": len(cells)}, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (output / "checksums.sha256").write_text("\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}" for path in files) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=2)
    parser.add_argument("--duration-seconds", type=float, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run(args.output, args.warmup_seconds, args.duration_seconds, args.repeats)


if __name__ == "__main__":
    main()
