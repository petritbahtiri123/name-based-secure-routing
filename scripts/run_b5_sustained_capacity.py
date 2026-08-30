from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority
from scripts.performance.sustained_capacity import analyze_soak_run
from scripts.run_p2a_established import build
from scripts.run_performance_validation import measured_client, wait_ready


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "crates/nbsr-transport/src/bin/b5_support/mod.rs",
    "crates/nbsr-transport/src/bin/perf_rust_source.rs",
    "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    "scripts/performance/sustained_capacity.py",
    "scripts/run_b5_sustained_capacity.py",
    "tests/performance/test_sustained_capacity.py",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_ndjson(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values), encoding="utf-8", newline="\n")


def _parse_run(value: str) -> dict[str, Any]:
    parts = value.split(":")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("run must be NAME:DURATION_SECONDS:PAYLOAD_BYTES:STREAMS")
    name, duration, payload, streams = parts
    result = {"name": name, "duration_seconds": int(duration), "payload_bytes": int(payload), "streams": int(streams)}
    if not name or result["duration_seconds"] < 10 or result["payload_bytes"] not in {1024, 16384} or result["streams"] not in {8, 64}:
        raise argparse.ArgumentTypeError("invalid bounded run configuration")
    return result


def _source_identity() -> dict[str, Any]:
    return {
        "base_git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "files_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCE_FILES},
    }


def _diagnostic_cleanup(source: list[dict[str, Any]], destination: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for role, records in (("source", source), ("destination", destination)):
        if records:
            final = records[-1]
            result[role] = {
                field: final[field]
                for field in (
                    "transport_sessions_current_live",
                    "service_channels_current_live",
                    "application_streams_current_live",
                    "nbsr_tasks_current_live",
                    "quic_connections_current_live",
                    "quic_streams_current_live",
                    "audit_queue_current_entries",
                    "replay_state_current_entries",
                )
                if field in final
            }
    return result


def _run_one(
    spec: dict[str, Any],
    *,
    binaries: dict[str, Path],
    authority: Path,
    output: Path,
    warmup_seconds: int,
    cooldown_seconds: int,
    sample_seconds: int,
) -> dict[str, Any]:
    run_dir = output / "raw" / spec["name"]
    run_dir.mkdir(parents=True)
    ready = run_dir / "destination-ready.json"
    result = run_dir / "destination-result.json"
    ack = run_dir / "destination-completion.ack"
    destination_diagnostics_path = run_dir / "destination-diagnostics.ndjson"
    server_argv = [
        str(binaries["server"]), "--ready", str(ready), "--result", str(result),
        "--authority-dir", str(authority), "--completion-ack", str(ack),
        "--destination-diagnostics-file", str(destination_diagnostics_path),
        "--diagnostic-drain-seconds", str(cooldown_seconds),
    ]
    server = subprocess.Popen(
        server_argv,
        cwd=ROOT,
        env={**os.environ, "NBSR_P2A_STREAMS": str(spec["streams"])},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    progress: list[dict[str, Any]] = []
    source_diagnostics: list[dict[str, Any]] = []
    final_records: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    received_progress: list[tuple[int, int]] = []
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        client_argv = [
            str(binaries["nbsr"]), "--authority-dir", str(authority), "--endpoint", endpoint,
            "--samples", "1", "--payload-bytes", str(spec["payload_bytes"]),
            "--p2a-streams", str(spec["streams"]), "--p2a-warmup-seconds", str(warmup_seconds),
            "--p2a-duration-seconds", str(spec["duration_seconds"]),
            "--p2a-progress-seconds", str(sample_seconds), "--p2a-cooldown-seconds", str(cooldown_seconds),
        ]
        call_started = time.perf_counter_ns()

        def line_sink(line: str) -> None:
            document = json.loads(line)
            if document.get("event") == "p2a_progress":
                progress.append(document)
                received_progress.append((time.perf_counter_ns(), int(document["elapsed_ns"])))
            elif document.get("event") == "diagnostic":
                source_diagnostics.append(document)
            elif document.get("schema") == "nbsr-p2a-repeat-v1":
                final_records.append(document)

        _stdout, _sampled = measured_client(
            client_argv,
            cwd=ROOT,
            server=server,
            timeout=warmup_seconds + int(spec["duration_seconds"]) + cooldown_seconds + 120,
            output_line_sink=line_sink,
            resource_sink=resources.append,
            sampling_interval_seconds=float(sample_seconds),
        )
        if len(final_records) != 1 or final_records[0].get("schema") != "nbsr-p2a-repeat-v1":
            raise RuntimeError("missing unique final P2A result")
        final = final_records[0]
        server.wait(timeout=cooldown_seconds + 30)
        if server.returncode:
            raise RuntimeError(server.stderr.read() if server.stderr else "destination failed")
        destination_diagnostics = [json.loads(line) for line in destination_diagnostics_path.read_text(encoding="utf-8").splitlines()]
        if not received_progress:
            raise RuntimeError("no periodic application telemetry")
        measurement_origin = int(round(sum(received - elapsed for received, elapsed in received_progress) / len(received_progress)))
        for sample in resources:
            absolute = call_started + int(sample["timestamp_ns"])
            relative = absolute - measurement_origin
            sample["measurement_relative_ns"] = relative
            sample["phase"] = "warmup" if relative < 0 else (
                "steady" if relative <= int(spec["duration_seconds"]) * 1_000_000_000 else "cooldown"
            )
        if int(final["completed_operations"]) != sum(int(item["completed_operations"]) for item in progress):
            raise RuntimeError("final and periodic completed-operation accounting differ")
        cleanup = _diagnostic_cleanup(source_diagnostics, destination_diagnostics)
        analysis = analyze_soak_run(
            progress,
            resources,
            cleanup,
            expected_duration_seconds=int(spec["duration_seconds"]),
            payload_bytes=int(spec["payload_bytes"]),
            streams=int(spec["streams"]),
        )
        analysis["process_cleanup"] = {
            "source_exited": True,
            "destination_exited": server.poll() is not None,
            "destination_return_code": server.returncode,
        }
        _write_ndjson(run_dir / "progress.ndjson", progress)
        _write_ndjson(run_dir / "resources.ndjson", resources)
        _write_ndjson(run_dir / "source-diagnostics.ndjson", source_diagnostics)
        _write_json(run_dir / "final.json", final)
        _write_json(run_dir / "cleanup.json", cleanup)
        _write_json(run_dir / "analysis.json", analysis)
        _write_json(run_dir / "commands.json", {"client": client_argv, "destination": server_argv})
        return analysis
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)


def _summary(analyses: list[dict[str, Any]], environment: dict[str, Any], command: str) -> str:
    rows = []
    for item in analyses:
        memory = item.get("memory", {})
        peak = max((role.get("peak_working_set_bytes") or 0 for role in memory.values()), default=0)
        slopes = ", ".join(f"{role}={values['steady_private_slope_bytes_per_second']:.1f} B/s" for role, values in memory.items())
        rows.append(
            f"| {item['duration_seconds']} | {item['payload_bytes']} | {item['streams']} | {item['completed_operations']} | "
            f"{item['median_goodput_bytes_per_second'] * 8 / 1e9:.3f} | {item['goodput_drift_percent']:.3f}% | "
            f"{item['median_p95_latency_ns']:.0f} | {item['median_p99_latency_ns']:.0f} | {peak / 1048576:.1f} MiB | "
            f"{slopes} | {item['errors']} | {item['timeouts']} | {item['cleanup_result']} | "
            f"{item['evidence_status']} / {item['system_result']} |"
        )
    overall_evidence = "PASS" if all(item["evidence_status"] == "PASS" for item in analyses) else "INCONCLUSIVE"
    outcomes = {item["system_result"] for item in analyses}
    overall_system = next(iter(outcomes)) if len(outcomes) == 1 else "UNSTABLE"
    return "\n".join([
        "# B5 Sustained Capacity", "", f"Evidence Status: **{overall_evidence}**", f"System Result: **{overall_system}**", "",
        "| Duration s | Payload B | Streams | Operations | Median Gbit/s | Goodput drift | p95 ns | p99 ns | Peak working set | Steady private slope | Errors | Timeouts | Cleanup | Classification |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|---:|---:|:---|:---|", *rows, "",
        "Latency percentiles use deterministic 1-in-64 samples; operation and goodput counts are exact. Early/late comparisons exclude warm-up by construction.",
        "Resource phase alignment uses monotonic progress arrival timestamps; packet capture was not enabled to avoid observer overhead.", "",
        f"Base Git SHA: `{environment['source_identity']['base_git_sha']}`", f"Host: {environment['os']} / {environment['cpu']}",
        f"Command: `{command}`", "",
    ])


def _checksums(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (root / "checksums.sha256").write_text(
        "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}" for path in files) + "\n",
        encoding="utf-8", newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="append", type=_parse_run, required=True)
    parser.add_argument("--warmup-seconds", type=int, default=10)
    parser.add_argument("--cooldown-seconds", type=int, default=30)
    parser.add_argument("--sample-seconds", type=int, default=5)
    args = parser.parse_args()
    if args.warmup_seconds < 1 or args.cooldown_seconds < 1 or not 1 <= args.sample_seconds <= 5:
        parser.error("warmup/cooldown must be positive and sampling must be 1..5 seconds")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / ".gitattributes").write_text(".gitattributes text eol=lf\n*.json text eol=lf\n*.ndjson text eol=lf\n*.md text eol=lf\n*.txt text eol=lf\n*.sha256 text eol=lf\n", encoding="utf-8", newline="\n")
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b5-soak\cargo-target"))
    binaries = build(target)
    environment = {
        "source_identity": _source_identity(),
        "branch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os": platform.platform(), "cpu": platform.processor(), "logical_processors": os.cpu_count(),
        "python": platform.python_version(),
        "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()},
        "build": "cargo release with benchmark-harness feature", "topology": "Windows loopback",
        "packet_capture": "not enabled; optional installed Dumpcap/Npcap capture excluded from authoritative run to avoid observer overhead",
    }
    _write_json(args.output / "environment.json", environment)
    analyses = []
    with tempfile.TemporaryDirectory(prefix="nbsr-b5-") as temporary:
        authority = Path(temporary) / "authority"
        write_loopback_authority(authority)
        for spec in args.run:
            analyses.append(
                _run_one(
                    spec, binaries=binaries, authority=authority, output=args.output,
                    warmup_seconds=args.warmup_seconds, cooldown_seconds=args.cooldown_seconds,
                    sample_seconds=args.sample_seconds,
                )
            )
    overall = {
        "schema": "nbsr-b5-analysis-v1",
        "evidence_status": "PASS" if all(item["evidence_status"] == "PASS" for item in analyses) else "INCONCLUSIVE",
        "system_result": analyses[0]["system_result"] if len({item["system_result"] for item in analyses}) == 1 else "UNSTABLE",
        "runs": analyses,
    }
    _write_json(args.output / "analysis.json", overall)
    command = shlex.join(sys.argv)
    (args.output / "commands.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
    (args.output / "summary.md").write_text(_summary(analyses, environment, command), encoding="utf-8", newline="\n")
    _checksums(args.output)
    print(json.dumps({"evidence_status": overall["evidence_status"], "system_result": overall["system_result"], "runs": len(analyses)}))


if __name__ == "__main__":
    main()
