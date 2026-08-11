from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority
from scripts.performance.p2d_stream_credit import (
    CONCURRENCIES,
    OUTCOME_ACCEPTED,
    evaluate_acceptance,
    nearest_rank_percentile,
    select_saturation_concurrency,
    should_stop_after_three,
    summarize_pairs,
    validate_continuity,
    validate_live_cell,
    validate_matched_pair,
)
from scripts.run_performance_validation import measured_client, wait_ready

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "crates" / "nbsr-transport"
SHARD_OPERATIONS = 8_000
PAYLOAD_BYTES = 1_024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def source_binding() -> dict[str, Any]:
    paths = (
        "crates/nbsr-transport/src/stream_credit.rs",
        "crates/nbsr-transport/src/session.rs",
        "crates/nbsr-transport/src/quinn_adapter.rs",
        "crates/nbsr-transport/src/bin/perf_rust_source.rs",
        "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
        "scripts/performance/p2d_stream_credit.py",
        "scripts/run_p2d_stream_credit.py",
        "docs/protocol/stream-credit-extension.md",
    )
    files = {path: sha256(ROOT / path) for path in paths}
    digest = hashlib.sha256()
    for path, value in files.items():
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(value.encode())
        digest.update(b"\n")
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain=v1", "--untracked-files=all")),
        "measured_source_sha256": digest.hexdigest(),
        "files": files,
    }


def environment_binding() -> dict[str, Any]:
    return {
        "host": platform.node(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "logical_processors": os.cpu_count(),
        "timer": "rust-std-instant-qpc" if os.name == "nt" else "rust-std-instant",
        "loopback_only": True,
    }


def build(target: Path) -> tuple[dict[str, Path], dict[str, Any]]:
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    command = [
        "cargo",
        "build",
        "--release",
        "--manifest-path",
        str(TRANSPORT / "Cargo.toml"),
        "--features",
        "benchmark-harness",
        "--bin",
        "perf_rust_source",
        "--bin",
        "wp8_interop_server",
    ]
    started = time.monotonic()
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=900
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    suffix = ".exe" if os.name == "nt" else ""
    binaries = {
        "source": target / "release" / f"perf_rust_source{suffix}",
        "server": target / "release" / f"wp8_interop_server{suffix}",
    }
    return binaries, {
        "profile": "release",
        "features": ["benchmark-harness"],
        "cargo_command": command,
        "build_seconds": time.monotonic() - started,
        "binaries": {name: sha256(path) for name, path in binaries.items()},
    }


def reset(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def process_resources(samples: list[dict[str, Any]]) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    all_measured = True
    total_cpu_ns = 0
    for role in ("source", "destination"):
        values = sorted(
            (sample for sample in samples if sample["role"] == role),
            key=lambda sample: sample["timestamp_ns"],
        )
        if len(values) < 2:
            all_measured = False
            roles[role] = {"status": "UNAVAILABLE", "sample_count": len(values)}
            continue
        cpu_ns = (
            values[-1]["user_cpu_ns"]
            + values[-1]["kernel_cpu_ns"]
            - values[0]["user_cpu_ns"]
            - values[0]["kernel_cpu_ns"]
        )
        total_cpu_ns += cpu_ns
        roles[role] = {
            "status": "MEASURED",
            "sample_count": len(values),
            "process_cpu_ns": cpu_ns,
            "peak_working_set_bytes": max(value["peak_working_set_bytes"] for value in values),
            "peak_private_bytes": max(value["private_bytes"] for value in values),
            "peak_threads": max(value["thread_count"] for value in values),
        }
    return {
        "status": "MEASURED" if all_measured else "UNAVAILABLE",
        "process_cpu_ns": total_cpu_ns if all_measured else None,
        "roles": roles,
    }


def parse_source(stdout: str) -> dict[str, Any]:
    records = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    matches = [record for record in records if record.get("event") == "p2d_shard"]
    if len(matches) != 1:
        raise RuntimeError(f"expected one P2D shard result, observed {len(matches)}")
    return matches[0]


def run_shard(
    *,
    mode: str,
    operations: int,
    concurrency: int,
    smoke_exhaustion: bool,
    binaries: dict[str, Path],
    authority: Path,
    temporary: Path,
    ordinal: int,
) -> dict[str, Any]:
    prefix = f"{mode}-c{concurrency}-s{ordinal}"
    ready = temporary / f"{prefix}.ready.json"
    result = temporary / f"{prefix}.result.json"
    ack = temporary / f"{prefix}.ack"
    reset(ready, result, ack)
    server_env = {
        **os.environ,
        "NBSR_P2D_MODE": mode,
        "NBSR_P2D_OPERATIONS": str(operations),
        "NBSR_P2D_CONCURRENCY": str(concurrency),
    }
    if smoke_exhaustion:
        server_env["NBSR_P2D_SMOKE_EXHAUSTION"] = "1"
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
        env=server_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        endpoint = wait_ready(ready, server)["endpoint"]
        client = [
            str(binaries["source"]),
            "--authority-dir",
            str(authority),
            "--endpoint",
            endpoint,
            "--samples",
            str(operations),
            "--payload-bytes",
            str(PAYLOAD_BYTES),
            "--p2d-mode",
            mode,
            "--p2d-concurrency",
            str(concurrency),
        ]
        if smoke_exhaustion:
            client.extend(["--p2d-smoke-exhaustion", "1"])
        try:
            stdout, samples = measured_client(
                client,
                cwd=ROOT,
                server=server,
                timeout=180,
                sampling_interval_seconds=0.02,
            )
        except BaseException as error:
            if server.poll() is None:
                server.wait(timeout=5)
            destination_stderr = server.stderr.read() if server.stderr else ""
            raise RuntimeError(
                f"P2D {mode} shard {ordinal} client failed: {error}\n"
                f"destination exit={server.returncode}\n{destination_stderr}"
            ) from error
        ack.touch()
        server.wait(timeout=30)
        server_stderr = server.stderr.read() if server.stderr else ""
        if server.returncode:
            raise RuntimeError(server_stderr)
        source = parse_source(stdout)
        destination = json.loads(result.read_text(encoding="utf-8"))
        for side, value in (("source", source), ("destination", destination)):
            if value["mode"] != mode:
                raise RuntimeError(f"{side} mode mismatch")
            if value["completed_operations"] != operations:
                raise RuntimeError(f"{side} operation loss")
            if value["payload_correct"] is not True or value["errors"] != 0:
                raise RuntimeError(f"{side} payload/error gate failed")
        for field in (
            "refill_count",
            "active_epochs",
            "active_epochs_high_water",
            "replay_entries",
            "replay_limit",
            "minimum_remaining_credits",
            "buffer_exhaustions",
        ):
            if source[field] != destination[field]:
                raise RuntimeError(f"source/destination {field} mismatch")
        return {
            "ordinal": ordinal,
            "source": source,
            "destination": destination,
            "resources": process_resources(samples),
        }
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)


def run_cell(
    *,
    mode: str,
    concurrency: int,
    binaries: dict[str, Path],
    authority: Path,
    temporary: Path,
    environment: dict[str, Any],
    build_binding: dict[str, Any],
    source: dict[str, Any],
    duration_seconds: int | None = None,
    operations: int | None = None,
    smoke_exhaustion: bool = False,
) -> dict[str, Any]:
    if (duration_seconds is None) == (operations is None):
        raise ValueError("choose exactly one of duration_seconds or operations")
    shards: list[dict[str, Any]] = []
    measured_ns = 0
    remaining_operations = operations
    while (
        measured_ns < (duration_seconds or 0) * 1_000_000_000
        if duration_seconds is not None
        else remaining_operations is not None and remaining_operations > 0
    ):
        shard_operations = (
            SHARD_OPERATIONS
            if duration_seconds is not None
            else min(SHARD_OPERATIONS, remaining_operations or 0)
        )
        shard = run_shard(
            mode=mode,
            operations=shard_operations,
            concurrency=concurrency,
            smoke_exhaustion=smoke_exhaustion,
            binaries=binaries,
            authority=authority,
            temporary=temporary,
            ordinal=len(shards) + 1,
        )
        shards.append(shard)
        measured_ns += int(shard["source"]["duration_ns"])
        if remaining_operations is not None:
            remaining_operations -= shard_operations
    latencies = [
        int(latency)
        for shard in shards
        for latency in shard["source"]["latencies_ns"]
    ]
    completed = sum(int(shard["source"]["completed_operations"]) for shard in shards)
    measured_cpu = all(shard["resources"]["status"] == "MEASURED" for shard in shards)
    total_cpu_ns = (
        sum(int(shard["resources"]["process_cpu_ns"]) for shard in shards)
        if measured_cpu
        else None
    )
    last = shards[-1]["source"]
    periods = []
    for shard in shards:
        source_shard = shard["source"]
        shard_latencies = source_shard["latencies_ns"]
        periods.append(
            {
                "ordinal": shard["ordinal"],
                "completed_operations": source_shard["completed_operations"],
                "duration_ns": source_shard["duration_ns"],
                "operations_per_second": source_shard["completed_operations"]
                / (source_shard["duration_ns"] / 1e9),
                "p99_ns": nearest_rank_percentile(shard_latencies, 99),
                "refill_count": source_shard["refill_count"],
                "remaining_credits": source_shard["remaining_credits"],
                "active_epochs_high_water": source_shard["active_epochs_high_water"],
                "replay_entries": source_shard["replay_entries"],
                "resources": shard["resources"],
            }
        )
    cell = {
        "schema": "nbsr-p2d-live-cell-v1",
        "mode": mode,
        "profile": "legacy-stream-open" if mode == "before" else "nbsr-stream-credit-1",
        "concurrency": concurrency,
        "payload_bytes": PAYLOAD_BYTES,
        "payload_correct": all(
            shard[side]["payload_correct"]
            for shard in shards
            for side in ("source", "destination")
        ),
        "completed_operations": completed,
        "duration_ns": measured_ns,
        "operations_per_second": completed / (measured_ns / 1e9),
        "p50_ns": nearest_rank_percentile(latencies, 50),
        "p95_ns": nearest_rank_percentile(latencies, 95),
        "p99_ns": nearest_rank_percentile(latencies, 99),
        "cpu": {
            "status": "MEASURED" if measured_cpu else "UNAVAILABLE",
            "process_cpu_ns": total_cpu_ns,
            "roles": {
                role: {
                    "peak_working_set_bytes": max(
                        shard["resources"]["roles"].get(role, {}).get(
                            "peak_working_set_bytes", 0
                        )
                        for shard in shards
                    ),
                    "peak_private_bytes": max(
                        shard["resources"]["roles"].get(role, {}).get(
                            "peak_private_bytes", 0
                        )
                        for shard in shards
                    ),
                }
                for role in ("source", "destination")
            },
        },
        "errors": sum(
            int(shard[side]["errors"])
            for shard in shards
            for side in ("source", "destination")
        ),
        "remaining_credits": last["remaining_credits"],
        "refill_count": sum(int(shard["source"]["refill_count"]) for shard in shards),
        "windows_crossed": sum(int(shard["source"]["windows_crossed"]) for shard in shards),
        "active_epochs": last["active_epochs"],
        "active_epochs_high_water": max(
            int(shard["source"]["active_epochs_high_water"]) for shard in shards
        ),
        "replay_entries": max(int(shard["source"]["replay_entries"]) for shard in shards),
        "replay_limit": int(last["replay_limit"]),
        "minimum_remaining_credits": (
            min(
                int(shard["source"]["minimum_remaining_credits"])
                for shard in shards
            )
            if mode == "after"
            else None
        ),
        "buffer_exhaustions": sum(
            int(shard["source"]["buffer_exhaustions"]) for shard in shards
        ),
        "build": build_binding,
        "environment": environment,
        "source": source,
        "periods": periods,
        "shards": shards,
    }
    validate_live_cell(cell)
    return cell


def manifest(
    *,
    mode: str,
    concurrency: int,
    duration_seconds: int,
    environment: dict[str, Any],
    build_binding: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "nbsr-p2d-cell-manifest-v1",
        "mode": mode,
        "profile": "legacy-stream-open" if mode == "before" else "nbsr-stream-credit-1",
        "concurrency": concurrency,
        "payload_bytes": PAYLOAD_BYTES,
        "operation": "new-application-stream-admission-and-echo",
        "transport_session_model": "persistent-per-shard",
        "service_channel_model": "existing-authorized-per-shard",
        "application_stream_model": "new-per-operation",
        "duration_seconds_requested": duration_seconds,
        "max_operations_per_session": SHARD_OPERATIONS,
        "build": build_binding,
        "environment": environment,
        "source": source,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def cell_summary(cell: dict[str, Any]) -> dict[str, Any]:
    excluded = {"shards", "periods", "build", "environment", "source"}
    return {key: value for key, value in cell.items() if key not in excluded}


def package_inputs(output: Path) -> None:
    design = output / "design"
    design.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "docs/protocol/stream-credit-extension.md",
        design / "stream-credit-extension.md",
    )
    shutil.copyfile(
        ROOT / "docs/superpowers/plans/2026-08-11-p2d-stream-credit-window.md",
        design / "implementation-plan.md",
    )
    preface_manifest = ROOT / "vectors/stream-credit-v1/manifest.json"
    write_json(
        output / "wire" / "stream-credit-preface-reference.json",
        {
            "schema": "nbsr-p2d-wire-reference-v1",
            "path": "vectors/stream-credit-v1/manifest.json",
            "sha256": sha256(preface_manifest),
        },
    )
    write_json(
        output / "wire" / "refill-control-v1.json",
        {
            "schema": "nbsr-stream-credit-refill-v1-vectors",
            "body_bytes": 30,
            "framed_bytes": 31,
            "channel_id_hex": "404142434445464748494a4b4c4d4e4f",
            "epoch": 2,
            "request_hex": "1e4e5343520101404142434445464748494a4b4c4d4e4f0000000000000002",
            "grant_hex": "1e4e5343520102404142434445464748494a4b4c4d4e4f0000000000000002",
        },
    )


def run_all(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output
    if output.exists():
        raise FileExistsError(f"immutable evidence output already exists: {output}")
    output.mkdir(parents=True)
    package_inputs(output)
    source = source_binding()
    environment = environment_binding()
    binaries, build_binding = build(args.target)
    write_json(output / "environment.json", environment)
    write_json(output / "build.json", build_binding)
    write_json(output / "source-binding.json", source)

    with tempfile.TemporaryDirectory(prefix="nbsr-p2d-") as temporary_name:
        temporary = Path(temporary_name)
        authority = temporary / "authority"
        write_loopback_authority(authority)

        smoke_before = run_cell(
            mode="before",
            concurrency=64,
            operations=192,
            binaries=binaries,
            authority=authority,
            temporary=temporary,
            environment=environment,
            build_binding=build_binding,
            source=source,
        )
        smoke_after = run_cell(
            mode="after",
            concurrency=64,
            operations=192,
            smoke_exhaustion=True,
            binaries=binaries,
            authority=authority,
            temporary=temporary,
            environment=environment,
            build_binding=build_binding,
            source=source,
        )
        write_json(output / "raw/smoke/before-c64.json", smoke_before)
        write_json(output / "raw/smoke/after-c64.json", smoke_after)
        refill_gate = (
            "PASS"
            if smoke_after["refill_count"] >= 2
            and smoke_after["buffer_exhaustions"] >= 1
            and smoke_after["active_epochs_high_water"] <= 2
            and smoke_after["errors"] == 0
            else "FAIL"
        )

        sweep_before = []
        sweep_after = []
        for concurrency in CONCURRENCIES:
            for mode, target in (("before", sweep_before), ("after", sweep_after)):
                value = run_cell(
                    mode=mode,
                    concurrency=concurrency,
                    operations=args.sweep_operations,
                    binaries=binaries,
                    authority=authority,
                    temporary=temporary,
                    environment=environment,
                    build_binding=build_binding,
                    source=source,
                )
                target.append(value)
                write_json(
                    output / f"raw/sweep/{mode}-c{concurrency}.json", value
                )
        selected = select_saturation_concurrency(sweep_after)

        before_pairs: list[dict[str, Any]] = []
        after_pairs: list[dict[str, Any]] = []
        for repeat in range(1, 6):
            before_manifest = manifest(
                mode="before",
                concurrency=selected,
                duration_seconds=args.pair_seconds,
                environment=environment,
                build_binding=build_binding,
                source=source,
            )
            after_manifest = manifest(
                mode="after",
                concurrency=selected,
                duration_seconds=args.pair_seconds,
                environment=environment,
                build_binding=build_binding,
                source=source,
            )
            validate_matched_pair(before_manifest, after_manifest)
            before_cell = run_cell(
                mode="before",
                concurrency=selected,
                duration_seconds=args.pair_seconds,
                binaries=binaries,
                authority=authority,
                temporary=temporary,
                environment=environment,
                build_binding=build_binding,
                source=source,
            )
            after_cell = run_cell(
                mode="after",
                concurrency=selected,
                duration_seconds=args.pair_seconds,
                binaries=binaries,
                authority=authority,
                temporary=temporary,
                environment=environment,
                build_binding=build_binding,
                source=source,
            )
            before_pairs.append(before_cell)
            after_pairs.append(after_cell)
            write_json(output / f"manifests/pairs/before-r{repeat}.json", before_manifest)
            write_json(output / f"manifests/pairs/after-r{repeat}.json", after_manifest)
            write_json(output / f"raw/pairs/before-r{repeat}.json", before_cell)
            write_json(output / f"raw/pairs/after-r{repeat}.json", after_cell)
            if repeat == 3 and should_stop_after_three(before_pairs, after_pairs):
                break
        paired = summarize_pairs(before_pairs, after_pairs)
        preliminary_performance = (
            paired["after_median_operations_per_second"]
            >= 1.20 * paired["before_median_operations_per_second"]
            and paired["after_median_p99_ns"] <= 1.05 * paired["before_median_p99_ns"]
            and paired["errors"] == 0
        )

        continuity_cell = None
        soak_cell = None
        continuity_gate = "INCONCLUSIVE"
        soak_gate = "INCONCLUSIVE"
        resource_gate = "INCONCLUSIVE"
        if preliminary_performance and refill_gate == "PASS" and args.security_gate == "PASS":
            continuity_cell = run_cell(
                mode="after",
                concurrency=selected,
                operations=1_024,
                binaries=binaries,
                authority=authority,
                temporary=temporary,
                environment=environment,
                build_binding=build_binding,
                source=source,
            )
            continuity_gate = validate_continuity(continuity_cell)
            write_json(output / "raw/continuity/after.json", continuity_cell)
            if continuity_gate == "PASS":
                soak_cell = run_cell(
                    mode="after",
                    concurrency=selected,
                    duration_seconds=args.soak_seconds,
                    binaries=binaries,
                    authority=authority,
                    temporary=temporary,
                    environment=environment,
                    build_binding=build_binding,
                    source=source,
                )
                write_json(output / "raw/soak/after.json", soak_cell)
                soak_gate = (
                    "PASS"
                    if soak_cell["duration_ns"] >= args.soak_seconds * 1_000_000_000
                    and soak_cell["errors"] == 0
                    and soak_cell["payload_correct"]
                    else "FAIL"
                )
                resource_gate = (
                    "PASS"
                    if soak_cell["cpu"]["status"] == "MEASURED"
                    and soak_cell["active_epochs_high_water"] <= 2
                    and soak_cell["replay_entries"] <= soak_cell["replay_limit"]
                    and soak_cell["replay_limit"] == 10_000
                    else "INCONCLUSIVE"
                )

    acceptance = evaluate_acceptance(
        paired,
        security=args.security_gate,
        refill=refill_gate,
        continuity=continuity_gate,
        soak=soak_gate,
        resource=resource_gate,
    )
    analysis = {
        "schema": "nbsr-p2d-analysis-v1",
        "outcome": acceptance["outcome"],
        "observed": {
            "smoke": {
                "before": cell_summary(smoke_before),
                "after": cell_summary(smoke_after),
            },
            "sweep": {
                "before": [cell_summary(cell) for cell in sweep_before],
                "after": [cell_summary(cell) for cell in sweep_after],
            },
            "paired": paired,
            "continuity": cell_summary(continuity_cell) if continuity_cell else None,
            "soak": cell_summary(soak_cell) if soak_cell else None,
        },
        "raw_references": {
            "smoke": "raw/smoke/",
            "sweep": "raw/sweep/",
            "pairs": "raw/pairs/",
            "continuity": "raw/continuity/after.json" if continuity_cell else None,
            "soak": "raw/soak/after.json" if soak_cell else None,
        },
        "selected_saturation_concurrency": selected,
        "stopping_rule": {
            "pairs_run": len(before_pairs),
            "stopped_after_three": len(before_pairs) == 3,
            "three_pair_rule_satisfied": (
                should_stop_after_three(before_pairs, after_pairs)
                if len(before_pairs) == 3
                else False
            ),
        },
        "mandatory_gates": acceptance["gates"],
        "blocking_gate": acceptance["blocking_gate"],
        "not_run_reason": (
            None
            if soak_cell is not None
            else "continuity/soak run only after all short security, refill, throughput, p99, and error gates pass"
        ),
        "measurement_semantics": {
            "observed": "All raw cells are actual Rust/Quinn loopback measurements.",
            "estimates": "No estimate is substituted for a mandatory measured gate.",
            "timer": environment["timer"],
            "payload_bytes": PAYLOAD_BYTES,
            "p1f_session_shard_limit": SHARD_OPERATIONS,
        },
    }
    write_json(output / "analysis.json", analysis)
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["all"], default="all")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--target",
        type=Path,
        default=Path(os.environ.get("CARGO_TARGET_DIR", r"C:\codex-target\nbsr-p2d")),
    )
    parser.add_argument("--sweep-operations", type=int, default=512)
    parser.add_argument("--pair-seconds", type=int, default=60)
    parser.add_argument("--soak-seconds", type=int, default=300)
    parser.add_argument(
        "--security-gate", choices=["PASS", "FAIL", "INCONCLUSIVE"], required=True
    )
    args = parser.parse_args()
    if not 60 <= args.pair_seconds <= 120:
        parser.error("--pair-seconds must be 60 through 120")
    if not 300 <= args.soak_seconds <= 600:
        parser.error("--soak-seconds must be 300 through 600")
    if not 1 <= args.sweep_operations <= SHARD_OPERATIONS:
        parser.error("--sweep-operations must be 1 through 8000")
    analysis = run_all(args)
    print(
        json.dumps(
            {
                "outcome": analysis["outcome"],
                "selected_concurrency": analysis["selected_saturation_concurrency"],
                "mandatory_gates": analysis["mandatory_gates"],
            }
        )
    )
    if analysis["outcome"] == OUTCOME_ACCEPTED:
        return


if __name__ == "__main__":
    main()
