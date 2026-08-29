from __future__ import annotations

from scripts.performance.mixed_workload import analyze_mixed_records, scheduled_admission_count, workload_cells


def _record(
    rate: float,
    repeat: int,
    *,
    goodput: float,
    p99: int,
    admitted: int,
    failed: int = 0,
    planned: list[float] | None = None,
) -> dict:
    duration = 10.0
    scheduled = scheduled_admission_count(rate, duration)
    return {
        "schema": "nbsr-b4-mixed-repeat-v1",
        "repeat": repeat,
        "payload_bytes": 1024,
        "streams": 8,
        "duration_seconds": duration,
        "admission_rate_per_second": rate,
        "planned_admission_rates": planned or [0.0, 25.0],
        "scheduled_admissions": scheduled,
        "successful_admissions": admitted,
        "failed_admissions": failed,
        "timeouts": 0,
        "errors": failed,
        "established_goodput_bytes_per_second": goodput,
        "p50_latency_ns": 100,
        "p95_latency_ns": 200,
        "p99_latency_ns": p99,
        "admission_p50_latency_ns": 300 if rate else None,
        "admission_p95_latency_ns": 400 if rate else None,
        "admission_p99_latency_ns": 500 if rate else None,
        "max_admission_start_lateness_ns": 0,
        "resources": {"peak_working_set_bytes": 1_000_000, "peak_private_bytes": 900_000, "total_cpu_ns": 1_000},
    }


def test_workload_cells_keep_baseline_and_load_sweep_equivalent() -> None:
    cells = workload_cells(smoke=False)

    assert [cell["admission_rate_per_second"] for cell in cells] == [0.0, 25.0, 100.0, 400.0]
    assert {(cell["payload_bytes"], cell["streams"], cell["duration_seconds"]) for cell in cells} == {(1024, 8, 10.0)}


def test_analysis_compares_mixed_goodput_to_the_zero_admission_baseline() -> None:
    records = []
    for repeat in range(1, 4):
        records.extend(
            [
                _record(0, repeat, goodput=1_000_000, p99=1_000, admitted=0),
                _record(25, repeat, goodput=950_000, p99=1_500, admitted=250),
            ]
        )

    analysis = analyze_mixed_records(records)

    mixed = analysis["cells"][1]
    assert mixed["median_goodput_ratio_to_baseline"] == 0.95
    assert mixed["median_p99_ratio_to_baseline"] == 1.5
    assert mixed["status"] == "STABLE"
    assert analysis["classification"] == "PASS"


def test_analysis_preserves_first_saturation_point() -> None:
    records = []
    for repeat in range(1, 4):
        records.extend(
            [
                _record(0, repeat, goodput=1_000_000, p99=1_000, admitted=0, planned=[0, 100, 400]),
                _record(100, repeat, goodput=920_000, p99=1_700, admitted=1_000, planned=[0, 100, 400]),
                _record(400, repeat, goodput=700_000, p99=3_000, admitted=3_000, failed=1_000, planned=[0, 100, 400]),
            ]
        )

    analysis = analyze_mixed_records(records)

    assert analysis["classification"] == "PARTIAL"
    assert analysis["first_saturation"] == {
        "admission_rate_per_second": 400.0,
        "reason": "admission failures; achieved admission rate below 90%; established goodput below 90%; p99 latency above 2x baseline",
    }
    assert analysis["cells"][-1]["status"] == "SATURATED"


def test_analysis_rejects_missing_repeats_and_mismatched_workloads() -> None:
    baseline = _record(0, 1, goodput=1_000_000, p99=1_000, admitted=0)
    mixed = _record(25, 1, goodput=950_000, p99=1_500, admitted=250)
    mixed["payload_bytes"] = 16_384

    analysis = analyze_mixed_records([baseline, mixed])

    assert analysis["classification"] == "INCONCLUSIVE"
    assert analysis["invalid_records"]


def test_analysis_preserves_saturation_before_any_admission_latency_exists() -> None:
    records = []
    for repeat in range(1, 4):
        records.append(_record(0, repeat, goodput=1_000_000, p99=1_000, admitted=0, planned=[0, 100]))
        saturated = _record(100, repeat, goodput=950_000, p99=1_200, admitted=0, failed=1_000, planned=[0, 100])
        saturated["admission_p50_latency_ns"] = None
        saturated["admission_p95_latency_ns"] = None
        saturated["admission_p99_latency_ns"] = None
        records.append(saturated)

    analysis = analyze_mixed_records(records)

    assert analysis["cells"][1]["status"] == "SATURATED"
    assert analysis["cells"][1]["median_admission_p99_latency_ns"] is None


def test_fractional_schedule_matches_rust_rounding_rule() -> None:
    assert scheduled_admission_count(0.25, 2.0) == 1


def test_analysis_rejects_duplicate_repeat_ids() -> None:
    baseline = _record(0, 1, goodput=1_000_000, p99=1_000, admitted=0)
    mixed = _record(25, 1, goodput=950_000, p99=1_500, admitted=250)

    analysis = analyze_mixed_records([baseline, baseline.copy(), baseline.copy(), mixed, mixed.copy(), mixed.copy()])

    assert analysis["classification"] == "INCONCLUSIVE"
    assert any(item["reason"] == "duplicate repeat identifier" for item in analysis["invalid_records"])


def test_analysis_rejects_missing_planned_cell_or_baseline() -> None:
    records = [
        _record(25, repeat, goodput=950_000, p99=1_500, admitted=250, planned=[0, 25, 100])
        for repeat in range(1, 4)
    ]

    analysis = analyze_mixed_records(records)

    assert analysis["classification"] == "INCONCLUSIVE"
    assert analysis["invalid_records"]


def test_analysis_rejects_duration_and_scheduled_count_mismatch() -> None:
    records = []
    for repeat in range(1, 4):
        records.append(_record(0, repeat, goodput=1_000_000, p99=1_000, admitted=0))
        records.append(_record(25, repeat, goodput=950_000, p99=1_500, admitted=250))
    records[-1]["duration_seconds"] = 9.0
    records[-2]["scheduled_admissions"] = 249

    analysis = analyze_mixed_records(records)

    assert analysis["classification"] == "INCONCLUSIVE"
    reasons = {item["reason"] for item in analysis["invalid_records"]}
    assert "mismatched workload shape" in reasons
    assert "scheduled admission count does not match rate and duration" in reasons
