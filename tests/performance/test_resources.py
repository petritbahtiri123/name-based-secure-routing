from __future__ import annotations

import os
import time

import pytest

from scripts.performance.resources import (
    MemorySample,
    ProcessResourceSampler,
    RequestActivityBuckets,
    ResourceSeries,
    analyze_memory_window,
    classify_memory_stability,
    sample_windows_process,
)


def test_request_activity_is_correlated_at_fixed_cadence() -> None:
    activity = RequestActivityBuckets(
        offered_rate=2.0,
        sample_count=6,
        cadence_ns=1_000_000_000,
    )
    activity.record(started_ns=100_000_000, completed_ns=400_000_000)
    activity.record(started_ns=200_000_000, completed_ns=1_200_000_000)
    activity.record(started_ns=1_100_000_000, completed_ns=2_200_000_000)

    first = activity.at(1_000_000_000)
    assert first.processed_requests == 1
    assert first.active_concurrency == 1
    assert first.queue_depth == 0

    second = activity.at(2_000_000_000)
    assert second.processed_requests == 2
    assert second.active_concurrency == 1
    assert second.queue_depth == 1


def test_request_activity_rejects_missing_or_invalid_intervals() -> None:
    activity = RequestActivityBuckets(offered_rate=1.0, sample_count=1, cadence_ns=1_000_000_000)
    with pytest.raises(ValueError, match="completion precedes start"):
        activity.record(started_ns=2, completed_ns=1)
    with pytest.raises(ValueError, match="expected 1 request intervals, observed 0"):
        activity.finish()


def test_windows_resource_sample_reports_current_process() -> None:
    sample = sample_windows_process(os.getpid())
    assert sample.pid == os.getpid()
    assert sample.user_cpu_ns >= 0
    assert sample.kernel_cpu_ns >= 0
    assert sample.working_set_bytes > 0
    assert sample.private_bytes > 0
    assert sample.thread_count >= 1


def test_resource_samples_cannot_silently_disappear() -> None:
    series = ResourceSeries(expected_samples=3)
    series.record(timestamp_ns=0, working_set_bytes=100)
    series.record(timestamp_ns=1_000_000_000, working_set_bytes=110)
    with pytest.raises(ValueError, match="expected 3 resource samples, observed 2"):
        series.finish()


def test_memory_slope_uses_all_post_warmup_samples() -> None:
    series = ResourceSeries(expected_samples=4)
    for second, memory in enumerate((100, 120, 140, 160)):
        series.record(timestamp_ns=second * 1_000_000_000, working_set_bytes=memory)
    result = series.finish()
    assert result.sample_count == 4
    assert result.slope_bytes_per_second == pytest.approx(20.0)
    assert result.slope_lower_95 == pytest.approx(20.0)
    assert result.slope_upper_95 == pytest.approx(20.0)
    assert result.r_squared == pytest.approx(1.0)


def test_background_sampler_retains_every_authoritative_process_sample() -> None:
    sampler = ProcessResourceSampler({"source": os.getpid()}, interval_seconds=0.01, assigned_logical_processors=1)
    sampler.start()
    time.sleep(0.12)
    records = sampler.stop()
    assert len(records) >= 3
    assert {record.role for record in records} == {"source"}
    assert all(record.working_set_bytes > 0 for record in records)
    assert all(record.cpu_percent_assigned >= 0 for record in records)


def memory_samples(values: tuple[int, ...], *, warmup_count: int = 2) -> list[MemorySample]:
    return [
        MemorySample(
            timestamp_ns=index * 1_000_000_000,
            working_set_bytes=value,
            private_bytes=value - 10,
            peak_working_set_bytes=max(values[: index + 1]),
            cpu_percent_assigned=20.0,
            processed_requests=index * 100,
            active_concurrency=1,
            queue_depth=0,
            phase="warmup" if index < warmup_count else "steady",
        )
        for index, value in enumerate(values)
    ]


def test_memory_analysis_excludes_warmup_and_detects_missing_cadence() -> None:
    samples = memory_samples((1_000, 2_000, 100, 110, 120, 130))
    result = analyze_memory_window(samples, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)
    assert result.sample_count == 4
    assert result.working_set_full.slope_bytes_per_second == pytest.approx(10.0)
    assert result.private_bytes_full.slope_bytes_per_second == pytest.approx(10.0)
    assert result.processed_request_delta == 300

    missing = [samples[0], samples[1], samples[2], samples[4], samples[5]]
    with pytest.raises(ValueError, match="memory sample cadence gap"):
        analyze_memory_window(missing, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)


def test_allocator_step_is_not_automatically_classified_as_a_leak() -> None:
    step_then_plateau = memory_samples((100, 100, 200, 200, 200, 200, 200, 200), warmup_count=2)
    run_50 = analyze_memory_window(step_then_plateau, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)
    run_75 = analyze_memory_window(step_then_plateau, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)
    conclusion = classify_memory_stability("direct-quic", {50: run_50, 75: run_75})
    assert conclusion.status == "PASS"
    assert conclusion.reason == "both stable loads show bounded post-warm-up retention"


def test_sustained_request_correlated_growth_is_classified_as_fail() -> None:
    growth = memory_samples((100, 100, 200, 300, 400, 500, 600, 700), warmup_count=2)
    run_50 = analyze_memory_window(growth, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)
    run_75 = analyze_memory_window(growth, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)
    conclusion = classify_memory_stability("rust-rust", {50: run_50, 75: run_75})
    assert conclusion.status == "FAIL"
    assert conclusion.reason == "both stable loads show sustained request-correlated growth"


def test_noisy_or_incomplete_memory_evidence_remains_inconclusive() -> None:
    noisy = memory_samples((100, 100, 200, 100, 220, 90, 210, 100), warmup_count=2)
    run_50 = analyze_memory_window(noisy, warmup_end_ns=2_000_000_000, expected_cadence_ns=1_000_000_000)
    assert classify_memory_stability("go-rust", {50: run_50}).status == "INCONCLUSIVE"
    assert classify_memory_stability("go-rust", {50: run_50, 75: run_50}).status == "INCONCLUSIVE"
