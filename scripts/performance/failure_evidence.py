from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class UnsupportedAttempt:
    run_id: str
    implementation: str
    scenario: str
    requested_concurrency: int
    configured_limit: int
    service_id: str
    channel_id: str
    sample_id: int
    scheduled_ns: int | None
    started_ns: int | None
    admission_phase: str
    expected_fail_closed: bool
    operating_point: str

    def __post_init__(self) -> None:
        if not self.run_id or self.sample_id < 0:
            raise ValueError("invalid unsupported attempt identity")
        if self.operating_point not in {"supported", "unsupported"}:
            raise ValueError("invalid operating point")
        if self.admission_phase not in {"pre-admission", "post-admission"}:
            raise ValueError("invalid admission phase")
        if self.operating_point == "unsupported" and self.requested_concurrency <= self.configured_limit:
            raise ValueError("unsupported operating point must exceed configured limit")


def unsupported_attempts(
    *, run_id: str, implementation: str, requested_concurrency: int,
    configured_limit: int, services: int,
) -> list[UnsupportedAttempt]:
    if services < 1 or requested_concurrency < services:
        raise ValueError("invalid unsupported attempt distribution")
    base, remainder = divmod(requested_concurrency, services)
    attempts: list[UnsupportedAttempt] = []
    sample_id = 0
    for service_index in range(services):
        count = base + (1 if service_index < remainder else 0)
        for _ in range(count):
            attempts.append(
                UnsupportedAttempt(
                    run_id=run_id,
                    implementation=implementation,
                    scenario=f"{services}-services-{base}-streams-concurrent",
                    requested_concurrency=requested_concurrency,
                    configured_limit=configured_limit,
                    service_id=f"service-{service_index:02d}",
                    channel_id=f"channel-{service_index:02d}",
                    sample_id=sample_id,
                    scheduled_ns=None,
                    started_ns=None,
                    admission_phase="pre-admission",
                    expected_fail_closed=True,
                    operating_point="unsupported",
                )
            )
            sample_id += 1
    return attempts


def terminal_failure_record(
    attempt: UnsupportedAttempt,
    *,
    error_type: str,
    timeout_category: str | None,
    detail: str,
) -> dict[str, Any]:
    if not error_type:
        raise ValueError("typed failure is required")
    failure_class = (
        "unsupported-limit-fail-closed"
        if attempt.operating_point == "unsupported" and attempt.expected_fail_closed
        else "protocol-correctness-failure"
    )
    source = asdict(attempt)
    return {
        "schema": "nbsr-performance-unsupported-attempt-v1",
        "run_id": source["run_id"],
        "implementation": source["implementation"],
        "scenario": source["scenario"],
        "requested_concurrency": source["requested_concurrency"],
        "configured_limit": source["configured_limit"],
        "service_id": source["service_id"],
        "channel_id": source["channel_id"],
        "sample_id": source["sample_id"],
        "scheduled_ns": source["scheduled_ns"],
        "started_ns": source["started_ns"],
        "final_result": "failure",
        "error_type": error_type,
        "timeout_category": timeout_category,
        "admission_phase": source["admission_phase"],
        "expected_fail_closed": source["expected_fail_closed"],
        "operating_point": source["operating_point"],
        "failure_class": failure_class,
        "detail": detail,
    }


def reconcile_attempt_records(
    attempts: list[UnsupportedAttempt], records: list[dict[str, Any]],
) -> None:
    expected = {(attempt.run_id, attempt.sample_id) for attempt in attempts}
    observed = {(record.get("run_id"), record.get("sample_id")) for record in records}
    if len(observed) != len(records) or observed != expected:
        raise ValueError(f"unsupported attempt terminal mismatch expected={sorted(expected)} observed={sorted(observed)}")
    if any(record.get("final_result") not in {"success", "failure", "rejected", "timeout"} for record in records):
        raise ValueError("unsupported attempt lacks terminal result")
    if any(not record.get("error_type") for record in records if record.get("final_result") != "success"):
        raise ValueError("unsupported attempt lacks typed failure")
