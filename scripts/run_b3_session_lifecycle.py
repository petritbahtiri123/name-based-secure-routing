from __future__ import annotations

import argparse
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

from scripts.performance.authorities import write_authority_set
from scripts.performance.resources import sample_windows_process
from scripts.performance.session_lifecycle_closure import analyze_path
from scripts.run_performance_validation import GO_PEER, ROOT, build_release, wait_ready


SOURCE_FILES = (
    "crates/nbsr-transport/src/bin/b3_support/mod.rs",
    "crates/nbsr-transport/src/bin/perf_rust_source.rs",
    "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    "interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go",
    "scripts/performance/session_lifecycle_closure.py",
    "scripts/run_b3_session_lifecycle.py",
    "tests/performance/test_session_lifecycle_closure.py",
)
COUNTERS = (
    "transport_sessions_current_live", "service_channels_current_live",
    "application_streams_current_live", "nbsr_tasks_current_live",
    "quic_connections_current_live", "quic_streams_current_live",
    "audit_queue_current_entries", "replay_state_current_entries",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def public_command(argv: list[str], temporary_root: Path) -> list[str]:
    replacements = ((str(temporary_root), "<temporary>"), (str(ROOT), "<repo>"))
    return [next((value.replace(prefix, replacement) for prefix, replacement in replacements if prefix in value), value) for value in argv]


def wait_paths(paths: list[Path], processes: list[subprocess.Popen[str]], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not all(path.is_file() for path in paths):
        failed = [process.returncode for process in processes if process.poll() not in (None, 0)]
        if failed:
            raise RuntimeError(f"lifecycle process exited before marker: {failed}")
        if time.monotonic() >= deadline:
            missing = [path.name for path in paths if not path.is_file()]
            raise RuntimeError(f"lifecycle marker timeout: {missing}")
        time.sleep(0.01)


def wait_active_ordinal(root: Path, pending: set[int], processes: list[subprocess.Popen[str]], timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while True:
        for ordinal in sorted(pending):
            if (root / f"connection-{ordinal}.active").is_file():
                return ordinal
        failed = [process.returncode for process in processes if process.poll() not in (None, 0)]
        if failed:
            raise RuntimeError(f"lifecycle process exited before active marker: {failed}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"lifecycle active marker timeout: {sorted(pending)}")
        time.sleep(0.01)


def capture(resources: list[dict[str, Any]], destination: subprocess.Popen[str], clients: list[subprocess.Popen[str]], *, phase: str, cycle: int, seconds: float, cadence: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        observed = time.perf_counter_ns()
        if destination.poll() is None:
            resources.append({"timestamp_ns": observed, "role": "destination", "phase": phase, "cycle": cycle, **asdict(sample_windows_process(destination.pid))})
        source_samples = [sample_windows_process(client.pid) for client in clients if client.poll() is None]
        if source_samples:
            resources.append({
                "timestamp_ns": observed, "role": "source", "phase": phase, "cycle": cycle,
                "working_set_bytes": sum(item.working_set_bytes for item in source_samples),
                "peak_working_set_bytes": sum(item.peak_working_set_bytes for item in source_samples),
                "private_bytes": sum(item.private_bytes for item in source_samples),
                "user_cpu_ns": sum(item.user_cpu_ns for item in source_samples),
                "kernel_cpu_ns": sum(item.kernel_cpu_ns for item in source_samples),
                "thread_count": sum(item.thread_count for item in source_samples),
                "handle_count": sum(item.handle_count for item in source_samples),
                "process_count": len(source_samples),
            })
        time.sleep(cadence)


def client_command(path: str, binaries: dict[str, Path], ready: Path, authority: Path, lifecycle: Path, *, connections: int, services: int, streams: int, offset: int, runtime_path: Path) -> tuple[list[str], Path]:
    if path == "rust-rust":
        return ([
            str(binaries["rust"]), "--authority-dir", str(authority), "--endpoint",
            json.loads(ready.read_text(encoding="utf-8"))["endpoint"], "--samples", "1",
            "--payload-bytes", "1024", "--lifecycle-authority-dir", str(lifecycle),
            "--connections", str(connections), "--services", str(services),
            "--streams-per-service", str(streams), "--concurrent-streams", "--hold-for-release",
            "--connection-offset", str(offset),
        ], ROOT)
    config = lifecycle / f"go-{offset}.json"
    write_json(config, {
        "readiness_path": str(ready), "f75_package": str(ROOT / "vectors/wp8-f75-route-open"),
        "local_attestation_package": str(ROOT / "vectors/wp8-local-admission"), "safe_payload": "Z" * 1024,
        "benchmark_samples": 1, "lifecycle_authority_dir": str(lifecycle),
        "lifecycle_connections": connections, "lifecycle_services": services,
        "lifecycle_streams_per_service": streams, "lifecycle_concurrent": True,
        "lifecycle_connection_offset": offset, "lifecycle_report_connections": True,
        "lifecycle_hold_for_release": True, "runtime_series_path": str(runtime_path),
        "runtime_sampling_cadence_ms": 1000,
    })
    return ([str(binaries["go"]), "--config", str(config)], GO_PEER)


def run_cell(path: str, spec: dict[str, int | str], binaries: dict[str, Path], root: Path, *, idle_seconds: float, active_seconds: float, cooldown_seconds: float, cadence: float) -> dict[str, Any]:
    name = str(spec["name"])
    sessions, services, streams, cycles = (int(spec[key]) for key in ("sessions", "channels", "streams", "cycles"))
    cell_dir = root / "raw" / path / name
    cell_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="nbsr-b3-cell-") as temporary:
        temporary_root = Path(temporary)
        lifecycle = temporary_root / "lifecycle"
        write_authority_set(lifecycle, services)
        authority = temporary_root / "authority"
        from scripts.performance.authority import write_loopback_authority
        write_loopback_authority(authority)
        ready, result = temporary_root / "ready.json", cell_dir / "server-result.json"
        completion_ack = temporary_root / "completion.ack"
        diagnostics = cell_dir / "destination-diagnostics.ndjson"
        server_argv = [str(binaries["server"]), "--ready", str(ready), "--result", str(result), "--authority-dir", str(authority), "--completion-ack", str(completion_ack), "--destination-diagnostics-file", str(diagnostics), "--diagnostic-drain-seconds", str(max(1, round(cooldown_seconds)))]
        total_connections = sessions if sessions > 1 else cycles
        server = subprocess.Popen(server_argv, cwd=ROOT, env={**os.environ, "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle), "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(total_connections), "NBSR_PERF_LIFECYCLE_SERVICES": str(services), "NBSR_PERF_STREAMS_PER_SERVICE": str(streams), "NBSR_PERF_CONCURRENT_STREAMS": "1", **({"NBSR_PERF_CONCURRENT_SESSIONS": "1"} if sessions > 1 else {})}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        clients: list[subprocess.Popen[str]] = []
        commands: list[list[str]] = []
        resources: list[dict[str, Any]] = []
        failure_detail = ""
        try:
            wait_ready(ready, server)
            client_specs = [(1, ordinal, temporary_root / f"go-runtime-{ordinal}.ndjson") for ordinal in range(sessions)] if sessions > 1 else [(cycles, 0, temporary_root / "go-runtime-0.ndjson")]
            for connections, offset, runtime_path in client_specs:
                argv, cwd = client_command(path, binaries, ready, authority, lifecycle, connections=connections, services=services, streams=streams, offset=offset, runtime_path=runtime_path)
                commands.append(argv)
                clients.append(subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            rounds = 1 if sessions > 1 else cycles
            for cycle in range(rounds):
                cycle_index = int(spec.get("cycle_index", cycle))
                ordinals = list(range(sessions)) if sessions > 1 else [cycle]
                capture(resources, server, clients, phase="idle" if cycle == 0 else "cooldown", cycle=cycle_index, seconds=idle_seconds if cycle == 0 else cooldown_seconds, cadence=cadence)
                for ordinal in ordinals:
                    (lifecycle / f"connection-{ordinal}.start").write_text("start\n", encoding="ascii")
                if spec["kind"] == "connections":
                    wait_paths([lifecycle / f"connection-{ordinal}.connected" for ordinal in ordinals], [server, *clients], 60)
                    capture(resources, server, clients, phase="active", cycle=cycle_index, seconds=active_seconds, cadence=cadence)
                    pending = set(ordinals)
                    while pending:
                        ordinal = wait_active_ordinal(lifecycle, pending, [server, *clients], 60)
                        (lifecycle / f"connection-{ordinal}.release").write_text("release\n", encoding="ascii")
                        wait_paths([lifecycle / f"connection-{ordinal}.ack"], [server, *clients], 60)
                        pending.remove(ordinal)
                    continue
                wait_paths([lifecycle / f"connection-{ordinal}.active" for ordinal in ordinals], [server, *clients], 60)
                capture(resources, server, clients, phase="active", cycle=cycle_index, seconds=active_seconds, cadence=cadence)
                for ordinal in ordinals:
                    (lifecycle / f"connection-{ordinal}.release").write_text("release\n", encoding="ascii")
                wait_paths([lifecycle / f"connection-{ordinal}.ack" for ordinal in ordinals], [server, *clients], 60)
            final_cycle = int(spec.get("cycle_index", rounds - 1))
            capture(resources, server, clients, phase="cooldown", cycle=final_cycle, seconds=cooldown_seconds, cadence=cadence)
            outputs = []
            for client in clients:
                stdout, stderr = client.communicate(timeout=30)
                if client.returncode:
                    raise RuntimeError(stderr)
                outputs.extend(json.loads(line) for line in stdout.splitlines() if line.strip())
            for _, ordinal, runtime_path in client_specs:
                if runtime_path.is_file():
                    (cell_dir / f"go-runtime-{ordinal}.ndjson").write_bytes(runtime_path.read_bytes())
            server.wait(timeout=30)
            if server.returncode:
                raise RuntimeError(server.stderr.read() if server.stderr else "destination failed")
        except Exception as error:
            details = []
            for label, process in [("destination", server), *[(f"source-{index}", client) for index, client in enumerate(clients)]]:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                if process.stderr is not None and not process.stderr.closed:
                    details.append(f"{label}: {process.stderr.read()}")
            details.append(f"lifecycle_files: {sorted(item.name for item in lifecycle.iterdir())}")
            details.append(f"commands: {commands}")
            failure_detail = "\n".join(details)
            raise RuntimeError(f"{error}\n{failure_detail}") from error
        finally:
            for process in [*clients, server]:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
        diagnostic_records = [json.loads(line) for line in diagnostics.read_text(encoding="utf-8").splitlines()]
        final = diagnostic_records[-1]
        cleanup_values = {field: int(final[field]) for field in COUNTERS if field in final}
        cleanup = {"counters": cleanup_values, "all_zero": len(cleanup_values) == len(COUNTERS) and all(value == 0 for value in cleanup_values.values()), "source_processes_exited": all(client.poll() is not None for client in clients), "destination_exited": server.poll() is not None}
        cell = {**spec, "active_count": int(spec["active_count"]), "samples": resources, "cleanup": cleanup, "commands": {"server": public_command(server_argv, temporary_root), "clients": [public_command(command, temporary_root) for command in commands]}, "client_results": outputs}
        write_json(cell_dir / "cell.json", cell)
        return cell


def specs(validation: bool) -> list[dict[str, int | str]]:
    if validation:
        return [{"name": "validation", "kind": "cycles", "active_count": 8, "sessions": 1, "channels": 1, "streams": 8, "cycles": 1, "cycle_index": 0, "cycle_mode": "process-isolated"}]
    result = []
    result.extend({"name": f"connections-{count}", "kind": "connections", "active_count": count, "sessions": count, "channels": 1, "streams": 1, "cycles": 1} for count in (1, 2, 4, 8))
    result.extend({"name": f"channels-{count}", "kind": "channels", "active_count": count, "sessions": 1, "channels": count, "streams": 1, "cycles": 1} for count in (1, 2, 4, 8))
    result.extend({"name": f"streams-{count}", "kind": "streams", "active_count": count, "sessions": 1, "channels": 1, "streams": count, "cycles": 1} for count in (1, 2, 4, 8))
    result.extend({"name": f"cycle-{cycle + 1}", "kind": "cycles", "active_count": 8, "sessions": 1, "channels": 2, "streams": 4, "cycles": 1, "cycle_index": cycle, "cycle_mode": "process-isolated"} for cycle in range(5))
    return result


def checksums(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (root / "checksums.sha256").write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n" for path in files), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--path", action="append", choices=("rust-rust", "go-rust"))
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b3-memory\cargo-target"))
    binaries = build_release(target)
    environment = {"base_git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(), "branch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(), "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "os": platform.platform(), "cpu": platform.processor(), "logical_processors": os.cpu_count(), "python": platform.python_version(), "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}, "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()}, "build": "release", "topology": "Windows loopback"}
    write_json(args.output / "environment.json", environment)
    paths = args.path or ["rust-rust", "go-rust"]
    all_cells: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        all_cells[path] = [run_cell(path, spec, binaries, args.output, idle_seconds=1.5 if args.validation else 2, active_seconds=2, cooldown_seconds=1.5 if args.validation else 2, cadence=0.5) for spec in specs(args.validation)]
    analysis = {"schema": "nbsr-b3-memory-session-analysis-v1", "paths": {path: analyze_path(path, cells) for path, cells in all_cells.items()}}
    write_json(args.output / "analysis.json", analysis)
    lines = ["# B3 Memory / Session Lifecycle", ""]
    for path, result in analysis["paths"].items():
        lines.extend([f"## {path}", "", f"Evidence: **{result['evidence']}**", f"Lifecycle: **{result['lifecycle']}**", "", f"Scaling: `{json.dumps(result['scaling'], sort_keys=True)}`", "", f"Cycles: `{json.dumps(result['cycles'], sort_keys=True)}`", ""])
    (args.output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    (args.output / "commands.txt").write_text(" ".join(sys.argv) + "\n", encoding="utf-8", newline="\n")
    checksums(args.output)
    print(json.dumps({path: {key: value for key, value in result.items() if key in {"evidence", "lifecycle"}} for path, result in analysis["paths"].items()}, sort_keys=True))


if __name__ == "__main__":
    main()
