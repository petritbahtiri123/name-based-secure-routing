"""Internal Derived OriginSet model.

This module is deliberately not a wire format. Its digest is an internal
comparison value, not a Core v0.1 or Core v0.2 serialization.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


MAX_UINT64 = 2**64 - 1
MAX_TIMESTAMP = 253_402_300_799
MAX_ENDPOINTS = 32
MAX_PORT = 65_535
MAX_ENDPOINT_METADATA = 65_535
TEXT_ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
_DIGEST_DOMAIN = "nbsr-derived-originset-digest-v1"


class OriginSetError(ValueError):
    """Base error for the internal OriginSet model."""


class OriginSetValidationError(OriginSetError):
    """The candidate is malformed or violates the approved D7 model."""


class OriginSetStaleError(OriginSetError):
    """The candidate is expired or older than accepted security state."""


class OriginSetEquivocationError(OriginSetError):
    """The same version was presented with different normalized content."""


class PublicationMode(StrEnum):
    LEGACY_DNS = "LEGACY_DNS"
    HYBRID = "HYBRID"
    NBSR_NATIVE = "NBSR_NATIVE"


class AuthorityKind(StrEnum):
    LOCAL_DERIVATION = "local-derivation"
    OWNER = "owner"
    DELEGATED = "delegated"


class DnssecStatus(StrEnum):
    SECURE = "secure"
    INSECURE = "insecure"
    BOGUS = "bogus"
    INDETERMINATE = "indeterminate"


class OriginTransport(StrEnum):
    TCP = "tcp"


def _require_uint(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise OriginSetValidationError(
            f"{name} must be an integer in [{minimum}, {maximum}]",
        )
    return value


def _require_text_id(name: str, value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 64 or not value.isascii() or TEXT_ID_PATTERN.fullmatch(value) is None:
        raise OriginSetValidationError(f"{name} is not a valid textual ID")
    return value


def _require_optional_text_id(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _require_text_id(name, value)


def _require_enum[T: StrEnum](
    name: str,
    value: object,
    enum_type: type[T],
) -> T:
    if isinstance(value, enum_type):
        return value
    if type(value) is str:
        try:
            return enum_type(value)
        except ValueError:
            pass
    raise OriginSetValidationError(f"{name} is unsupported")


def _require_bytes(
    name: str,
    value: object,
    *,
    minimum: int,
    maximum: int,
) -> bytes:
    if type(value) is not bytes or not minimum <= len(value) <= maximum:
        raise OriginSetValidationError(
            f"{name} must be bytes with length in [{minimum}, {maximum}]",
        )
    return bytes(value)


@dataclass(frozen=True, slots=True)
class OriginEndpoint:
    """One normalized internal origin candidate for the initial TCP profile."""

    address: str
    port: int
    transport: OriginTransport | str = OriginTransport.TCP
    priority: int = 0
    weight: int = 0
    region: str | None = None
    locality: str | None = None

    def __post_init__(self) -> None:
        if type(self.address) is not str:
            raise OriginSetValidationError("address must be an IP literal string")
        try:
            normalized_address = str(ipaddress.ip_address(self.address))
        except ValueError as exc:
            raise OriginSetValidationError(
                "address must be a valid IP literal",
            ) from exc

        object.__setattr__(self, "address", normalized_address)
        object.__setattr__(
            self,
            "port",
            _require_uint("port", self.port, minimum=1, maximum=MAX_PORT),
        )
        object.__setattr__(
            self,
            "transport",
            _require_enum("transport", self.transport, OriginTransport),
        )
        object.__setattr__(
            self,
            "priority",
            _require_uint(
                "priority",
                self.priority,
                minimum=0,
                maximum=MAX_ENDPOINT_METADATA,
            ),
        )
        object.__setattr__(
            self,
            "weight",
            _require_uint(
                "weight",
                self.weight,
                minimum=0,
                maximum=MAX_ENDPOINT_METADATA,
            ),
        )
        object.__setattr__(
            self,
            "region",
            _require_optional_text_id("region", self.region),
        )
        object.__setattr__(
            self,
            "locality",
            _require_optional_text_id("locality", self.locality),
        )

    def _sort_key(self) -> tuple[object, ...]:
        address = ipaddress.ip_address(self.address)
        return (
            address.version,
            address.packed,
            self.port,
            self.transport.value,
            self.priority,
            self.weight,
            self.region or "",
            self.locality or "",
        )

    def _digest_value(self) -> list[object]:
        return [
            self.address,
            self.port,
            self.transport.value,
            self.priority,
            self.weight,
            self.region,
            self.locality,
        ]


_ALLOWED_AUTHORITIES = {
    PublicationMode.LEGACY_DNS: frozenset({AuthorityKind.LOCAL_DERIVATION}),
    PublicationMode.HYBRID: frozenset(
        {AuthorityKind.LOCAL_DERIVATION, AuthorityKind.DELEGATED},
    ),
    PublicationMode.NBSR_NATIVE: frozenset(
        {AuthorityKind.OWNER, AuthorityKind.DELEGATED},
    ),
}


@dataclass(frozen=True, slots=True)
class DerivedOriginSet:
    """Bounded internal reachability state approved by D7."""

    service_id: str
    service_record_generation: int
    origin_generation: int
    sequence: int
    endpoints: tuple[OriginEndpoint, ...]
    publication_mode: PublicationMode | str
    authority_kind: AuthorityKind | str
    issuer_id: bytes
    not_before: int
    expires_at: int
    dnssec_status: DnssecStatus | str | None = None
    previous_digest: bytes | None = None
    content_digest: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "service_id",
            _require_text_id("service_id", self.service_id),
        )
        for name in (
            "service_record_generation",
            "origin_generation",
            "sequence",
        ):
            object.__setattr__(
                self,
                name,
                _require_uint(
                    name,
                    getattr(self, name),
                    minimum=1,
                    maximum=MAX_UINT64,
                ),
            )

        if type(self.endpoints) not in (list, tuple):
            raise OriginSetValidationError("endpoints must be a list or tuple")
        if not 1 <= len(self.endpoints) <= MAX_ENDPOINTS:
            raise OriginSetValidationError(
                f"endpoints must contain between 1 and {MAX_ENDPOINTS} values",
            )
        if any(type(item) is not OriginEndpoint for item in self.endpoints):
            raise OriginSetValidationError(
                "endpoints must contain OriginEndpoint values",
            )
        normalized_endpoints = tuple(
            sorted(self.endpoints, key=OriginEndpoint._sort_key),
        )
        identities = {(item.address, item.port, item.transport) for item in normalized_endpoints}
        if len(identities) != len(normalized_endpoints):
            raise OriginSetValidationError(
                "endpoint address, port, and transport identities must be unique",
            )
        object.__setattr__(self, "endpoints", normalized_endpoints)

        mode = _require_enum(
            "publication_mode",
            self.publication_mode,
            PublicationMode,
        )
        authority = _require_enum(
            "authority_kind",
            self.authority_kind,
            AuthorityKind,
        )
        if authority not in _ALLOWED_AUTHORITIES[mode]:
            raise OriginSetValidationError(
                "authority_kind is not permitted for publication_mode",
            )
        object.__setattr__(self, "publication_mode", mode)
        object.__setattr__(self, "authority_kind", authority)
        object.__setattr__(
            self,
            "issuer_id",
            _require_bytes("issuer_id", self.issuer_id, minimum=1, maximum=64),
        )

        not_before = _require_uint(
            "not_before",
            self.not_before,
            minimum=0,
            maximum=MAX_TIMESTAMP,
        )
        expires_at = _require_uint(
            "expires_at",
            self.expires_at,
            minimum=0,
            maximum=MAX_TIMESTAMP,
        )
        if expires_at <= not_before:
            raise OriginSetValidationError("expires_at must be after not_before")
        object.__setattr__(self, "not_before", not_before)
        object.__setattr__(self, "expires_at", expires_at)

        dnssec_status = self.dnssec_status
        if dnssec_status is not None:
            dnssec_status = _require_enum(
                "dnssec_status",
                dnssec_status,
                DnssecStatus,
            )
            if dnssec_status is DnssecStatus.BOGUS:
                raise OriginSetValidationError(
                    "bogus DNSSEC data cannot produce an OriginSet",
                )
        if authority is AuthorityKind.LOCAL_DERIVATION and dnssec_status is None:
            raise OriginSetValidationError(
                "local derivation requires an explicit DNSSEC status",
            )
        object.__setattr__(self, "dnssec_status", dnssec_status)

        if self.previous_digest is not None:
            object.__setattr__(
                self,
                "previous_digest",
                _require_bytes(
                    "previous_digest",
                    self.previous_digest,
                    minimum=32,
                    maximum=32,
                ),
            )
        object.__setattr__(self, "content_digest", self._compute_digest())

    @property
    def version(self) -> tuple[int, int, int]:
        return (
            self.service_record_generation,
            self.origin_generation,
            self.sequence,
        )

    def require_valid_at(self, timestamp: int) -> None:
        checked = _require_uint(
            "timestamp",
            timestamp,
            minimum=0,
            maximum=MAX_TIMESTAMP,
        )
        if not self.not_before <= checked < self.expires_at:
            raise OriginSetStaleError("OriginSet is outside its validity window")

    def _compute_digest(self) -> bytes:
        value: list[Any] = [
            _DIGEST_DOMAIN,
            self.service_id,
            self.service_record_generation,
            self.origin_generation,
            self.sequence,
            [endpoint._digest_value() for endpoint in self.endpoints],
            self.publication_mode.value,
            self.authority_kind.value,
            self.issuer_id.hex(),
            self.not_before,
            self.expires_at,
            self.dnssec_status.value if self.dnssec_status is not None else None,
            self.previous_digest.hex() if self.previous_digest is not None else None,
        ]
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        return hashlib.sha256(encoded).digest()


@dataclass(frozen=True, slots=True)
class OriginSetTombstone:
    """Highest accepted removed state retained to prevent resurrection."""

    service_id: str
    issuer_id: bytes
    service_record_generation: int
    origin_generation: int
    sequence: int
    content_digest: bytes

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "service_id",
            _require_text_id("service_id", self.service_id),
        )
        object.__setattr__(
            self,
            "issuer_id",
            _require_bytes("issuer_id", self.issuer_id, minimum=1, maximum=64),
        )
        for name in (
            "service_record_generation",
            "origin_generation",
            "sequence",
        ):
            object.__setattr__(
                self,
                name,
                _require_uint(
                    name,
                    getattr(self, name),
                    minimum=1,
                    maximum=MAX_UINT64,
                ),
            )
        object.__setattr__(
            self,
            "content_digest",
            _require_bytes(
                "content_digest",
                self.content_digest,
                minimum=32,
                maximum=32,
            ),
        )

    @property
    def version(self) -> tuple[int, int, int]:
        return (
            self.service_record_generation,
            self.origin_generation,
            self.sequence,
        )


def make_tombstone(originset: DerivedOriginSet) -> OriginSetTombstone:
    if type(originset) is not DerivedOriginSet:
        raise OriginSetValidationError(
            "originset must be a DerivedOriginSet",
        )
    return OriginSetTombstone(
        service_id=originset.service_id,
        issuer_id=originset.issuer_id,
        service_record_generation=originset.service_record_generation,
        origin_generation=originset.origin_generation,
        sequence=originset.sequence,
        content_digest=originset.content_digest,
    )


def accept_originset(
    candidate: DerivedOriginSet,
    *,
    current: DerivedOriginSet | None = None,
    tombstone: OriginSetTombstone | None = None,
) -> DerivedOriginSet:
    """Validate candidate ordering and digest continuity against retained state."""

    if type(candidate) is not DerivedOriginSet:
        raise OriginSetValidationError(
            "candidate must be a DerivedOriginSet",
        )
    if current is not None and type(current) is not DerivedOriginSet:
        raise OriginSetValidationError("current must be a DerivedOriginSet")
    if tombstone is not None and type(tombstone) is not OriginSetTombstone:
        raise OriginSetValidationError(
            "tombstone must be an OriginSetTombstone",
        )

    references: list[tuple[tuple[int, int, int], bytes, bool, Any]] = []
    for reference, is_tombstone in ((current, False), (tombstone, True)):
        if reference is None:
            continue
        if candidate.service_id != reference.service_id or candidate.issuer_id != reference.issuer_id:
            raise OriginSetValidationError(
                "candidate and retained state must share service and issuer context",
            )
        references.append(
            (
                reference.version,
                reference.content_digest,
                is_tombstone,
                reference,
            ),
        )

    if not references:
        if candidate.previous_digest is not None:
            raise OriginSetValidationError(
                "initial candidate cannot reference unavailable prior state",
            )
        return candidate

    reference_version, reference_digest, is_tombstone, reference = max(
        references,
        key=lambda item: item[0],
    )
    if any(
        candidate_value < reference_value
        for candidate_value, reference_value in zip(
            candidate.version,
            reference_version,
            strict=True,
        )
    ):
        raise OriginSetStaleError(
            "candidate generation or sequence is older than retained state",
        )
    if candidate.version == reference_version:
        if candidate.content_digest != reference_digest:
            raise OriginSetEquivocationError(
                "same version has different normalized content",
            )
        if is_tombstone:
            raise OriginSetStaleError("tombstoned state cannot be resurrected")
        return reference
    if candidate.previous_digest != reference_digest:
        raise OriginSetValidationError(
            "candidate previous_digest does not match retained state",
        )
    return candidate
