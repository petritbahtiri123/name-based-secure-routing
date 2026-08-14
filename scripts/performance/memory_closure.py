from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.performance.resources import MemorySample, ResourceSeries, analyze_memory_window, classify_memory_stability
except ModuleNotFoundError:
    from performance.resources import MemorySample, ResourceSeries, analyze_memory_window, classify_memory_stability


def _trend(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    series = ResourceSeries(expected_samples=len(records))
    for record in records:
        series.record(timestamp_ns=int(record["timestamp_ns"]), working_set_bytes=int(record[field]))
    result = series.finish()
    return {
        "samples": result.sample_count,
        "slope_bytes_per_second": result.slope_bytes_per_second,
        "lower_95": result.slope_lower_95,
        "upper_95": result.slope_upper_95,
        "r_squared": result.r_squared,
    }


def analyze_resource_records(records: list[dict[str, Any]], *, role: str) -> dict[str, Any]:
    selected = [record for record in records if record.get("role") == role and record.get("phase", "steady") == "steady"]
    if len(selected) < 4:
        raise ValueError(f"insufficient {role} resource samples")
    second_half = selected[len(selected) // 2 :]
    final_quarter = selected[3 * len(selected) // 4 :]
    request_delta = (
        int(selected[-1]["processed_requests"]) - int(selected[0]["processed_requests"])
        if all("processed_requests" in record for record in selected)
        else None
    )
    working_delta = int(selected[-1]["working_set_bytes"]) - int(selected[0]["working_set_bytes"])
    private_delta = int(selected[-1]["private_bytes"]) - int(selected[0]["private_bytes"])
    backlog = None
    if all("queue_depth" in record for record in selected):
        values = [int(record["queue_depth"]) for record in selected]
        backlog = {"start": values[0], "end": values[-1], "peak": max(values), "delta": values[-1] - values[0]}
    return {
        "role": role,
        "samples": len(selected),
        "working_set_bytes": {
            "start": int(selected[0]["working_set_bytes"]),
            "end": int(selected[-1]["working_set_bytes"]),
            "peak": max(int(record["peak_working_set_bytes"]) for record in selected),
        },
        "private_bytes_values": {
            "start": int(selected[0]["private_bytes"]),
            "end": int(selected[-1]["private_bytes"]),
            "peak": max(int(record["private_bytes"]) for record in selected),
        },
        "working_set": {
            "overall": _trend(selected, "working_set_bytes"),
            "second_half": _trend(second_half, "working_set_bytes"),
            "final_quarter": _trend(final_quarter, "working_set_bytes"),
        },
        "private_bytes": {
            "overall": _trend(selected, "private_bytes"),
            "second_half": _trend(second_half, "private_bytes"),
            "final_quarter": _trend(final_quarter, "private_bytes"),
        },
        "processed_request_delta": request_delta,
        "working_set_bytes_per_request": working_delta / request_delta if request_delta else None,
        "private_bytes_per_request": private_delta / request_delta if request_delta else None,
        "backlog": backlog,
    }


def analyze_go_runtime(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) < 2:
        raise ValueError("at least two Go runtime samples are required")
    first, last = records[0], records[-1]
    pauses = [
        int(current["total_gc_pause_ns"]) - int(previous["total_gc_pause_ns"])
        for previous, current in zip(records, records[1:], strict=False)
    ]
    fields = ("heap_alloc_bytes", "heap_sys_bytes", "heap_idle_bytes", "heap_inuse_bytes", "heap_released_bytes")
    result = {
        field: {"start": int(first[field]), "end": int(last[field]), "peak": max(int(item[field]) for item in records)} for field in fields
    }
    result.update(
        {
            "processed_request_delta": int(last["processed_requests"]) - int(first["processed_requests"]),
            "num_gc_delta": int(last["num_gc"]) - int(first["num_gc"]),
            "total_alloc_delta_bytes": int(last["total_alloc_bytes"]) - int(first["total_alloc_bytes"]),
            "mallocs_delta": int(last["mallocs"]) - int(first["mallocs"]),
            "frees_delta": int(last["frees"]) - int(first["frees"]),
            "total_gc_pause_delta_ns": int(last["total_gc_pause_ns"]) - int(first["total_gc_pause_ns"]),
            "recent_observed_interval_pause_ns": pauses[-1],
            "max_observed_interval_pause_ns": max(pauses),
            "per_gc_max_pause_ns": None,
        }
    )
    return result


def classify_completion_paths(
    *,
    direct_status: str,
    rust_status: str,
    go_runs: list[dict[str, Any]],
) -> dict[str, str]:
    go_eligible = (
        len(go_runs) == 2
        and all(run.get("authoritative_run") is True for run in go_runs)
        and all(run.get("authoritative_pass_eligible") is True for run in go_runs)
    )
    go_status = "PASS" if go_eligible else "INCONCLUSIVE"
    paths = {
        "direct-quic": direct_status,
        "rust-rust": rust_status,
        "go-rust": go_status,
    }
    baseline = "COMPLETE_LOOPBACK_BASELINE" if all(status in {"PASS", "FAIL"} for status in paths.values()) else "PARTIAL_BASELINE"
    return {**paths, "baseline": baseline}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_source_bindings(base: Path, destination: Path, sources: Iterable[Path]) -> None:
    base = base.resolve()
    files = []
    for source in sources:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            files.append({"path": path.resolve().relative_to(base).as_posix(), "sha256": _digest(path)})
    destination.write_text(
        json.dumps({"schema": "nbsr-performance-source-bindings-v1", "files": files}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_source_bindings(base: Path, binding_path: Path) -> int:
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    for item in binding["files"]:
        path = base / item["path"]
        if not path.is_file() or _digest(path) != item["sha256"]:
            raise ValueError(f"source binding mismatch: {item['path']}")
    return len(binding["files"])


def _json_lines(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _completed_run(root: Path, *, role: str = "destination") -> tuple[dict[str, Any], Any]:
    finalized = root / "finalized-cell"
    summary_path = finalized / "summary.json" if (finalized / "summary.json").is_file() else root / "summary.json"
    resource_path = finalized / "resources.ndjson" if (finalized / "resources.ndjson").is_file() else root / "resources.ndjson"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    resources = _json_lines(resource_path)
    analysis = analyze_resource_records(resources, role=role)
    selected = [item for item in resources if item.get("role") == role and item.get("phase") == "steady"]
    samples = [
        MemorySample(
            timestamp_ns=int(item["timestamp_ns"]),
            working_set_bytes=int(item["working_set_bytes"]),
            private_bytes=int(item["private_bytes"]),
            peak_working_set_bytes=int(item["peak_working_set_bytes"]),
            cpu_percent_assigned=float(item["cpu_percent_assigned"]),
            processed_requests=int(item["processed_requests"]),
            active_concurrency=int(item["active_concurrency"]),
            queue_depth=int(item["queue_depth"]),
            phase="steady",
        )
        for item in selected
    ]
    window = analyze_memory_window(samples, warmup_end_ns=0, expected_cadence_ns=2_000_000_000)
    analysis.update(
        {
            "run_id": summary["run_id"],
            "terminal_state": "completed",
            "authoritative_pass_eligible": True,
            "counts": {
                "offered": int(summary["offered_requests"]),
                "completed": int(summary["completed_requests"]),
                "persisted": int(summary["completed_requests"]),
                "failed": int(summary["failed_requests"]),
                "timed_out": int(summary["timeout_requests"]),
            },
            "scheduler_lag": {
                "late_requests": int(summary["late_requests"]),
                "p95_start_lateness_ns": int(summary["p95_start_lateness_ns"]),
                "max_start_lateness_ns": int(summary["max_start_lateness_ns"]),
            },
            "peak_backlog": int(summary["peak_backlog"]),
            "success_rate": float(summary["success_rate"]),
        }
    )
    return analysis, window


def _partial_go_run(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    terminal = json.loads((root / "terminal-manifest.json").read_text(encoding="utf-8"))
    resources = _json_lines(root / "resources.ndjson")
    runtime_records = _json_lines(root / "runtime.ndjson")
    process = analyze_resource_records(resources, role="source")
    runtime = analyze_go_runtime(runtime_records)
    request_delta = runtime["processed_request_delta"]
    process["processed_request_delta"] = request_delta
    process["working_set_bytes_per_request"] = (
        (process["working_set_bytes"]["end"] - process["working_set_bytes"]["start"]) / request_delta if request_delta else None
    )
    process["private_bytes_per_request"] = (
        (process["private_bytes_values"]["end"] - process["private_bytes_values"]["start"]) / request_delta if request_delta else None
    )
    process.update(
        {
            "terminal_state": terminal["terminal_state"],
            "authoritative_run": terminal["authoritative_run"],
            "authoritative_pass_eligible": terminal["authoritative_pass_eligible"],
            "cleanup_verified": terminal["cleanup_verified"],
            "counts": terminal["counters"],
            "series_counts": terminal["series_counts"],
            "scheduler_lag": None,
            "backlog": None,
            "go_runtime": runtime,
        }
    )
    return process, terminal


def _write_report(path: Path, analysis: dict[str, Any]) -> None:
    lines = [
        "# NBSR loopback memory completion report",
        "",
        f"Final classification: **{analysis['classification']['baseline']}**",
        "",
        "The frozen memory methodology classifies both stable-load windows as PASS only when bounded, FAIL only when reproducible request-correlated sustained growth satisfies the confidence and fit gates, and otherwise INCONCLUSIVE.",
        "",
    ]
    for key, run in analysis["runs"].items():
        lines.extend(
            [
                f"## {key}",
                "",
                f"Terminal state: {run['terminal_state']}; eligible: {run['authoritative_pass_eligible']}; counts: {json.dumps(run['counts'], sort_keys=True)}.",
                "",
                f"Working set: {json.dumps(run['working_set_bytes'], sort_keys=True)}.",
                "",
                f"Private bytes: {json.dumps(run['private_bytes_values'], sort_keys=True)}.",
                "",
                f"Working-set trends: {json.dumps(run['working_set'], sort_keys=True)}.",
                "",
                f"Private-byte trends: {json.dumps(run['private_bytes'], sort_keys=True)}.",
                "",
                f"Processed-request delta: {run['processed_request_delta']}; bytes/request: working set={run['working_set_bytes_per_request']}, private={run['private_bytes_per_request']}.",
                "",
                f"Scheduler lag: {json.dumps(run.get('scheduler_lag'), sort_keys=True)}; backlog: {json.dumps(run.get('backlog'), sort_keys=True)}.",
                "",
            ]
        )
        if run.get("go_runtime") is not None:
            lines.extend([f"Go runtime: {json.dumps(run['go_runtime'], sort_keys=True)}.", ""])
    lines.extend(
        [
            "## Candidate future diagnostic work — NOT IMPLEMENTED",
            "",
            "Both retained Go loads stopped processing requests around the middle of the offered set while runtime sampling continued. Diagnose this separately before any rerun; this report does not modify or optimize Go/NBSR behavior.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_memory_closure(repo: Path, output: Path) -> dict[str, Any]:
    repo, output = repo.resolve(), output.resolve()
    memory = repo / "evidence/performance/memory-completion-6366334/memory"
    prior = repo / "evidence/performance/loopback-completion-3188c7c/memory"
    direct_50, direct_50_window = _completed_run(prior / "direct-quic-memory-2375-50pct-r1")
    direct_68, direct_68_window = _completed_run(memory / "direct-quic-memory-3230-68pct-r1")
    rust_50, rust_50_window = _completed_run(memory / "rust-rust-memory-843.75-50pct-r1")
    rust_75, rust_75_window = _completed_run(memory / "rust-rust-memory-1265.62-75pct-r1")
    go_50, go_50_terminal = _partial_go_run(memory / "go-rust-memory-200-50pct-r1")
    go_75, go_75_terminal = _partial_go_run(memory / "go-rust-memory-300-75pct-r1")
    direct = classify_memory_stability("direct-quic", {50: direct_50_window, 75: direct_68_window})
    rust = classify_memory_stability("rust-rust", {50: rust_50_window, 75: rust_75_window})
    classification = classify_completion_paths(
        direct_status=direct.status,
        rust_status=rust.status,
        go_runs=[go_50_terminal, go_75_terminal],
    )
    analysis = {
        "schema": "nbsr-performance-memory-analysis-v1",
        "classification": classification,
        "classification_reasons": {
            "direct-quic": direct.reason,
            "rust-rust": rust.reason,
            "go-rust": "neither retained long run is authoritative-PASS-eligible",
        },
        "accepted_capacities": {"direct-quic": 4750, "rust-rust": 1687.5, "go-rust": 400},
        "runs": {"direct-50": direct_50, "direct-68": direct_68, "rust-50": rust_50, "rust-75": rust_75, "go-50": go_50, "go-75": go_75},
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summaries").mkdir(exist_ok=True)
    (output / "summaries/analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    references = {
        "prior_partial_baseline": "evidence/performance/complete-loopback-db55d18-partial",
        "accepted_capacity_and_previous_memory": "evidence/performance/loopback-completion-3188c7c",
        "new_memory_evidence": "evidence/performance/memory-completion-6366334",
        "superseded_or_invalid_attempts": [
            f"evidence/performance/{name}"
            for name in (
                "memory-completion-adff461",
                "memory-completion-f5396ff",
                "memory-completion-f90bd61",
                "memory-completion-d8e40c5",
                "memory-completion-9fa77b5",
                "memory-completion-a6b11de",
            )
        ],
    }
    (output / "references.json").write_text(json.dumps(references, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_paths = [repo / value for key, value in references.items() if isinstance(value, str)]
    source_paths.extend(repo / value for value in references["superseded_or_invalid_attempts"])
    write_source_bindings(repo, output / "source-bindings.json", source_paths)
    _write_report(output / "reports/memory-completion.md", analysis)
    files = sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "checksums.json"}
    )
    manifest = {
        "schema": "nbsr-performance-memory-closure-v1",
        "outcome": classification["baseline"],
        "classifications": {key: classification[key] for key in ("direct-quic", "rust-rust", "go-rust")},
        "analysis": "summaries/analysis.json",
        "source_bindings": "source-bindings.json",
        "files": ["manifest.json", *files],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {name: _digest(output / name) for name in manifest["files"]}
    (output / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return analysis
