from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import math
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
from scripts.performance.b3_failure_markers import snapshot_markers
from scripts.performance.resources import sample_windows_process
from scripts.performance.post_close_cleanup import FIELDS as RUST_CLEANUP_FIELDS
from scripts.performance.session_lifecycle_closure import analyze_path
from scripts.run_performance_validation import GO_PEER, ROOT, build_release, wait_ready


SOURCE_FILES = (
    "crates/nbsr-transport/src/config.rs",
    "crates/nbsr-transport/src/bin/b3_support/mod.rs",
    "crates/nbsr-transport/src/bin/perf_rust_source.rs",
    "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    "interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go",
    "scripts/performance/session_lifecycle_closure.py",
    "scripts/run_b3_session_lifecycle.py",
    "tests/performance/test_session_lifecycle_closure.py",
    "tests/performance/test_b3_keep_alive.py",
    "crates/nbsr-transport/tests/benchmark_keep_alive.rs",
)
COUNTERS = (
    "transport_sessions_current_live", "service_channels_current_live",
    "application_streams_current_live", "nbsr_tasks_current_live",
    "quic_connections_current_live", "quic_streams_current_live",
    "audit_queue_current_entries", "replay_state_current_entries",
)


def ownership_cleanup(path, final, outputs, *, source_count, cycles=None):
    """Rust requires all current fields; preserve the historical Go-only scope."""
    if path != 'rust-rust':
        values = {field: int(final[field]) for field in COUNTERS if field in final}
        return dict(counters=values, all_zero=len(values) == len(COUNTERS) and all(v == 0 for v in values.values()),
                    counter_scope='historical-go-destination-8-fields')

    def zero(row):
        return all(type(row.get(field)) is int and row[field] == 0 for field in RUST_CLEANUP_FIELDS)

    source_final = [row for row in outputs if row.get('phase') == 'lifecycle_cleanup']
    source_zero = len(source_final) == source_count and all(zero(row) for row in source_final)
    cleanup = dict(counters={field: final.get(field) for field in RUST_CLEANUP_FIELDS},
                   all_zero=zero(final) and source_zero, source_all_zero=source_zero,
                   source_counters=[{field: row.get(field) for field in RUST_CLEANUP_FIELDS} for row in source_final],
                   counter_scope='rust-all-11-current-fields')
    if cycles is not None:
        rows = [row for row in outputs if row.get('phase', '').startswith('lifecycle_cycle_')]
        cleanup['source_cycle_all_zero'] = len(rows) == cycles and all(zero(row) for row in rows)
        cleanup['all_zero'] = cleanup['all_zero'] and cleanup['source_cycle_all_zero']
    return cleanup


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


def wait_json_paths(paths, processes, timeout):
    """Wait for readable atomic JSON publications within one original deadline.

    Windows can report a renamed marker before another file handle permits its
    read. Retry only missing/sharing-denied reads; malformed JSON still fails.
    """
    deadline = time.monotonic() + timeout
    decoded = {}
    while len(decoded) < len(paths):
        failed = [process.returncode for process in processes if process.poll() not in (None, 0)]
        if failed:
            raise RuntimeError(f"lifecycle process exited before JSON marker: {failed}")
        for index, path in enumerate(paths):
            if index in decoded:
                continue
            if time.monotonic() >= deadline:
                missing = [p.name for i, p in enumerate(paths) if i not in decoded]
                raise RuntimeError(f"lifecycle JSON marker timeout: {missing}")
            try:
                decoded[index] = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, PermissionError):
                break
        if len(decoded) < len(paths):
            time.sleep(min(.01, max(0, deadline - time.monotonic())))
    return [decoded[index] for index in range(len(paths))]


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


def sample_if_running(process):
    if process.poll() is not None:
        return None
    try:
        return sample_windows_process(process.pid)
    except ProcessLookupError:
        if process.poll() is None:
            raise
        return None


def capture(resources: list[dict[str, Any]], destination: subprocess.Popen[str], clients: list[subprocess.Popen[str]], *, phase: str, cycle: int, seconds: float, cadence: float, capture_backend=None) -> None:
    if capture_backend is not None:
        return capture_backend.capture(resources, destination, clients, phase=phase, cycle=cycle, seconds=seconds, cadence=cadence)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        observed = time.perf_counter_ns()
        destination_sample = sample_if_running(destination)
        if destination_sample is not None:
            resources.append({"timestamp_ns": observed, "role": "destination", "phase": phase, "cycle": cycle, **asdict(destination_sample)})
        source_samples = [sample for client in clients if (sample := sample_if_running(client)) is not None]
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


def capture_final_cooldown(resources, server, clients, lifecycle, *, cycle, seconds, cadence, report_gate, capture_backend=None, allow_exited_sources=False):
    if allow_exited_sources and (not report_gate or capture_backend is None):
        raise ValueError('expected final source exit requires explicit backend and report-ready gate')
    if report_gate:
        wait_paths([lifecycle / "destination.report-ready"], [server], 120)
    if allow_exited_sources:
        # Bundle sources have no final-release gate and may be exiting here.
        # Move their existing join before cooldown instead of racing /proc.
        for client in clients:
            if client.wait(timeout=30) != 0:
                raise RuntimeError('bundle source failed before final cooldown')
        capture_backend.capture(resources, server, clients, phase="cooldown", cycle=cycle,
                                seconds=seconds, cadence=cadence, allow_exited_sources=True)
    else:
        capture(resources, server, clients, phase="cooldown", cycle=cycle, seconds=seconds, cadence=cadence, **({"capture_backend": capture_backend} if capture_backend is not None else {}))
    if report_gate:
        phase = {"phase": "report_generation", "started_unix_ns": time.time_ns(),
                 "scope": "report serialization and destination diagnostic drain; excluded from cooldown"}
        (lifecycle / "destination.report-release").write_text("release\n", encoding="ascii")
        return phase
    return None


def source_plan(path: str, sessions: int, cycles: int) -> list[tuple[int, int, int]]:
    if path == "rust-rust" and sessions > 1:
        return [(1, 0, sessions)]
    return [(1, ordinal, 1) for ordinal in range(sessions)] if sessions > 1 else [(cycles, 0, 1)]


def diagnostic_accept_environment(path, spec):
    if 'NBSR_PERF_LIFECYCLE_ACCEPT_WINDOW' in os.environ:
        raise ValueError('accept window must be an explicit recorded workload setting')
    window = spec.get('accept_window')
    if window is None:
        return {}
    rate = spec.get('start_rate', 0)
    if (path != 'rust-rust' or spec.get('kind') != 'sessions'
            or type(window) is not int or window not in (1, 2, 4, 8, 16, 32)
            or spec.get('sessions', 0) < max(window, 2)
            or type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0):
        raise ValueError('accept window requires bounded paced Rust simultaneous bundles')
    return {'NBSR_PERF_LIFECYCLE_ACCEPT_WINDOW': str(window)}


def run_cell(path: str, spec: dict[str, int | str], binaries: dict[str, Path], root: Path, *, idle_seconds: float, active_seconds: float, cooldown_seconds: float, cadence: float, capture_backend=None) -> dict[str, Any]:
    if capture_backend is not None and path != "rust-rust":
        raise ValueError("explicit capture backend supports Rust B3 only")
    capture_options = {"capture_backend": capture_backend} if capture_backend is not None else {}
    accept_environment = diagnostic_accept_environment(path, spec)
    name = str(spec["name"])
    allocator_snapshots = spec.get('allocator_snapshots', False)
    if allocator_snapshots:
        from scripts.performance.b3_allocator_snapshot import observer_spec
        observer_spec(spec, platform='linux' if capture_backend is not None else 'windows', enabled=True)
    sessions, services, streams, cycles = (int(spec[key]) for key in ("sessions", "channels", "streams", "cycles"))
    keep_alive = spec.get("keep_alive_seconds", 0)
    if (type(keep_alive) is not int or keep_alive not in (0, 1)
            or keep_alive and (path != "rust-rust" or spec["kind"] != "sessions")):
        raise ValueError("keepalive requires the separate Rust session-bundle workload at 1 second")
    materialized = spec.get("materialized_streams", False)
    if materialized and path != "rust-rust":
        raise ValueError("materialized streams require the Rust B3 harness")
    if materialized and spec["kind"] == "connections":
        raise ValueError("materialized streams do not support connection-only workload")
    if materialized:
        spec = {**spec,
                "stream_residency": "both endpoint stream handles and authorized request payload retained before common release",
                "timing_scope": "materialized-stream workload includes explicit hold in request/processing times; not comparable with registry-only timing"}
    cell_dir = root / "raw" / path / name
    cell_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="nbsr-b3-cell-") as temporary, ExitStack() as logs:
        def log(label, stream):
            return logs.enter_context((cell_dir / f"{label}.{stream}").open("w", encoding="utf-8"))
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
        report_gate = path == "rust-rust"
        if report_gate:
            server_argv.extend(["--b3-report-gate", str(lifecycle)])
        if materialized:
            server_argv.extend(["--b3-materialized-streams", "1"])
        if capture_backend is not None:
            server_argv = capture_backend.command(server_argv)
        server = subprocess.Popen(server_argv, cwd=ROOT, env={**os.environ, "NBSR_PERF_LIFECYCLE_ROOT": str(lifecycle), "NBSR_PERF_LIFECYCLE_CONNECTIONS": str(total_connections), "NBSR_PERF_LIFECYCLE_SERVICES": str(services), "NBSR_PERF_STREAMS_PER_SERVICE": str(streams), "NBSR_PERF_CONCURRENT_STREAMS": "1", **({"NBSR_PERF_LIFECYCLE_OFFERED_RATE": str(spec["start_rate"])} if float(spec.get("start_rate", 0)) > 0 else {}), **({"NBSR_PERF_CONCURRENT_SESSIONS": "1", "NBSR_PERF_LIFECYCLE_SERIAL_ACCEPT": "1"} if sessions > 1 else {}), **accept_environment}, stdout=log("destination", "stdout"), stderr=log("destination", "stderr"), text=True)
        clients: list[subprocess.Popen[str]] = []
        commands: list[list[str]] = []
        resources: list[dict[str, Any]] = []
        failure_detail = ""
        try:
            wait_ready(ready, server)
            client_specs = source_plan(path, sessions, cycles)
            for index, (connections, offset, logical_clients) in enumerate(client_specs):
                runtime_path = temporary_root / f"go-runtime-{offset}.ndjson"
                argv, cwd = client_command(path, binaries, ready, authority, lifecycle, connections=connections, services=services, streams=streams, offset=offset, runtime_path=runtime_path)
                if path == "rust-rust":
                    argv.extend(["--diagnostics", "1"])
                    if allocator_snapshots:
                        allocator_root = (cell_dir / 'source-allocator').resolve()
                        allocator_root.mkdir(exist_ok=False)
                        argv.extend(['--b3-allocator-directory', str(allocator_root)])
                    if keep_alive:
                        argv.extend(["--b3-keep-alive-seconds", str(keep_alive)])
                    if materialized:
                        argv.extend(["--b3-materialized-streams", "1"])
                    if logical_clients > 1:
                        argv.extend(["--lifecycle-clients", str(logical_clients), "--lifecycle-source-shards", "2"])
                    else:
                        argv.extend(["--lifecycle-final-release", str(lifecycle / "source.final-release")])
                if capture_backend is not None:
                    argv = capture_backend.command(argv)
                commands.append(argv)
                clients.append(subprocess.Popen(argv, cwd=cwd, stdout=log(f"source-{index}", "stdout"), stderr=log(f"source-{index}", "stderr"), text=True))
            rounds = 1 if sessions > 1 else cycles
            for cycle in range(rounds):
                cycle_index = int(spec.get("cycle_index", cycle))
                ordinals = list(range(sessions)) if sessions > 1 else [cycle]
                capture(resources, server, clients, phase="idle" if cycle == 0 else "cooldown", cycle=cycle_index if cycle == 0 else cycle_index - 1, seconds=idle_seconds if cycle == 0 else cooldown_seconds, cadence=cadence, **capture_options)
                start_origin = time.perf_counter()
                for start_index, ordinal in enumerate(ordinals):
                    if float(spec.get("start_rate", 0)) > 0:
                        time.sleep(max(0, start_origin + start_index / float(spec["start_rate"]) - time.perf_counter()))
                    (lifecycle / f"connection-{ordinal}.start").write_text("start\n", encoding="ascii")
                if spec["kind"] == "connections":
                    wait_paths([lifecycle / f"connection-{ordinal}.connected" for ordinal in ordinals], [server, *clients], 60)
                    capture(resources, server, clients, phase="active", cycle=cycle_index, seconds=active_seconds, cadence=cadence, **capture_options)
                    pending = set(ordinals)
                    while pending:
                        ordinal = wait_active_ordinal(lifecycle, pending, [server, *clients], 60)
                        (lifecycle / f"connection-{ordinal}.release").write_text("release\n", encoding="ascii")
                        wait_paths([lifecycle / f"connection-{ordinal}.ack"], [server, *clients], 60)
                        pending.remove(ordinal)
                    continue
                wait_paths([lifecycle / f"connection-{ordinal}.active" for ordinal in ordinals], [server, *clients], 60)
                if materialized:
                    snapshots = wait_json_paths(
                        [lifecycle / f"destination-{ordinal}.active" for ordinal in ordinals],
                        [server, *clients], 120)
                    for ordinal, snapshot in zip(ordinals, snapshots, strict=True):
                        write_json(cell_dir / f"destination-{ordinal}.active.json", snapshot)
                capture(resources, server, clients, phase="active", cycle=cycle_index, seconds=active_seconds, cadence=cadence, **capture_options)
                for ordinal in ordinals:
                    (lifecycle / f"connection-{ordinal}.release").write_text("release\n", encoding="ascii")
                wait_paths([lifecycle / f"connection-{ordinal}.ack" for ordinal in ordinals], [server, *clients], 60)
            final_cycle = int(spec.get("cycle_index", rounds - 1))
            report_phase = capture_final_cooldown(resources, server, clients, lifecycle,
                                                  cycle=final_cycle, seconds=cooldown_seconds,
                                                  cadence=cadence, report_gate=report_gate,
                                                  **(dict(capture_options, allow_exited_sources=True)
                                                     if capture_backend is not None and sessions > 1 else capture_options))
            if path == "rust-rust":
                (lifecycle / "source.final-release").write_text("release\n", encoding="ascii")
            outputs = []
            for index, client in enumerate(clients):
                if capture_backend is None or sessions <= 1:
                    client.wait(timeout=30)
                if client.returncode:
                    raise RuntimeError((cell_dir / f"source-{index}.stderr").read_text())
                stdout = (cell_dir / f"source-{index}.stdout").read_text()
                outputs.extend(json.loads(line) for line in stdout.splitlines() if line.strip())
            for _, ordinal, _ in client_specs:
                runtime_path = temporary_root / f"go-runtime-{ordinal}.ndjson"
                if runtime_path.is_file():
                    (cell_dir / f"go-runtime-{ordinal}.ndjson").write_bytes(runtime_path.read_bytes())
            server.wait(timeout=30)
            if server.returncode:
                raise RuntimeError((cell_dir / "destination.stderr").read_text())
            if report_phase is not None:
                report_phase["ended_unix_ns"] = time.time_ns()
                write_json(cell_dir / "report-phase.json", report_phase)
        except Exception as error:
            snapshot = getattr(capture_backend, "failure_snapshot", None)
            if snapshot is not None:
                try:
                    observed = snapshot({"destination": server, **{f"source-{i}": p for i, p in enumerate(clients)}})
                except Exception as diagnostic_error:
                    observed = {"status": "UNAVAILABLE", "error_type": type(diagnostic_error).__name__}
                write_json(cell_dir / "linux-udp-failure.json", observed)
            details = []
            for label, process in [("destination", server), *[(f"source-{index}", client) for index, client in enumerate(clients)]]:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                details.append(f"{label}: {(cell_dir / f'{label}.stderr').read_text()}")
            write_json(cell_dir / "failure-markers.json", snapshot_markers(lifecycle))
            details.append(f"lifecycle_files: {sorted(item.name for item in lifecycle.iterdir())}")
            details.append(f"commands: {commands}")
            failure_detail = "\n".join(details)
            write_json(cell_dir / "failure.json", {"error": str(error), "detail": failure_detail, "samples": resources})
            raise RuntimeError(f"{error}\n{failure_detail}") from error
        finally:
            for process in [*clients, server]:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        diagnostic_records = [json.loads(line) for line in diagnostics.read_text(encoding="utf-8").splitlines()]
        final = diagnostic_records[-1]
        cleanup = ownership_cleanup(path, final, outputs, source_count=len(clients),
                                    cycles=cycles if spec["kind"] == "cycles" else None)
        cleanup.update(source_processes_exited=all(client.poll() is not None for client in clients),
                       destination_exited=server.poll() is not None)
        cell = {**spec, "active_count": int(spec["active_count"]), "samples": resources, "cleanup": cleanup, "commands": {"server": public_command(server_argv, temporary_root), "clients": [public_command(command, temporary_root) for command in commands]}, "client_results": outputs}
        if allocator_snapshots:
            from scripts.performance.b3_allocator_snapshot import parse_snapshot
            expected = {f'allocator-{i}.xml' for i in range(cycles + 1)}
            if {p.name for p in allocator_root.iterdir()} != expected:
                raise ValueError('allocator snapshot inventory incomplete')
            cell['source_allocator'] = [dict(ordinal=i,
                phase='lifecycle_entry' if i == 0 else 'post_close_before_cooldown',
                **parse_snapshot((allocator_root / f'allocator-{i}.xml').read_bytes()))
                for i in range(cycles + 1)]
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
