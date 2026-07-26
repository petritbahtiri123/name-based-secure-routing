from __future__ import annotations

from types import MappingProxyType
from typing import Callable, TypeVar

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.fields import thaw_core_value
from nbsr.protocol.models import (
    ControlEnvelope,
    ProtocolError,
    Revocation,
    RouteGrant,
    RouteIntent,
    ServiceRecord,
)
from nbsr.protocol.registry import ErrorCode


SERVICE_RECORD_FIELDS = MappingProxyType(
    {
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
    }
)
ROUTE_INTENT_FIELDS = MappingProxyType(
    {
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
    }
)
ROUTE_GRANT_FIELDS = MappingProxyType(
    {
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
    }
)
REVOCATION_FIELDS = MappingProxyType(
    {
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
    }
)
PROTOCOL_ERROR_FIELDS = MappingProxyType(
    {
        0: "error_version",
        1: "error_code",
        2: "request_id",
        3: "retryable",
        4: "retry_after_seconds",
    }
)
CONTROL_ENVELOPE_FIELDS = MappingProxyType(
    {
        0: "protocol_version",
        1: "message_type",
        2: "request_id",
        3: "session_id",
        4: "monotonic_sequence",
        5: "body",
        6: "critical_extension_keys",
    }
)

_Model = TypeVar(
    "_Model",
    ServiceRecord,
    RouteIntent,
    RouteGrant,
    Revocation,
    ProtocolError,
    ControlEnvelope,
)


def _unsupported(message: str) -> ProtocolViolation:
    return ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, message)


def _decode_fields(
    wire: bytes,
    *,
    field_map: MappingProxyType[int, str],
    optional_keys: frozenset[int] = frozenset(),
    allow_extensions: bool = False,
) -> tuple[dict[int, object], dict[int, object]]:
    value = decode_deterministic(wire)
    if not isinstance(value, dict):
        raise _unsupported("Schema payload must be a CBOR map")
    core: dict[int, object] = {}
    extensions: dict[int, object] = {}
    for key, item in value.items():
        if type(key) is not int:
            raise _unsupported("Schema keys must be unsigned integers")
        if key in field_map:
            core[key] = item
        elif 0 <= key <= 999:
            raise _unsupported("Unknown reserved Core field")
        elif key >= 1000 and allow_extensions:
            extensions[key] = item
        else:
            raise _unsupported("Extensions are not allowed by this schema")
    required = set(field_map) - set(optional_keys)
    if not required.issubset(core):
        raise _unsupported("Required Core field is missing")
    return core, extensions


def _construct(
    constructor: Callable[..., _Model],
    fields: dict[int, object],
    field_map: MappingProxyType[int, str],
    **extra: object,
) -> _Model:
    arguments = {field_map[key]: item for key, item in fields.items()}
    arguments.update(extra)
    try:
        return constructor(**arguments)
    except ProtocolViolation:
        raise
    except (TypeError, ValueError) as exc:
        raise _unsupported("Invalid schema field type") from exc


def _model_map(model: object) -> dict[int, object]:
    if type(model) is ServiceRecord:
        return {
            0: model.record_version,
            1: model.canonical_name,
            2: model.sequence,
            3: model.owner_key_id,
            4: model.service_id,
            5: model.destination_operator_id,
            6: model.destination_edge_set,
            7: model.origin_connector_id,
            8: model.transports,
            9: model.ports,
            10: model.route_profiles,
            11: model.publication_mode,
            12: model.not_before,
            13: model.not_after,
            14: model.revocation_ref,
        }
    if type(model) is RouteIntent:
        return {
            0: model.intent_version,
            1: model.resolution_context_digest,
            2: model.canonical_name,
            3: model.service_id,
            4: model.source_operator_id,
            5: model.source_edge_id,
            6: model.destination_operator_id,
            7: model.destination_edge_set,
            8: model.allowed_transports,
            9: model.allowed_ports,
            10: model.created_at,
            11: model.expires_at,
            12: model.record_sequence,
            13: model.policy_hash,
            14: model.route_id,
            15: model.lease_id,
        }
    if type(model) is RouteGrant:
        return {
            0: model.grant_version,
            1: model.route_id,
            2: model.name_digest,
            3: model.service_id,
            4: model.source_operator_id,
            5: model.source_edge_id,
            6: model.destination_operator_id,
            7: model.destination_edge_set,
            8: model.allowed_transports,
            9: model.allowed_ports,
            10: model.client_session_key_thumbprint,
            11: model.not_before,
            12: model.expires_at,
            13: model.lease_id,
            14: model.record_sequence,
            15: model.policy_hash,
            16: model.unique_nonce,
        }
    if type(model) is Revocation:
        result = {
            0: model.revocation_version,
            1: model.revocation_id,
            2: model.issuer_key_id,
            3: model.generation,
            4: int(model.target_type),
            5: model.target_id,
            6: int(model.mode),
            7: model.not_before,
            10: int(model.reason_code),
        }
        if model.expires_at is not None:
            result[8] = model.expires_at
        if model.target_sequence is not None:
            result[9] = model.target_sequence
        return result
    if type(model) is ProtocolError:
        result = {
            0: model.error_version,
            1: int(model.error_code),
            2: model.request_id,
            3: model.retryable,
        }
        if model.retry_after_seconds is not None:
            result[4] = model.retry_after_seconds
        return result
    if type(model) is ControlEnvelope:
        result = {
            0: model.protocol_version,
            1: int(model.message_type),
            2: model.request_id,
            3: model.session_id,
            4: model.monotonic_sequence,
            5: thaw_core_value(model.body),
        }
        if model.critical_extension_keys:
            result[6] = model.critical_extension_keys
        result.update({int(key): thaw_core_value(item) for key, item in model.extensions._items})
        return result
    raise TypeError("Unsupported NBSR protocol model")


def encode_model(model: object) -> bytes:
    return encode_deterministic(_model_map(model))


def decode_service_record(wire: bytes) -> ServiceRecord:
    fields, _ = _decode_fields(wire, field_map=SERVICE_RECORD_FIELDS)
    return _construct(ServiceRecord, fields, SERVICE_RECORD_FIELDS)


def decode_route_intent(wire: bytes) -> RouteIntent:
    fields, _ = _decode_fields(wire, field_map=ROUTE_INTENT_FIELDS)
    return _construct(RouteIntent, fields, ROUTE_INTENT_FIELDS)


def decode_route_grant(wire: bytes) -> RouteGrant:
    fields, _ = _decode_fields(wire, field_map=ROUTE_GRANT_FIELDS)
    return _construct(RouteGrant, fields, ROUTE_GRANT_FIELDS)


def decode_revocation(wire: bytes) -> Revocation:
    fields, _ = _decode_fields(
        wire,
        field_map=REVOCATION_FIELDS,
        optional_keys=frozenset({8, 9}),
    )
    if any(key in fields and fields[key] is None for key in (8, 9)):
        raise _unsupported("Optional Revocation fields are omitted, not null")
    optional_values: dict[str, object] = {}
    if 8 not in fields:
        optional_values["expires_at"] = None
    if 9 not in fields:
        optional_values["target_sequence"] = None
    return _construct(
        Revocation,
        fields,
        REVOCATION_FIELDS,
        **optional_values,
    )


def decode_error(wire: bytes) -> ProtocolError:
    fields, _ = _decode_fields(
        wire,
        field_map=PROTOCOL_ERROR_FIELDS,
        optional_keys=frozenset({4}),
    )
    if 4 in fields and fields[4] is None:
        raise _unsupported("Optional ProtocolError fields are omitted, not null")
    return _construct(ProtocolError, fields, PROTOCOL_ERROR_FIELDS)


def decode_envelope(wire: bytes) -> ControlEnvelope:
    fields, extensions = _decode_fields(
        wire,
        field_map=CONTROL_ENVELOPE_FIELDS,
        optional_keys=frozenset({6}),
        allow_extensions=True,
    )
    if 6 in fields and fields[6] == []:
        raise _unsupported("Empty critical-extension lists must be omitted")
    return _construct(
        ControlEnvelope,
        fields,
        CONTROL_ENVELOPE_FIELDS,
        extensions=extensions,
    )
