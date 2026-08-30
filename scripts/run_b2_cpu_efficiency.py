from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority
from scripts.performance.cpu_efficiency import analyze_repeat, classify_cells, summarize_cell
from scripts.run_p2a_established import build, run_repeat
from scripts.run_performance_validation import ROOT, environment


SOURCE_FILES = (
    "scripts/performance/cpu_efficiency.py",
    "scripts/performance/windows_affinity.py",
    "scripts/run_b2_cpu_efficiency.py",
    "scripts/run_p2a_established.py",
    "tests/performance/test_cpu_efficiency.py",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def checksums(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (root / "checksums.sha256").write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
        newline="\n",
    )


def comparison(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(cell["path"], cell["payload_bytes"], cell["streams"], cell["processors"]): cell for cell in cells}
    rows = []
    for key, nbsr in indexed.items():
        path, payload, streams, processors = key
        if path != "nbsr":
            continue
        direct = indexed.get(("direct", payload, streams, processors))
        if direct is None:
            continue
        rows.append(
            {
                "payload_bytes": payload,
                "streams": streams,
                "processors": processors,
                "nbsr_to_direct_operations_ratio": nbsr["median_operations_per_second"] / direct["median_operations_per_second"],
                "nbsr_minus_direct_cpu_ns_per_operation": nbsr["median_cpu_ns_per_operation"] - direct["median_cpu_ns_per_operation"],
                "nbsr_to_direct_gbit_per_core_ratio": nbsr["median_gbit_per_second_per_effective_core"]
                / direct["median_gbit_per_second_per_effective_core"],
            }
        )
    return rows


def prevent_system_sleep() -> None:
    result = ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    if result == 0:
        raise ctypes.WinError()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=5.0)
    parser.add_argument("--duration-seconds", type=float, default=15.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--validation", action="store_true")
    args = parser.parse_args()
    prevent_system_sleep()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b2-cpu\cargo-target"))
    binaries = build(target)
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        metadata = environment()
    else:
        metadata = environment(allowed_dirty_root=output)
    metadata.update(
        {
            "schema": "nbsr-b2-cpu-environment-v1",
            "base_git_sha": metadata.pop("repository_sha"),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "build": "release",
            "affinity": "SetProcessAffinityMask followed by GetProcessAffinityMask for both source and destination",
            "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES},
            "binary_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()},
        }
    )
    write_json(output / "environment.json", metadata)
    workloads = [(1024, 64)] if args.validation else [(1024, 64), (16384, 8)]
    processors = [1] if args.validation else [1, 2, 4]
    repeats = 1 if args.validation else args.repeats
    warmup = 1.0 if args.validation else args.warmup_seconds
    duration = 2.0 if args.validation else args.duration_seconds
    grouped: dict[tuple[str, int, int, int], list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory(prefix="nbsr-b2-") as temporary:
        temporary_root = Path(temporary)
        authority = temporary_root / "authority"
        write_loopback_authority(authority)
        for payload, streams in workloads:
            for processor_count in processors:
                for path in ("direct", "nbsr"):
                    key = (path, payload, streams, processor_count)
                    grouped[key] = []
                    for repeat in range(1, repeats + 1):
                        print(
                            f"running path={path} payload={payload} streams={streams} "
                            f"processors={processor_count} repeat={repeat}/{repeats}",
                            flush=True,
                        )
                        control = temporary_root / f"{path}-p{payload}-s{streams}-c{processor_count}-r{repeat}"
                        control.mkdir()
                        record = run_repeat(
                            {"path": path, "payload_bytes": payload, "streams": streams},
                            repeat,
                            binaries,
                            authority,
                            warmup,
                            duration,
                            control,
                            affinity_processors=processor_count,
                        )
                        derived = analyze_repeat(record)
                        grouped[key].append(derived)
                        write_json(output / "raw" / f"{path}-p{payload}-s{streams}-c{processor_count}-r{repeat}.json", derived)
    cells = [summarize_cell(records) for records in grouped.values()]
    classification = classify_cells(cells)
    analysis = {
        "schema": "nbsr-b2-cpu-analysis-v1",
        **classification,
        "cells": cells,
        "direct_nbsr_comparison": comparison(cells),
        "limitations": [
            "Windows loopback on one client host; source and destination each receive the requested affinity mask.",
            "Effective cores are derived from summed source and destination process CPU time divided by measured wall time.",
            "No ETW/CPU profile was captured, so scheduler or lock contention is inferred only from scaling and utilization.",
        ],
    }
    write_json(output / "analysis.json", analysis)
    lines = [
        "# B2 CPU Efficiency",
        "",
        f"Evidence: **{classification['evidence']}**",
        f"System: **{classification['system']}**",
        "",
        "| Path | Payload | Streams | Affinity | Ops/s | Gbit/s | Effective cores | CPU ns/op | Gbit/s/core | p50/p95/p99 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for cell in cells:
        lines.append(
            f"| {cell['path']} | {cell['payload_bytes']} | {cell['streams']} | {cell['processors']} | "
            f"{cell['median_operations_per_second']:.2f} | {cell['median_aggregate_application_gbps']:.6f} | "
            f"{cell['median_effective_cores']:.3f} | {cell['median_cpu_ns_per_operation']:.1f} | "
            f"{cell['median_gbit_per_second_per_effective_core']:.6f} | "
            f"{cell['median_p50_latency_ns'] / 1e6:.3f}/{cell['median_p95_latency_ns'] / 1e6:.3f}/{cell['median_p99_latency_ns'] / 1e6:.3f} |"
        )
    lines.extend(["", "Effective-core values sum CPU time for both benchmark peers; they are not per-process core counts.", ""])
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    (output / "commands.txt").write_text(" ".join(sys.argv) + "\n", encoding="utf-8", newline="\n")
    checksums(output)
    print(json.dumps(classification, sort_keys=True))


if __name__ == "__main__":
    main()
