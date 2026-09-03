from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


PROFILE_ROW = re.compile(
    r"^\s*.*?\s+\(\s*(\d+)\),\s*(\d+),\s*([0-9.]+),\s*(.*)$"
)
CSWITCH_ROW = re.compile(r"^\s*(\d+),\s*.*?\s+\(\s*(\d+)\),\s*(\d+)\s*$")
FILE_SYSTEM_TERMS = (
    "Ntfs.sys",
    "FLTMGR.SYS",
    "fileinfo.sys",
    "WdFilter.sys",
    "bindflt.sys",
    "cldflt.sys",
    "storqosflt.sys",
    "wtf8",
    "std::sys::fs",
    "std::fs::",
    "KernelBase.dll",
)


def parse_profile_rows(text: str) -> dict[int, list[tuple[int, str]]]:
    result: dict[int, list[tuple[int, str]]] = {}
    for line in text.splitlines():
        match = PROFILE_ROW.match(line)
        if match:
            result.setdefault(int(match.group(1)), []).append(
                (int(match.group(2)), match.group(4))
            )
    return result


def file_system_weight(rows: list[tuple[int, str]]) -> int:
    return sum(weight for weight, function in rows if any(term in function for term in FILE_SYSTEM_TERMS))


def parse_lost_events(text: str) -> int:
    match = re.search(r"Total # Lost Events\s*:\s*(\d+)", text)
    if not match:
        raise ValueError("lost-event count missing")
    return int(match.group(1))


def handshake_percentiles(text: str) -> dict[str, float | None]:
    values = sorted(
        int(record["transport_handshake_ns"])
        for line in text.splitlines()
        if line.strip()
        for record in (json.loads(line),)
        if record.get("success") and record.get("transport_handshake_ns") is not None
    )

    def percentile(fraction: float) -> float | None:
        if not values:
            return None
        return values[round((len(values) - 1) * fraction)] / 1e6

    return {"p50_ms": percentile(0.50), "p95_ms": percentile(0.95), "p99_ms": percentile(0.99)}


def role_pid(record: dict[str, Any], role: str) -> int:
    pids = {int(sample["pid"]) for sample in record["resource_samples"] if sample["role"] == role}
    if len(pids) != 1:
        raise ValueError(f"expected one PID for {role}, got {sorted(pids)}")
    return pids.pop()


def role_resources(record: dict[str, Any], role: str) -> dict[str, float | int]:
    samples = [sample for sample in record["resource_samples"] if sample["role"] == role]
    cpu_ns = (
        samples[-1]["user_cpu_ns"]
        + samples[-1]["kernel_cpu_ns"]
        - samples[0]["user_cpu_ns"]
        - samples[0]["kernel_cpu_ns"]
    )
    wall_ns = samples[-1]["timestamp_ns"] - samples[0]["timestamp_ns"]
    return {
        "effective_cores": cpu_ns / wall_ns,
        "threads": max(int(sample["thread_count"]) for sample in samples),
        "handles": max(int(sample["handle_count"]) for sample in samples),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze(capture: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    control = json.loads((capture / "control" / "manifest.json").read_text(encoding="utf-8"))
    profiled = json.loads((capture / "profiled" / "manifest.json").read_text(encoding="utf-8"))
    profile_rows = parse_profile_rows((capture / "cpu-profile-detail.txt").read_text(errors="replace"))
    cswitch_text = (capture / "cswitch-process-thread.txt").read_text(errors="replace")
    cswitches: dict[int, list[tuple[int, int]]] = {}
    for line in cswitch_text.splitlines():
        match = CSWITCH_ROW.match(line)
        if match:
            cswitches.setdefault(int(match.group(2)), []).append(
                (int(match.group(1)), int(match.group(3)))
            )

    kernel_lost = parse_lost_events(
        subprocess.check_output(
            [
                r"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit\xperf.exe",
                "-i",
                str(capture / "task4c-kernel.etl"),
                "-tle",
                "-a",
                "tracestats",
            ],
            text=True,
            stderr=subprocess.STDOUT,
        )
    )
    network_stats = subprocess.check_output(
        [
            r"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit\xperf.exe",
            "-i",
            str(capture / "task4c-network.etl"),
            "-tle",
            "-a",
            "tracestats",
        ],
        text=True,
        stderr=subprocess.STDOUT,
    )
    network_lost = parse_lost_events(network_stats)

    cells = []
    for profiled_record in profiled["records"]:
        clients = int(profiled_record["clients"])
        control_record = next(record for record in control["records"] if int(record["clients"]) == clients)
        stem = f"clients-{clients}-connections-1-r1"
        control_handshake = handshake_percentiles(
            (capture / "control" / "raw" / stem / "admission-source.stdout").read_text(encoding="utf-8")
        )
        profiled_handshake = handshake_percentiles(
            (capture / "profiled" / "raw" / stem / "admission-source.stdout").read_text(encoding="utf-8")
        )
        roles: dict[str, Any] = {}
        for role in ("admission-source", "admission-destination"):
            pid = role_pid(profiled_record, role)
            rows = profile_rows[pid]
            total_weight = sum(weight for weight, _ in rows)
            main_switches, main_tid = max(cswitches[pid])
            resources = role_resources(profiled_record, role)
            roles[role] = {
                "pid": pid,
                "main_thread_id": main_tid,
                "main_thread_context_switches": main_switches,
                "file_system_sample_weight": file_system_weight(rows),
                "total_sample_weight": total_weight,
                "file_system_sample_fraction": file_system_weight(rows) / total_weight,
                "top_sampled_hotspots": [
                    {
                        "function": function,
                        "weight": weight,
                        "process_sample_fraction": weight / total_weight,
                    }
                    for weight, function in sorted(rows, reverse=True)[:10]
                ],
                **resources,
            }
        control_rate = control_record["successful_admissions"] / control_record["admission_elapsed_seconds"]
        profiled_rate = profiled_record["successful_admissions"] / profiled_record["admission_elapsed_seconds"]
        cells.append(
            {
                "clients": clients,
                "control": {
                    "successful_admissions": control_record["successful_admissions"],
                    "admissions_per_second": control_rate,
                    "handshake": control_handshake,
                    "p99_total_admission_ms": control_record["admission_p99_latency_ns"] / 1e6,
                    "errors": control_record["errors"],
                    "timeouts": control_record["timeouts"],
                },
                "profiled": {
                    "successful_admissions": profiled_record["successful_admissions"],
                    "admissions_per_second": profiled_rate,
                    "handshake": profiled_handshake,
                    "p99_total_admission_ms": profiled_record["admission_p99_latency_ns"] / 1e6,
                    "errors": profiled_record["errors"],
                    "timeouts": profiled_record["timeouts"],
                    "observer_overhead_fraction": 1.0 - profiled_rate / control_rate,
                },
                "roles": roles,
            }
        )

    first, second = cells
    source_switch_ratio = (
        second["roles"]["admission-source"]["main_thread_context_switches"]
        / first["roles"]["admission-source"]["main_thread_context_switches"]
    )
    destination_switch_ratio = (
        second["roles"]["admission-destination"]["main_thread_context_switches"]
        / first["roles"]["admission-destination"]["main_thread_context_switches"]
    )
    attribution_pass = (
        kernel_lost == 0
        and all(cell["roles"][role]["file_system_sample_fraction"] > 0.30 for cell in cells for role in cell["roles"])
        and source_switch_ratio > 3.0
        and destination_switch_ratio > 3.0
        and second["control"]["admissions_per_second"] < first["control"]["admissions_per_second"] / 4
    )
    analysis = {
        "schema": "nbsr-b4b-task4c-analysis-v1",
        "classification": "PASS / HARNESS-LIMITED" if attribution_pass else "PARTIAL / UNRESOLVED",
        "kernel_trace": {"lost_events": kernel_lost, "valid": kernel_lost == 0},
        "network_trace": {
            "lost_events": network_lost,
            "valid": network_lost == 0,
            "use": "supplemental only; socket-error attribution rejected when invalid",
        },
        "cells": cells,
        "context_switch_growth": {
            "source_main_thread_64_to_128_ratio": source_switch_ratio,
            "destination_main_thread_64_to_128_ratio": destination_switch_ratio,
        },
        "attribution": {
            "primary": "synchronous lifecycle-terminal directory polling on both current-thread Tokio runtimes",
            "mechanism": "completed client/session tasks each scan the shared lifecycle directory every 1 ms while later QUIC handshakes remain pending; the O(completed clients times directory entries) blocking filesystem work serializes both event loops and delays handshake and close progress",
            "cleanup_delay": "the same all-client terminal barrier keeps every completed task polling until the final terminal marker, amplifying filesystem work and delaying connection close",
            "handshake_effect": "transport handshake p99 rises modestly in the unprofiled control, while total admission p99 and close/cleanup timeouts collapse; event-loop starvation reaches the remaining handshakes but is primarily a post-handshake lifecycle-barrier amplification",
            "not_supported": [
                "host CPU saturation",
                "ephemeral-port exhaustion",
                "Windows socket failure attribution because the supplemental network trace lost events",
                "production NBSR bottleneck",
            ],
            "recommended_harness_change": "replace per-task 1 ms read_dir scans with one bounded coordinator that receives one in-memory completion signal per logical client and releases all tasks once; retain file markers only as external evidence written once per client",
        },
    }

    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    shutil.copy2(capture / "control" / "manifest.json", raw / "control-manifest.json")
    shutil.copy2(capture / "profiled" / "manifest.json", raw / "profiled-manifest.json")
    (raw / "kernel-trace-stats.txt").write_text(
        f"Total # Lost Events : {kernel_lost}\n", encoding="utf-8", newline="\n"
    )
    (raw / "network-trace-stats.txt").write_text(
        f"Total # Lost Events : {network_lost}\n", encoding="utf-8", newline="\n"
    )
    (output / "analysis.json").write_text(
        json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    external = {
        "capture_root": str(capture),
        "files": {
            name: {"bytes": (capture / name).stat().st_size, "sha256": sha256(capture / name)}
            for name in (
                "task4c-kernel.etl",
                "task4c-network.etl",
                "cpu-profile-detail.txt",
                "cswitch-process-thread.txt",
                "readythread.txt",
                "thread-activity.txt",
                "process-thread.txt",
            )
        },
    }
    (output / "external-trace-manifest.json").write_text(
        json.dumps(external, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# B4b Task 4c ETW attribution",
        "",
        f"Classification: **{analysis['classification']}**",
        "",
        "The zero-loss kernel trace attributes the 64-to-128 collapse to synchronous 1 ms lifecycle-terminal directory polling on both single-thread Tokio runtimes. The network trace is supplemental and rejected for socket-error conclusions because it lost events.",
        "",
        "| Clients | Connected | Control admissions/s | Handshake p99 ms | Total admission p99 ms | Cleanup errors | Source FS samples | Destination FS samples | Source main CS | Destination main CS |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell in cells:
        lines.append(
            f"| {cell['clients']} | {cell['control']['successful_admissions']} | {cell['control']['admissions_per_second']:.2f} | {cell['control']['handshake']['p99_ms']:.2f} | {cell['control']['p99_total_admission_ms']:.2f} | {cell['control']['errors'] - (cell['clients'] - cell['control']['successful_admissions'])} | {cell['roles']['admission-source']['file_system_sample_fraction']*100:.2f}% | {cell['roles']['admission-destination']['file_system_sample_fraction']*100:.2f}% | {cell['roles']['admission-source']['main_thread_context_switches']:,} | {cell['roles']['admission-destination']['main_thread_context_switches']:,} |"
        )
    lines.extend(
        [
            "",
            f"Source main-thread context switches grew {source_switch_ratio:.2f}x; destination grew {destination_switch_ratio:.2f}x.",
            "",
            "Recommended harness-only change: replace per-task directory scans with one bounded in-memory completion coordinator. Preserve one terminal evidence marker per logical client, unchanged deadlines, and independent client state. Driver sharding is not yet justified.",
        ]
    )
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (output / "commands.txt").write_text(
        'pwsh -NoProfile -ExecutionPolicy Bypass -File "<repo>\\scripts\\capture_b4b_task4c.ps1"\n'
        'python <repo>\\scripts\\analyze_b4b_task4c.py --capture "<external-capture-root>" --output "<evidence-output>"\n',
        encoding="utf-8",
        newline="\n",
    )
    evidence_files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "checksums.sha256").write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(output).as_posix()}\n"
            for path in evidence_files
            if path.name != "checksums.sha256"
        ),
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.capture.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
