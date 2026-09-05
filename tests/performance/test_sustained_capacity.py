from __future__ import annotations

import pytest

from scripts.performance.sustained_capacity import analyze_soak_run


def _progress(index: int, completed: int, goodput: float, p95: int, p99: int) -> dict:
    return {
        "window_index": index,
        "elapsed_ns": index * 5_000_000_000,
        "interval_ns": 5_000_000_000,
        "completed_operations": completed,
        "completed_total": completed * index,
        "goodput_bytes_per_second": goodput,
        "p50_latency_ns": p95 // 2,
        "p95_latency_ns": p95,
        "p99_latency_ns": p99,
        "errors": 0,
        "timeouts": 0,
    }


def _resource(index: int, private_bytes: int, *, role: str = "source", phase: str = "steady") -> dict:
    return {
        "role": role,
        "timestamp_ns": index * 5_000_000_000,
        "user_cpu_ns": index * 1_000_000_000,
        "kernel_cpu_ns": index * 100_000_000,
        "cpu_percent_assigned": 25.0,
        "working_set_bytes": private_bytes + 1_000_000,
        "peak_working_set_bytes": private_bytes + 2_000_000,
        "private_bytes": private_bytes,
        "thread_count": 4,
        "handle_count": 20,
        "phase": phase,
    }


def test_analysis_separates_valid_evidence_from_observed_stability() -> None:
    progress = [_progress(i, 1_000, 100_000_000 - i * 100_000, 1000 + i, 2000 + i) for i in range(1, 13)]
    resources = [
        _resource(i, 10_000_000 + (i % 2) * 10_000, role=role)
        for role in ("source", "destination") for i in range(1, 13)
    ]
    resources.extend(_resource(13, 9_000_000, role=role, phase="cooldown") for role in ("source", "destination"))
    cleanup_fields = {
        "transport_sessions_current_live": 0, "service_channels_current_live": 0,
        "application_streams_current_live": 0, "nbsr_tasks_current_live": 0,
        "quic_connections_current_live": 0, "quic_streams_current_live": 0,
        "audit_queue_current_entries": 0, "replay_state_current_entries": 0,
    }
    diagnostics = {
        "source": cleanup_fields,
        "destination": cleanup_fields,
    }

    result = analyze_soak_run(
        progress,
        resources,
        diagnostics,
        expected_duration_seconds=60,
        payload_bytes=1024,
        streams=8,
    )

    assert result["evidence_status"] == "PASS"
    assert result["system_result"] == "STABLE"
    assert result["completed_operations"] == 12_000
    assert result["cleanup_result"] == "PASS"
    assert result["goodput_drift_percent"] < 0
    assert result["memory"]["source"]["post_load_private_bytes"] == 9_000_000
    assert result["memory"]["source"]["max_handles"] == 20


@pytest.mark.parametrize("late_goodput,late_p99", [(80_000_000, 2000), (100_000_000, 3000)])
def test_observed_decay_or_latency_drift_is_not_stable(late_goodput, late_p99):
    progress = [_progress(i, 1000, 100_000_000 if i <= 6 else late_goodput, 1000,
                          2000 if i <= 6 else late_p99) for i in range(1, 13)]
    fields = {key: 0 for key in (
        "transport_sessions_current_live", "service_channels_current_live", "application_streams_current_live",
        "nbsr_tasks_current_live", "quic_connections_current_live", "quic_streams_current_live",
        "audit_queue_current_entries", "replay_state_current_entries")}
    resources = [_resource(i, 10_000_000, role=role, phase="steady" if i < 13 else "cooldown")
                 for role in ("source", "destination") for i in range(1, 14)]
    result = analyze_soak_run(progress, resources, {"source": fields, "destination": fields},
                              expected_duration_seconds=60, payload_bytes=1024, streams=8)
    assert result["evidence_status"] == "PASS"
    assert result["system_result"] == "UNSTABLE"


def test_analysis_rejects_missing_cadence_and_unreconciled_totals() -> None:
    progress = [_progress(i, 1_000, 100_000_000, 1000, 2000) for i in range(1, 13)]
    progress.pop(5)

    result = analyze_soak_run(
        progress,
        [_resource(i, 10_000_000) for i in range(1, 13)],
        {},
        expected_duration_seconds=60,
        payload_bytes=1024,
        streams=8,
    )

    assert result["evidence_status"] == "INCONCLUSIVE"
    assert result["invalid_reasons"]


def test_analysis_preserves_continuous_resource_growth_as_resource_growth() -> None:
    progress = [_progress(i, 1_000, 100_000_000, 1000, 2000) for i in range(1, 13)]
    resources = [_resource(i, 10_000_000 + i * 1_000_000) for i in range(1, 13)]

    resources.extend(_resource(i, 10_000_000, role="destination") for i in range(1, 13))
    resources.extend(_resource(13, 9_000_000, role=role, phase="cooldown") for role in ("source", "destination"))
    cleanup_fields = {
        "transport_sessions_current_live": 0, "service_channels_current_live": 0,
        "application_streams_current_live": 0, "nbsr_tasks_current_live": 0,
        "quic_connections_current_live": 0, "quic_streams_current_live": 0,
        "audit_queue_current_entries": 0, "replay_state_current_entries": 0,
    }
    diagnostics = {role: cleanup_fields for role in ("source", "destination")}
    result = analyze_soak_run(
        progress,
        resources,
        diagnostics,
        expected_duration_seconds=60,
        payload_bytes=1024,
        streams=8,
    )

    assert result["evidence_status"] == "PASS"
    assert result["system_result"] == "RESOURCE-GROWTH"


def test_analysis_rejects_non_positive_configuration() -> None:
    with pytest.raises(ValueError):
        analyze_soak_run([], [], {}, expected_duration_seconds=0, payload_bytes=1024, streams=8)


def test_analysis_rejects_missing_resource_role_or_cooldown() -> None:
    progress = [_progress(i, 1_000, 100_000_000, 1000, 2000) for i in range(1, 13)]
    result = analyze_soak_run(
        progress,
        [_resource(i, 10_000_000) for i in range(1, 13)],
        {},
        expected_duration_seconds=60,
        payload_bytes=1024,
        streams=8,
    )

    assert result["evidence_status"] == "INCONCLUSIVE"
    assert any("resource" in reason or "cleanup" in reason for reason in result["invalid_reasons"])
