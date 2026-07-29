from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.fields import (
    FrozenMap,
    freeze_core_value,
    require_bytes,
    require_port,
    require_sequence,
    require_text_id,
    require_timestamp,
    require_uint,
)
from nbsr.protocol.models import ProtocolError, RouteGrant
from nbsr.protocol.registry import ErrorCode, MessageType
from nbsr.protocol.schemas import decode_error, decode_route_grant
from scripts.core_v02_vectors.crypto import (
    encode_route_open_transcript,
    verify_cose_sign1,
    verify_route_open,
)


class UnknownCoreVersion(ValueError):
    """Signals a generic close when no safe version-specific error exists."""


_BODY_FIELDS = {
    MessageType.CLIENT_HELLO: {
        0: "body_version",
        1: "source_operator_id",
        2: "source_edge_id",
        3: "destination_operator_id",
        4: "destination_edge_id",
        5: "client_nonce",
        6: "client_session_public_key",
        7: "sent_at",
    },
    MessageType.EDGE_HELLO: {
        0: "body_version",
        1: "source_edge_id",
        2: "destination_edge_id",
        3: "client_nonce",
        4: "edge_nonce",
        5: "client_session_key_thumbprint",
        6: "accepted_at",
    },
    MessageType.ROUTE_OPEN: {
        0: "body_version",
        1: "channel_id",
        2: "route_grant",
        3: "edge_nonce",
        4: "requested_transport",
        5: "requested_port",
        6: "opened_at",
        7: "proof_signature",
    },
    MessageType.ROUTE_ACCEPT: {
        0: "body_version",
        1: "channel_id",
        2: "route_id",
        3: "route_grant_digest",
        4: "accepted_at",
    },
    MessageType.ROUTE_REJECT: {
        0: "body_version",
        1: "channel_id",
        2: "route_id",
        3: "route_grant_digest",
        4: "protocol_error",
    },
    MessageType.STREAM_OPEN: {
        0: "body_version",
        1: "quic_stream_id",
        2: "channel_id",
        3: "route_id",
        4: "route_grant_digest",
        5: "transport",
        6: "port",
    },
    MessageType.STREAM_ACCEPT: {
        0: "body_version",
        1: "quic_stream_id",
        2: "channel_id",
        3: "route_id",
        4: "accepted_at",
    },
    MessageType.STREAM_REJECT: {
        0: "body_version",
        1: "quic_stream_id",
        2: "channel_id",
        3: "route_id",
        4: "protocol_error",
    },
}
BODY_FIELDS: Mapping[MessageType, Mapping[int, str]] = MappingProxyType(
    {message_type: MappingProxyType(fields) for message_type, fields in _BODY_FIELDS.items()}
)

SOURCE_MESSAGES = frozenset(
    {
        MessageType.CLIENT_HELLO,
        MessageType.ROUTE_OPEN,
        MessageType.STREAM_OPEN,
    }
)
DESTINATION_MESSAGES = frozenset(
    {
        MessageType.EDGE_HELLO,
        MessageType.ROUTE_ACCEPT,
        MessageType.ROUTE_REJECT,
        MessageType.STREAM_ACCEPT,
        MessageType.STREAM_REJECT,
    }
)


def _violation(code: ErrorCode, message: str) -> ProtocolViolation:
    return ProtocolViolation(code, message)


@dataclass(frozen=True, slots=True)
class ReferenceContext:
    expected_core_version: int
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_id: str
    route_grant_issuer_public_key: bytes
    route_grant_kid: bytes
    client_session_public_key: bytes
    now: int
    accepted_record_sequence: int
    max_clock_skew_seconds: int
    expected_policy_hash: bytes | None = None

    def __post_init__(self) -> None:
        if type(self.expected_core_version) is not int or self.expected_core_version not in {
            1,
            2,
        }:
            raise ValueError("expected_core_version must be one or two")
        for name in (
            "source_operator_id",
            "source_edge_id",
            "destination_operator_id",
            "destination_edge_id",
        ):
            require_text_id(getattr(self, name))
        require_bytes(
            self.route_grant_issuer_public_key,
            minimum=32,
            maximum=32,
        )
        require_bytes(self.route_grant_kid, minimum=1, maximum=64)
        require_bytes(self.client_session_public_key, minimum=32, maximum=32)
        require_timestamp(self.now)
        require_sequence(self.accepted_record_sequence)
        require_uint(
            self.max_clock_skew_seconds,
            maximum=300,
            message="Invalid clock skew",
        )
        if self.expected_policy_hash is not None:
            require_bytes(self.expected_policy_hash, minimum=32, maximum=32)


@dataclass(frozen=True, slots=True)
class VerifiedEnvelope:
    protocol_version: int
    message_type: MessageType
    request_id: bytes
    session_id: bytes
    monotonic_sequence: int
    body: FrozenMap
    destination_edge_id: str
    route_grant: RouteGrant | None = None
    route_grant_digest: bytes | None = None
    protocol_error: ProtocolError | None = None


@dataclass(frozen=True, slots=True)
class ConformanceState:
    transport_session_active: bool = False
    transport_session_closed: bool = False
    session_id: bytes | None = None
    source_sequence: int = 0
    destination_sequence: int = 0
    client_request_id: bytes | None = None
    client_nonce: bytes | None = None
    edge_nonce: bytes | None = None
    client_session_public_key: bytes | None = None
    seen_request_ids: frozenset[bytes] = frozenset()
    seen_client_nonces: frozenset[bytes] = frozenset()
    seen_edge_nonces: frozenset[bytes] = frozenset()
    seen_grant_nonces: frozenset[bytes] = frozenset()
    active_channel_ids: frozenset[bytes] = frozenset()
    active_stream_ids: frozenset[int] = frozenset()
    pending_channel_id: bytes | None = None
    pending_route_id: bytes | None = None
    pending_grant_digest: bytes | None = None
    pending_route_request_id: bytes | None = None
    pending_transport: str | None = None
    pending_port: int | None = None
    pending_stream_id: int | None = None
    pending_stream_request_id: bytes | None = None


def _require_map(value: object, name: str) -> dict[int, object]:
    if not isinstance(value, dict):
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            f"{name} must be a map",
        )
    if any(type(key) is not int or key < 0 for key in value):
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            f"{name} keys must be unsigned integers",
        )
    return value


def _require_exact_keys(
    value: dict[int, object],
    expected: Mapping[int, str],
) -> None:
    if set(value) != set(expected):
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            "Unknown or missing Core v0.2 field",
        )


def _require_id16(value: object, message: str) -> bytes:
    return require_bytes(
        value,
        minimum=16,
        maximum=16,
        message=message,
    )


def _require_digest(value: object, message: str) -> bytes:
    return require_bytes(
        value,
        minimum=32,
        maximum=32,
        message=message,
    )


def _require_nonzero(value: object, length: int, message: str) -> bytes:
    result = require_bytes(
        value,
        minimum=length,
        maximum=length,
        message=message,
    )
    if not any(result):
        raise _violation(ErrorCode.NBSR_E_REPLAY, message)
    return result


def _require_near_now(value: object, context: ReferenceContext) -> int:
    timestamp = require_timestamp(value)
    if abs(timestamp - context.now) > context.max_clock_skew_seconds:
        raise _violation(
            ErrorCode.NBSR_E_ROUTE_DENIED,
            "Timestamp is outside bounded clock skew",
        )
    return timestamp


def _require_equal(actual: object, expected: object, message: str) -> None:
    if actual != expected or type(actual) is not type(expected):
        raise _violation(ErrorCode.NBSR_E_ROUTE_DENIED, message)


def _validate_protocol_error(
    value: object,
    request_id: bytes,
) -> ProtocolError:
    raw = _require_map(value, "ProtocolError")
    error = decode_error(encode_deterministic(raw))
    if error.request_id != request_id:
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            "ProtocolError request ID mismatch",
        )
    return error


def _validate_body(
    message_type: MessageType,
    body: object,
    context: ReferenceContext,
    request_id: bytes,
    session_id: bytes,
) -> tuple[dict[int, object], RouteGrant | None, bytes | None, ProtocolError | None]:
    value = _require_map(body, "message body")
    fields = BODY_FIELDS[message_type]
    _require_exact_keys(value, fields)
    require_uint(
        value[0],
        minimum=1,
        maximum=1,
        message="Invalid body version",
    )
    grant: RouteGrant | None = None
    grant_digest: bytes | None = None
    protocol_error: ProtocolError | None = None

    if message_type is MessageType.CLIENT_HELLO:
        _require_equal(value[1], context.source_operator_id, "Source operator mismatch")
        _require_equal(value[2], context.source_edge_id, "Source edge mismatch")
        _require_equal(
            value[3],
            context.destination_operator_id,
            "Destination operator mismatch",
        )
        _require_equal(
            value[4],
            context.destination_edge_id,
            "Destination edge mismatch",
        )
        _require_nonzero(value[5], 32, "Invalid client nonce")
        session_public_key = require_bytes(value[6], minimum=32, maximum=32)
        _require_equal(
            session_public_key,
            context.client_session_public_key,
            "Session public key mismatch",
        )
        _require_near_now(value[7], context)
    elif message_type is MessageType.EDGE_HELLO:
        _require_equal(value[1], context.source_edge_id, "Source edge mismatch")
        _require_equal(
            value[2],
            context.destination_edge_id,
            "Destination edge mismatch",
        )
        _require_nonzero(value[3], 32, "Invalid echoed client nonce")
        _require_nonzero(value[4], 32, "Invalid edge nonce")
        _require_digest(value[5], "Invalid session key thumbprint")
        _require_near_now(value[6], context)
    elif message_type is MessageType.ROUTE_OPEN:
        channel_id = _require_nonzero(value[1], 16, "Invalid channel ID")
        grant_wire = require_bytes(
            value[2],
            minimum=1,
            maximum=32_768,
            message="Invalid RouteGrant wrapper",
        )
        edge_nonce = _require_nonzero(value[3], 32, "Invalid edge nonce")
        transport = require_text_id(value[4], message="Invalid transport")
        if transport != "tcp":
            raise _violation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Unsupported transport",
            )
        port = require_port(value[5])
        opened_at = _require_near_now(value[6], context)
        signature = require_bytes(value[7], minimum=64, maximum=64)
        payload = verify_cose_sign1(
            grant_wire,
            context.route_grant_issuer_public_key,
            context.route_grant_kid,
        )
        grant = decode_route_grant(payload)
        grant.require_valid_at(context.now)
        grant.require_record_sequence(context.accepted_record_sequence)
        if grant.client_session_key_thumbprint != sha256(context.client_session_public_key).digest():
            raise _violation(
                ErrorCode.NBSR_E_GRANT_INVALID,
                "RouteGrant session key thumbprint mismatch",
            )
        _require_equal(
            grant.source_operator_id,
            context.source_operator_id,
            "RouteGrant source operator mismatch",
        )
        _require_equal(
            grant.source_edge_id,
            context.source_edge_id,
            "RouteGrant source edge mismatch",
        )
        _require_equal(
            grant.destination_operator_id,
            context.destination_operator_id,
            "RouteGrant destination operator mismatch",
        )
        if context.destination_edge_id not in grant.destination_edge_set:
            raise _violation(
                ErrorCode.NBSR_E_GRANT_INVALID,
                "RouteGrant destination edge mismatch",
            )
        if transport not in grant.allowed_transports or port not in grant.allowed_ports:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Requested transport or port is not authorized",
            )
        if context.expected_policy_hash is not None and grant.policy_hash != context.expected_policy_hash:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Policy hash mismatch",
            )
        grant_digest = sha256(grant_wire).digest()
        transcript = encode_route_open_transcript(
            protocol_version=2,
            session_id=session_id,
            request_id=request_id,
            channel_id=channel_id,
            route_id=grant.route_id,
            service_id=grant.service_id,
            destination_edge_id=context.destination_edge_id,
            edge_nonce=edge_nonce,
            transport=transport,
            port=port,
            route_grant_digest=grant_digest,
            opened_at=opened_at,
        )
        verify_route_open(
            transcript,
            signature,
            context.client_session_public_key,
        )
    elif message_type in {MessageType.ROUTE_ACCEPT, MessageType.ROUTE_REJECT}:
        _require_id16(value[1], "Invalid channel ID")
        _require_id16(value[2], "Invalid route ID")
        grant_digest = _require_digest(value[3], "Invalid RouteGrant digest")
        if message_type is MessageType.ROUTE_ACCEPT:
            _require_near_now(value[4], context)
        else:
            protocol_error = _validate_protocol_error(value[4], request_id)
    elif message_type is MessageType.STREAM_OPEN:
        stream_id = require_uint(
            value[1],
            minimum=4,
            maximum=2**62 - 1,
            message="Invalid QUIC stream ID",
        )
        if stream_id % 4:
            raise _violation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "STREAM_OPEN requires a source bidirectional stream",
            )
        _require_id16(value[2], "Invalid channel ID")
        _require_id16(value[3], "Invalid route ID")
        grant_digest = _require_digest(value[4], "Invalid RouteGrant digest")
        transport = require_text_id(value[5], message="Invalid transport")
        if transport != "tcp":
            raise _violation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Unsupported transport",
            )
        require_port(value[6])
    else:
        stream_id = require_uint(
            value[1],
            minimum=4,
            maximum=2**62 - 1,
            message="Invalid QUIC stream ID",
        )
        if stream_id % 4:
            raise _violation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Invalid source bidirectional stream ID",
            )
        _require_id16(value[2], "Invalid channel ID")
        _require_id16(value[3], "Invalid route ID")
        if message_type is MessageType.STREAM_ACCEPT:
            _require_near_now(value[4], context)
        else:
            protocol_error = _validate_protocol_error(value[4], request_id)
    return value, grant, grant_digest, protocol_error


def verify_envelope(
    wire: bytes,
    context: ReferenceContext,
) -> VerifiedEnvelope:
    value = _require_map(decode_deterministic(wire), "ControlEnvelope")
    if set(value) != {0, 1, 2, 3, 4, 5}:
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            "Unknown, missing, or unsupported envelope field",
        )
    version = require_uint(value[0], message="Invalid protocol version")
    if version not in {1, 2}:
        raise UnknownCoreVersion("Unsupported Core version")
    if version != context.expected_core_version or version != 2:
        raise _violation(
            ErrorCode.NBSR_E_DOWNGRADE,
            "Core version mismatch",
        )
    try:
        message_type = MessageType(require_uint(value[1], minimum=1, maximum=17))
    except (ValueError, ProtocolViolation) as exc:
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            "Unknown message code",
        ) from exc
    if message_type not in BODY_FIELDS:
        raise _violation(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            "No approved Core v0.2 body schema",
        )
    request_id = _require_id16(value[2], "Invalid request ID")
    session_id = _require_id16(value[3], "Invalid session ID")
    sequence = require_sequence(value[4], message="Invalid monotonic sequence")
    body, grant, grant_digest, protocol_error = _validate_body(
        message_type,
        value[5],
        context,
        request_id,
        session_id,
    )
    frozen = freeze_core_value(body)
    if not isinstance(frozen, FrozenMap):
        raise AssertionError("validated body did not freeze as a map")
    return VerifiedEnvelope(
        protocol_version=version,
        message_type=message_type,
        request_id=request_id,
        session_id=session_id,
        monotonic_sequence=sequence,
        body=frozen,
        destination_edge_id=context.destination_edge_id,
        route_grant=grant,
        route_grant_digest=grant_digest,
        protocol_error=protocol_error,
    )


def _body(envelope: VerifiedEnvelope, key: int) -> object:
    return envelope.body[key]


def _require_next_sequence(
    state: ConformanceState,
    envelope: VerifiedEnvelope,
) -> None:
    previous = state.source_sequence if envelope.message_type in SOURCE_MESSAGES else state.destination_sequence
    if envelope.monotonic_sequence != previous + 1:
        raise _violation(
            ErrorCode.NBSR_E_REPLAY,
            "Monotonic sequence is stale or skipped",
        )


def apply_envelope(
    state: ConformanceState,
    envelope: VerifiedEnvelope,
) -> ConformanceState:
    if state.transport_session_closed:
        raise _violation(ErrorCode.NBSR_E_ROUTE_DENIED, "Session is closed")
    if state.session_id is not None and envelope.session_id != state.session_id:
        raise _violation(ErrorCode.NBSR_E_ROUTE_DENIED, "Session ID mismatch")
    if envelope.message_type in SOURCE_MESSAGES and (envelope.request_id in state.seen_request_ids):
        raise _violation(ErrorCode.NBSR_E_REPLAY, "Request replay")
    if envelope.message_type is MessageType.ROUTE_OPEN and not state.transport_session_active:
        raise _violation(
            ErrorCode.NBSR_E_ROUTE_DENIED,
            "Route admission requires accepted session",
        )
    if envelope.message_type is MessageType.STREAM_OPEN and _body(envelope, 2) not in state.active_channel_ids:
        raise _violation(
            ErrorCode.NBSR_E_ROUTE_DENIED,
            "Stream requires an active Service Channel",
        )
    _require_next_sequence(state, envelope)

    if envelope.message_type is MessageType.CLIENT_HELLO:
        nonce = _body(envelope, 5)
        if nonce in state.seen_client_nonces:
            raise _violation(ErrorCode.NBSR_E_REPLAY, "Client nonce replay")
        return replace(
            state,
            session_id=envelope.session_id,
            source_sequence=envelope.monotonic_sequence,
            client_request_id=envelope.request_id,
            client_nonce=nonce,
            client_session_public_key=_body(envelope, 6),
            seen_request_ids=state.seen_request_ids | {envelope.request_id},
            seen_client_nonces=state.seen_client_nonces | {nonce},
        )

    if envelope.message_type is MessageType.EDGE_HELLO:
        if state.client_nonce is None:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "EDGE_HELLO before CLIENT_HELLO",
            )
        if envelope.request_id != state.client_request_id:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "EDGE_HELLO request mismatch",
            )
        if _body(envelope, 3) != state.client_nonce:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Client nonce echo mismatch",
            )
        if _body(envelope, 5) != sha256(state.client_session_public_key or b"").digest():
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Session key thumbprint mismatch",
            )
        edge_nonce = _body(envelope, 4)
        if edge_nonce in state.seen_edge_nonces:
            raise _violation(ErrorCode.NBSR_E_REPLAY, "Edge nonce replay")
        return replace(
            state,
            transport_session_active=True,
            destination_sequence=envelope.monotonic_sequence,
            edge_nonce=edge_nonce,
            seen_edge_nonces=state.seen_edge_nonces | {edge_nonce},
        )

    if envelope.message_type is MessageType.ROUTE_OPEN:
        if not state.transport_session_active or state.edge_nonce is None:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Route admission requires accepted session",
            )
        if _body(envelope, 3) != state.edge_nonce:
            raise _violation(
                ErrorCode.NBSR_E_PROOF_INVALID,
                "Edge nonce binding mismatch",
            )
        if envelope.route_grant is None or envelope.route_grant_digest is None:
            raise AssertionError("verified Route Open lacks grant metadata")
        if state.client_session_public_key is None:
            raise _violation(
                ErrorCode.NBSR_E_PROOF_INVALID,
                "Session key is unavailable",
            )
        transcript = encode_route_open_transcript(
            protocol_version=2,
            session_id=envelope.session_id,
            request_id=envelope.request_id,
            channel_id=_body(envelope, 1),
            route_id=envelope.route_grant.route_id,
            service_id=envelope.route_grant.service_id,
            destination_edge_id=envelope.destination_edge_id,
            edge_nonce=_body(envelope, 3),
            transport=_body(envelope, 4),
            port=_body(envelope, 5),
            route_grant_digest=envelope.route_grant_digest,
            opened_at=_body(envelope, 6),
        )
        verify_route_open(
            transcript,
            _body(envelope, 7),
            state.client_session_public_key,
        )
        nonce = envelope.route_grant.unique_nonce
        channel_id = _body(envelope, 1)
        if nonce in state.seen_grant_nonces or channel_id in state.active_channel_ids:
            raise _violation(ErrorCode.NBSR_E_REPLAY, "Grant or channel replay")
        return replace(
            state,
            source_sequence=envelope.monotonic_sequence,
            seen_request_ids=state.seen_request_ids | {envelope.request_id},
            seen_grant_nonces=state.seen_grant_nonces | {nonce},
            pending_channel_id=channel_id,
            pending_route_id=envelope.route_grant.route_id,
            pending_grant_digest=envelope.route_grant_digest,
            pending_route_request_id=envelope.request_id,
            pending_transport=_body(envelope, 4),
            pending_port=_body(envelope, 5),
        )

    if envelope.message_type in {
        MessageType.ROUTE_ACCEPT,
        MessageType.ROUTE_REJECT,
    }:
        if state.pending_channel_id is None or envelope.request_id != state.pending_route_request_id:
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Route response without matching request",
            )
        if (
            _body(envelope, 1) != state.pending_channel_id
            or _body(envelope, 2) != state.pending_route_id
            or _body(envelope, 3) != state.pending_grant_digest
        ):
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Route response binding mismatch",
            )
        if envelope.message_type is MessageType.ROUTE_REJECT:
            return replace(
                state,
                destination_sequence=envelope.monotonic_sequence,
                pending_channel_id=None,
                pending_route_id=None,
                pending_grant_digest=None,
                pending_route_request_id=None,
                pending_transport=None,
                pending_port=None,
            )
        return replace(
            state,
            destination_sequence=envelope.monotonic_sequence,
            active_channel_ids=state.active_channel_ids | {state.pending_channel_id},
        )

    if envelope.message_type is MessageType.STREAM_OPEN:
        if (
            _body(envelope, 2) not in state.active_channel_ids
            or _body(envelope, 3) != state.pending_route_id
            or _body(envelope, 4) != state.pending_grant_digest
            or _body(envelope, 5) != state.pending_transport
            or _body(envelope, 6) != state.pending_port
        ):
            raise _violation(
                ErrorCode.NBSR_E_ROUTE_DENIED,
                "Stream is not bound to an active route",
            )
        stream_id = _body(envelope, 1)
        if stream_id in state.active_stream_ids:
            raise _violation(ErrorCode.NBSR_E_REPLAY, "Stream replay")
        return replace(
            state,
            source_sequence=envelope.monotonic_sequence,
            seen_request_ids=state.seen_request_ids | {envelope.request_id},
            pending_stream_id=stream_id,
            pending_stream_request_id=envelope.request_id,
        )

    if (
        state.pending_stream_id is None
        or envelope.request_id != state.pending_stream_request_id
        or _body(envelope, 1) != state.pending_stream_id
        or _body(envelope, 2) not in state.active_channel_ids
        or _body(envelope, 3) != state.pending_route_id
    ):
        raise _violation(
            ErrorCode.NBSR_E_ROUTE_DENIED,
            "Stream response without matching request",
        )
    if envelope.message_type is MessageType.STREAM_REJECT:
        return replace(
            state,
            destination_sequence=envelope.monotonic_sequence,
            pending_stream_id=None,
            pending_stream_request_id=None,
        )
    return replace(
        state,
        destination_sequence=envelope.monotonic_sequence,
        active_stream_ids=state.active_stream_ids | {state.pending_stream_id},
    )
