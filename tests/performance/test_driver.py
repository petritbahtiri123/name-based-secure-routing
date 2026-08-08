from __future__ import annotations

from pathlib import Path

import pytest

from scripts.performance.driver import (
    CapacityObservation,
    FormalRunRequirements,
    lifecycle_batch_plan,
    concurrency_distribution,
    progressive_counts,
    choose_sustainable_capacity,
    ensure_release_binary,
    open_loop_deadlines_ns,
)
from scripts.run_performance_validation import merge_destination_measurements, normalize


def observation(path: str, rate: float, **changes: object) -> CapacityObservation:
    values: dict[str, object] = {
        "path": path,
        "offered_rate": rate,
        "success_rate": 0.999,
        "unexpected_rejections": 0,
        "resource_limit_errors": 0,
        "destination_cpu_percent": 80.0,
        "memory_slope_bytes_per_second": 0.0,
        "p99_ns": 1_500,
        "idle_p99_ns": 1_000,
    }
    values.update(changes)
    return CapacityObservation(**values)  # type: ignore[arg-type]


def test_debug_binary_cannot_be_measured(tmp_path: Path) -> None:
    binary = tmp_path / "debug" / "peer.exe"
    binary.parent.mkdir()
    binary.write_bytes(b"MZ")
    with pytest.raises(ValueError, match="release binary"):
        ensure_release_binary(binary)


def test_open_loop_deadlines_use_absolute_schedule() -> None:
    assert open_loop_deadlines_ns(start_ns=1_000_000_000, rate_per_second=4, count=4) == [
        1_000_000_000,
        1_250_000_000,
        1_500_000_000,
        1_750_000_000,
    ]


def test_capacity_is_chosen_independently_for_each_path() -> None:
    observations = [
        observation("direct-quic", 1000),
        observation("direct-quic", 1200, destination_cpu_percent=90),
        observation("rust-rust", 700),
        observation("rust-rust", 900, success_rate=0.998),
        observation("go-rust", 500),
        observation("go-rust", 600, p99_ns=2_001),
    ]
    assert choose_sustainable_capacity(observations) == {
        "direct-quic": 1000,
        "rust-rust": 700,
        "go-rust": 500,
    }


def test_any_protocol_or_resource_error_disqualifies_capacity() -> None:
    with pytest.raises(ValueError, match="no sustainable capacity"):
        choose_sustainable_capacity([observation("go-rust", 100, unexpected_rejections=1)])


def test_formal_capacity_window_cannot_be_silently_shortened() -> None:
    requirements = FormalRunRequirements()
    requirements.validate_capacity_window(warmup_seconds=60, steady_state_seconds=600)
    with pytest.raises(ValueError, match="60 second warm-up"):
        requirements.validate_capacity_window(warmup_seconds=59, steady_state_seconds=600)
    with pytest.raises(ValueError, match="600 second steady-state"):
        requirements.validate_capacity_window(warmup_seconds=60, steady_state_seconds=599)


def test_requested_concurrency_is_not_silently_clamped() -> None:
    requirements = FormalRunRequirements()
    requirements.validate_concurrency(requested=64, active=64)
    with pytest.raises(ValueError, match="requested concurrency 64, active 32"):
        requirements.validate_concurrency(requested=64, active=32)


def test_warm_new_batches_preserve_every_sample_and_existing_transport() -> None:
    batches = lifecycle_batch_plan(samples=45, services_per_session=20)
    assert batches == (20, 20, 5)
    assert sum(batches) == 45
    assert all(batch <= 20 for batch in batches)


def test_lifecycle_batch_plan_rejects_silent_zero_or_over_limit_values() -> None:
    with pytest.raises(ValueError, match="samples must be positive"):
        lifecycle_batch_plan(samples=0, services_per_session=20)
    with pytest.raises(ValueError, match="services per session must be in 1..20"):
        lifecycle_batch_plan(samples=1, services_per_session=21)


def test_destination_measurements_are_joined_without_cross_process_clock_subtraction() -> None:
    records = [{"sample_id": 0, "destination_admission_ns": None, "application_processing_ns": None}]
    merge_destination_measurements(
        records,
        {"samples": [{"destination_admission_ns": 17, "application_processing_ns": 23}]},
    )
    assert records == [{"sample_id": 0, "destination_admission_ns": 17, "application_processing_ns": 23}]
    with pytest.raises(ValueError, match="destination measurement count mismatch"):
        merge_destination_measurements(records, {"samples": []})


def test_concurrency_is_distributed_without_silent_clamping() -> None:
    assert concurrency_distribution(requested=10, services=3) == (4, 3, 3)
    assert sum(concurrency_distribution(requested=64, services=1)) == 64
    with pytest.raises(ValueError, match="requested concurrency 65 exceeds configured limit 64"):
        concurrency_distribution(requested=65, services=1)
    with pytest.raises(ValueError, match="requested concurrency must cover every service"):
        concurrency_distribution(requested=19, services=20)


def test_normalization_preserves_observed_cardinality_and_concurrency() -> None:
    record = {
        "success": True, "bytes_transmitted": 1, "bytes_received": 1,
        "transport_sessions": 1, "service_channels": 20,
        "application_streams": 20, "request_concurrency": 20,
    }
    observed = normalize(
        record, sample_id=0, path="rust-rust", scenario="nbsr-warm-new-service",
        payload=1, environment_digest="e", repository_sha="r", run_id="run",
    )
    assert observed["service_channels"] == 20
    assert observed["application_streams"] == 20
    assert observed["request_concurrency"] == 20


def test_capacity_discovery_uses_bounded_progressive_counts() -> None:
    assert progressive_counts(maximum=20) == (1, 2, 4, 8, 16, 20)
    assert progressive_counts(maximum=1) == (1,)
    with pytest.raises(ValueError, match="maximum must be positive"):
        progressive_counts(maximum=0)
