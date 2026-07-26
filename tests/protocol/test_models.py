from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.models import (
    ControlEnvelope,
    ProtocolError,
    Revocation,
    RevocationMode,
    RevocationReason,
    RevocationTargetType,
    RouteGrant,
    RouteIntent,
    ServiceRecord,
)
from nbsr.protocol.registry import ErrorCode, MessageType


ID16 = bytes(range(16))
DIGEST32 = bytes(range(32))
KID = b"owner-key"


def valid_service_record(**changes: object) -> ServiceRecord:
    values: dict[str, object] = {
        "record_version": 1,
        "canonical_name": "api.example.com",
        "sequence": 42,
        "owner_key_id": KID,
        "service_id": "svc_api",
        "destination_operator_id": "op_example",
        "destination_edge_set": ["edge-a", "edge-b"],
        "origin_connector_id": "connector-a",
        "transports": ["tcp"],
        "ports": [443],
        "route_profiles": ["nbsr-quic-1"],
        "publication_mode": "nbsr-secure-only",
        "not_before": 1_785_000_000,
        "not_after": 1_785_003_600,
        "revocation_ref": "revset_2026_207",
    }
    values.update(changes)
    return ServiceRecord(**values)  # type: ignore[arg-type]


def valid_route_intent(**changes: object) -> RouteIntent:
    values: dict[str, object] = {
        "intent_version": 1,
        "resolution_context_digest": DIGEST32,
        "canonical_name": "api.example.com",
        "service_id": "svc_api",
        "source_operator_id": "op_source",
        "source_edge_id": "edge-source",
        "destination_operator_id": "op_destination",
        "destination_edge_set": ["edge-a"],
        "allowed_transports": ["tcp"],
        "allowed_ports": [443],
        "created_at": 1_785_000_000,
        "expires_at": 1_785_000_120,
        "record_sequence": 42,
        "policy_hash": DIGEST32,
        "route_id": ID16,
        "lease_id": bytes(reversed(ID16)),
    }
    values.update(changes)
    return RouteIntent(**values)  # type: ignore[arg-type]


def valid_route_grant(**changes: object) -> RouteGrant:
    values: dict[str, object] = {
        "grant_version": 1,
        "route_id": ID16,
        "name_digest": DIGEST32,
        "service_id": "svc_api",
        "source_operator_id": "op_source",
        "source_edge_id": "edge-source",
        "destination_operator_id": "op_destination",
        "destination_edge_set": ["edge-a"],
        "allowed_transports": ["tcp"],
        "allowed_ports": [443],
        "client_session_key_thumbprint": DIGEST32,
        "not_before": 1_785_000_000,
        "expires_at": 1_785_000_120,
        "lease_id": bytes(reversed(ID16)),
        "record_sequence": 42,
        "policy_hash": DIGEST32,
        "unique_nonce": b"nonce-1234567890",
    }
    values.update(changes)
    return RouteGrant(**values)  # type: ignore[arg-type]


def valid_revocation(**changes: object) -> Revocation:
    values: dict[str, object] = {
        "revocation_version": 1,
        "revocation_id": ID16,
        "issuer_key_id": b"issuer-key",
        "generation": 7,
        "target_type": RevocationTargetType.SERVICE_RECORD,
        "target_id": DIGEST32,
        "mode": RevocationMode.DENY_NEW_USE,
        "not_before": 1_785_000_000,
        "expires_at": None,
        "target_sequence": 42,
        "reason_code": RevocationReason.ADMINISTRATIVE,
    }
    values.update(changes)
    return Revocation(**values)  # type: ignore[arg-type]


def test_presentation_name_normalizes_before_signed_model() -> None:
    from nbsr.protocol.fields import normalize_presentation_name

    assert normalize_presentation_name("API.Example.COM.") == "api.example.com"
    assert valid_service_record().canonical_name == "api.example.com"


@pytest.mark.parametrize(
    "name",
    (
        "API.example.com",
        "api.example.com.",
        "api..example.com",
        "a" * 64 + ".example",
        "éxample.com",
        "192.0.2.9",
        "2001:db8::9",
    ),
)
def test_signed_models_reject_noncanonical_or_ip_literal_names(name: str) -> None:
    with pytest.raises(ProtocolViolation):
        valid_service_record(canonical_name=name)


@pytest.mark.parametrize(
    "identifier",
    ("Upper", "with space", "../escape", "a/b", "a__b", "a-", "\x00bad", "1leading"),
)
def test_textual_ids_enforce_frozen_ascii_pattern(identifier: str) -> None:
    with pytest.raises(ProtocolViolation):
        valid_service_record(service_id=identifier)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sequence", True),
        ("ports", [True]),
        ("not_before", False),
        ("owner_key_id", b""),
        ("owner_key_id", b"k" * 65),
        ("publication_mode", []),
    ),
)
def test_service_record_rejects_wrong_exact_types_and_bounds(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ProtocolViolation):
        valid_service_record(**{field: value})


def test_service_record_rejects_reversed_excessive_and_duplicate_values() -> None:
    with pytest.raises(ProtocolViolation):
        valid_service_record(not_after=1_785_000_000)
    with pytest.raises(ProtocolViolation):
        valid_service_record(not_after=1_785_604_801)
    with pytest.raises(ProtocolViolation):
        valid_service_record(ports=[443, 443])
    with pytest.raises(ProtocolViolation):
        valid_service_record(destination_edge_set=["edge-b", "edge-a"])


def test_models_copy_collections_and_are_deeply_immutable() -> None:
    edges = ["edge-a"]
    body = {1: [b"first"]}
    record = valid_service_record(destination_edge_set=edges)
    envelope = ControlEnvelope(
        protocol_version=1,
        message_type=MessageType.PING,
        request_id=ID16,
        session_id=bytes(reversed(ID16)),
        monotonic_sequence=1,
        body=body,
    )

    edges.append("edge-b")
    body[1].append(b"second")

    assert record.destination_edge_set == ("edge-a",)
    assert envelope.body[1] == (b"first",)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        record.sequence = 43  # type: ignore[misc]
    with pytest.raises(TypeError):
        envelope.body[2] = b"mutable"  # type: ignore[index]


def test_sequence_and_time_guards_fail_closed() -> None:
    record = valid_service_record()

    record.require_newer_than(41)
    record.require_valid_at(1_785_000_100)
    with pytest.raises(ProtocolViolation) as stale:
        record.require_newer_than(42)
    with pytest.raises(ProtocolViolation):
        record.require_valid_at(1_785_003_600)

    assert stale.value.code is ErrorCode.NBSR_E_RECORD_STALE


def test_route_windows_and_bindings_use_d6_bounds() -> None:
    with pytest.raises(ProtocolViolation):
        valid_route_intent(expires_at=1_785_000_301)
    with pytest.raises(ProtocolViolation):
        valid_route_grant(expires_at=1_785_000_601)
    with pytest.raises(ProtocolViolation):
        valid_route_grant(name_digest=b"short")
    with pytest.raises(ProtocolViolation):
        valid_route_grant(allowed_ports=[0])


def test_route_and_revocation_sequence_bindings_fail_closed() -> None:
    intent = valid_route_intent(record_sequence=42)
    grant = valid_route_grant(record_sequence=42)
    revocation = valid_revocation(target_sequence=42)

    intent.require_record_sequence(42)
    grant.require_record_sequence(42)
    revocation.require_target_sequence(42)
    with pytest.raises(ProtocolViolation):
        intent.require_record_sequence(41)
    with pytest.raises(ProtocolViolation):
        grant.require_record_sequence(41)
    with pytest.raises(ProtocolViolation):
        revocation.require_target_sequence(41)


def test_revocation_optional_expiry_and_target_sequence_rules() -> None:
    assert valid_revocation(expires_at=None).expires_at is None
    assert valid_revocation(expires_at=2_000_000_000).expires_at == 2_000_000_000

    with pytest.raises(ProtocolViolation):
        valid_revocation(expires_at=1_785_000_000)
    with pytest.raises(ProtocolViolation):
        valid_revocation(
            reason_code=RevocationReason.KEY_COMPROMISE,
            expires_at=2_000_000_000,
        )
    with pytest.raises(ProtocolViolation):
        valid_revocation(
            target_type=RevocationTargetType.ROUTE,
            target_sequence=42,
        )


def test_revocation_generation_guard_uses_persistent_tombstone_value() -> None:
    revocation = valid_revocation(generation=8)

    revocation.require_newer_generation(7)
    with pytest.raises(ProtocolViolation) as rollback:
        revocation.require_newer_generation(8)

    assert rollback.value.code is ErrorCode.NBSR_E_RECORD_STALE


def test_protocol_error_retry_fields_are_coherent() -> None:
    ProtocolError(
        error_version=1,
        error_code=ErrorCode.NBSR_E_OVER_CAPACITY,
        request_id=ID16,
        retryable=True,
        retry_after_seconds=30,
    )
    ProtocolError(
        error_version=1,
        error_code=ErrorCode.NBSR_E_OVER_CAPACITY,
        request_id=ID16,
        retryable=True,
        retry_after_seconds=None,
    )
    with pytest.raises(ProtocolViolation):
        ProtocolError(
            error_version=1,
            error_code=ErrorCode.NBSR_E_INTERNAL,
            request_id=ID16,
            retryable=False,
            retry_after_seconds=30,
        )


def test_control_envelope_rejects_stale_or_critical_extension_state() -> None:
    envelope = ControlEnvelope(
        protocol_version=1,
        message_type=MessageType.PING,
        request_id=ID16,
        session_id=bytes(reversed(ID16)),
        monotonic_sequence=2,
        body={},
        extensions={1000: b"optional"},
    )

    envelope.require_newer_than(1)
    with pytest.raises(ProtocolViolation):
        envelope.require_newer_than(2)
    with pytest.raises(ProtocolViolation):
        ControlEnvelope(
            protocol_version=1,
            message_type=MessageType.PING,
            request_id=ID16,
            session_id=bytes(reversed(ID16)),
            monotonic_sequence=2,
            body={},
            extensions={1000: b"unsupported"},
            critical_extension_keys=[1000],
        )


def test_control_envelope_rejects_unsupported_nested_core_values() -> None:
    with pytest.raises(ProtocolViolation):
        ControlEnvelope(
            protocol_version=1,
            message_type=MessageType.PING,
            request_id=ID16,
            session_id=bytes(reversed(ID16)),
            monotonic_sequence=2,
            body={0: 2**65},
        )
