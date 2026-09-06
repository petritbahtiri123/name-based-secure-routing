from __future__ import annotations

import argparse
import ctypes
from contextlib import ExitStack
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
from scripts.performance.mixed_connections import analyze_records, load_levels, remember_completion
from scripts.performance.resources import sample_windows_process, sample_windows_threads
from scripts.performance.stderr_drain import StderrDrain
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
    "crates/nbsr-transport/src/bin/benchmark_support/lifecycle_completion.rs",
    "crates/nbsr-transport/src/bin/perf_rust_source.rs",
    "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    "scripts/performance/mixed_connections.py",
    "scripts/run_b4b_mixed_connections.py",
    "scripts/performance/stderr_drain.py",
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


def terminal_evidence_complete(expected: set[int], acknowledgments: set[int], failures: set[int], *, source_succeeded: bool) -> bool:
    return source_succeeded and acknowledgments | failures == expected and acknowledgments.isdisjoint(failures)


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


def sample_admission_threads(process: subprocess.Popen[str] | None, samples: list[dict[str, Any]]) -> None:
    if process is None or process.poll() is not None:
        return
    observed = time.perf_counter_ns()
    try:
        samples.extend(
            {
                "timestamp_ns": observed,
                "thread_id": sample.thread_id,
                "user_cpu_ns": sample.user_cpu_ns,
                "kernel_cpu_ns": sample.kernel_cpu_ns,
            }
            for sample in sample_windows_threads(process.pid)
        )
    except OSError:
        pass


def summarize_shard_cpu(samples: list[dict[str, Any]], mapping: dict[int, int]) -> dict[str, Any]:
    result = {}
    for shard, thread_id in sorted(mapping.items()):
        rows = sorted(
            (sample for sample in samples if int(sample["thread_id"]) == thread_id),
            key=lambda sample: sample["timestamp_ns"],
        )
        if len(rows) < 2:
            result[str(shard)] = {"thread_id": thread_id, "valid": False}
            continue
        elapsed_ns = int(rows[-1]["timestamp_ns"]) - int(rows[0]["timestamp_ns"])
        cpu_ns = int(rows[-1]["user_cpu_ns"]) + int(rows[-1]["kernel_cpu_ns"]) - int(rows[0]["user_cpu_ns"]) - int(rows[0]["kernel_cpu_ns"])
        result[str(shard)] = {
            "thread_id": thread_id,
            "valid": elapsed_ns > 0,
            "effective_cores": cpu_ns / elapsed_ns if elapsed_ns > 0 else None,
            "samples": len(rows),
        }
    return result


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


def lifecycle_server_environment(base: dict[str, str], release_rate: float | None) -> dict[str, str]:
    result = dict(base)
    if release_rate is not None:
        result["NBSR_PERF_LIFECYCLE_OFFERED_RATE"] = str(release_rate)
    return result


def lifecycle_client_command(
    binary: Path,
    endpoint: str,
    authority: Path,
    lifecycle: Path,
    *,
    connections: int,
    offset: int,
    logical_clients: int | None = None,
    release_batch: int | None = None,
    release_interval_ms: int | None = None,
    release_rate: float | None = None,
    source_shards: int = 1,
) -> list[str]:
    if (release_batch is None) != (release_interval_ms is None):
        raise ValueError("release batch and interval must be supplied together")
    if release_rate is not None and release_batch is not None:
        raise ValueError("release batch and offered rate are mutually exclusive")
    if source_shards not in (1, 2):
        raise ValueError("source shards must be 1 or 2")
    command = [
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
    if logical_clients is not None:
        command.extend(["--lifecycle-clients", str(logical_clients)])
    if release_batch is not None:
        command.extend(["--lifecycle-release-batch", str(release_batch), "--lifecycle-release-interval-ms", str(release_interval_ms)])
    if release_rate is not None:
        command.extend(["--lifecycle-offered-rate", str(release_rate)])
    if source_shards == 2:
        command.extend(["--lifecycle-source-shards", "2"])
    return command


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
    timeline: bool = False,
    release_batch: int | None = None,
    release_interval_ms: int | None = None,
    release_rate: float | None = None,
    source_shards: int = 1,
    packet_capture: Any = None,
    backend: Any = None,
) -> dict[str, Any]:
    command = backend.command if backend is not None else lambda argv: argv
    sample_owned = backend.sample if backend is not None else sample_processes
    stem = f"clients-{clients}-connections-{connections_per_client}-r{repeat}"
    cell_dir = raw_dir / stem
    cell_dir.mkdir(parents=True)
    with ExitStack() as timeline_lifetime, tempfile.TemporaryDirectory(prefix="nbsr-b4b-") as temporary:
        source_timeline = destination_timeline = None
        if timeline:
            from scripts.performance.handshake_timeline import Timeline

            source_timeline = timeline_lifetime.enter_context(Timeline(clients * connections_per_client, 1))
            destination_timeline = timeline_lifetime.enter_context(Timeline(clients * connections_per_client, 2))
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
            command(established_server_argv),
            cwd=ROOT,
            env={**os.environ, "NBSR_P2A_STREAMS": "8"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lifecycle_server: subprocess.Popen[str] | None = None
        admission_client: subprocess.Popen[str] | None = None
        processes: dict[str, subprocess.Popen[str]] = {"established-destination": established_server}
        samples: list[dict[str, Any]] = []
        admission_thread_samples: list[dict[str, Any]] = []
        lifecycle_server_commands: list[list[str]] = []
        client_commands: list[list[str]] = []
        established_client: subprocess.Popen[str] | None = None
        admission_stdout_file = None
        admission_stderr_file = None
        admission_stdout_path = cell_dir / "admission-source.stdout"
        admission_stderr_path = cell_dir / "admission-source.stderr"
        destination_stderr_path = cell_dir / "admission-destination.stderr.raw"
        stderr_drain = None
        stderr_capture = {"valid": True, "not_applicable": clients == 0}
        destination_cleanup_seconds = None
        failure = ""
        try:
            established_endpoint = wait_ready(established_ready, established_server)["endpoint"]
            lifecycle_diagnostics = cell_dir / "lifecycle-diagnostics.ndjson"
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
                command(established_client_argv), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            processes["established-source"] = established_client
            warmup_deadline = time.monotonic() + warmup
            while time.monotonic() < warmup_deadline:
                sample_owned(processes, samples)
                time.sleep(0.1)
            if clients:
                lifecycle_ready = temp / "lifecycle-ready.json"
                server_argv = [
                    str(binaries["server"]),
                    "--ready",
                    str(lifecycle_ready),
                    "--result",
                    str(cell_dir / "lifecycle-server-result.json"),
                    "--authority-dir",
                    str(lifecycle_authority),
                    "--completion-ack",
                    str(temp / "lifecycle.ack"),
                    "--destination-diagnostics-file",
                    str(lifecycle_diagnostics),
                    "--diagnostic-drain-seconds",
                    "1",
                ]
                lifecycle_server_commands.append(server_argv)
                lifecycle_server = subprocess.Popen(
                    command(server_argv),
                    cwd=ROOT,
                    env=lifecycle_server_environment(
                        {
                            **os.environ,
                            "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle),
                            "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(clients * connections_per_client),
                            "NBSR_PERF_LIFECYCLE_SERVICES": "1",
                            "NBSR_PERF_STREAMS_PER_SERVICE": "1",
                            "NBSR_PERF_CONCURRENT_STREAMS": "1",
                            "NBSR_PERF_CONCURRENT_SESSIONS": "1",
                            "NBSR_BENCH_TIMELINE": destination_timeline.name if destination_timeline else "",
                        },
                        release_rate,
                    ),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                )
                stderr_drain = StderrDrain(lifecycle_server.stderr, destination_stderr_path)
                processes["admission-destination"] = lifecycle_server
                lifecycle_endpoint = wait_ready(lifecycle_ready, lifecycle_server)["endpoint"]
                if packet_capture is not None:
                    timeline_lifetime.enter_context(packet_capture.capture(lifecycle_endpoint, cell_dir))
            admission_started_epoch = time.time()
            admission_started = time.monotonic()
            if clients:
                argv = lifecycle_client_command(
                    binaries["nbsr"],
                    lifecycle_endpoint,
                    lifecycle_authority,
                    lifecycle,
                    connections=connections_per_client,
                    offset=0,
                    logical_clients=clients * connections_per_client,
                    release_batch=release_batch,
                    release_interval_ms=release_interval_ms,
                    release_rate=release_rate,
                    source_shards=source_shards,
                )
                client_commands.append(argv)
                admission_stdout_file = admission_stdout_path.open("w", encoding="utf-8", newline="\n")
                admission_stderr_file = admission_stderr_path.open("w", encoding="utf-8", newline="\n")
                admission_client = subprocess.Popen(
                    command(argv),
                    cwd=ROOT,
                    env={**os.environ, "NBSR_BENCH_TIMELINE": source_timeline.name if source_timeline else ""},
                    stdout=admission_stdout_file,
                    stderr=admission_stderr_file,
                    text=True,
                )
                processes["admission-source"] = admission_client
            peak_pending = 0
            admission_finished: float | None = admission_started if clients == 0 else None
            deadline = time.monotonic() + duration + 45
            while established_client.poll() is None or (admission_client is not None and admission_client.poll() is None):
                sample_owned(processes, samples)
                if backend is None:
                    sample_admission_threads(admission_client, admission_thread_samples)
                pending = clients * connections_per_client if admission_client is not None and admission_client.poll() is None else 0
                peak_pending = max(peak_pending, pending)
                admission_finished = remember_completion(admission_finished, pending=pending, now=time.monotonic())
                if time.monotonic() >= deadline:
                    if admission_client is not None and admission_client.poll() is None:
                        admission_client.kill()
                        admission_client.wait(timeout=5)
                    raise TimeoutError(
                        "B4b cell exceeded duration plus 45-second cleanup bound; "
                        f"admission_process_running={admission_client is not None and admission_client.poll() is None}"
                    )
                time.sleep(0.1)
            established_finished = time.monotonic()
            workload_finished_epoch = time.time()
            if admission_client is not None and admission_client.poll() is not None:
                admission_finished = remember_completion(admission_finished, pending=0, now=established_finished)
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
            if admission_client is not None:
                admission_client.wait(timeout=5)
                admission_stdout_file.close()
                admission_stderr_file.close()
                admission_stdout_file = None
                admission_stderr_file = None
                stdout = admission_stdout_path.read_text(encoding="utf-8")
                stderr = admission_stderr_path.read_text(encoding="utf-8")
                shard_mapping = {}
                for line in stderr.splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("event") == "lifecycle_source_shard":
                        shard_mapping[int(event["shard"])] = int(event["thread_id"])
                if admission_client.returncode:
                    failed_clients = clients
                    failure += stderr
                admission_outputs.extend(json.loads(line) for line in stdout.splitlines() if line.strip())
            server_failures = []
            if lifecycle_server is not None:
                cleanup_started = time.monotonic()
                cleanup_deadline = cleanup_started + 15
                try:
                    lifecycle_server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server_failures.append("lifecycle destination cleanup exceeded 15 seconds")
                    lifecycle_server.kill()
                    lifecycle_server.wait(timeout=5)
                try:
                    stderr_capture = stderr_drain.finish(cleanup_deadline - time.monotonic())
                except (RuntimeError, TimeoutError) as error:
                    stderr_capture = {"valid": False, "error": str(error)}
                    server_failures.append(str(error))
                destination_cleanup_seconds = time.monotonic() - cleanup_started
                if lifecycle_server.returncode:
                    detail = (
                        destination_stderr_path.read_bytes().decode("utf-8", errors="replace")
                        if stderr_capture["valid"]
                        else "stderr evidence incomplete"
                    )
                    server_failures.append(f"lifecycle server failed: {detail}")
            established = json.loads(established_stdout.strip().splitlines()[-1])
            measured_seconds = int(established["measured_ns"]) / 1e9
            completed = int(established["completed_operations"])
            latencies = [int(value["ttfab_ns"]) for value in admission_outputs if value.get("success")]
            successful_clients = {
                int(value["logical_client_id"]) for value in admission_outputs if value.get("success") and "logical_client_id" in value
            }
            failed_client_records = [
                value
                for value in admission_outputs
                if not value.get("success")
                and value.get("phase") not in {"close", "cleanup"}
                and int(value["logical_client_id"]) not in successful_clients
            ]
            cleanup_error_records = [value for value in admission_outputs if value.get("phase") in {"close", "cleanup"}]
            connected_clients = {
                int(value["logical_client_id"])
                for value in admission_outputs
                if value.get("success") and value.get("transport_handshake_ns") is not None
            }
            cleaned_clients = {
                int(path.name.removeprefix("connection-").removesuffix(".ack")) for path in lifecycle.glob("connection-*.ack")
            }
            failed_marker_clients = {
                int(path.name.removeprefix("connection-").removesuffix(".failed")) for path in lifecycle.glob("connection-*.failed")
            }
            expected_client_ids = set(range(clients * connections_per_client))
            terminal_marker_clients = cleaned_clients | failed_marker_clients
            terminal_evidence_exact = terminal_evidence_complete(
                expected_client_ids,
                cleaned_clients,
                failed_marker_clients,
                source_succeeded=admission_client is None or admission_client.returncode == 0,
            )
            cleanup_parts = [diagnostics_cleanup(established_diagnostics)]
            if clients:
                cleanup_parts.append(diagnostics_cleanup(lifecycle_diagnostics))
            process_exit = all(process.poll() is not None for process in processes.values())
            cleanup = {
                "all_zero": all(part["all_zero"] for part in cleanup_parts) and terminal_evidence_exact,
                "processes_exited": process_exit,
                "destinations": cleanup_parts,
                "driver_completed_clients": len(terminal_marker_clients),
                "terminal_evidence_exact": terminal_evidence_exact,
            }
            timeline_capture = {"valid": True, "enabled": timeline}
            if timeline:
                try:
                    if not process_exit:
                        raise ValueError("timeline read before measured process exit")
                    # Preserve original bytes, including rejected/corrupt evidence.
                    for role, owner in (("source", source_timeline), ("destination", destination_timeline)):
                        (cell_dir / f"timeline-{role}.bin").write_bytes(owner.mapping[:])
                    timeline_capture.update(source=source_timeline.snapshot(), destination=destination_timeline.snapshot())
                except (ValueError, OSError) as error:
                    timeline_capture.update(valid=False, error=str(error))
            return {
                "schema": "nbsr-b4b-mixed-connections-repeat-v2",
                "repeat": repeat,
                "clients": clients,
                "connections_per_client": connections_per_client,
                "planned_clients": planned_clients,
                "scheduled_admissions": clients * connections_per_client,
                "requested_clients": clients * connections_per_client,
                "started_clients": clients * connections_per_client,
                "connected_clients": len(connected_clients),
                "admitted_clients": len(successful_clients),
                "cleaned_clients": len(cleaned_clients),
                "successful_admissions": len(latencies),
                "failed_admissions": clients * connections_per_client - len(latencies),
                "errors": len(failed_client_records) + len(cleanup_error_records) + failed_clients + len(server_failures),
                "timeouts": sum(bool(value.get("timed_out")) for value in [*failed_client_records, *cleanup_error_records]),
                "cleanup_errors": len(cleanup_error_records),
                "established_goodput_bytes_per_second": 2 * completed * 1024 / measured_seconds,
                "established_p50_latency_ns": int(established["p50_latency_ns"]),
                "established_p95_latency_ns": int(established["p95_latency_ns"]),
                "established_p99_latency_ns": int(established["p99_latency_ns"]),
                "admission_p50_latency_ns": percentile(latencies, 0.50),
                "admission_p95_latency_ns": percentile(latencies, 0.95),
                "admission_p99_latency_ns": percentile(latencies, 0.99),
                "handshake_latency_ns": {
                    str(p): percentile(
                        [
                            int(v["transport_handshake_ns"])
                            for v in admission_outputs
                            if v.get("success") and v.get("transport_handshake_ns") is not None
                        ],
                        p / 100,
                    )
                    for p in (50, 95, 99)
                },
                "admission_elapsed_seconds": max(admission_finished - admission_started, 1e-9),
                "orchestrator_epoch": {
                    "admission_started": admission_started_epoch,
                    "workload_processes_finished": workload_finished_epoch,
                },
                "admissions_completed_before_established_end": admission_finished <= established_finished,
                "peak_pending_clients": peak_pending,
                "resources": backend.summarize(samples) if backend is not None else summarize_resources(samples),
                "source_shards": source_shards,
                "source_shard_cpu": (backend.shard_cpu(shard_mapping) if backend is not None
                                     else summarize_shard_cpu(admission_thread_samples, shard_mapping)) if admission_client is not None else {},
                "admission_thread_samples": admission_thread_samples,
                "harness_topology": {
                    "admission_source_processes": 1 if clients else 0,
                    "admission_source_shards": source_shards if clients else 0,
                    "admission_destination_processes": 1 if clients else 0,
                    "logical_clients_share_session": False,
                    "tls_edge_identity": "source.edge",
                },
                "resource_samples": samples,
                "ownership": {
                    "connections_created": len(latencies),
                    "sessions_created": len(latencies),
                    "routes_admitted": len(latencies),
                    "streams_created": len(latencies),
                },
                "logical_client_terminal_cleanup": {
                    "requested": clients * connections_per_client,
                    "cleaned": len(cleaned_clients),
                    "driver_completed": len(terminal_marker_clients),
                    "all_terminal": len(successful_clients) + len(failed_client_records) == clients * connections_per_client,
                    "client_ids": sorted(successful_clients | {int(value["logical_client_id"]) for value in failed_client_records}),
                },
                "cleanup": cleanup,
                "stderr_capture": stderr_capture,
                "timeline_capture": timeline_capture,
                "diagnostic_release": {"batch_size": release_batch, "interval_ms": release_interval_ms},
                "offered_admission_rate": release_rate,
                "packet_capture": packet_capture.report if packet_capture is not None else {"enabled": False, "valid": True},
                "destination_cleanup_wait_seconds": destination_cleanup_seconds,
                "saturation_failure": "; ".join(server_failures) if server_failures else None,
                "commands": {
                    "established_server": public_command(command(established_server_argv), temp),
                    "established_client": public_command(command(established_client_argv), temp),
                    "lifecycle_servers": [public_command(command(argv), temp) for argv in lifecycle_server_commands],
                    "admission_clients": [public_command(command(argv), temp) for argv in client_commands],
                },
                "failure_detail": "\n".join(value for value in [failure, *server_failures] if value) or None,
            }
        finally:
            shutdown_error = None
            for process in [admission_client, established_client, lifecycle_server, established_server]:
                if process is not None and process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        shutdown_error = error
            if timeline and all(
                process is None or process.poll() is not None
                for process in [admission_client, established_client, lifecycle_server, established_server]
            ):
                # Exceptional runs retain raw records after child termination too.
                for role, owner in (("source", source_timeline), ("destination", destination_timeline)):
                    path = cell_dir / f"timeline-{role}.bin"
                    if not path.exists():
                        path.write_bytes(owner.mapping[:])
            if admission_stdout_file is not None:
                admission_stdout_file.close()
            if admission_stderr_file is not None:
                admission_stderr_file.close()
            if stderr_drain is not None and stderr_drain.thread.is_alive():
                # Never extend a used cleanup deadline. A live daemon reader
                # cannot hold interpreter exit; the capture is already invalid.
                try:
                    stderr_drain.finish(0)
                except (RuntimeError, TimeoutError):
                    pass
            if backend is not None:
                backend.preserve(cell_dir, samples, processes)
            if shutdown_error is not None:
                raise shutdown_error


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
            "Each logical client creates a fresh QUIC transport connection, ControlSession, federated route/channel, and application stream inside one bounded source driver. Logical clients do not share NBSR sessions. The authenticated TLS edge identity remains source.edge.",
            "",
            "The admission workload uses one source driver process and one concurrent destination listener process. Established forwarding remains the unchanged separate source/destination pair. This is Windows loopback harness evidence, not WAN/server-class scaling.",
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
