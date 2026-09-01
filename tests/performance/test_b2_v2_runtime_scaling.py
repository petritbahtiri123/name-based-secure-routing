from __future__ import annotations

from pathlib import Path
import importlib
import pytest
import subprocess
import sys

import scripts.run_p2a_established as p2a


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_scaling_script_runs_as_a_direct_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_b2_v2_runtime_scaling.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_runtime_scaling_manifest_preserves_exact_command() -> None:
    source = (ROOT / "scripts/run_b2_v2_runtime_scaling.py").read_text(encoding="utf-8")
    assert '"command": [sys.executable, *sys.argv]' in source


def test_benchmark_feature_alone_enables_multithread_runtime() -> None:
    cargo = (ROOT / "crates/nbsr-transport/Cargo.toml").read_text(encoding="utf-8")
    assert 'benchmark-harness = ["tokio/rt-multi-thread"]' in cargo


def test_all_peers_use_the_same_benchmark_runtime_worker_flag() -> None:
    for relative in (
        "crates/nbsr-transport/src/bin/perf_direct_peer.rs",
        "crates/nbsr-transport/src/bin/perf_rust_source.rs",
        "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "parse_runtime_workers" in source
        assert "build_benchmark_runtime" in source


def test_resource_summary_exposes_worker_and_thread_utilization() -> None:
    samples = [
        {"role": role, "timestamp_ns": timestamp, "user_cpu_ns": cpu, "kernel_cpu_ns": 0,
         "peak_working_set_bytes": 10, "private_bytes": 8, "thread_count": threads}
        for role, threads in (("source", 5), ("destination", 6))
        for timestamp, cpu in ((0, 0), (1_000_000_000, 500_000_000))
    ]
    summary = p2a.summarize_resources(samples, completed=10, measured_seconds=1, runtime_workers=4)
    assert summary["runtime_workers"] == 4
    assert summary["roles"]["source"]["peak_thread_count"] == 5
    assert summary["roles"]["source"]["effective_cores"] == 0.5
    assert summary["roles"]["source"]["effective_cores_per_runtime_worker"] == 0.125


def test_runtime_scaling_matrix_is_matched_and_bounded() -> None:
    scaling = importlib.import_module("scripts.run_b2_v2_runtime_scaling")
    cells = scaling.scaling_cells()
    assert {(cell["path"], cell["runtime_workers"]) for cell in cells} == {
        (path, workers) for path in ("direct", "nbsr") for workers in (1, 2, 4)
    }
    assert {(cell["payload_bytes"], cell["streams"], cell["outstanding_per_stream"]) for cell in cells} == {
        (1024, 64, 1),
        (16384, 1, 4),
    }


def test_analysis_reports_worker_scaling_and_highest_stable_cell() -> None:
    scaling = importlib.import_module("scripts.run_b2_v2_runtime_scaling")
    records = []
    for path in ("direct", "nbsr"):
        for workers, gbps in ((1, 2.0), (2, 2.8), (4, 2.7)):
            for repeat in range(3):
                records.append({
                    "path": path,
                    "payload_bytes": 1024,
                    "streams": 64,
                    "outstanding_per_stream": 1,
                    "runtime_workers": workers,
                    "repeat": repeat + 1,
                    "valid": True,
                    "errors": 0,
                    "timeouts": 0,
                    "aggregate_application_gbps": gbps,
                    "operations_per_second": gbps * 1000,
                    "p50_latency_ns": 1,
                    "p95_latency_ns": 2,
                    "p99_latency_ns": 3,
                    "measured_ns": 1_000_000_000,
                    "resources": {"total_cpu_ns": workers * 500_000_000, "cpu_ns_per_completed_operation": 10,
                                  "roles": {"source": {"effective_cores": workers / 4, "peak_thread_count": workers + 2},
                                            "destination": {"effective_cores": workers / 4, "peak_thread_count": workers + 2}}},
                })
    analysis = scaling.analyze(records)
    ceiling = analysis["workloads"]["p1024-s64-o1"]["nbsr"]["stable_ceiling"]
    assert ceiling["runtime_workers"] == 2
    scaling_percent = analysis["workloads"]["p1024-s64-o1"]["nbsr"]["scaling_percent"]
    assert scaling_percent["1_to_2"] == pytest.approx(40.0)
    assert scaling_percent["2_to_4"] == pytest.approx(-3.5714285714)
    assert scaling_percent["1_to_4"] == pytest.approx(35.0)
    matched = analysis["workloads"]["p1024-s64-o1"]["matched_direct_nbsr_delta_percent"]
    assert matched == pytest.approx({"1": 0.0, "2": 0.0, "4": 0.0})
    assert "stable_ceiling_nbsr_delta_percent" not in analysis["workloads"]["p1024-s64-o1"]
