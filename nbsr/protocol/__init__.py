"""Stable, dependency-light NBSR Protocol Core v0.1 public API."""

from nbsr.protocol.cbor import DEFAULT_LIMITS, CborLimits, decode_deterministic, encode_deterministic
from nbsr.protocol.cose import VerifiedSign1, require_kid, sign1, verify_sign1
from nbsr.protocol.errors import InvalidTransition, ProtocolViolation
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
from nbsr.protocol.registry import ErrorCode, MessageType, ProtocolVersion
from nbsr.protocol.schemas import (
    decode_envelope,
    decode_error,
    decode_revocation,
    decode_route_grant,
    decode_route_intent,
    decode_service_record,
    encode_model,
)
from nbsr.protocol.states import (
    ConnectorState,
    ResolutionState,
    StreamState,
    TunnelState,
    transition,
)


__all__ = [
    "CborLimits",
    "ConnectorState",
    "ControlEnvelope",
    "DEFAULT_LIMITS",
    "ErrorCode",
    "InvalidTransition",
    "MessageType",
    "ProtocolError",
    "ProtocolVersion",
    "ProtocolViolation",
    "ResolutionState",
    "Revocation",
    "RevocationMode",
    "RevocationReason",
    "RevocationTargetType",
    "RouteGrant",
    "RouteIntent",
    "ServiceRecord",
    "StreamState",
    "TunnelState",
    "VerifiedSign1",
    "decode_deterministic",
    "decode_envelope",
    "decode_error",
    "decode_revocation",
    "decode_route_grant",
    "decode_route_intent",
    "decode_service_record",
    "encode_deterministic",
    "encode_model",
    "require_kid",
    "sign1",
    "transition",
    "verify_sign1",
]
