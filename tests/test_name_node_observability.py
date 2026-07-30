from __future__ import annotations

import hashlib
import hmac
from dataclasses import fields

import pytest

from nbsr.legacy_origin import LegacyOriginCache
from nbsr.name_node import NameNode, NameResolution, NbsrServicePolicy
from nbsr.name_node_observability import (
    BoundedNameNodeMetrics,
    NameNodeEvent,
)
from nbsr.protocol import ErrorCode, ProtocolViolation
from nbsr.resolution_state import NameClassification, ResolutionContextStore
from nbsr.synthetic import SyntheticAddressPool


AUDIT_KEY = b"a" * 32


def event(**changes: object) -> NameNodeEvent:
    values = {
        "event_kind": "resolution-succeeded",
        "classification": NameClassification.NBSR_SERVICE,
        "error_code": None,
        "service_audit_id": "0123456789abcdef",
        "duration_bucket_ms": 10,
        "capacity_bucket": "available",
    }
    values.update(changes)
    return NameNodeEvent(**values)


def test_event_contract_is_an_exact_privacy_allowlist() -> None:
    allowed = {
        "event_kind",
        "classification",
        "error_code",
        "service_audit_id",
        "duration_bucket_ms",
        "capacity_bucket",
    }

    assert {field.name for field in fields(NameNodeEvent)} == allowed

    forbidden_fragments = (
        "name",
        "origin",
        "endpoint",
        "route",
        "lease",
        "context",
        "key",
        "signature",
        "payload",
        "answer",
        "exception",
    )
    assert all(not any(fragment in field_name for fragment in forbidden_fragments) for field_name in allowed)


def test_event_factory_uses_keyed_hmac_audit_id_and_fixed_buckets() -> None:
    created = NameNodeEvent.create(
        audit_key=AUDIT_KEY,
        canonical_name="api.example",
        event_kind="resolution-succeeded",
        classification=NameClassification.NBSR_SERVICE,
        error_code=None,
        duration_ms=7,
        capacity_exhausted=False,
    )
    expected = hmac.new(AUDIT_KEY, b"api.example", hashlib.sha256).hexdigest()[:16]
    unkeyed = hashlib.sha256(b"api.example").hexdigest()[:16]

    assert created.service_audit_id == expected
    assert created.service_audit_id != unkeyed
    assert created.duration_bucket_ms == 10
    assert created.capacity_bucket == "available"


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"event_kind": "unknown"}, ValueError),
        ({"classification": "nbsr-service"}, TypeError),
        ({"error_code": 7}, TypeError),
        ({"service_audit_id": "UPPERCASE1234567"}, ValueError),
        ({"duration_bucket_ms": 7}, ValueError),
        ({"capacity_bucket": "full"}, ValueError),
    ),
)
def test_event_rejects_unknown_or_unbounded_labels(changes, error) -> None:
    with pytest.raises(error):
        event(**changes)


def test_metrics_snapshot_is_bounded_immutable_and_aggregate_only() -> None:
    metrics = BoundedNameNodeMetrics()
    metrics.record(event())
    metrics.record(
        event(
            event_kind="resolution-failed",
            classification=None,
            error_code=ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
            duration_bucket_ms=25,
            capacity_bucket="exhausted",
        )
    )

    snapshot = metrics.snapshot()

    assert snapshot.result_counts == (
        ("resolution-failed:7", 1),
        ("resolution-succeeded:nbsr-service", 1),
    )
    assert snapshot.duration_counts == ((10, 1), (25, 1))
    assert snapshot.capacity_counts == (("available", 1), ("exhausted", 1))
    assert not hasattr(snapshot, "events")
    with pytest.raises((AttributeError, TypeError)):
        snapshot.result_counts += (("other", 1),)


def instrumented_node(
    event_sink,
    *,
    monotonic_clock,
) -> NameNode:
    return NameNode(
        object(),
        (
            NbsrServicePolicy(
                canonical_name="api.example",
                source_operator_id="source.operator",
                source_edge_id="source.edge",
                policy_hash=b"p" * 32,
            ),
        ),
        (),
        lambda _request, _now: None,
        lambda _request, _endpoint: True,
        LegacyOriginCache(max_entries=1),
        SyntheticAddressPool(
            "127.80.0.0/30",
            "fd00:6e62:7372::/126",
            ttl_seconds=60,
        ),
        ResolutionContextStore(max_entries=1),
        lambda length: b"x" * length,
        event_sink=event_sink,
        audit_key=AUDIT_KEY,
        monotonic_clock=monotonic_clock,
    )


def test_name_node_emits_only_safe_success_event(monkeypatch) -> None:
    events: list[NameNodeEvent] = []
    clock = iter((1.0, 1.007))
    node = instrumented_node(events.append, monotonic_clock=lambda: next(clock))
    resolution = NameResolution(
        classification=NameClassification.NBSR_SERVICE,
        canonical_name="api.example",
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        route_id=b"r" * 16,
        expires_at=160,
    )
    monkeypatch.setattr(node, "_resolve_nbsr", lambda _policy, _now: resolution)

    assert node.resolve("API.EXAMPLE.", now=100) is resolution

    assert len(events) == 1
    emitted = events[0]
    assert emitted.event_kind == "resolution-succeeded"
    assert emitted.classification is NameClassification.NBSR_SERVICE
    assert emitted.error_code is None
    assert emitted.duration_bucket_ms == 10


def test_event_sink_failure_never_changes_resolution_result(monkeypatch) -> None:
    clock = iter((1.0, 1.001))
    node = instrumented_node(
        lambda _event: (_ for _ in ()).throw(RuntimeError("sink failed")),
        monotonic_clock=lambda: next(clock),
    )
    resolution = NameResolution(
        classification=NameClassification.NBSR_SERVICE,
        canonical_name="api.example",
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        route_id=b"r" * 16,
        expires_at=160,
    )
    monkeypatch.setattr(node, "_resolve_nbsr", lambda _policy, _now: resolution)

    assert node.resolve("api.example", now=100) is resolution


def test_name_node_failure_event_preserves_only_classification_and_error(monkeypatch) -> None:
    events: list[NameNodeEvent] = []
    clock = iter((1.0, 1.003))
    node = instrumented_node(events.append, monotonic_clock=lambda: next(clock))

    def exhausted(_policy, _now):
        raise ProtocolViolation(
            ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
            "internal capacity detail",
        )

    monkeypatch.setattr(node, "_resolve_nbsr", exhausted)

    with pytest.raises(ProtocolViolation):
        node.resolve("api.example", now=100)

    assert len(events) == 1
    emitted = events[0]
    assert emitted.event_kind == "resolution-failed"
    assert emitted.classification is NameClassification.NBSR_SERVICE
    assert emitted.error_code is ErrorCode.NBSR_E_HANDLE_EXHAUSTED
    assert emitted.capacity_bucket == "exhausted"
    assert "detail" not in repr(emitted)
