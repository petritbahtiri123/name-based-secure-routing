from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority
from scripts.performance.wire_overhead import UdpFlowCounter, analyze_pairs
from scripts.run_p2a_established import build, summarize_resources
from scripts.run_performance_validation import environment, measured_client, wait_ready

ROOT = Path(__file__).resolve().parents[1]


def workload_cells(*, smoke: bool) -> list[dict[str, int]]:
    if smoke:
        return [{"payload_bytes": 1024, "streams": 1, "operations_per_stream": 10}]
    return [
        {"payload_bytes": 1024, "streams": 64, "operations_per_stream": 10_000},
        {"payload_bytes": 16_384, "streams": 8, "operations_per_stream": 10_000},
    ]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def failure_record(
    *,
    path: str,
    cell: dict[str, int],
    repeat: int,
    warmup_seconds: float,
    error: Exception,
) -> dict[str, Any]:
    expected = cell["streams"] * cell["operations_per_stream"]
    return {
        "schema": "nbsr-b1-wire-overhead-repeat-v1",
        "status": "invalid",
        "path": path,
        "repeat": repeat,
        "payload_bytes": cell["payload_bytes"],
        "streams": cell["streams"],
        "operations_per_stream": cell["operations_per_stream"],
        "expected_operations": expected,
        "completed_operations": 0,
        "errors": 1,
        "timeouts": int(isinstance(error, (TimeoutError, subprocess.TimeoutExpired))),
        "warmup_seconds": warmup_seconds,
        "failure": f"{type(error).__name__}: {error}",
    }


def _run_repeat(
    *,
    path: str,
    cell: dict[str, int],
    repeat: int,
    binaries: dict[str, Path],
    authority: Path,
    warmup_seconds: float,
    raw_dir: Path,
) -> dict[str, Any]:
    stem = f"{path}-p{cell['payload_bytes']}-s{cell['streams']}-r{repeat}"
    ready = raw_dir / f"{stem}.ready.json"
    result = raw_dir / f"{stem}.result.json"
    ack = raw_dir / f"{stem}.ack"
    for marker in (ready, result, ack):
        marker.unlink(missing_ok=True)
    if path == "direct":
        server_argv = [
            str(binaries["direct"]), "--role", "server", "--ready", str(ready),
            "--authority-dir", str(authority), "--connections", "1",
            "--requests-per-connection", "1", "--p2a-streams", str(cell["streams"]),
        ]
        server_env = os.environ.copy()
    else:
        server_argv = [
            str(binaries["server"]), "--ready", str(ready), "--result", str(result),
            "--authority-dir", str(authority), "--completion-ack", str(ack),
        ]
        server_env = {**os.environ, "NBSR_P2A_STREAMS": str(cell["streams"])}
    server = subprocess.Popen(
        server_argv,
        cwd=ROOT,
        env=server_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    counter: UdpFlowCounter | None = None
    try:
        server_endpoint = wait_ready(ready, server)["endpoint"]
        host, port = server_endpoint.rsplit(":", 1)
        counter = UdpFlowCounter((host, int(port)))
        counter.start()
        relay = f"{counter.relay_endpoint[0]}:{counter.relay_endpoint[1]}"
        control = f"{counter.control_endpoint[0]}:{counter.control_endpoint[1]}"
        common = [
            "--authority-dir", str(authority), "--endpoint", relay,
            "--payload-bytes", str(cell["payload_bytes"]), "--p2a-streams", str(cell["streams"]),
            "--p2a-warmup-seconds", str(warmup_seconds),
            "--p2a-operations-per-stream", str(cell["operations_per_stream"]),
            "--p2a-counter-control", control,
        ]
        client_argv = (
            [str(binaries["direct"]), "--role", "client", "--samples", "1", "--lifecycle", "warm", *common]
            if path == "direct"
            else [str(binaries["nbsr"]), "--samples", "1", *common]
        )
        stdout, resources = measured_client(
            client_argv,
            cwd=ROOT,
            server=server,
            timeout=600,
            client_started=counter.authorize_client_process,
        )
        record = json.loads(stdout.strip().splitlines()[-1])
        server.wait(timeout=60)
        if server.returncode:
            raise RuntimeError(server.stderr.read() if server.stderr else "server failed")
        capture = counter.result()
        completed = int(record["completed_operations"])
        expected = cell["streams"] * cell["operations_per_stream"]
        if completed != expected:
            raise RuntimeError(f"completed operations {completed} != expected {expected}")
        measured_seconds = int(record["measured_ns"]) / 1e9
        record.update(
            {
                "schema": "nbsr-b1-wire-overhead-repeat-v1",
                "repeat": repeat,
                "operations_per_stream": cell["operations_per_stream"],
                "expected_operations": expected,
                "warmup_seconds": warmup_seconds,
                "benchmark_build": "cargo release with benchmark-harness feature",
                "phase_semantics": "setup then excluded warmup then established fixed operations without teardown",
                "timeouts": 0,
                "application_bytes": completed * cell["payload_bytes"] * 2,
                "application_bytes_definition": "aggregate request plus response payload bytes",
                "capture_method": capture["capture_method"],
                "measured_unit": capture["measured_unit"],
                "client_ownership": capture["client_ownership"],
                "setup": capture["phases"]["setup"],
                "established": capture["phases"]["established"],
                "rejected_datagrams": capture["rejected_datagrams"],
                "server_endpoint": capture["server_endpoint"],
                "relay_endpoint": capture["relay_endpoint"],
                "resources": summarize_resources(resources, completed, measured_seconds),
                "client_command": client_argv,
                "server_command": server_argv,
            }
        )
        if record["rejected_datagrams"]:
            raise RuntimeError("isolated relay rejected contaminating datagrams")
        return record
    finally:
        if counter is not None:
            counter.close()
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)


def _render_summary(analysis: dict[str, Any], env: dict[str, Any], command_line: str) -> str:
    rows = []
    for cell in analysis["cells"]:
        representative = cell["representative_pair"]
        if representative is None:
            rows.append(
                f"| {cell['payload_bytes']} | {cell['streams']} | 0 | no valid pair | no valid pair | "
                f"0 | 0 | no valid pair | no valid pair | {cell['stability']} |"
            )
            continue
        rows.append(
            "| {payload} | {streams} | {pairs} | {direct:.0f} | {nbsr:.0f} | {dp:.0f} | {np:.0f} | {delta:.0f} | {overhead:.4f}% | {stability} |".format(
                payload=cell["payload_bytes"], streams=cell["streams"], pairs=cell["valid_pairs"],
                direct=representative["direct_measured_udp_payload_bytes"],
                nbsr=representative["nbsr_measured_udp_payload_bytes"],
                dp=cell["median_direct_packets"], np=cell["median_nbsr_packets"],
                delta=representative["incremental_bytes"],
                overhead=representative["incremental_overhead_percent"], stability=cell["stability"],
            )
        )
    setup = []
    for cell in analysis["cells"]:
        if not cell["valid_pairs"]:
            setup.append(
                f"- {cell['payload_bytes']} B / {cell['streams']} streams: no valid Direct/NBSR pair."
            )
            continue
        setup.append(
            f"- {cell['payload_bytes']} B / {cell['streams']} streams: Direct {cell['median_direct_setup_udp_payload_bytes']:.0f} bytes, "
            f"NBSR {cell['median_nbsr_setup_udp_payload_bytes']:.0f} bytes, delta {cell['median_setup_incremental_bytes']:.0f} bytes "
            f"({cell['median_setup_incremental_overhead_percent']:.2f}%)."
        )
    return "\n".join(
        [
            "# B1 Direct-vs-NBSR Wire Overhead",
            "",
            f"Classification: **{analysis['classification']}**",
            "",
            "## Measurement method",
            "",
            "MEASURED: UDP payload bytes and UDP datagrams forwarded by a single-flow loopback relay. The relay binds a fresh loopback endpoint per run and admits a source endpoint only when OS UDP ownership identifies the authorized benchmark client PID; rejected datagrams invalidate a run.",
            "",
            "DERIVED: IPv4+UDP network bytes add 28 bytes per measured datagram. Physical Ethernet framing, preamble, inter-packet gap, and FCS are not present on Windows loopback and are not reported as measured.",
            "",
            "Retransmissions are NOT MEASURABLE with the available non-privileged instrumentation. Windows pktmon was present but access was denied.",
            "",
            "Application bytes mean aggregate request plus response payload bytes; one echo operation carries two payloads.",
            "",
            "| Payload | Streams | Valid pairs | Representative Direct measured UDP bytes | Representative NBSR measured UDP bytes | Median Direct packets | Median NBSR packets | Paired incremental bytes | Paired incremental overhead | Stability |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
            *rows,
            "",
            "## Setup/admission",
            "",
            *setup,
            "",
            "Warm-up traffic is excluded. Established counters begin only after an acknowledged measurement-start marker and stop after all fixed-count operations complete.",
            "",
            "## Previous estimate comparison",
            "",
            "The earlier approximate 6.45–8.59% values modeled total framing/transport overhead. They were not measured incremental NBSR tax and are not directly comparable to this Direct-vs-NBSR delta.",
            "",
            "## Environment",
            "",
            f"- Base Git SHA: `{env['repository_sha']}`",
            f"- OS: {env['os']}",
            f"- CPU: {env['cpu']}",
            f"- RAM bytes: {env['memory_bytes']}",
            f"- Command: `{command_line}`",
            "",
        ]
    )


def _write_checksums(root: Path) -> None:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"checksums.sha256", ".gitattributes"}
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
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup-seconds", type=float, default=3.0)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--analyze-existing", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1 or args.warmup_seconds <= 0:
        raise SystemExit("positive repeats and warm-up are required")
    command_line = shlex.join(sys.argv)
    if args.analyze_existing:
        env = json.loads((args.output / "environment.json").read_text(encoding="utf-8"))
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((args.output / "raw").glob("*.json"))
            if path.name.startswith(("direct-p", "nbsr-p"))
            and ".ready." not in path.name
            and ".result." not in path.name
        ]
        analysis = analyze_pairs(records)
        analysis["environment_path"] = "environment.json"
        analysis["valid_repeats"] = sum(cell["valid_pairs"] * 2 for cell in analysis["cells"])
        analysis["invalid_repeats"] = len(analysis["invalid_pairs"])
        _write_json(args.output / "analysis.json", analysis)
        original_command = (args.output / "commands.txt").read_text(encoding="utf-8").splitlines()[0]
        (args.output / "summary.md").write_text(
            _render_summary(analysis, env, original_command), encoding="utf-8", newline="\n"
        )
        with (args.output / "commands.txt").open("a", encoding="utf-8", newline="\n") as commands:
            commands.write(command_line + "\n")
        _write_checksums(args.output)
        print(json.dumps({"classification": analysis["classification"], "cells": len(analysis["cells"]), "records": len(records)}))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    _write_evidence_attributes(args.output)
    raw_dir = args.output / "raw"
    raw_dir.mkdir()
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b1-wire-overhead\cargo-target"))
    binaries = build(target)
    allowed_root = args.output if args.output.resolve().is_relative_to(ROOT.resolve()) else None
    env = environment(allowed_dirty_root=allowed_root)
    env.update(
        {
            "branch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "capture_method": "isolated single-flow UDP relay",
            "directly_measured": ["UDP payload bytes", "UDP datagrams"],
            "derived": ["IPv4 plus UDP bytes using 28 bytes per datagram"],
            "unavailable": ["physical L2 bytes", "retransmissions"],
            "benchmark_build": "cargo release with benchmark-harness feature",
            "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()},
        }
    )
    _write_json(args.output / "environment.json", env)
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-b1-") as temp_name:
        authority = Path(temp_name) / "authority"
        write_loopback_authority(authority)
        for cell in workload_cells(smoke=args.smoke):
            for repeat in range(1, args.repeats + 1):
                paths = ("direct", "nbsr") if repeat % 2 else ("nbsr", "direct")
                for path in paths:
                    try:
                        record = _run_repeat(
                            path=path, cell=cell, repeat=repeat, binaries=binaries, authority=authority,
                            warmup_seconds=args.warmup_seconds, raw_dir=raw_dir,
                        )
                    except Exception as error:  # Preserve every invalid repeat before continuing.
                        record = failure_record(
                            path=path,
                            cell=cell,
                            repeat=repeat,
                            warmup_seconds=args.warmup_seconds,
                            error=error,
                        )
                    records.append(record)
                    _write_json(raw_dir / f"{path}-p{cell['payload_bytes']}-s{cell['streams']}-r{repeat}.json", record)
    analysis = analyze_pairs(records)
    analysis["environment_path"] = "environment.json"
    analysis["valid_repeats"] = sum(cell["valid_pairs"] * 2 for cell in analysis["cells"])
    analysis["invalid_repeats"] = len(analysis["invalid_pairs"])
    _write_json(args.output / "analysis.json", analysis)
    (args.output / "summary.md").write_text(_render_summary(analysis, env, command_line), encoding="utf-8", newline="\n")
    (args.output / "commands.txt").write_text(command_line + "\n", encoding="utf-8", newline="\n")
    _write_checksums(args.output)
    print(json.dumps({"classification": analysis["classification"], "cells": len(analysis["cells"]), "records": len(records)}))


if __name__ == "__main__":
    main()
