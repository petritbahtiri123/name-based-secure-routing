from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authorities import write_authority_set
from scripts.performance.authority import write_loopback_authority
from scripts.performance.mixed_connections import admission_server_specs, analyze_records, load_levels, remember_completion
from scripts.performance.resources import sample_windows_process
from scripts.run_p2a_established import build
from scripts.run_performance_validation import ROOT, environment as host_environment, wait_ready


COUNTERS = (
    "transport_sessions_current_live",
    "service_channels_current_live",
    "application_streams_current_live",
    "nbsr_tasks_current_live",
    "quic_connections_current_live",
    "quic_streams_current_live",
    "audit_queue_current_entries",
    "replay_state_current_entries",
)
SOURCE_FILES = (
    "crates/nbsr-transport/src/bin/perf_rust_source.rs",
    "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    "scripts/performance/mixed_connections.py",
    "scripts/run_b4b_mixed_connections.py",
    "scripts/run_p2a_established.py",
    "tests/performance/test_mixed_connections.py",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    values.sort()
    return values[round((len(values) - 1) * fraction)]


def public_command(argv: list[str], temporary_root: Path) -> list[str]:
    replacements = ((str(temporary_root), "<temporary>"), (str(ROOT), "<repo>"))
    return [next((value.replace(prefix, replacement) for prefix, replacement in replacements if prefix in value), value) for value in argv]


def sample_processes(processes: dict[str, subprocess.Popen[str]], samples: list[dict[str, Any]]) -> None:
    observed = time.perf_counter_ns()
    for role, process in processes.items():
        if process.poll() is not None:
            continue
        try:
            samples.append({"timestamp_ns": observed, "role": role, "pid": process.pid, **asdict(sample_windows_process(process.pid))})
        except OSError:
            pass


def summarize_resources(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_pid: dict[int, list[dict[str, Any]]] = {}
    for sample in samples:
        by_pid.setdefault(int(sample["pid"]), []).append(sample)
    cpu_ns = 0
    for values in by_pid.values():
        values.sort(key=lambda value: value["timestamp_ns"])
        if len(values) > 1:
            cpu_ns += values[-1]["user_cpu_ns"] + values[-1]["kernel_cpu_ns"] - values[0]["user_cpu_ns"] - values[0]["kernel_cpu_ns"]
    timestamps = sorted({int(sample["timestamp_ns"]) for sample in samples})
    aggregate = []
    for timestamp in timestamps:
        current = [sample for sample in samples if int(sample["timestamp_ns"]) == timestamp]
        aggregate.append(
            {
                "working_set_bytes": sum(int(sample["working_set_bytes"]) for sample in current),
                "private_bytes": sum(int(sample["private_bytes"]) for sample in current),
                "threads": sum(int(sample["thread_count"]) for sample in current),
                "handles": sum(int(sample["handle_count"]) for sample in current),
                "processes": len(current),
            }
        )
    return {
        "cpu_seconds": cpu_ns / 1e9,
        "peak_working_set_bytes": max((value["working_set_bytes"] for value in aggregate), default=0),
        "peak_private_bytes": max((value["private_bytes"] for value in aggregate), default=0),
        "peak_threads": max((value["threads"] for value in aggregate), default=0),
        "peak_handles": max((value["handles"] for value in aggregate), default=0),
        "peak_processes": max((value["processes"] for value in aggregate), default=0),
    }


def diagnostics_cleanup(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"all_zero": False, "counters": {}, "reason": "diagnostics file missing"}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        return {"all_zero": False, "counters": {}, "reason": "diagnostics file empty"}
    final = records[-1]
    counters = {name: int(final[name]) for name in COUNTERS if name in final}
    return {"all_zero": len(counters) == len(COUNTERS) and all(value == 0 for value in counters.values()), "counters": counters}


def lifecycle_client_command(
    binary: Path,
    endpoint: str,
    authority: Path,
    lifecycle: Path,
    *,
    connections: int,
    offset: int,
) -> list[str]:
    return [
        str(binary),
        "--authority-dir",
        str(authority),
        "--endpoint",
        endpoint,
        "--samples",
        "1",
        "--payload-bytes",
        "1024",
        "--lifecycle-authority-dir",
        str(lifecycle),
        "--connections",
        str(connections),
        "--services",
        "1",
        "--streams-per-service",
        "1",
        "--concurrent-streams",
        "--connection-offset",
        str(offset),
    ]


def run_cell(
    clients: int,
    connections_per_client: int,
    repeat: int,
    binaries: dict[str, Path],
    raw_dir: Path,
    *,
    duration: float,
    warmup: float,
    planned_clients: list[int],
) -> dict[str, Any]:
    stem = f"clients-{clients}-connections-{connections_per_client}-r{repeat}"
    cell_dir = raw_dir / stem
    cell_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="nbsr-b4b-") as temporary:
        temp = Path(temporary)
        established_authority = temp / "established-authority"
        lifecycle_authority = temp / "lifecycle-authority"
        lifecycle = temp / "lifecycle"
        write_loopback_authority(established_authority)
        write_loopback_authority(lifecycle_authority)
        write_authority_set(lifecycle, 1)
        established_ready = temp / "established-ready.json"
        established_result = cell_dir / "established-server-result.json"
        established_ack = temp / "established.ack"
        established_diagnostics = cell_dir / "established-diagnostics.ndjson"
        established_server_argv = [
            str(binaries["server"]),
            "--ready",
            str(established_ready),
            "--result",
            str(established_result),
            "--authority-dir",
            str(established_authority),
            "--completion-ack",
            str(established_ack),
            "--destination-diagnostics-file",
            str(established_diagnostics),
            "--diagnostic-drain-seconds",
            "1",
        ]
        established_server = subprocess.Popen(
            established_server_argv,
            cwd=ROOT,
            env={**os.environ, "NBSR_P2A_STREAMS": "8"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lifecycle_servers: list[subprocess.Popen[str]] = []
        admission_clients: list[subprocess.Popen[str]] = []
        processes: dict[str, subprocess.Popen[str]] = {"established-destination": established_server}
        samples: list[dict[str, Any]] = []
        lifecycle_server_commands: list[list[str]] = []
        client_commands: list[list[str]] = []
        established_client: subprocess.Popen[str] | None = None
        failure = ""
        try:
            established_endpoint = wait_ready(established_ready, established_server)["endpoint"]
            lifecycle_endpoints: list[str] = []
            lifecycle_diagnostics: list[Path] = []
            established_client_argv = [
                str(binaries["nbsr"]),
                "--authority-dir",
                str(established_authority),
                "--endpoint",
                established_endpoint,
                "--samples",
                "1",
                "--payload-bytes",
                "1024",
                "--p2a-streams",
                "8",
                "--p2a-warmup-seconds",
                str(warmup),
                "--p2a-duration-seconds",
                str(duration),
            ]
            established_client = subprocess.Popen(
                established_client_argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            processes["established-source"] = established_client
            warmup_deadline = time.monotonic() + warmup
            while time.monotonic() < warmup_deadline:
                sample_processes(processes, samples)
                time.sleep(0.1)
            if clients:
                for index, _ in admission_server_specs(clients, connections_per_client):
                    lifecycle_ready = temp / f"lifecycle-ready-{index}.json"
                    diagnostics = cell_dir / f"lifecycle-diagnostics-{index}.ndjson"
                    lifecycle_diagnostics.append(diagnostics)
                    server_argv = [
                        str(binaries["server"]),
                        "--ready",
                        str(lifecycle_ready),
                        "--result",
                        str(cell_dir / f"lifecycle-server-result-{index}.json"),
                        "--authority-dir",
                        str(lifecycle_authority),
                        "--completion-ack",
                        str(temp / f"lifecycle-{index}.ack"),
                        "--destination-diagnostics-file",
                        str(diagnostics),
                        "--diagnostic-drain-seconds",
                        "1",
                    ]
                    lifecycle_server_commands.append(server_argv)
                    server = subprocess.Popen(
                        server_argv,
                        cwd=ROOT,
                        env={
                            **os.environ,
                            "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle),
                            "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(connections_per_client),
                            "NBSR_PERF_LIFECYCLE_SERVICES": "1",
                            "NBSR_PERF_STREAMS_PER_SERVICE": "1",
                            "NBSR_PERF_CONCURRENT_STREAMS": "1",
                        },
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    lifecycle_servers.append(server)
                    processes[f"admission-destination-{index}"] = server
                    lifecycle_endpoints.append(wait_ready(lifecycle_ready, server)["endpoint"])
            admission_started = time.monotonic()
            if clients:
                for index, offset in admission_server_specs(clients, connections_per_client):
                    argv = lifecycle_client_command(
                        binaries["nbsr"],
                        lifecycle_endpoints[index],
                        lifecycle_authority,
                        lifecycle,
                        connections=connections_per_client,
                        offset=offset,
                    )
                    client_commands.append(argv)
                    client = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    admission_clients.append(client)
                    processes[f"admission-source-{index}"] = client
            peak_pending = 0
            admission_finished: float | None = admission_started if clients == 0 else None
            deadline = time.monotonic() + duration + 45
            while established_client.poll() is None or any(client.poll() is None for client in admission_clients):
                sample_processes(processes, samples)
                pending = sum(client.poll() is None for client in admission_clients)
                peak_pending = max(peak_pending, pending)
                admission_finished = remember_completion(admission_finished, pending=pending, now=time.monotonic())
                if time.monotonic() >= deadline:
                    raise TimeoutError("B4b cell exceeded duration plus 45-second cleanup bound")
                time.sleep(0.1)
            established_finished = time.monotonic()
            if admission_finished is None:
                raise RuntimeError("admission completion timestamp missing")
            established_stdout, established_stderr = established_client.communicate(timeout=5)
            if established_client.returncode:
                raise RuntimeError(f"established client failed: {established_stderr}")
            established_server.wait(timeout=15)
            if established_server.returncode:
                raise RuntimeError(f"established server failed: {established_server.stderr.read()}")
            admission_outputs: list[dict[str, Any]] = []
            failed_clients = 0
            for client in admission_clients:
                stdout, stderr = client.communicate(timeout=5)
                if client.returncode:
                    failed_clients += 1
                    failure += stderr
                admission_outputs.extend(json.loads(line) for line in stdout.splitlines() if line.strip())
            server_failures = []
            for index, server in enumerate(lifecycle_servers):
                server.wait(timeout=15)
                if server.returncode:
                    server_failures.append(f"lifecycle server {index} failed: {server.stderr.read()}")
            established = json.loads(established_stdout.strip().splitlines()[-1])
            measured_seconds = int(established["measured_ns"]) / 1e9
            completed = int(established["completed_operations"])
            latencies = [int(value["ttfab_ns"]) for value in admission_outputs if value.get("success")]
            cleanup_parts = [diagnostics_cleanup(established_diagnostics)]
            cleanup_parts.extend(diagnostics_cleanup(path) for path in lifecycle_diagnostics)
            process_exit = all(process.poll() is not None for process in processes.values())
            cleanup = {
                "all_zero": all(part["all_zero"] for part in cleanup_parts),
                "processes_exited": process_exit,
                "destinations": cleanup_parts,
            }
            return {
                "schema": "nbsr-b4b-mixed-connections-repeat-v1",
                "repeat": repeat,
                "clients": clients,
                "connections_per_client": connections_per_client,
                "planned_clients": planned_clients,
                "scheduled_admissions": clients * connections_per_client,
                "successful_admissions": len(latencies),
                "failed_admissions": clients * connections_per_client - len(latencies),
                "errors": failed_clients + len(server_failures),
                "timeouts": sum("HandshakeTimeout" in detail for detail in server_failures),
                "established_goodput_bytes_per_second": 2 * completed * 1024 / measured_seconds,
                "established_p50_latency_ns": int(established["p50_latency_ns"]),
                "established_p95_latency_ns": int(established["p95_latency_ns"]),
                "established_p99_latency_ns": int(established["p99_latency_ns"]),
                "admission_p50_latency_ns": percentile(latencies, 0.50),
                "admission_p95_latency_ns": percentile(latencies, 0.95),
                "admission_p99_latency_ns": percentile(latencies, 0.99),
                "admission_elapsed_seconds": max(admission_finished - admission_started, 1e-9),
                "admissions_completed_before_established_end": admission_finished <= established_finished,
                "peak_pending_clients": peak_pending,
                "resources": summarize_resources(samples),
                "resource_samples": samples,
                "ownership": {
                    "connections_created": len(latencies),
                    "sessions_created": len(latencies),
                    "routes_admitted": len(latencies),
                    "streams_created": len(latencies),
                },
                "cleanup": cleanup,
                "saturation_failure": "; ".join(server_failures) if server_failures else None,
                "commands": {
                    "established_server": public_command(established_server_argv, temp),
                    "established_client": public_command(established_client_argv, temp),
                    "lifecycle_servers": [public_command(argv, temp) for argv in lifecycle_server_commands],
                    "admission_clients": [public_command(argv, temp) for argv in client_commands],
                },
                "failure_detail": "\n".join(value for value in [failure, *server_failures] if value) or None,
            }
        finally:
            for process in [*admission_clients, established_client, *lifecycle_servers, established_server]:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


def checksums(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (root / "checksums.sha256").write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
        newline="\n",
    )


def render_summary(analysis: dict[str, Any], environment: dict[str, Any], command: str) -> str:
    lines = [
        "# B4b Mixed Connections and Route Admissions",
        "",
        f"Evidence: **{analysis['evidence']}**",
        f"System: **{analysis['system']}**",
        "",
        "| Clients | Connections/client | Admissions/s | Established Gbit/s | Goodput/base | p95/p99 ms | p99/base | CPU s | Peak private MiB | Pending clients | Fail/timeout | Status |",
        "| ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for cell in analysis["cells"]:
        lines.append(
            f"| {cell['clients']} | {cell['connections_per_client']} | {cell['median_achieved_admissions_per_second']:.2f} | "
            f"{cell['median_established_goodput_bytes_per_second'] * 8 / 1e9:.3f} | {cell['median_goodput_ratio_to_baseline']:.3f} | "
            f"{cell['median_established_p95_latency_ns'] / 1e6:.3f}/{cell['median_established_p99_latency_ns'] / 1e6:.3f} | "
            f"{cell['median_p99_ratio_to_baseline']:.3f} | {cell['median_cpu_seconds']:.2f} | "
            f"{cell['median_peak_private_bytes'] / 1_048_576:.1f} | {cell['median_peak_pending_clients']:.0f} | "
            f"{cell['failed_admissions']}/{cell['timeouts']} | {cell['status']} |"
        )
    saturation = analysis["first_saturation"]
    lines.extend(
        [
            "",
            "First saturation: " + ("not observed" if saturation is None else f"{saturation['clients']} clients — {saturation['reason']}"),
            "",
            "Each admission creates a fresh QUIC transport connection, ControlSession, federated route/channel, and application stream from an independent client process. All ownership counters must return to zero.",
            "",
            "Limitation: established forwarding and admission churn use separate destination processes/listeners on the same Windows loopback host. This measures host contention and multi-client lifecycle behavior, not contention inside one shared destination runtime or WAN/server-class scaling.",
            "",
            f"Base Git SHA: `{environment['base_git_sha']}`",
            f"Host: {environment['os']} / {environment['cpu']}",
            f"Command: `{command}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--duration-seconds", type=float, default=20.0)
    parser.add_argument("--warmup-seconds", type=float, default=2.0)
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--clients")
    parser.add_argument("--connections-per-client", type=int, default=4)
    args = parser.parse_args()
    if args.repeats < 1 or args.duration_seconds <= 0 or args.warmup_seconds <= 0:
        raise SystemExit("repeats and durations must be positive")
    if ctypes.windll.kernel32.SetThreadExecutionState(0x80000001) == 0:
        raise ctypes.WinError()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b4b-mixed\cargo-target"))
    binaries = build(target)
    levels = load_levels(validation=args.validation)
    if args.clients is not None:
        requested = [int(value) for value in args.clients.split(",")]
        if not requested or requested[0] != 0 or any(value < 0 for value in requested):
            raise SystemExit("client levels must be non-negative and start with zero")
        if args.connections_per_client < 1:
            raise SystemExit("connections per client must be positive")
        levels = [(clients, args.connections_per_client if clients else 0) for clients in requested]
    if args.validation:
        args.repeats, args.duration_seconds, args.warmup_seconds = 1, 5.0, 1.0
    planned_clients = [clients for clients, _ in levels]
    environment = host_environment()
    environment.update(
        {
            "schema": "nbsr-b4b-environment-v1",
            "base_git_sha": environment.pop("repository_sha"),
            "branch": subprocess.run(
                ["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip(),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "build": "release",
            "topology": "Windows loopback, separate established and admission destination runtimes",
            "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES},
            "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()},
        }
    )
    write_json(output / "environment.json", environment)
    records = []
    command = shlex.join(sys.argv)
    for clients, connections in levels:
        for repeat in range(1, args.repeats + 1):
            print(f"running clients={clients} connections_per_client={connections} repeat={repeat}/{args.repeats}", flush=True)
            try:
                record = run_cell(
                    clients,
                    connections,
                    repeat,
                    binaries,
                    output / "raw",
                    duration=args.duration_seconds,
                    warmup=args.warmup_seconds,
                    planned_clients=planned_clients,
                )
            except Exception as error:
                record = {
                    "schema": "nbsr-b4b-mixed-connections-repeat-v1",
                    "repeat": repeat,
                    "clients": clients,
                    "connections_per_client": connections,
                    "planned_clients": planned_clients,
                    "scheduled_admissions": clients * connections,
                    "errors": 1,
                    "timeouts": int(isinstance(error, (TimeoutError, subprocess.TimeoutExpired))),
                    "failure": f"{type(error).__name__}: {error}",
                }
            records.append(record)
            write_json(output / "raw" / f"clients-{clients}-connections-{connections}-r{repeat}.json", record)
    analysis = analyze_records(records)
    write_json(output / "analysis.json", analysis)
    (output / "summary.md").write_text(render_summary(analysis, environment, command), encoding="utf-8", newline="\n")
    (output / "commands.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
    checksums(output)
    print(json.dumps({"evidence": analysis["evidence"], "system": analysis["system"], "records": len(records)}))


if __name__ == "__main__":
    main()
