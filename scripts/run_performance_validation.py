from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority  # noqa: E402
from scripts.performance.authorities import write_authority_set  # noqa: E402
from scripts.performance.driver import ensure_release_binary, lifecycle_batch_plan  # noqa: E402
from scripts.performance.resources import ProcessResourceSampler  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "crates" / "nbsr-transport"
GO_PEER = ROOT / "interop" / "nbsr-go-peer"
DURATIONS = (
    "transport_handshake_ns",
    "hello_rtt_ns",
    "source_admission_ns",
    "destination_admission_ns",
    "route_open_rtt_ns",
    "channel_binding_ns",
    "stream_open_rtt_ns",
    "ttfab_ns",
    "request_latency_ns",
    "application_processing_ns",
    "total_scenario_ns",
)


def command(argv: list[str], *, cwd: Path = ROOT, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv!r}\n{result.stderr}")
    return result


def measured_client(
    argv: list[str], *, cwd: Path, server: subprocess.Popen[str], timeout: int,
    stdout_path: Path | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    output_handle = stdout_path.open("w", encoding="utf-8", newline="\n") if stdout_path is not None else None
    client = subprocess.Popen(
        argv, cwd=cwd, stdout=output_handle if output_handle is not None else subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    sampler = ProcessResourceSampler(
        {"source": client.pid, "destination": server.pid},
        interval_seconds=1.0,
        assigned_logical_processors=os.cpu_count() or 1,
    )
    sampler.start()
    try:
        stdout, stderr = client.communicate(timeout=timeout)
        resources = [asdict(record) for record in sampler.stop()]
        if client.returncode:
            raise RuntimeError(f"command failed ({client.returncode}): {argv!r}\n{stderr}")
        return stdout or "", resources
    finally:
        if output_handle is not None:
            output_handle.close()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_value(*args: str) -> str:
    return command(["git", *args]).stdout.strip()


def environment() -> dict[str, Any]:
    powershell = command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$cpu=Get-CimInstance Win32_Processor|Select-Object -First 1; $cs=Get-CimInstance Win32_ComputerSystem; [ordered]@{cpu=$cpu.Name;cores=$cpu.NumberOfCores;logical_processors=$cpu.NumberOfLogicalProcessors;memory_bytes=[uint64]$cs.TotalPhysicalMemory;power_plan=(powercfg /getactivescheme)}|ConvertTo-Json -Compress",
        ]
    )
    host = json.loads(powershell.stdout)
    return {
        "schema": "nbsr-performance-environment-v1",
        "repository_sha": git_value("rev-parse", "HEAD"),
        "dirty_tree": bool(git_value("status", "--porcelain=v1")),
        "os": platform.platform(),
        "python": platform.python_version(),
        "rustc": command(["rustc", "--version"]).stdout.strip(),
        "cargo": command(["cargo", "--version"]).stdout.strip(),
        "go": command(["go", "version"]).stdout.strip(),
        "cpu": host["cpu"],
        "cores": host["cores"],
        "logical_processors": host["logical_processors"],
        "memory_bytes": host["memory_bytes"],
        "power_plan": host["power_plan"],
        "affinity": "inherited; not modified",
        "topology": "windows-loopback",
    }


def build_release(target: Path) -> dict[str, Path]:
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    result = subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--manifest-path",
            str(TRANSPORT / "Cargo.toml"),
            "--bin",
            "perf_direct_peer",
            "--bin",
            "wp8_interop_server",
            "--bin",
            "perf_rust_source",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    suffix = ".exe" if os.name == "nt" else ""
    go_binary = target / "release" / f"nbsr-go-peer{suffix}"
    command(["go", "build", "-trimpath", "-o", str(go_binary), "./cmd/nbsr-go-peer"], cwd=GO_PEER)
    binaries = {
        "direct": target / "release" / f"perf_direct_peer{suffix}",
        "server": target / "release" / f"wp8_interop_server{suffix}",
        "rust": target / "release" / f"perf_rust_source{suffix}",
        "go": go_binary,
    }
    return {name: ensure_release_binary(path) for name, path in binaries.items()}


def wait_ready(path: Path, process: subprocess.Popen[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    if not path.exists():
        raise RuntimeError(process.stderr.read() if process.stderr else "peer readiness timeout")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_ndjson(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def merge_destination_measurements(records: list[dict[str, Any]], result: dict[str, Any]) -> None:
    measurements = result.get("samples")
    if not isinstance(measurements, list) or len(measurements) != len(records):
        observed = len(measurements) if isinstance(measurements, list) else "invalid"
        raise ValueError(f"destination measurement count mismatch: source={len(records)} destination={observed}")
    for record, measurement in zip(records, measurements, strict=True):
        record["destination_admission_ns"] = int(measurement["destination_admission_ns"])
        record["application_processing_ns"] = int(measurement["application_processing_ns"])


def direct_samples(
    binary: Path, authority: Path, samples: int, payload: int, lifecycle: str, temp: Path,
    offered_rate: float | None = None,
    resource_records: list[dict[str, Any]] | None = None,
    raw_output: Path | None = None,
) -> list[dict[str, Any]]:
    if raw_output is not None and resource_records is None:
        raise ValueError("direct-to-disk load evidence requires resource capture")
    winmm = ctypes.WinDLL("winmm", use_last_error=True) if offered_rate is not None else None
    if winmm is not None and winmm.timeBeginPeriod(1) != 0:
        raise RuntimeError("failed to request 1 ms Windows timer resolution")
    ready = temp / f"direct-{lifecycle}.ready.json"
    ready.unlink(missing_ok=True)
    connections = samples if lifecycle == "cold" else 1
    per_connection = 1 if lifecycle == "cold" else samples
    server = subprocess.Popen(
        [
            str(binary),
            "--role",
            "server",
            "--ready",
            str(ready),
            "--authority-dir",
            str(authority),
            "--connections",
            str(connections),
            "--requests-per-connection",
            str(per_connection),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        client_command = [
                str(binary),
                "--role",
                "client",
                "--authority-dir",
                str(authority),
                "--endpoint",
                endpoint,
                "--samples",
                str(samples),
                "--payload-bytes",
                str(payload),
                "--lifecycle",
                lifecycle,
            ]
        if offered_rate is not None:
            client_command.extend(["--offered-rate", str(offered_rate)])
        if resource_records is None:
            stdout = command(client_command, timeout=3600).stdout
        else:
            stdout, observed_resources = measured_client(
                client_command, cwd=ROOT, server=server, timeout=3600, stdout_path=raw_output,
            )
            resource_records.extend(observed_resources)
        server.wait(30)
        if server.returncode:
            raise RuntimeError(server.stderr.read())
        return [] if raw_output is not None else parse_ndjson(stdout)
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(10)
        if winmm is not None and winmm.timeEndPeriod(1) != 0:
            raise RuntimeError("failed to release 1 ms Windows timer resolution")


def nbsr_samples(
    path: str, binaries: dict[str, Path], authority: Path, samples: int, payload: int, temp: Path,
    offered_rate: float | None = None,
    resource_records: list[dict[str, Any]] | None = None,
    raw_output: Path | None = None,
    go_runtime_series: Path | None = None,
) -> list[dict[str, Any]]:
    if raw_output is not None and resource_records is None:
        raise ValueError("direct-to-disk load evidence requires resource capture")
    winmm = ctypes.WinDLL("winmm", use_last_error=True) if offered_rate is not None else None
    if winmm is not None and winmm.timeBeginPeriod(1) != 0:
        raise RuntimeError("failed to request 1 ms Windows timer resolution")
    ready, result, ack = temp / f"{path}.ready.json", temp / f"{path}.result.json", temp / f"{path}.ack"
    for stale in (ready, result, ack):
        stale.unlink(missing_ok=True)
    env = {**os.environ, "NBSR_PERF_STREAM_SAMPLES": str(samples)}
    server = subprocess.Popen(
        [
            str(binaries["server"]),
            "--ready",
            str(ready),
            "--result",
            str(result),
            "--authority-dir",
            str(authority),
            "--completion-ack",
            str(ack),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        if path == "rust-rust":
            client_command = [
                    str(binaries["rust"]),
                    "--authority-dir",
                    str(authority),
                    "--endpoint",
                    endpoint,
                    "--samples",
                    str(samples),
                    "--payload-bytes",
                    str(payload),
                ] + (["--offered-rate", str(offered_rate)] if offered_rate is not None else [])
            if resource_records is None:
                stdout = command(client_command, timeout=3600).stdout
            else:
                stdout, observed_resources = measured_client(
                    client_command, cwd=ROOT, server=server, timeout=3600, stdout_path=raw_output,
                )
                resource_records.extend(observed_resources)
            records = [] if raw_output is not None else parse_ndjson(stdout)
        else:
            config = temp / "go-config.json"
            config.write_text(
                json.dumps(
                    {
                        "readiness_path": str(ready),
                        "f75_package": str(ROOT / "vectors/wp8-f75-route-open"),
                        "local_attestation_package": str(ROOT / "vectors/wp8-local-admission"),
                        "safe_payload": "Z" * payload,
                        "benchmark_samples": samples,
                        "offered_rate": offered_rate,
                        "runtime_series_path": str(go_runtime_series) if go_runtime_series is not None else "",
                        "runtime_sampling_cadence_ms": 1000 if go_runtime_series is not None else 0,
                    }
                ),
                encoding="utf-8",
            )
            client_command = [str(binaries["go"]), "--config", str(config)]
            if resource_records is None:
                stdout = command(client_command, cwd=GO_PEER, timeout=3600).stdout
            else:
                stdout, observed_resources = measured_client(
                    client_command, cwd=GO_PEER, server=server, timeout=3600, stdout_path=raw_output,
                )
                resource_records.extend(observed_resources)
            if raw_output is not None:
                records = []
            elif offered_rate is None:
                records = json.loads(stdout)["samples"]
            else:
                documents = [json.loads(line) for line in stdout.splitlines() if line.strip()]
                records = [document for document in documents if "sample_id" in document]
                if not documents or documents[-1].get("status") != "PASS":
                    raise RuntimeError("Go load stream omitted completion metadata")
        ack.touch()
        server.wait(30)
        if server.returncode:
            raise RuntimeError(server.stderr.read())
        return records
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(10)
        if winmm is not None and winmm.timeEndPeriod(1) != 0:
            raise RuntimeError("failed to release 1 ms Windows timer resolution")


def rust_lifecycle_samples(
    binaries: dict[str, Path],
    authority: Path,
    samples: int,
    payload: int,
    scenario: str,
    temp: Path,
    streams_per_service: int = 1,
    concurrent: bool = False,
    services_per_session: int = 20,
) -> list[dict[str, Any]]:
    if not 1 <= streams_per_service <= 64:
        raise ValueError("streams per service must be in 1..64")
    if scenario == "nbsr-cold":
        batches = (samples,)
        def services_for_batch(_batch: int) -> int:
            return 1

        def connections_for_batch(batch: int) -> int:
            return batch
    elif scenario == "nbsr-warm-new-service":
        batches = lifecycle_batch_plan(samples=samples, services_per_session=services_per_session)
        def services_for_batch(batch: int) -> int:
            return batch

        def connections_for_batch(_batch: int) -> int:
            return 1
    else:
        raise ValueError(f"unsupported lifecycle scenario {scenario}")
    lifecycle_root = temp / "lifecycle-authority"
    write_authority_set(lifecycle_root, services_per_session)
    records: list[dict[str, Any]] = []
    for ordinal, batch in enumerate(batches):
        services = services_for_batch(batch)
        connections = connections_for_batch(batch)
        ready = temp / f"rust-lifecycle-{scenario}-{ordinal}.ready.json"
        result = temp / f"rust-lifecycle-{scenario}-{ordinal}.result.json"
        ack = temp / f"rust-lifecycle-{scenario}-{ordinal}.ack"
        for connection_ordinal in range(connections):
            (lifecycle_root / f"connection-{connection_ordinal}.ack").unlink(missing_ok=True)
        server_env = {
            **os.environ,
            "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle_root),
            "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(connections),
            "NBSR_PERF_LIFECYCLE_SERVICES": str(services),
            "NBSR_PERF_STREAMS_PER_SERVICE": str(streams_per_service),
        }
        if concurrent:
            server_env["NBSR_PERF_CONCURRENT_STREAMS"] = "1"
        server = subprocess.Popen(
            [
                str(binaries["server"]), "--ready", str(ready), "--result", str(result),
                "--authority-dir", str(authority), "--completion-ack", str(ack),
            ],
            cwd=ROOT,
            env=server_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            endpoint = wait_ready(ready, server)["endpoint"]
            client_command = [
                    str(binaries["rust"]), "--authority-dir", str(authority), "--endpoint", endpoint,
                    "--samples", "1", "--payload-bytes", str(payload),
                    "--lifecycle-authority-dir", str(lifecycle_root),
                    "--connections", str(connections), "--services", str(services),
                    "--streams-per-service", str(streams_per_service),
                ]
            if concurrent:
                client_command.extend(["--concurrent-streams", "true"])
            client = command(
                client_command,
                timeout=3600,
            )
            batch_records = parse_ndjson(client.stdout)
            expected_records = batch * streams_per_service
            if len(batch_records) != expected_records:
                raise RuntimeError(f"lifecycle sample loss: expected {expected_records}, observed {len(batch_records)}")
            server.wait(30)
            if server.returncode:
                raise RuntimeError(server.stderr.read())
            merge_destination_measurements(batch_records, json.loads(result.read_text(encoding="utf-8")))
            for record in batch_records:
                record["sample_id"] = len(records)
                record["transport_sessions"] = 1
                record["service_channels"] = services
                record["application_streams"] = expected_records
                record["request_concurrency"] = expected_records if concurrent else 1
                if scenario == "nbsr-warm-new-service":
                    record["transport_handshake_ns"] = None
                    record["hello_rtt_ns"] = None
                records.append(record)
        finally:
            if server.poll() is None:
                server.terminate()
                server.wait(10)
    return records


def go_lifecycle_samples(
    binaries: dict[str, Path],
    authority: Path,
    samples: int,
    payload: int,
    scenario: str,
    temp: Path,
    streams_per_service: int = 1,
    concurrent: bool = False,
    services_per_session: int = 20,
) -> list[dict[str, Any]]:
    if not 1 <= streams_per_service <= 64:
        raise ValueError("streams per service must be in 1..64")
    if scenario == "nbsr-cold":
        batches = (samples,)
        def services_for_batch(_batch: int) -> int:
            return 1

        def connections_for_batch(batch: int) -> int:
            return batch
    elif scenario == "nbsr-warm-new-service":
        batches = lifecycle_batch_plan(samples=samples, services_per_session=services_per_session)
        def services_for_batch(batch: int) -> int:
            return batch

        def connections_for_batch(_batch: int) -> int:
            return 1
    else:
        raise ValueError(f"unsupported lifecycle scenario {scenario}")
    lifecycle_root = temp / "go-lifecycle-authority"
    write_authority_set(lifecycle_root, services_per_session)
    records: list[dict[str, Any]] = []
    for ordinal, batch in enumerate(batches):
        services = services_for_batch(batch)
        connections = connections_for_batch(batch)
        ready = temp / f"go-lifecycle-{scenario}-{ordinal}.ready.json"
        result = temp / f"go-lifecycle-{scenario}-{ordinal}.result.json"
        ack = temp / f"go-lifecycle-{scenario}-{ordinal}.ack"
        for connection_ordinal in range(connections):
            (lifecycle_root / f"connection-{connection_ordinal}.ack").unlink(missing_ok=True)
        server_environment = {
            **os.environ,
            "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle_root),
            "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(connections),
            "NBSR_PERF_LIFECYCLE_SERVICES": str(services),
            "NBSR_PERF_STREAMS_PER_SERVICE": str(streams_per_service),
        }
        if concurrent:
            server_environment["NBSR_PERF_CONCURRENT_STREAMS"] = "1"
        server = subprocess.Popen(
            [
                str(binaries["server"]), "--ready", str(ready), "--result", str(result),
                "--authority-dir", str(authority), "--completion-ack", str(ack),
            ],
            cwd=ROOT,
            env=server_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(ready, server)
            config = temp / f"go-lifecycle-{scenario}-{ordinal}.json"
            config.write_text(
                json.dumps(
                    {
                        "readiness_path": str(ready),
                        "f75_package": str(ROOT / "vectors/wp8-f75-route-open"),
                        "local_attestation_package": str(ROOT / "vectors/wp8-local-admission"),
                        "safe_payload": "Z" * payload,
                        "benchmark_samples": batch,
                        "lifecycle_authority_dir": str(lifecycle_root),
                        "lifecycle_connections": connections,
                        "lifecycle_services": services,
                        "lifecycle_streams_per_service": streams_per_service,
                        "lifecycle_concurrent": concurrent,
                    }
                ),
                encoding="utf-8",
            )
            client = command([str(binaries["go"]), "--config", str(config)], cwd=GO_PEER, timeout=3600)
            batch_records = json.loads(client.stdout)["samples"]
            expected_records = batch * streams_per_service
            if len(batch_records) != expected_records:
                raise RuntimeError(f"lifecycle sample loss: expected {expected_records}, observed {len(batch_records)}")
            server.wait(30)
            if server.returncode:
                raise RuntimeError(server.stderr.read())
            merge_destination_measurements(batch_records, json.loads(result.read_text(encoding="utf-8")))
            for record in batch_records:
                record["sample_id"] = len(records)
                record["transport_sessions"] = 1
                record["service_channels"] = services
                record["application_streams"] = expected_records
                record["request_concurrency"] = expected_records if concurrent else 1
                if scenario == "nbsr-warm-new-service":
                    record["transport_handshake_ns"] = None
                    record["hello_rtt_ns"] = None
                records.append(record)
        finally:
            if server.poll() is None:
                server.terminate()
                server.wait(10)
    return records


def session_scaling_samples(
    path: str,
    binaries: dict[str, Path],
    authority: Path,
    sessions: int,
    payload: int,
    temp: Path,
) -> dict[str, Any]:
    if path not in {"direct-quic", "rust-rust", "go-rust"} or sessions < 1:
        raise ValueError("unsupported session scaling request")
    lifecycle_root = temp / f"{path}-session-scaling-authority"
    if path != "direct-quic":
        write_authority_set(lifecycle_root, 1)
    else:
        lifecycle_root.mkdir(parents=True, exist_ok=True)
    for ordinal in range(sessions):
        for suffix in ("ack", "connected"):
            (lifecycle_root / f"connection-{ordinal}.{suffix}").unlink(missing_ok=True)
    ready = temp / f"{path}-sessions-{sessions}.ready.json"
    result = temp / f"{path}-sessions-{sessions}.result.json"
    completion_ack = temp / f"{path}-sessions-{sessions}.ack"
    for stale in (ready, result, completion_ack):
        stale.unlink(missing_ok=True)
    if path == "direct-quic":
        server_argv = [str(binaries["direct"]), "--role", "server", "--ready", str(ready), "--authority-dir", str(authority), "--connections", str(sessions), "--requests-per-connection", "1"]
        server_environment = os.environ.copy()
    else:
        server_argv = [str(binaries["server"]), "--ready", str(ready), "--result", str(result), "--authority-dir", str(authority), "--completion-ack", str(completion_ack)]
        server_environment = {
            **os.environ,
            "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle_root),
            "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(sessions),
            "NBSR_PERF_LIFECYCLE_SERVICES": "1",
            "NBSR_PERF_STREAMS_PER_SERVICE": "1",
            "NBSR_PERF_CONCURRENT_SESSIONS": "1",
        }
    server = subprocess.Popen(
        server_argv,
        cwd=ROOT,
        env=server_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    clients: list[subprocess.Popen[str]] = []
    try:
        wait_ready(ready, server)
        started = time.perf_counter()
        endpoint = json.loads(ready.read_text(encoding="utf-8"))["endpoint"]
        for ordinal in range(sessions):
            if path == "direct-quic":
                marker = lifecycle_root / f"connection-{ordinal}.connected"
                argv = [str(binaries["direct"]), "--role", "client", "--authority-dir", str(authority), "--endpoint", endpoint, "--samples", "1", "--payload-bytes", str(payload), "--lifecycle", "warm", "--connected-marker", str(marker)]
                clients.append(subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            elif path == "rust-rust":
                argv = [
                    str(binaries["rust"]), "--authority-dir", str(authority), "--endpoint", endpoint,
                    "--samples", "1", "--payload-bytes", str(payload), "--lifecycle-authority-dir", str(lifecycle_root),
                    "--connections", "1", "--services", "1", "--streams-per-service", "1", "--connection-offset", str(ordinal),
                ]
                clients.append(subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            else:
                config = temp / f"go-session-{sessions}-{ordinal}.json"
                config.write_text(json.dumps({
                    "readiness_path": str(ready), "f75_package": str(ROOT / "vectors/wp8-f75-route-open"),
                    "local_attestation_package": str(ROOT / "vectors/wp8-local-admission"), "safe_payload": "Z" * payload,
                    "benchmark_samples": 1, "lifecycle_authority_dir": str(lifecycle_root), "lifecycle_connections": 1,
                    "lifecycle_services": 1, "lifecycle_streams_per_service": 1,
                    "lifecycle_connection_offset": ordinal, "lifecycle_report_connections": True,
                }), encoding="utf-8")
                clients.append(subprocess.Popen([str(binaries["go"]), "--config", str(config)], cwd=GO_PEER, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 30
        connected = [lifecycle_root / f"connection-{ordinal}.connected" for ordinal in range(sessions)]
        while not all(marker.exists() for marker in connected) and time.monotonic() < deadline:
            time.sleep(0.001)
        if not all(marker.exists() for marker in connected):
            raise RuntimeError("not all requested Transport Sessions became active")
        establishment_seconds = time.perf_counter() - started
        records: list[dict[str, Any]] = []
        for ordinal, client in enumerate(clients):
            stdout, stderr = client.communicate(timeout=60)
            if client.returncode:
                raise RuntimeError(f"session scaling client {ordinal} failed: {stderr}")
            observed = parse_ndjson(stdout) if path in {"direct-quic", "rust-rust"} else json.loads(stdout)["samples"]
            if len(observed) != 1:
                raise RuntimeError(f"session scaling client {ordinal} sample loss")
            observed[0].update({"sample_id": ordinal, "transport_sessions": sessions, "service_channels": sessions, "application_streams": sessions, "request_concurrency": sessions})
            records.append(observed[0])
        server.wait(30)
        if server.returncode:
            raise RuntimeError(server.stderr.read())
        if path != "direct-quic":
            merge_destination_measurements(records, json.loads(result.read_text(encoding="utf-8")))
        return {
            "active_transport_sessions": sessions,
            "connection_establishment_seconds": establishment_seconds,
            "connection_establishment_rate": sessions / establishment_seconds,
            "successful_requests": len(records),
            "failures": 0,
            "records": records,
        }
    finally:
        for client in clients:
            if client.poll() is None:
                client.terminate()
                client.wait(10)
        if server.poll() is None:
            server.terminate()
            server.wait(10)


def normalize(
    record: dict[str, Any],
    *,
    sample_id: int,
    path: str,
    scenario: str,
    payload: int,
    environment_digest: str,
    repository_sha: str,
    run_id: str,
    load_level: str = "idle",
    offered_load: float | None = None,
    achieved_load: float | None = None,
) -> dict[str, Any]:
    result = {name: record.get(name) for name in DURATIONS}
    result.update(
        {
            "schema": "nbsr-performance-sample-v1",
            "run_id": run_id,
            "sample_id": sample_id,
            "repository_sha": repository_sha,
            "dirty_tree": False,
            "environment_digest": environment_digest,
            "topology": "windows-loopback",
            "build_profile": "release",
            "path": path,
            "implementation_version": repository_sha,
            "scenario": scenario,
            "transport_sessions": int(record.get("transport_sessions", 1)),
            "service_channels": int(record.get("service_channels", 0 if path == "direct-quic" else 1)),
            "application_streams": int(record.get("application_streams", 1)),
            "request_concurrency": int(record.get("request_concurrency", 1)),
            "payload_bytes": payload,
            "load_level": load_level,
            "offered_load": offered_load,
            "achieved_load": achieved_load,
            "success": bool(record.get("success", True)),
            "error_type": record.get("error_type"),
            "error_stage": record.get("error_stage"),
            "bytes_transmitted": int(record["bytes_transmitted"]),
            "bytes_received": int(record["bytes_received"]),
        }
    )
    for name in (
        "scheduled_ns", "started_ns", "completed_ns", "start_lateness_ns", "service_latency_ns",
        "send_lag_ns", "receive_lag_ns", "queue_depth", "active_requests",
    ):
        if name in record:
            result[name] = int(record[name])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["calibration", "latency", "capacity", "load"], required=True)
    parser.add_argument("--paths", default="direct-quic,rust-rust,go-rust")
    parser.add_argument("--samples", type=int, default=100_000)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/performance")
    args = parser.parse_args()
    if args.phase != "latency":
        raise SystemExit(f"{args.phase} execution is not yet implemented")
    if not (1 <= args.samples <= 100_000):
        raise SystemExit("samples must be in 1..100000")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "raw").mkdir(exist_ok=True)
    env_record = environment()
    if env_record["dirty_tree"]:
        raise SystemExit("formal benchmark requires a clean working tree")
    encoded_environment = json.dumps(env_record, sort_keys=True, separators=(",", ":")).encode()
    environment_digest = hashlib.sha256(encoded_environment).hexdigest()
    (args.output / "environment.json").write_text(json.dumps(env_record, indent=2) + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="nbsr-perf-") as temporary:
        temp = Path(temporary)
        authority = temp / "authority"
        write_loopback_authority(authority)
        target = Path(os.environ.get("NBSR_PERF_CARGO_TARGET", r"C:\codex-target\nbsr-perf-formal"))
        binaries = build_release(target)
        for path in args.paths.split(","):
            run_id = f"{path}-warm-existing-1024-idle"
            if path == "direct-quic":
                raw = direct_samples(binaries["direct"], authority, args.samples, args.payload_bytes, "warm", temp)
                scenario = "direct-warm"
            elif path in {"rust-rust", "go-rust"}:
                raw = nbsr_samples(path, binaries, authority, args.samples, args.payload_bytes, temp)
                scenario = "nbsr-warm-existing-service"
            else:
                raise SystemExit(f"unsupported path {path}")
            records = [
                normalize(
                    record,
                    sample_id=index,
                    path=path,
                    scenario=scenario,
                    payload=args.payload_bytes,
                    environment_digest=environment_digest,
                    repository_sha=env_record["repository_sha"],
                    run_id=run_id,
                )
                for index, record in enumerate(raw)
            ]
            output = args.output / "raw" / f"{run_id}.ndjson"
            output.write_text(
                "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records), encoding="utf-8"
            )
            print(f"{path}: {len(records)} samples -> {output}")


if __name__ == "__main__":
    main()
