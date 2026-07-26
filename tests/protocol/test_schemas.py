from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
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
from nbsr.protocol.schemas import (
    CONTROL_ENVELOPE_FIELDS,
    PROTOCOL_ERROR_FIELDS,
    REVOCATION_FIELDS,
    ROUTE_GRANT_FIELDS,
    ROUTE_INTENT_FIELDS,
    SERVICE_RECORD_FIELDS,
    decode_envelope,
    decode_error,
    decode_revocation,
    decode_route_grant,
    decode_route_intent,
    decode_service_record,
    encode_model,
)


ID16 = bytes(range(16))
DIGEST32 = bytes(range(32))

EXPECTED_FIELD_MAPS = {
    "ServiceRecord": {
        0: "record_version",
        1: "canonical_name",
        2: "sequence",
        3: "owner_key_id",
        4: "service_id",
        5: "destination_operator_id",
        6: "destination_edge_set",
        7: "origin_connector_id",
        8: "transports",
        9: "ports",
        10: "route_profiles",
        11: "publication_mode",
        12: "not_before",
        13: "not_after",
        14: "revocation_ref",
    },
    "RouteIntent": {
        0: "intent_version",
        1: "resolution_context_digest",
        2: "canonical_name",
        3: "service_id",
        4: "source_operator_id",
        5: "source_edge_id",
        6: "destination_operator_id",
        7: "destination_edge_set",
        8: "allowed_transports",
        9: "allowed_ports",
        10: "created_at",
        11: "expires_at",
        12: "record_sequence",
        13: "policy_hash",
        14: "route_id",
        15: "lease_id",
    },
    "RouteGrant": {
        0: "grant_version",
        1: "route_id",
        2: "name_digest",
        3: "service_id",
        4: "source_operator_id",
        5: "source_edge_id",
        6: "destination_operator_id",
        7: "destination_edge_set",
        8: "allowed_transports",
        9: "allowed_ports",
        10: "client_session_key_thumbprint",
        11: "not_before",
        12: "expires_at",
        13: "lease_id",
        14: "record_sequence",
        15: "policy_hash",
        16: "unique_nonce",
    },
    "Revocation": {
        0: "revocation_version",
        1: "revocation_id",
        2: "issuer_key_id",
        3: "generation",
        4: "target_type",
        5: "target_id",
        6: "mode",
        7: "not_before",
        8: "expires_at",
        9: "target_sequence",
        10: "reason_code",
    },
    "ProtocolError": {
        0: "error_version",
        1: "error_code",
        2: "request_id",
        3: "retryable",
        4: "retry_after_seconds",
    },
    "ControlEnvelope": {
        0: "protocol_version",
        1: "message_type",
        2: "request_id",
        3: "session_id",
        4: "monotonic_sequence",
        5: "body",
        6: "critical_extension_keys",
    },
}


def models_and_decoders() -> list[tuple[object, Callable[[bytes], object]]]:
    return [
        (
            ServiceRecord(
                1,
                "api.example.com",
                42,
                b"owner-key",
                "svc_api",
                "op_destination",
                ("edge-a",),
                "connector-a",
                ("tcp",),
                (443,),
                ("nbsr-quic-1",),
                "nbsr-secure-only",
                1_785_000_000,
                1_785_003_600,
                "revset_2026_207",
            ),
            decode_service_record,
        ),
        (
            RouteIntent(
                1,
                DIGEST32,
                "api.example.com",
                "svc_api",
                "op_source",
                "edge-source",
                "op_destination",
                ("edge-a",),
                ("tcp",),
                (443,),
                1_785_000_000,
                1_785_000_120,
                42,
                DIGEST32,
                ID16,
                bytes(reversed(ID16)),
            ),
            decode_route_intent,
        ),
        (
            RouteGrant(
                1,
                ID16,
                DIGEST32,
                "svc_api",
                "op_source",
                "edge-source",
                "op_destination",
                ("edge-a",),
                ("tcp",),
                (443,),
                DIGEST32,
                1_785_000_000,
                1_785_000_120,
                bytes(reversed(ID16)),
                42,
                DIGEST32,
                b"nonce-1234567890",
            ),
            decode_route_grant,
        ),
        (
            Revocation(
                1,
                ID16,
                b"issuer-key",
                7,
                RevocationTargetType.SERVICE_RECORD,
                DIGEST32,
                RevocationMode.DENY_NEW_USE,
                1_785_000_000,
                None,
                42,
                RevocationReason.ADMINISTRATIVE,
            ),
            decode_revocation,
        ),
        (
            ProtocolError(
                1,
                ErrorCode.NBSR_E_OVER_CAPACITY,
                ID16,
                True,
                30,
            ),
            decode_error,
        ),
        (
            ControlEnvelope(
                1,
                MessageType.PING,
                ID16,
                bytes(reversed(ID16)),
                1,
                {0: b"ping"},
                extensions={1000: [b"optional"]},
            ),
            decode_envelope,
        ),
    ]


def test_numeric_field_maps_are_explicit_and_complete() -> None:
    actual = {
        "ServiceRecord": dict(SERVICE_RECORD_FIELDS),
        "RouteIntent": dict(ROUTE_INTENT_FIELDS),
        "RouteGrant": dict(ROUTE_GRANT_FIELDS),
        "Revocation": dict(REVOCATION_FIELDS),
        "ProtocolError": dict(PROTOCOL_ERROR_FIELDS),
        "ControlEnvelope": dict(CONTROL_ENVELOPE_FIELDS),
    }

    assert actual == EXPECTED_FIELD_MAPS


@pytest.mark.parametrize(("model", "decoder"), models_and_decoders())
def test_all_models_round_trip_with_exact_numeric_keys(
    model: object,
    decoder: Callable[[bytes], object],
) -> None:
    wire = encode_model(model)
    decoded_map = decode_deterministic(wire)

    assert decoder(wire) == model
    assert set(decoded_map) >= set(
        key for key, field in EXPECTED_FIELD_MAPS[type(model).__name__].items() if getattr(model, field) not in (None, ())
    )


@pytest.mark.parametrize(("model", "decoder"), models_and_decoders())
def test_unknown_reserved_core_keys_fail_closed(
    model: object,
    decoder: Callable[[bytes], object],
) -> None:
    value = decode_deterministic(encode_model(model))
    value[50] = "203.0.113.9"

    with pytest.raises(ProtocolViolation) as exc_info:
        decoder(encode_deterministic(value))

    assert exc_info.value.code is not ErrorCode.NBSR_E_INTERNAL


@pytest.mark.parametrize(
    ("model", "decoder"),
    models_and_decoders()[:-1],
)
def test_closed_payload_schemas_reject_noncritical_extensions(
    model: object,
    decoder: Callable[[bytes], object],
) -> None:
    value = decode_deterministic(encode_model(model))
    value[1000] = b"unknown"

    with pytest.raises(ProtocolViolation):
        decoder(encode_deterministic(value))


def test_envelope_preserves_noncritical_extensions_immutably() -> None:
    model, _ = models_and_decoders()[-1]
    wire = encode_model(model)
    decoded = decode_envelope(wire)

    assert decoded.extensions[1000] == (b"optional",)
    assert encode_model(decoded) == wire


def test_envelope_round_trips_nested_extension_maps_with_array_keys() -> None:
    model = ControlEnvelope(
        1,
        MessageType.PING,
        ID16,
        bytes(reversed(ID16)),
        1,
        {},
        extensions={1000: {(1, 2): b"value"}},
    )

    assert decode_envelope(encode_model(model)) == model


def test_envelope_rejects_unknown_critical_extensions() -> None:
    model, _ = models_and_decoders()[-1]
    value = decode_deterministic(encode_model(model))
    value[6] = [1000]

    with pytest.raises(ProtocolViolation) as exc_info:
        decode_envelope(encode_deterministic(value))

    assert exc_info.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED


def test_envelope_rejects_present_but_empty_critical_extension_list() -> None:
    model, _ = models_and_decoders()[-1]
    value = decode_deterministic(encode_model(model))
    value[6] = []

    with pytest.raises(ProtocolViolation):
        decode_envelope(encode_deterministic(value))


def test_schema_rejects_boolean_where_uint_is_required() -> None:
    record, _ = models_and_decoders()[0]
    value = decode_deterministic(encode_model(record))
    value[2] = True

    with pytest.raises(ProtocolViolation):
        decode_service_record(encode_deterministic(value))


@pytest.mark.parametrize(("model", "decoder"), models_and_decoders())
def test_missing_required_fields_fail_closed(
    model: object,
    decoder: Callable[[bytes], object],
) -> None:
    value = decode_deterministic(encode_model(model))
    del value[0]

    with pytest.raises(ProtocolViolation):
        decoder(encode_deterministic(value))


@pytest.mark.parametrize(
    ("model_index", "optional_key", "decoder"),
    (
        (3, 8, decode_revocation),
        (3, 9, decode_revocation),
        (4, 4, decode_error),
    ),
)
def test_optional_fields_reject_explicit_null(
    model_index: int,
    optional_key: int,
    decoder: Callable[[bytes], object],
) -> None:
    model, _ = models_and_decoders()[model_index]
    value = decode_deterministic(encode_model(model))
    value[optional_key] = None

    with pytest.raises(ProtocolViolation):
        decoder(encode_deterministic(value))


def test_optional_fields_are_omitted_not_encoded_as_null() -> None:
    revocation, _ = models_and_decoders()[3]
    protocol_error, _ = models_and_decoders()[4]
    revocation_map = decode_deterministic(encode_model(revocation))
    error_map = decode_deterministic(encode_model(replace(protocol_error, retryable=False, retry_after_seconds=None)))

    assert 8 not in revocation_map
    assert 4 not in error_map


def test_service_record_route_grant_and_revocation_have_no_signature_field() -> None:
    for model, _ in (models_and_decoders()[0], models_and_decoders()[2], models_and_decoders()[3]):
        wire_map = decode_deterministic(encode_model(model))

        assert "signature" not in wire_map.values()
