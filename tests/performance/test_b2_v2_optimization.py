from __future__ import annotations

import importlib
import importlib.util


def _analysis():
    assert importlib.util.find_spec("scripts.analyze_b2_v2_optimization") is not None
    return importlib.import_module("scripts.analyze_b2_v2_optimization")


def _record(gbps: float, p99_ms: float, cpu_ns: float = 100.0) -> dict:
    return {
        "valid": True,
        "errors": 0,
        "timeouts": 0,
        "aggregate_application_gbps": gbps,
        "operations_per_second": gbps * 1000,
        "p50_latency_ns": 100_000,
        "p95_latency_ns": 200_000,
        "p99_latency_ns": p99_ms * 1_000_000,
        "measured_ns": 1_000_000_000,
        "resources": {
            "total_cpu_ns": 900_000_000,
            "cpu_ns_per_completed_operation": cpu_ns,
            "roles": {"source": {"cpu_ns": 450_000_000}, "destination": {"cpu_ns": 450_000_000}},
        },
        "path": "nbsr",
        "payload_bytes": 1024,
        "streams": 8,
        "outstanding_per_stream": 2,
        "configured_total_outstanding": 16,
        "max_outstanding_per_stream_observed": 2,
    }


def test_summary_requires_valid_conserved_repeats_and_computes_cv() -> None:
    summary = _analysis().summarize_cell([_record(2.0, 1.0), _record(2.02, 1.1), _record(1.98, 0.9)])
    assert summary["valid"] is True
    assert summary["repeat_count"] == 3
    assert summary["throughput_cv"] < 0.05
    assert summary["configured_total_outstanding"] == 16
    assert summary["max_outstanding_per_stream_observed"] == 2


def test_stable_ceiling_excludes_faster_unstable_cell() -> None:
    analysis = _analysis()
    stable = analysis.summarize_cell([_record(2.0, 1.0), _record(2.01, 1.0), _record(1.99, 1.0)])
    unstable_records = [_record(2.4, 2.0), _record(1.9, 2.0), _record(2.5, 2.0)]
    for record in unstable_records:
        record["streams"] = 16
    unstable = analysis.summarize_cell(unstable_records)
    assert analysis.stable_ceiling([stable, unstable], payload_bytes=1024)["median_gbps"] == stable["median_gbps"]
