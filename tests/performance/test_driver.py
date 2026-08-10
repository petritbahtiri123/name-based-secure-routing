from __future__ import annotations

from pathlib import Path

import pytest

from scripts.performance.driver import (
    CapacityConfirmation,
    CapacityObservation,
    FormalRunRequirements,
    accept_confirmed_capacity,
    lifecycle_batch_plan,
    concurrency_distribution,
    progressive_counts,
    choose_sustainable_capacity,
    ensure_release_binary,
    formal_load_rate,
    open_loop_deadlines_ns,
    OpenLoopIssue,
    summarize_open_loop_issues,
    validate_formal_load_result,
)
from scripts.run_performance_validation import merge_destination_measurements, normalize, rust_server_command
from scripts.run_performance_load_cell import streamed_document_kind


def test_streamed_diagnostic_is_not_request_completion_metadata() -> None:
    assert streamed_document_kind({"event": "diagnostic", "phase": "post_drain"}) == "diagnostic"
    assert streamed_document_kind({"sample_id": 7, "success": True}) == "request"
    assert streamed_document_kind({"status": "PASS"}) == "completion"


def test_destination_diagnostics_are_absent_by_default_and_bounded_when_enabled(tmp_path: Path) -> None:
    binaries = {"server": tmp_path / "server.exe"}
    common = {
        "binaries": binaries,
        "ready": tmp_path / "ready.json",
        "result": tmp_path / "result.json",
        "authority": tmp_path / "authority",
        "ack": tmp_path / "ack",
    }

    disabled = rust_server_command(**common)
    assert "--destination-diagnostics-file" not in disabled
    assert "--diagnostic-drain-seconds" not in disabled

    output = tmp_path / "destination.ndjson"
    enabled = rust_server_command(
        **common,
        destination_diagnostics=output,
        diagnostic_drain_seconds=20,
    )
    assert enabled[-4:] == [
        "--destination-diagnostics-file",
        str(output),
        "--diagnostic-drain-seconds",
        "20",
    ]


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


def test_open_loop_overload_remains_visible_as_backlog_and_failure() -> None:
    issues = [
        OpenLoopIssue(scheduled_ns=100, started_ns=100, completed_ns=150, success=True, error_type=None),
        OpenLoopIssue(scheduled_ns=110, started_ns=140, completed_ns=170, success=True, error_type=None),
        OpenLoopIssue(scheduled_ns=120, started_ns=170, completed_ns=180, success=False, error_type="timeout"),
    ]
    summary = summarize_open_loop_issues(issues, offered_rate=100.0, window_seconds=0.03)
    assert summary.offered_requests == 3
    assert summary.successful_requests == 2
    assert summary.failed_requests == 1
    assert summary.late_requests == 2
    assert summary.max_start_lateness_ns == 50
    assert summary.peak_backlog == 2
    assert summary.completed_requests == 3
    assert summary.achieved_rate == pytest.approx(2 / 0.03)


def test_open_loop_scheduler_lag_and_backlog_remain_measurable() -> None:
    issues = [
        OpenLoopIssue(0, 0, 10, True, None),
        OpenLoopIssue(5, 20, 30, True, None),
        OpenLoopIssue(10, 30, 40, False, "timeout"),
        OpenLoopIssue(15, 40, 50, False, "rejected"),
    ]
    summary = summarize_open_loop_issues(issues, offered_rate=4.0, window_seconds=1.0, expected_requests=4)
    assert summary.offered_requests == 4
    assert summary.completed_requests == 4
    assert summary.failed_requests == 2
    assert summary.timeout_requests == 1
    assert summary.rejected_requests == 1
    assert summary.peak_backlog == 3
    assert summary.p95_start_lateness_ns == 25


def test_open_loop_summary_rejects_silent_sample_loss() -> None:
    with pytest.raises(ValueError, match="offered request count 4, observed 3"):
        summarize_open_loop_issues(
            [OpenLoopIssue(0, 0, 1, True, None)] * 3,
            offered_rate=4.0,
            window_seconds=1.0,
            expected_requests=4,
        )


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
    with pytest.raises(ValueError, match="services per session must be in 1..32"):
        lifecycle_batch_plan(samples=1, services_per_session=33)


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


def test_normalization_preserves_open_loop_schedule_evidence() -> None:
    record = {
        "success": False, "error_type": "timeout", "error_stage": "application",
        "bytes_transmitted": 1, "bytes_received": 0,
        "scheduled_ns": 100, "started_ns": 130, "completed_ns": 180,
        "start_lateness_ns": 30, "service_latency_ns": 50,
        "send_lag_ns": 7, "receive_lag_ns": 11, "queue_depth": 3,
        "active_requests": 1,
    }
    observed = normalize(
        record, sample_id=0, path="direct-quic", scenario="direct-warm",
        payload=1, environment_digest="e", repository_sha="r", run_id="run",
        load_level="capacity", offered_load=100.0, achieved_load=90.0,
    )
    assert observed["success"] is False
    assert observed["start_lateness_ns"] == 30
    assert observed["service_latency_ns"] == 50
    assert observed["send_lag_ns"] == 7
    assert observed["receive_lag_ns"] == 11
    assert observed["queue_depth"] == 3
    assert observed["active_requests"] == 1
    assert observed["offered_load"] == 100.0


def test_capacity_discovery_uses_bounded_progressive_counts() -> None:
    assert progressive_counts(maximum=20) == (1, 2, 4, 8, 16, 20)
    assert progressive_counts(maximum=1) == (1,)
    with pytest.raises(ValueError, match="maximum must be positive"):
        progressive_counts(maximum=0)


def test_capacity_candidate_requires_three_independent_confirmations() -> None:
    confirmations = [
        CapacityConfirmation(f"direct-r{ordinal}", observation("direct-quic", 1_000))
        for ordinal in (1, 2)
    ]
    with pytest.raises(ValueError, match="requires at least 3 independent confirmations"):
        accept_confirmed_capacity(confirmations)


def test_failing_confirmation_invalidates_capacity_candidate() -> None:
    confirmations = [
        CapacityConfirmation("go-r1", observation("go-rust", 400)),
        CapacityConfirmation("go-r2", observation("go-rust", 400, p99_ns=2_001)),
        CapacityConfirmation("go-r3", observation("go-rust", 400)),
    ]
    with pytest.raises(ValueError, match="confirmation go-r2 failed frozen criteria"):
        accept_confirmed_capacity(confirmations)


def test_confirmed_capacities_remain_independent_by_path() -> None:
    confirmations = [
        *[
            CapacityConfirmation(f"direct-r{ordinal}", observation("direct-quic", 1_000))
            for ordinal in (1, 2, 3)
        ],
        *[
            CapacityConfirmation(f"rust-r{ordinal}", observation("rust-rust", 700))
            for ordinal in (1, 2, 3)
        ],
    ]
    assert accept_confirmed_capacity(confirmations) == {"direct-quic": 1_000, "rust-rust": 700}


def test_formal_load_uses_accepted_capacity_for_same_path() -> None:
    accepted = {"direct-quic": 1_000, "rust-rust": 700, "go-rust": 400}
    assert formal_load_rate("rust-rust", 90, accepted) == pytest.approx(630.0)
    with pytest.raises(ValueError, match="accepted capacity missing for unknown"):
        formal_load_rate("unknown", 90, accepted)
    with pytest.raises(ValueError, match="formal load percent must be one of"):
        formal_load_rate("rust-rust", 80, accepted)


def test_formal_90_percent_failure_forces_capacity_re_evaluation() -> None:
    failed = observation("rust-rust", 630, p99_ns=2_001)
    with pytest.raises(ValueError, match="capacity re-evaluation required for rust-rust"):
        validate_formal_load_result(percent=90, observation=failed)
    validate_formal_load_result(percent=75, observation=observation("rust-rust", 525))
