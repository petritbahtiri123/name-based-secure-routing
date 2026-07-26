from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.fields import (
    MAX_UINT64,
    FrozenMap,
    freeze_uint_map,
    require_bytes,
    require_canonical_name,
    require_ordered_unique_tuple,
    require_port,
    require_sequence,
    require_text_id,
    require_time_window,
    require_timestamp,
    require_uint,
)
from nbsr.protocol.registry import ErrorCode, MessageType


class RevocationTargetType(IntEnum):
    SERVICE_RECORD = 1
    SIGNING_KEY = 2
    ROUTE = 3
    LEASE = 4
    OPERATOR = 5
    EDGE = 6
    ORIGIN_CONNECTOR = 7


class RevocationMode(IntEnum):
    DENY_NEW_USE = 1
    TERMINATE_ACTIVE_USE = 2


class RevocationReason(IntEnum):
    UNSPECIFIED = 1
    KEY_COMPROMISE = 2
    OWNERSHIP_CHANGE = 3
    POLICY_VIOLATION = 4
    ADMINISTRATIVE = 5
    SUPERSEDED = 6


def _require_version(value: object) -> int:
    return require_uint(value, minimum=1, maximum=1, message="Unsupported object version")


def _require_key_id(value: object) -> bytes:
    return require_bytes(value, minimum=1, maximum=64, message="Invalid key identifier")


def _require_id16(value: object) -> bytes:
    return require_bytes(value, minimum=16, maximum=16, message="Invalid 16-byte identifier")


def _require_digest(value: object) -> bytes:
    return require_bytes(value, minimum=32, maximum=32, message="Invalid SHA-256 digest")


def _require_text_ids(value: object, *, maximum_items: int = 16) -> tuple[str, ...]:
    return require_ordered_unique_tuple(
        value,
        item_validator=require_text_id,
        minimum_items=1,
        maximum_items=maximum_items,
        message="Invalid textual identifier set",
    )


def _require_tcp(value: object) -> tuple[str, ...]:
    result = require_ordered_unique_tuple(
        value,
        item_validator=lambda item: require_text_id(item, message="Invalid transport"),
        minimum_items=1,
        maximum_items=1,
        message="Invalid transport set",
    )
    if result != ("tcp",):
        raise ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, "Unsupported transport")
    return result


def _require_route_profile(value: object) -> tuple[str, ...]:
    result = require_ordered_unique_tuple(
        value,
        item_validator=lambda item: require_text_id(item, message="Invalid route profile"),
        minimum_items=1,
        maximum_items=1,
        message="Invalid route profile set",
    )
    if result != ("nbsr-quic-1",):
        raise ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, "Unsupported route profile")
    return result


def _require_ports(value: object) -> tuple[int, ...]:
    return require_ordered_unique_tuple(
        value,
        item_validator=require_port,
        minimum_items=1,
        maximum_items=32,
        message="Invalid port set",
    )


def _enum_value(value: object, enum_type: type[IntEnum], message: str) -> IntEnum:
    if isinstance(value, enum_type):
        return value
    number = require_uint(value, minimum=1, maximum=MAX_UINT64, message=message)
    try:
        return enum_type(number)
    except ValueError as exc:
        raise ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, message) from exc


def _require_current(now: object, start: int, end: int | None, code: ErrorCode) -> None:
    current = require_timestamp(now)
    if current < start or (end is not None and current >= end):
        raise ProtocolViolation(code, "Object is outside its validity interval")


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    record_version: int
    canonical_name: str
    sequence: int
    owner_key_id: bytes
    service_id: str
    destination_operator_id: str
    destination_edge_set: tuple[str, ...]
    origin_connector_id: str
    transports: tuple[str, ...]
    ports: tuple[int, ...]
    route_profiles: tuple[str, ...]
    publication_mode: str
    not_before: int
    not_after: int
    revocation_ref: str

    def __post_init__(self) -> None:
        start, end = require_time_window(
            self.not_before,
            self.not_after,
            maximum_lifetime=604_800,
            code=ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        publication_modes = {
            "legacy",
            "dual-published",
            "nbsr-preferred",
            "nbsr-secure-only",
        }
        if not isinstance(self.publication_mode, str) or self.publication_mode not in publication_modes:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Invalid publication mode",
            )
        object.__setattr__(self, "record_version", _require_version(self.record_version))
        object.__setattr__(self, "canonical_name", require_canonical_name(self.canonical_name))
        object.__setattr__(self, "sequence", require_sequence(self.sequence))
        object.__setattr__(self, "owner_key_id", _require_key_id(self.owner_key_id))
        object.__setattr__(self, "service_id", require_text_id(self.service_id))
        object.__setattr__(
            self,
            "destination_operator_id",
            require_text_id(self.destination_operator_id),
        )
        object.__setattr__(
            self,
            "destination_edge_set",
            _require_text_ids(self.destination_edge_set),
        )
        object.__setattr__(
            self,
            "origin_connector_id",
            require_text_id(self.origin_connector_id),
        )
        object.__setattr__(self, "transports", _require_tcp(self.transports))
        object.__setattr__(self, "ports", _require_ports(self.ports))
        object.__setattr__(self, "route_profiles", _require_route_profile(self.route_profiles))
        object.__setattr__(self, "not_before", start)
        object.__setattr__(self, "not_after", end)
        object.__setattr__(self, "revocation_ref", require_text_id(self.revocation_ref))

    def require_newer_than(self, last_sequence: object) -> None:
        previous = require_uint(last_sequence, maximum=MAX_UINT64, message="Invalid prior sequence")
        if self.sequence <= previous:
            raise ProtocolViolation(ErrorCode.NBSR_E_RECORD_STALE, "Stale ServiceRecord")

    def require_valid_at(self, now: object) -> None:
        _require_current(now, self.not_before, self.not_after, ErrorCode.NBSR_E_RECORD_UNTRUSTED)


@dataclass(frozen=True, slots=True)
class RouteIntent:
    intent_version: int
    resolution_context_digest: bytes
    canonical_name: str
    service_id: str
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_set: tuple[str, ...]
    allowed_transports: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    created_at: int
    expires_at: int
    record_sequence: int
    policy_hash: bytes
    route_id: bytes
    lease_id: bytes

    def __post_init__(self) -> None:
        start, end = require_time_window(
            self.created_at,
            self.expires_at,
            maximum_lifetime=300,
        )
        object.__setattr__(self, "intent_version", _require_version(self.intent_version))
        object.__setattr__(
            self,
            "resolution_context_digest",
            _require_digest(self.resolution_context_digest),
        )
        object.__setattr__(self, "canonical_name", require_canonical_name(self.canonical_name))
        for field_name in (
            "service_id",
            "source_operator_id",
            "source_edge_id",
            "destination_operator_id",
        ):
            object.__setattr__(self, field_name, require_text_id(getattr(self, field_name)))
        object.__setattr__(
            self,
            "destination_edge_set",
            _require_text_ids(self.destination_edge_set),
        )
        object.__setattr__(self, "allowed_transports", _require_tcp(self.allowed_transports))
        object.__setattr__(self, "allowed_ports", _require_ports(self.allowed_ports))
        object.__setattr__(self, "created_at", start)
        object.__setattr__(self, "expires_at", end)
        object.__setattr__(
            self,
            "record_sequence",
            require_sequence(self.record_sequence),
        )
        object.__setattr__(self, "policy_hash", _require_digest(self.policy_hash))
        object.__setattr__(self, "route_id", _require_id16(self.route_id))
        object.__setattr__(self, "lease_id", _require_id16(self.lease_id))

    def require_valid_at(self, now: object) -> None:
        _require_current(now, self.created_at, self.expires_at, ErrorCode.NBSR_E_ROUTE_DENIED)

    def require_record_sequence(self, accepted_sequence: object) -> None:
        expected = require_sequence(accepted_sequence)
        if self.record_sequence != expected:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_RECORD_STALE,
                "RouteIntent record sequence does not match accepted state",
            )


@dataclass(frozen=True, slots=True)
class RouteGrant:
    grant_version: int
    route_id: bytes
    name_digest: bytes
    service_id: str
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_set: tuple[str, ...]
    allowed_transports: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    client_session_key_thumbprint: bytes
    not_before: int
    expires_at: int
    lease_id: bytes
    record_sequence: int
    policy_hash: bytes
    unique_nonce: bytes

    def __post_init__(self) -> None:
        start, end = require_time_window(
            self.not_before,
            self.expires_at,
            maximum_lifetime=600,
            code=ErrorCode.NBSR_E_GRANT_INVALID,
        )
        object.__setattr__(self, "grant_version", _require_version(self.grant_version))
        object.__setattr__(self, "route_id", _require_id16(self.route_id))
        object.__setattr__(self, "name_digest", _require_digest(self.name_digest))
        for field_name in (
            "service_id",
            "source_operator_id",
            "source_edge_id",
            "destination_operator_id",
        ):
            object.__setattr__(self, field_name, require_text_id(getattr(self, field_name)))
        object.__setattr__(
            self,
            "destination_edge_set",
            _require_text_ids(self.destination_edge_set),
        )
        object.__setattr__(self, "allowed_transports", _require_tcp(self.allowed_transports))
        object.__setattr__(self, "allowed_ports", _require_ports(self.allowed_ports))
        object.__setattr__(
            self,
            "client_session_key_thumbprint",
            _require_digest(self.client_session_key_thumbprint),
        )
        object.__setattr__(self, "not_before", start)
        object.__setattr__(self, "expires_at", end)
        object.__setattr__(self, "lease_id", _require_id16(self.lease_id))
        object.__setattr__(
            self,
            "record_sequence",
            require_sequence(self.record_sequence),
        )
        object.__setattr__(self, "policy_hash", _require_digest(self.policy_hash))
        object.__setattr__(self, "unique_nonce", _require_id16(self.unique_nonce))

    def require_valid_at(self, now: object) -> None:
        _require_current(now, self.not_before, self.expires_at, ErrorCode.NBSR_E_GRANT_EXPIRED)

    def require_record_sequence(self, accepted_sequence: object) -> None:
        expected = require_sequence(accepted_sequence)
        if self.record_sequence != expected:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_GRANT_INVALID,
                "RouteGrant record sequence does not match accepted state",
            )


@dataclass(frozen=True, slots=True)
class Revocation:
    revocation_version: int
    revocation_id: bytes
    issuer_key_id: bytes
    generation: int
    target_type: RevocationTargetType
    target_id: bytes
    mode: RevocationMode
    not_before: int
    expires_at: int | None
    target_sequence: int | None
    reason_code: RevocationReason

    def __post_init__(self) -> None:
        target_type = _enum_value(
            self.target_type,
            RevocationTargetType,
            "Invalid revocation target type",
        )
        mode = _enum_value(self.mode, RevocationMode, "Invalid revocation mode")
        reason = _enum_value(self.reason_code, RevocationReason, "Invalid revocation reason")
        start = require_timestamp(self.not_before)
        end: int | None = None
        if self.expires_at is not None:
            _, end = require_time_window(start, self.expires_at, maximum_lifetime=None)
        target_sequence: int | None = None
        if self.target_sequence is not None:
            target_sequence = require_sequence(self.target_sequence)
            if target_type is not RevocationTargetType.SERVICE_RECORD:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                    "target_sequence is only valid for ServiceRecord revocations",
                )
        if reason is RevocationReason.KEY_COMPROMISE and end is not None:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Key-compromise revocations cannot expire automatically",
            )
        object.__setattr__(self, "revocation_version", _require_version(self.revocation_version))
        object.__setattr__(self, "revocation_id", _require_id16(self.revocation_id))
        object.__setattr__(self, "issuer_key_id", _require_key_id(self.issuer_key_id))
        object.__setattr__(self, "generation", require_sequence(self.generation))
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", _require_digest(self.target_id))
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "not_before", start)
        object.__setattr__(self, "expires_at", end)
        object.__setattr__(self, "target_sequence", target_sequence)
        object.__setattr__(self, "reason_code", reason)

    def require_newer_generation(self, highest_accepted_generation: object) -> None:
        previous = require_uint(
            highest_accepted_generation,
            maximum=MAX_UINT64,
            message="Invalid revocation generation tombstone",
        )
        if self.generation <= previous:
            raise ProtocolViolation(ErrorCode.NBSR_E_RECORD_STALE, "Stale revocation generation")

    def require_valid_at(self, now: object) -> None:
        _require_current(now, self.not_before, self.expires_at, ErrorCode.NBSR_E_RECORD_REVOKED)

    def require_target_sequence(self, target_sequence: object) -> None:
        if self.target_sequence is None:
            return
        expected = require_sequence(target_sequence)
        if self.target_sequence != expected:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_RECORD_STALE,
                "Revocation target sequence does not match accepted state",
            )


@dataclass(frozen=True, slots=True)
class ProtocolError:
    error_version: int
    error_code: ErrorCode
    request_id: bytes
    retryable: bool
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.error_code, ErrorCode):
            error_code = self.error_code
        else:
            number = require_uint(
                self.error_code,
                minimum=1,
                maximum=19,
                message="Invalid protocol error code",
            )
            try:
                error_code = ErrorCode(number)
            except ValueError as exc:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                    "Unknown protocol error code",
                ) from exc
        if type(self.retryable) is not bool:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "retryable must be a CBOR boolean",
            )
        retry_after: int | None = None
        if self.retry_after_seconds is not None:
            retry_after = require_uint(
                self.retry_after_seconds,
                minimum=1,
                maximum=3_600,
                message="Invalid retry-after value",
            )
            if not self.retryable:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                    "Non-retryable errors cannot carry retry-after",
                )
        object.__setattr__(self, "error_version", _require_version(self.error_version))
        object.__setattr__(self, "error_code", error_code)
        object.__setattr__(self, "request_id", _require_id16(self.request_id))
        object.__setattr__(self, "retry_after_seconds", retry_after)


@dataclass(frozen=True, slots=True)
class ControlEnvelope:
    protocol_version: int
    message_type: MessageType
    request_id: bytes
    session_id: bytes
    monotonic_sequence: int
    body: FrozenMap
    critical_extension_keys: tuple[int, ...] = ()
    extensions: FrozenMap = FrozenMap(())

    def __post_init__(self) -> None:
        if isinstance(self.message_type, MessageType):
            message_type = self.message_type
        else:
            number = require_uint(
                self.message_type,
                minimum=1,
                maximum=17,
                message="Invalid message type",
            )
            try:
                message_type = MessageType(number)
            except ValueError as exc:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                    "Unknown message type",
                ) from exc
        body = freeze_uint_map(self.body, minimum_key=0, maximum_pairs=128)
        extensions = freeze_uint_map(
            self.extensions,
            minimum_key=1000,
            maximum_pairs=122,
        )
        critical = require_ordered_unique_tuple(
            self.critical_extension_keys,
            item_validator=lambda item: require_uint(
                item,
                minimum=1000,
                message="Invalid critical extension key",
            ),
            minimum_items=0,
            maximum_items=32,
            message="Invalid critical extension key list",
        )
        if any(key not in extensions for key in critical):
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Critical extension key is absent",
            )
        if critical:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Core v0.1 recognizes no critical extensions",
            )
        object.__setattr__(self, "protocol_version", _require_version(self.protocol_version))
        object.__setattr__(self, "message_type", message_type)
        object.__setattr__(self, "request_id", _require_id16(self.request_id))
        object.__setattr__(self, "session_id", _require_id16(self.session_id))
        object.__setattr__(
            self,
            "monotonic_sequence",
            require_sequence(self.monotonic_sequence),
        )
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "critical_extension_keys", critical)
        object.__setattr__(self, "extensions", extensions)

    def require_newer_than(self, last_sequence: object) -> None:
        previous = require_uint(last_sequence, maximum=MAX_UINT64, message="Invalid prior sequence")
        if self.monotonic_sequence <= previous:
            raise ProtocolViolation(ErrorCode.NBSR_E_REPLAY, "Stale control sequence")
