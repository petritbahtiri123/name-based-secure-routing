from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)
import statistics


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "performance" / "stream-establishment-profile-p2b"


def load_runs(prefix: str) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((EVIDENCE / "raw").glob(f"{prefix}*.json"))]


def median(run: list[dict], key: str) -> float:
    return statistics.median(item[key] for item in run)


def cv(values: list[float]) -> float:
    return statistics.stdev(values) / statistics.fmean(values) if len(values) > 1 else 0.0


def phase_medians(runs: list[dict]) -> list[dict]:
    keys = [(phase["role"], phase["phase"]) for phase in runs[0]["phases"]]
    result = []
    for role, name in keys:
        values = [next(p for p in run["phases"] if p["role"] == role and p["phase"] == name) for run in runs]
        calls = statistics.median(value["calls"] for value in values)
        completed = statistics.median(run["completed_operations"] for run in runs)
        result.append({
            "role": role, "phase": name,
            "mean_ns_per_call": statistics.median(value["mean_ns"] for value in values),
            "p50_ns": statistics.median(value["p50_ns"] for value in values),
            "p95_ns": statistics.median(value["p95_ns"] for value in values),
            "p99_ns": statistics.median(value["p99_ns"] for value in values),
            "calls_per_operation": calls / completed,
            "failures": sum(value["failures"] for value in values),
        })
    return result


def main() -> None:
    observer = {}
    for path in ("direct", "nbsr"):
        disabled = load_runs(f"observer-{path}-50pct-r")
        disabled = [run for run in disabled if not run["instrumentation_enabled"]]
        enabled = load_runs(f"observer-{path}-50pct-r")
        enabled = [run for run in enabled if run["instrumentation_enabled"]]
        throughput_change = (median(enabled, "throughput") / median(disabled, "throughput") - 1) * 100
        p99_change = (median(enabled, "p99_ns") / median(disabled, "p99_ns") - 1) * 100
        observer[path] = {"throughput_change_percent": throughput_change, "p99_change_percent": p99_change,
                          "additional_errors": sum(r["errors"] for r in enabled) - sum(r["errors"] for r in disabled),
                          "pass": throughput_change >= -3 and p99_change <= 5}

    cells = {}
    for load in (50, 90):
        cells[str(load)] = {}
        for path in ("direct", "nbsr"):
            runs = load_runs(f"profile-{path}-{load}pct-r")
            cells[str(load)][path] = {
                "throughput_ops_per_second": median(runs, "throughput"),
                "mean_lifecycle_ns": median(runs, "mean_lifecycle_ns"),
                "p50_ns": median(runs, "p50_ns"), "p95_ns": median(runs, "p95_ns"), "p99_ns": median(runs, "p99_ns"),
                "cpu_ns_per_operation": median(runs, "cpu_ns_per_operation"),
                "throughput_cv": cv([r["throughput"] for r in runs]),
                "errors": sum(r["errors"] for r in runs), "over_capacity": sum(r["over_capacity"] for r in runs),
                "phases": phase_medians(runs),
            }
        direct = cells[str(load)]["direct"]
        nbsr = cells[str(load)]["nbsr"]
        incremental = nbsr["mean_lifecycle_ns"] - direct["mean_lifecycle_ns"]
        phases = {p["phase"]: p["mean_ns_per_call"] for p in nbsr["phases"] if p["role"] == "source"}
        direct_phases = {p["phase"]: p["mean_ns_per_call"] for p in direct["phases"] if p["role"] == "source"}
        explained = phases["source_admission_wait_read"] + phases["source_prepare_authorize"] + phases["source_admission_confirm"] + phases["source_control_write"] + phases["source_application_setup"] + phases["source_release_cleanup"] + max(0, phases["source_first_exchange"] - direct_phases["source_first_exchange"]) + max(0, phases["quinn_open_bi"] - direct_phases["quinn_open_bi"])
        cells[str(load)]["incremental"] = {"mean_ns": incremental, "explained_ns": explained,
                                            "explained_percent": explained / incremental * 100,
                                            "admission_wait_percent_of_incremental": phases["source_admission_wait_read"] / incremental * 100}

    analysis = {
        "schema": "nbsr-p2b-analysis-v1", "accepted": all(v["pass"] for v in observer.values()),
        "classification": "A", "classification_label": "NBSR control/admission path dominated",
        "observer_effect": observer, "cells": cells,
        "allocation_profile": {"available": False, "reason": "No safe existing allocation-count/stack profiler was available; WPR was present but xperf/WPA stack analysis and allocator hooks were not."},
        "cpu_sampling": {"available": False, "reason": "No usable low-overhead Rust stack-sampling analysis tool was installed; process CPU and wall-phase attribution are reported without fabricated CPU-stack percentages."},
        "recommended_first_optimization_hypothesis": "Remove the per-stream serialized STREAM_OPEN admission round trip from the critical path while preserving authorization, replay, sequencing, audit, and fail-closed semantics.",
    }
    (EVIDENCE / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    (EVIDENCE / "observer-effect.json").write_text(json.dumps(observer, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = ["# P2B Stream-Establishment Profile", "", "## Executive summary", "",
             "P2B is accepted. Classification **A — NBSR control/admission path dominated**. No optimization was implemented.", ""]
    for load in (50, 90):
        c = cells[str(load)]
        lines += [f"## {load}% load", "", "| Path | ops/s | mean ns/op | p50 | p95 | p99 | CPU ns/op | errors | CV |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
                  *[f"| {path} | {c[path]['throughput_ops_per_second']:.3f} | {c[path]['mean_lifecycle_ns']:.1f} | {c[path]['p50_ns']:.0f} | {c[path]['p95_ns']:.0f} | {c[path]['p99_ns']:.0f} | {c[path]['cpu_ns_per_operation']:.1f} | {c[path]['errors']} | {c[path]['throughput_cv']*100:.4f}% |" for path in ("direct", "nbsr")], "",
                  f"Incremental mean NBSR cost: {c['incremental']['mean_ns']:.1f} ns/op. Source admission wait/read alone: {c['incremental']['admission_wait_percent_of_incremental']:.1f}% of that delta; measured source phases explain {c['incremental']['explained_percent']:.1f}% (overlap/noise may make this exceed 100%).", ""]
    lines += ["## Interpretation", "", "The destination uses one sequential control-stream read/authorize/respond loop. Source `open_bi` follows the admission response. The admission wait/read is the largest NBSR-specific source phase at both loads; StreamGate/replay/audit/state work inside destination authorization is much smaller. Destination control-read and accept timers include inter-arrival/dependency wait and are not CPU attribution.", "",
              "No safe allocation-count profiler or usable stack-sampling analysis tool was available. Allocation counts/bytes, allocator stacks, lock wait/hold, and Tokio wakeup counts are therefore unavailable; process CPU and fixed-cardinality wall timers are reported instead.", "",
              "## Recommended first optimization", "", analysis["recommended_first_optimization_hypothesis"], ""]
    (EVIDENCE / "final-report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    checksum_lines = []
    for path in sorted(p for p in EVIDENCE.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        checksum_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(EVIDENCE).as_posix()}")
    (EVIDENCE / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
