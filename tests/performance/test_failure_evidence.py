from __future__ import annotations

import pytest

from scripts.performance.failure_evidence import (
    UnsupportedAttempt,
    classify_unsupported_error,
    reconcile_attempt_records,
    terminal_failure_record,
    unsupported_attempts,
)


def attempt(implementation: str, sample_id: int) -> UnsupportedAttempt:
    return UnsupportedAttempt(
        run_id=f"{implementation}-640",
        implementation=implementation,
        scenario="20-services-32-streams-concurrent",
        requested_concurrency=640,
        configured_limit=320,
        service_id=f"service-{sample_id // 32:02d}",
        channel_id=f"channel-{sample_id // 32:02d}",
        sample_id=sample_id,
        scheduled_ns=None,
        started_ns=sample_id,
        admission_phase="pre-admission",
        expected_fail_closed=True,
        operating_point="unsupported",
    )


def test_rust_audit_unavailable_produces_typed_raw_record() -> None:
    record = terminal_failure_record(
        attempt("rust-rust", 0),
        error_type="AuditUnavailable",
        timeout_category=None,
        detail="mandatory audit queue unavailable",
    )
    assert record == {
        "schema": "nbsr-performance-unsupported-attempt-v1",
        "run_id": "rust-rust-640",
        "implementation": "rust-rust",
        "scenario": "20-services-32-streams-concurrent",
        "requested_concurrency": 640,
        "configured_limit": 320,
        "service_id": "service-00",
        "channel_id": "channel-00",
        "sample_id": 0,
        "scheduled_ns": None,
        "started_ns": 0,
        "final_result": "failure",
        "error_type": "AuditUnavailable",
        "timeout_category": None,
        "admission_phase": "pre-admission",
        "expected_fail_closed": True,
        "operating_point": "unsupported",
        "failure_class": "unsupported-limit-fail-closed",
        "detail": "mandatory audit queue unavailable",
    }


def test_go_network_inactivity_timeout_remains_distinct_from_protocol_failure() -> None:
    record = terminal_failure_record(
        attempt("go-rust", 1),
        error_type="timeout",
        timeout_category="no-recent-network-activity",
        detail="no recent network activity",
    )
    assert record["timeout_category"] == "no-recent-network-activity"
    assert record["failure_class"] == "unsupported-limit-fail-closed"
    assert record["error_type"] != "protocol-correctness-failure"


def test_every_unsupported_attempt_requires_one_terminal_record() -> None:
    attempts = [attempt("rust-rust", sample_id) for sample_id in range(3)]
    records = [
        terminal_failure_record(item, error_type="AuditUnavailable", timeout_category=None, detail="audit")
        for item in attempts
    ]
    reconcile_attempt_records(attempts, records)
    with pytest.raises(ValueError, match="unsupported attempt terminal mismatch"):
        reconcile_attempt_records(attempts, records[:-1])


def test_supported_boundary_failure_is_not_mislabeled_as_expected_unsupported() -> None:
    supported = UnsupportedAttempt(
        **{
            **attempt("rust-rust", 0).__dict__,
            "requested_concurrency": 320,
            "operating_point": "supported",
            "expected_fail_closed": False,
        }
    )
    record = terminal_failure_record(
        supported,
        error_type="protocol-correctness-failure",
        timeout_category=None,
        detail="unexpected rejection",
    )
    assert record["failure_class"] == "protocol-correctness-failure"


def test_640_stream_plan_preserves_every_service_and_request_identity() -> None:
    attempts = unsupported_attempts(
        run_id="rust-rust-640", implementation="rust-rust", requested_concurrency=640,
        configured_limit=320, services=20,
    )
    assert len(attempts) == 640
    assert attempts[0].service_id == "service-00"
    assert attempts[31].channel_id == "channel-00"
    assert attempts[32].service_id == "service-01"
    assert attempts[-1].sample_id == 639
    assert {item.service_id for item in attempts} == {f"service-{index:02d}" for index in range(20)}


def test_observed_batch_errors_map_to_stable_typed_categories() -> None:
    assert classify_unsupported_error("rust-rust", "called Result::unwrap on AuditUnavailable") == (
        "AuditUnavailable", None,
    )
    assert classify_unsupported_error("go-rust", "timeout: no recent network activity") == (
        "timeout", "no-recent-network-activity",
    )
    with pytest.raises(ValueError, match="unrecognized unsupported failure"):
        classify_unsupported_error("go-rust", "unexpected protocol parse failure")
