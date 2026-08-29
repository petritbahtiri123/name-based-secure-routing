from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority
from scripts.performance.mixed_workload import analyze_mixed_records, scheduled_admission_count, workload_cells
from scripts.run_p2a_established import build, summarize_resources
from scripts.run_performance_validation import environment, measured_client, wait_ready


ROOT = Path(__file__).resolve().parents[1]
B4_SOURCE_PATHS = (
    "crates/nbsr-transport/src/bin/b4_support/mod.rs",
    "crates/nbsr-transport/src/bin/perf_rust_source.rs",
    "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    "scripts/performance/mixed_workload.py",
    "scripts/run_b4_mixed_workload.py",
    "tests/performance/test_mixed_workload.py",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def capture_capability() -> dict[str, Any]:
    dumpcap = Path(r"C:\Program Files\Wireshark\dumpcap.exe")
    tshark = Path(r"C:\Program Files\Wireshark\tshark.exe")
    if not dumpcap.is_file() or not tshark.is_file():
        return {"available": False, "reason": "dumpcap/tshark not installed at the repository-approved path"}
    dumpcap_version = subprocess.run([str(dumpcap), "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    tshark_version = subprocess.run([str(tshark), "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    interfaces = subprocess.run([str(dumpcap), "-D"], capture_output=True, text=True, check=True).stdout.splitlines()
    loopback = r"\Device\NPF_Loopback"
    return {
        "available": any(loopback in interface for interface in interfaces),
        "dumpcap": str(dumpcap),
        "dumpcap_version": dumpcap_version,
        "tshark": str(tshark),
        "tshark_version": tshark_version,
        "interface": loopback,
        "interfaces": interfaces,
        "b4_use": "capability verified but not enabled for headline runs; encrypted packet capture adds observer overhead while benchmark-native counters provide the required B4 metrics",
        "b1_follow_up": "suitable for a separately approved targeted packet-level rerun with fixed-port BPF isolation and dump-drop validation",
    }


def source_identity() -> dict[str, Any]:
    return {
        "base_git_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "files_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in B4_SOURCE_PATHS
        },
    }


def _run_repeat(
    *,
    cell: dict[str, float | int],
    repeat: int,
    binaries: dict[str, Path],
    authority: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    rate = float(cell["admission_rate_per_second"])
    duration = float(cell["duration_seconds"])
    streams = int(cell["streams"])
    payload = int(cell["payload_bytes"])
    admissions = scheduled_admission_count(rate, duration)
    stem = f"nbsr-s{streams}-p{payload}-a{rate:g}-r{repeat}"
    ready = raw_dir / f"{stem}.ready.json"
    result = raw_dir / f"{stem}.result.json"
    ack = raw_dir / f"{stem}.ack"
    server_argv = [
        str(binaries["server"]),
        "--ready",
        str(ready),
        "--result",
        str(result),
        "--authority-dir",
        str(authority),
        "--completion-ack",
        str(ack),
    ]
    server = subprocess.Popen(
        server_argv,
        cwd=ROOT,
        env={
            **os.environ,
            "NBSR_P2A_STREAMS": str(streams),
            "NBSR_B4_ADMISSIONS": str(admissions),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        client_argv = [
            str(binaries["nbsr"]),
            "--authority-dir",
            str(authority),
            "--endpoint",
            endpoint,
            "--samples",
            "1",
            "--payload-bytes",
            str(payload),
            "--p2a-streams",
            str(streams),
            "--p2a-warmup-seconds",
            "1",
            "--p2a-duration-seconds",
            str(duration),
            "--b4-admission-rate",
            str(rate),
        ]
        try:
            stdout, resources = measured_client(
                client_argv,
                cwd=ROOT,
                server=server,
                timeout=int(duration + 90),
                sampling_interval_seconds=0.5,
            )
        except Exception as client_error:
            server.wait(timeout=10)
            server_error = server.stderr.read() if server.stderr else ""
            raise RuntimeError(f"client failure: {client_error}\nserver failure: {server_error}") from client_error
        record = json.loads(stdout.strip().splitlines()[-1])
        server.wait(timeout=30)
        if server.returncode:
            raise RuntimeError(server.stderr.read() if server.stderr else "mixed server failed")
        server_result = json.loads(result.read_text(encoding="utf-8"))
        measured_seconds = int(record["measured_ns"]) / 1e9
        completed = int(record["completed_operations"])
        record.update(
            {
                "schema": "nbsr-b4-mixed-repeat-v1",
                "repeat": repeat,
                "duration_seconds": duration,
                "admission_rate_per_second": rate,
                "admission_scope": "new application-stream admissions on the established authorized route",
                "admission_concurrency": 1,
                "scheduled_admissions": admissions,
                "successful_admissions": int(record["successful_admissions"]),
                "failed_admissions": max(
                    int(record["failed_admissions"]), int(server_result.get("rejected_admissions", 0))
                ),
                "client_failed_admissions": int(record["failed_admissions"]),
                "server_rejected_admissions": int(server_result.get("rejected_admissions", 0)),
                "timeouts": int(record["admission_timeouts"]),
                "errors": int(record["errors"]),
                "established_goodput_bytes_per_second": 2 * completed * payload / measured_seconds,
                "established_goodput_gbps": 16 * completed * payload / measured_seconds / 1e9,
                "achieved_admissions_per_second": int(record["successful_admissions"]) / duration,
                "resources": summarize_resources(resources, completed, measured_seconds),
                "resource_samples": resources,
                "server_result": server_result,
                "client_command": client_argv,
                "server_command": server_argv,
            }
        )
        return record
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)


def _render_summary(analysis: dict[str, Any], env: dict[str, Any], command: str) -> str:
    rows = []
    for cell in analysis["cells"]:
        rows.append(
            "| {rate:g} | {repeats} | {goodput:.3f} | {ratio:.3f} | {p99:.0f} | {p99ratio:.3f} | {admitted:.0f}/{scheduled:.0f} | {failed} | {timeouts} | {status} |".format(
                rate=cell["admission_rate_per_second"],
                repeats=cell["valid_repeats"],
                goodput=cell["median_established_goodput_bytes_per_second"] * 8 / 1e9,
                ratio=cell["median_goodput_ratio_to_baseline"],
                p99=cell["median_p99_latency_ns"],
                p99ratio=cell["median_p99_ratio_to_baseline"],
                admitted=cell["median_successful_admissions"],
                scheduled=cell["median_scheduled_admissions"],
                failed=cell["failed_admissions"],
                timeouts=cell["timeouts"],
                status=cell["status"],
            )
        )
    saturation = analysis["first_saturation"]
    saturation_text = "No saturation point was observed in the bounded sweep." if saturation is None else (
        f"First observed saturation: {saturation['admission_rate_per_second']:g} admissions/s — {saturation['reason']}."
    )
    resources = [
        "- {rate:g} admissions/s: {cpu:.2f} median aggregate CPU-seconds over the sampled process lifetimes, {rss:.1f} MiB summed peak working set, {private:.1f} MiB summed peak private bytes, {late:.3f} ms median maximum scheduling lateness.".format(
            rate=cell["admission_rate_per_second"],
            cpu=cell["median_total_cpu_seconds"],
            rss=cell["median_peak_working_set_bytes"] / 1_048_576,
            private=cell["median_peak_private_bytes"] / 1_048_576,
            late=cell["median_max_admission_start_lateness_ns"] / 1e6,
        )
        for cell in analysis["cells"]
    ]
    return "\n".join(
        [
            "# B4 Mixed Workload",
            "",
            f"Classification: **{analysis['classification']}**",
            "",
            "Established NBSR application streams and newly admitted application streams share one authenticated connection, route, control stream, destination runtime, and process. Admissions are paced serially because the frozen control-session state machine is single-owner.",
            "",
            "| Offered admissions/s | Repeats | Established Gbit/s | Goodput/baseline | Established p99 ns | p99/baseline | Successful/scheduled | Failures | Timeouts | Status |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
            *rows,
            "",
            saturation_text,
            "",
            "## Resources and backpressure",
            "",
            *resources,
            "",
            "Per-role CPU, working-set, private-byte, and thread samples are stored in each raw record. Maximum admission scheduling lateness is the available backpressure signal.",
            "",
            "Limitation: this validates application-stream admission on an existing authorized route. It does not prove concurrent new transport connections or new route admissions; that requires a broader benchmark-only multi-connection server mode and remains external B4 closure work.",
            "",
            f"Base Git SHA: `{env['repository_sha']}`",
            f"Host: {env['os']} / {env['cpu']}",
            f"Command: `{command}`",
            "",
        ]
    )


def _write_checksums(root: Path) -> None:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "checksums.sha256"
    )
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}" for path in paths]
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_evidence_attributes(root: Path) -> None:
    (root / ".gitattributes").write_text(
        "*.txt text eol=lf\n*.sha256 text eol=lf\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--admission-rates")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--analyze-existing", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("repeats must be positive")
    command = shlex.join(sys.argv)
    if args.analyze_existing:
        env = json.loads((args.output / "environment.json").read_text(encoding="utf-8"))
        records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((args.output / "raw").glob("p*.json"))]
        analysis = analyze_mixed_records(records)
        _write_json(args.output / "analysis.json", analysis)
        original_command = (args.output / "commands.txt").read_text(encoding="utf-8").splitlines()[0]
        (args.output / "summary.md").write_text(_render_summary(analysis, env, original_command), encoding="utf-8", newline="\n")
        with (args.output / "commands.txt").open("a", encoding="utf-8", newline="\n") as commands:
            commands.write(command + "\n")
        _write_checksums(args.output)
        print(json.dumps({"classification": analysis["classification"], "records": len(records)}))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    _write_evidence_attributes(args.output)
    raw_dir = args.output / "raw"
    raw_dir.mkdir()
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b4-mixed\cargo-target"))
    binaries = build(target)
    allowed_root = args.output if args.output.resolve().is_relative_to(ROOT.resolve()) else None
    env = environment(allowed_dirty_root=allowed_root)
    env.update(
        {
            "branch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "benchmark_build": "cargo release with benchmark-harness feature",
            "capture_capability_path": "capture-capability.json",
            "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()},
            "source_identity": source_identity(),
        }
    )
    _write_json(args.output / "environment.json", env)
    _write_json(args.output / "capture-capability.json", capture_capability())
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-b4-") as temp_name:
        authority = Path(temp_name) / "authority"
        write_loopback_authority(authority)
        cells = workload_cells(smoke=args.smoke)
        if args.admission_rates is not None:
            rates = [float(value) for value in args.admission_rates.split(",")]
            if not rates or any(rate < 0 for rate in rates):
                raise SystemExit("admission rates must be non-negative")
            duration = args.duration_seconds or float(cells[0]["duration_seconds"])
            cells = [{**cells[0], "duration_seconds": duration, "admission_rate_per_second": rate} for rate in rates]
        planned_rates = [float(cell["admission_rate_per_second"]) for cell in cells]
        for cell in cells:
            for repeat in range(1, args.repeats + 1):
                try:
                    record = _run_repeat(
                        cell=cell,
                        repeat=repeat,
                        binaries=binaries,
                        authority=authority,
                        raw_dir=raw_dir,
                    )
                    record["planned_admission_rates"] = planned_rates
                except Exception as error:
                    record = {
                        "schema": "nbsr-b4-mixed-repeat-v1",
                        **cell,
                        "repeat": repeat,
                        "planned_admission_rates": planned_rates,
                        "errors": 1,
                        "timeouts": int(isinstance(error, (TimeoutError, subprocess.TimeoutExpired))),
                        "failure": f"{type(error).__name__}: {error}",
                    }
                records.append(record)
                _write_json(raw_dir / f"p{cell['payload_bytes']}-s{cell['streams']}-a{cell['admission_rate_per_second']:g}-r{repeat}.json", record)
    analysis = analyze_mixed_records(records)
    _write_json(args.output / "analysis.json", analysis)
    (args.output / "summary.md").write_text(_render_summary(analysis, env, command), encoding="utf-8", newline="\n")
    (args.output / "commands.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
    _write_checksums(args.output)
    print(json.dumps({"classification": analysis["classification"], "records": len(records)}))


if __name__ == "__main__":
    main()
