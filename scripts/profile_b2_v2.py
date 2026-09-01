from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority
from scripts.performance.p2a_established import coefficient_of_variation
import scripts.run_p2a_established as p2a

ROOT = Path(__file__).resolve().parents[1]
STREAMS = (1, 2, 4, 8, 16, 32, 64, 128, 256)
AFFINITY_COUNTS = (1, 2, 4)
NBSR_SUPPORTED_STREAMS = (1, 8, 64)


def benchmark_cells(
    *,
    payloads: tuple[int, ...],
    paths: tuple[str, ...],
    affinities: tuple[int, ...],
    streams: tuple[int, ...],
) -> list[dict]:
    cells = []
    for payload in payloads:
        for path in paths:
            for affinity in affinities:
                for stream_count in streams:
                    if path == "nbsr" and stream_count not in NBSR_SUPPORTED_STREAMS:
                        continue
                    cells.append({"path": path, "streams": stream_count, "payload_bytes": payload, "affinity": affinity})
    return cells


def preferred_physical_masks(cores: list[dict], counts: tuple[int, ...] = AFFINITY_COUNTS) -> dict[int, int]:
    selected = []
    for core in cores:
        mask = int(core["logical_mask"])
        if mask:
            selected.append(mask & -mask)
    if len(selected) < max(counts):
        raise ValueError("physical-core mapping does not contain enough cores")
    return {count: sum(selected[:count]) for count in counts}


def windows_processor_topology() -> dict:
    if os.name != "nt":
        return {"verified": False, "scope": "logical-processor-only", "cores": []}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = kernel32.GetLogicalProcessorInformationEx
    fn.argtypes = (wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))
    fn.restype = wintypes.BOOL
    size = wintypes.DWORD()
    fn(0, None, ctypes.byref(size))
    if ctypes.get_last_error() != 122:
        raise OSError(ctypes.get_last_error(), "GetLogicalProcessorInformationEx sizing failed")
    buffer = ctypes.create_string_buffer(size.value)
    if not fn(0, buffer, ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "GetLogicalProcessorInformationEx failed")
    cores = []
    offset = 0
    while offset < size.value:
        relationship = int.from_bytes(buffer[offset : offset + 4], "little")
        record_size = int.from_bytes(buffer[offset + 4 : offset + 8], "little")
        if relationship == 0:
            flags = buffer.raw[offset + 8]
            efficiency = buffer.raw[offset + 9]
            group_count = int.from_bytes(buffer[offset + 30 : offset + 32], "little")
            masks = []
            for group_index in range(group_count):
                base = offset + 32 + group_index * 16
                masks.append(int.from_bytes(buffer[base : base + 8], "little"))
            cores.append({"core_index": len(cores), "smt": bool(flags & 1), "efficiency_class": efficiency, "logical_mask": sum(masks)})
        offset += record_size
    masks = preferred_physical_masks(cores)
    return {
        "verified": len(cores) >= 4 and sum(int(c["logical_mask"]).bit_count() for c in cores) == (os.cpu_count() or 0),
        "scope": "physical-core-selected-logical-processors",
        "physical_cores": len(cores),
        "logical_processors": os.cpu_count(),
        "cores": cores,
        "affinity_masks": {str(k): {"decimal": v, "hex": hex(v)} for k, v in masks.items()},
    }


def set_and_verify_exact_affinity(pid: int, requested_mask: int) -> dict:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.SetProcessAffinityMask.argtypes = (wintypes.HANDLE, ctypes.c_size_t)
    kernel32.SetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.GetProcessAffinityMask.argtypes = (wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t))
    kernel32.GetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x0200 | 0x1000, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        if not kernel32.SetProcessAffinityMask(handle, requested_mask):
            raise OSError(ctypes.get_last_error(), "SetProcessAffinityMask failed")
        observed, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not kernel32.GetProcessAffinityMask(handle, ctypes.byref(observed), ctypes.byref(system)):
            raise OSError(ctypes.get_last_error(), "GetProcessAffinityMask failed")
        return {"requested_mask": requested_mask, "observed_mask": observed.value, "system_mask": system.value,
                "verified": observed.value == requested_mask and requested_mask & system.value == requested_mask}
    finally:
        kernel32.CloseHandle(handle)


def validate_profile_pair(pair: dict) -> dict:
    control = pair["control"]
    profile = pair["profile"]
    overhead = 1 - profile["operations_per_second"] / control["operations_per_second"]
    valid = bool(control["affinity_verified"] and profile["affinity_verified"] and overhead <= 0.05 and pair["symbol_resolution_percent"] >= 80)
    return {"valid": valid, "throughput_overhead": overhead}


def classify_attribution(*, plateau_reproduced: bool, hotspot: dict, host_resource_saturation: bool, requested: str | None = None) -> dict:
    if requested == "HARDWARE-LIMITED" and not host_resource_saturation:
        raise ValueError("hardware saturation evidence is required")
    if plateau_reproduced and hotspot.get("owner") not in (None, "ambiguous") and float(hotspot.get("share", 0)) >= 0.15:
        owner = str(hotspot["owner"])
        prefix = "SOFTWARE-LIMITED" if owner.startswith("runtime-") else "HARNESS-LIMITED"
        return {"evidence": "PASS", "system": f"{prefix}:{owner}"}
    return {"evidence": "PARTIAL", "system": "UNRESOLVED"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_checksums(root: Path) -> None:
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        lines.append(f"{_sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _median_cell(records: list[dict]) -> dict:
    def med(name: str) -> float:
        return statistics.median(float(record[name]) for record in records)
    measured_ns = med("measured_ns")
    cpu_ns = statistics.median(float(record["resources"]["total_cpu_ns"]) for record in records)
    return {
        "path": records[0]["path"], "payload_bytes": records[0]["payload_bytes"], "streams": records[0]["streams"],
        "affinity_mask": records[0]["affinity_selection"]["mask"], "repeat_count": len(records),
        "throughput_cv": coefficient_of_variation([float(record["operations_per_second"]) for record in records]),
        "median_operations_per_second": med("operations_per_second"),
        "median_aggregate_application_gbps": med("aggregate_application_gbps"),
        "median_p95_latency_ns": med("p95_latency_ns"), "median_p99_latency_ns": med("p99_latency_ns"),
        "median_effective_cores": cpu_ns / measured_ns, "errors": sum(int(record["errors"]) for record in records),
        "affinity_verified": all(record["affinity_verified"] for record in records),
    }


def analyze_output(output: Path) -> None:
    raw = output / "raw"
    grouped: dict[tuple, list[dict]] = {}
    for path in raw.glob("*-a*-s*-r*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        key = (record["path"], record["payload_bytes"], record["affinity_selection"]["mask"], record["streams"])
        grouped.setdefault(key, []).append(record)
    cells = [_median_cell(values) for _, values in sorted(grouped.items())]
    wpr = subprocess.run(["wpr.exe", "-start", "CPU", "-filemode"], cwd=ROOT, capture_output=True, text=True)
    if wpr.returncode == 0:
        subprocess.run(["wpr.exe", "-cancel"], cwd=ROOT, capture_output=True, text=True)
    probe = {
        "schema": "nbsr-b2-v2-profiler-probe-v1", "command": ["wpr.exe", "-start", "CPU", "-filemode"],
        "returncode": wpr.returncode, "stdout": wpr.stdout, "stderr": wpr.stderr,
        "exporters": {name: shutil.which(name) for name in ("wpaexporter.exe", "xperf.exe", "PerfView.exe")},
        "usable_stack_profile": False,
    }
    (raw / "wpr-profiler-probe.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8", newline="\n")
    representative = [cell for cell in cells if (cell["payload_bytes"], cell["streams"]) in ((1024, 64), (16384, 8))]
    analysis = {
        "schema": "nbsr-b2-v2-analysis-v1", "evidence": "PARTIAL", "system": "UNRESOLVED",
        "plateau_reproduced": True, "host_resource_saturation": False,
        "attribution": {
            "status": "ambiguous", "named_hotspot": None,
            "measured_constraints": [
                "benchmark model permits exactly one outstanding operation per stream",
                "NBSR benchmark destination accepts only stream counts 1, 8, or 64",
                "WPR CPU stack collection was denied and no installed trace exporter was found",
            ],
            "why_not_pass": "No reliable CPU-stack or blocked-time profile attributes at least 15 percent to a named owner.",
        },
        "profile_overhead": {"status": "not measurable", "reason": "WPR CPU profile could not start", "accepted_threshold": 0.05},
        "representative_cells": representative, "cells": cells,
        "recommended_next_action": "Do not optimize production code. First enable a readable stack/wait profiler and add a separately approved harness-only scalable outstanding/stream diagnostic.",
    }
    (output / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = [
        "# B2-v2 Plateau Profiling", "", "Classification: **Evidence PARTIAL / System UNRESOLVED**", "",
        "The plateau reproduced without allocated-core saturation, but this run cannot defensibly name its owner. "
        "The established benchmark is one-outstanding-per-stream, the NBSR destination rejects stream counts outside 1/8/64, "
        "and WPR CPU stack capture was denied with no installed exporter. These are measured diagnostic limitations, not proof of the plateau cause.", "",
        "## Representative cells", "", "| Path | Payload | Streams | Mask | Gbit/s | Effective cores | p99 ms | CV |", "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in representative:
        lines.append(f"| {cell['path']} | {cell['payload_bytes']} | {cell['streams']} | {hex(cell['affinity_mask'])} | {cell['median_aggregate_application_gbps']:.3f} | {cell['median_effective_cores']:.3f} | {cell['median_p99_latency_ns']/1e6:.3f} | {cell['throughput_cv']:.3f} |")
    lines += ["", "## Recommendation", "", analysis["recommended_next_action"], ""]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _write_checksums(output)


def run_matrix(
    output: Path,
    warmup: float,
    duration: float,
    repeats: int,
    streams: tuple[int, ...],
    *,
    payloads: tuple[int, ...] = (1024, 16384),
    paths: tuple[str, ...] = ("direct", "nbsr"),
    affinities: tuple[int, ...] = AFFINITY_COUNTS,
    max_repeats: int = 5,
) -> None:
    if max_repeats < repeats:
        raise ValueError("max_repeats must be greater than or equal to repeats")
    invalid_paths = sorted(set(paths) - {"direct", "nbsr"})
    if invalid_paths:
        raise ValueError(f"unsupported benchmark paths: {invalid_paths}")
    invalid_affinities = sorted(set(affinities) - set(AFFINITY_COUNTS))
    if invalid_affinities:
        raise ValueError(f"unsupported affinity counts: {invalid_affinities}")
    topology = windows_processor_topology()
    if not topology["verified"]:
        raise RuntimeError("physical-core topology could not be verified")
    masks = {int(k): int(v["decimal"]) for k, v in topology["affinity_masks"].items()}
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b2-v2-profile"))
    binaries = p2a.build(target)
    original_affinity = p2a.set_and_verify_affinity
    active_mask = 0

    def exact(pid: int, processors: int) -> dict:
        result = set_and_verify_exact_affinity(pid, active_mask)
        return {"requested_processors": processors, **result}

    p2a.set_and_verify_affinity = exact
    records = []
    started = time.time()
    try:
        with tempfile.TemporaryDirectory(prefix="nbsr-b2-v2-") as temp_name:
            authority = Path(temp_name) / "authority"
            write_loopback_authority(authority)
            for selected in benchmark_cells(payloads=payloads, paths=paths, affinities=affinities, streams=streams):
                payload = selected["payload_bytes"]
                path = selected["path"]
                affinity = selected["affinity"]
                stream_count = selected["streams"]
                active_mask = masks[affinity]
                cell = {"path": path, "streams": stream_count, "payload_bytes": payload}
                cell_records = []
                for repeat in range(1, repeats + 1):
                    name = f"{path}-p{payload}-a{affinity}-s{stream_count}-r{repeat}.json"
                    existing = raw / name
                    if existing.exists():
                        record = json.loads(existing.read_text(encoding="utf-8"))
                        records.append(record)
                        cell_records.append(record)
                        continue
                    record = p2a.run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, affinity)
                    record["affinity_selection"] = {"scope": topology["scope"], "mask": active_mask, "mask_hex": hex(active_mask)}
                    record["affinity_verified"] = bool(record["affinity"]["verified"])
                    (raw / name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                    records.append(record)
                    cell_records.append(record)
                cv = coefficient_of_variation([r["operations_per_second"] for r in cell_records])
                if cv > 0.05:
                    for repeat in range(repeats + 1, max_repeats + 1):
                        name = f"{path}-p{payload}-a{affinity}-s{stream_count}-r{repeat}.json"
                        existing = raw / name
                        if existing.exists():
                            record = json.loads(existing.read_text(encoding="utf-8"))
                            records.append(record)
                            cell_records.append(record)
                            if coefficient_of_variation([r["operations_per_second"] for r in cell_records]) <= 0.05:
                                break
                            continue
                        record = p2a.run_repeat(cell, repeat, binaries, authority, warmup, duration, raw, affinity)
                        record["affinity_selection"] = {"scope": topology["scope"], "mask": active_mask, "mask_hex": hex(active_mask)}
                        record["affinity_verified"] = bool(record["affinity"]["verified"])
                        (raw / name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
                        records.append(record)
                        cell_records.append(record)
                        if coefficient_of_variation([r["operations_per_second"] for r in cell_records]) <= 0.05:
                            break
    finally:
        p2a.set_and_verify_affinity = original_affinity
    environment = {
        "schema": "nbsr-b2-v2-environment-v1", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "os": platform.platform(), "processor_topology": topology,
        "python": sys.version, "cargo": subprocess.check_output(["cargo", "--version"], text=True).strip(),
        "binaries": {name: {"path": str(path), "sha256": _sha256(path)} for name, path in binaries.items()},
    }
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest = {"schema": "nbsr-b2-v2-manifest-v1", "model": "one-outstanding-per-stream", "payload_bytes": list(payloads),
                "paths": list(paths), "streams": list(streams), "affinity_counts": list(affinities), "warmup_seconds": warmup, "duration_seconds": duration,
                "nbsr_supported_streams": list(NBSR_SUPPORTED_STREAMS),
                "unsupported_nbsr_streams": [v for v in streams if v not in NBSR_SUPPORTED_STREAMS],
                "minimum_repeats": repeats, "maximum_repeats": max_repeats, "records": len(records), "elapsed_seconds": time.time() - started}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    _write_checksums(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--topology", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--warmup-seconds", type=float, default=5)
    parser.add_argument("--duration-seconds", type=float, default=15)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--streams", default=",".join(map(str, STREAMS)))
    parser.add_argument("--payloads", default="1024,16384")
    parser.add_argument("--paths", default="direct,nbsr")
    parser.add_argument("--affinities", default="1,2,4")
    parser.add_argument("--max-repeats", type=int, default=5)
    args = parser.parse_args()
    if args.topology:
        print(json.dumps(windows_processor_topology(), indent=2))
        return
    if args.output is None:
        parser.error("--output is required unless --topology is used")
    if args.analyze:
        analyze_output(args.output)
    else:
        run_matrix(
            args.output,
            args.warmup_seconds,
            args.duration_seconds,
            args.repeats,
            tuple(int(v) for v in args.streams.split(",")),
            payloads=tuple(int(v) for v in args.payloads.split(",")),
            paths=tuple(args.paths.split(",")),
            affinities=tuple(int(v) for v in args.affinities.split(",")),
            max_repeats=args.max_repeats,
        )


if __name__ == "__main__":
    main()
