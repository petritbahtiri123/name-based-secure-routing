from __future__ import annotations

import os
import time

import pytest

from scripts.performance.resources import ProcessResourceSampler, ResourceSeries, sample_windows_process


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
