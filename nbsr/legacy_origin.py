"""WP2 conversion of normalized legacy DNS data into internal OriginSets."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address, ip_network

from nbsr.name_model import normalize_hostname
from nbsr.originset import (
    AuthorityKind,
    DerivedOriginSet,
    DnssecStatus,
    OriginEndpoint,
    OriginSetError,
    PublicationMode,
)


MAX_UINT64 = 2**64 - 1
MAX_TIMESTAMP = 253_402_300_799
MAX_ENDPOINTS = 32
PROTOTYPE_MAX_DNS_TTL_SECONDS = 300
PROTOTYPE_LAST_KNOWN_GOOD_SECONDS = 300
_TEXT_ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")


class LegacyOriginError(ValueError):
    """Base error for isolated legacy-origin discovery state."""


class LegacyOriginValidationError(LegacyOriginError):
    """A snapshot or caller policy failed closed."""


class LegacyDnsResult(StrEnum):
    POSITIVE = "positive"
    TEMPORARY_FAILURE = "temporary-failure"
    AUTHENTICATED_NEGATIVE = "authenticated-negative"
    INVALID = "invalid"


def _uint(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise LegacyOriginValidationError(f"{name} is outside its allowed bound")
    return value


def _enum[T: StrEnum](name: str, value: object, enum_type: type[T]) -> T:
    if isinstance(value, enum_type):
        return value
    if type(value) is str:
        try:
            return enum_type(value)
        except ValueError:
            pass
    raise LegacyOriginValidationError(f"{name} is unsupported")


def _canonical_name(name: str, value: object) -> str:
    if type(value) is not str:
        raise LegacyOriginValidationError(f"{name} is invalid")
    try:
        normalized = normalize_hostname(value)
        ip_address(value)
    except ValueError:
        if value == normalized:
            return value
    raise LegacyOriginValidationError(f"{name} is invalid")


def _text_id(name: str, value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 64 or not value.isascii() or _TEXT_ID_PATTERN.fullmatch(value) is None:
        raise LegacyOriginValidationError(f"{name} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class LegacyOriginRequest:
    service_name: str
    service_id: str
    service_record_generation: int
    issuer_id: bytes
    origin_name: str
    allowed_ports: tuple[int, ...]
    allowed_networks: tuple[str, ...]
    max_endpoints: int = MAX_ENDPOINTS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "service_name",
            _canonical_name("service_name", self.service_name),
        )
        object.__setattr__(
            self,
            "service_id",
            _text_id("service_id", self.service_id),
        )
        object.__setattr__(
            self,
            "origin_name",
            _canonical_name("origin_name", self.origin_name),
        )
        object.__setattr__(
            self,
            "service_record_generation",
            _uint(
                "service_record_generation",
                self.service_record_generation,
                1,
                MAX_UINT64,
            ),
        )
        if type(self.issuer_id) is not bytes or not 1 <= len(self.issuer_id) <= 64:
            raise LegacyOriginValidationError("issuer_id is invalid")
        object.__setattr__(self, "issuer_id", bytes(self.issuer_id))

        if type(self.allowed_ports) not in (list, tuple) or not self.allowed_ports:
            raise LegacyOriginValidationError("allowed_ports is invalid")
        ports = tuple(sorted(self.allowed_ports))
        if len(set(ports)) != len(ports) or any(type(port) is not int or not 1 <= port <= 65_535 for port in ports):
            raise LegacyOriginValidationError("allowed_ports is invalid")
        object.__setattr__(self, "allowed_ports", ports)

        if type(self.allowed_networks) not in (list, tuple) or not self.allowed_networks:
            raise LegacyOriginValidationError("allowed_networks is invalid")
        networks: list[str] = []
        try:
            for value in self.allowed_networks:
                if type(value) is not str:
                    raise ValueError
                network = ip_network(value, strict=True)
                if value != str(network) or network.prefixlen == 0:
                    raise ValueError
                networks.append(value)
        except ValueError as exc:
            raise LegacyOriginValidationError(
                "allowed_networks is invalid",
            ) from exc
        if len(set(networks)) != len(networks):
            raise LegacyOriginValidationError("allowed_networks is invalid")
        object.__setattr__(self, "allowed_networks", tuple(sorted(networks)))
        object.__setattr__(
            self,
            "max_endpoints",
            _uint("max_endpoints", self.max_endpoints, 1, MAX_ENDPOINTS),
        )


@dataclass(frozen=True, slots=True)
class LegacyDnsSnapshot:
    result: LegacyDnsResult | str
    requested_name: str
    origin_name: str
    endpoints: tuple[OriginEndpoint, ...]
    ttl_seconds: int
    dnssec_status: DnssecStatus | str
    observed_at: int

    def __post_init__(self) -> None:
        result = _enum("result", self.result, LegacyDnsResult)
        status = _enum("dnssec_status", self.dnssec_status, DnssecStatus)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "dnssec_status", status)
        object.__setattr__(
            self,
            "requested_name",
            _canonical_name("requested_name", self.requested_name),
        )
        object.__setattr__(
            self,
            "origin_name",
            _canonical_name("origin_name", self.origin_name),
        )
        object.__setattr__(
            self,
            "ttl_seconds",
            _uint("ttl_seconds", self.ttl_seconds, 1, MAX_UINT64),
        )
        object.__setattr__(
            self,
            "observed_at",
            _uint("observed_at", self.observed_at, 0, MAX_TIMESTAMP),
        )
        if type(self.endpoints) not in (list, tuple) or any(type(endpoint) is not OriginEndpoint for endpoint in self.endpoints):
            raise LegacyOriginValidationError("endpoints are invalid")
        endpoints = tuple(sorted(self.endpoints, key=OriginEndpoint._sort_key))
        if result is LegacyDnsResult.POSITIVE and not endpoints:
            raise LegacyOriginValidationError("positive result requires endpoints")
        if result is not LegacyDnsResult.POSITIVE and endpoints:
            raise LegacyOriginValidationError(
                "non-positive result cannot contain endpoints",
            )
        object.__setattr__(self, "endpoints", endpoints)


CandidateValidator = Callable[[LegacyOriginRequest, OriginEndpoint], bool]


def derive_originset(
    request: LegacyOriginRequest,
    snapshot: LegacyDnsSnapshot,
    *,
    sequence: int,
    previous_digest: bytes | None,
    validator: CandidateValidator,
    previous_dnssec_status: DnssecStatus | None = None,
) -> DerivedOriginSet:
    """Validate one positive snapshot and create an internal candidate."""

    if type(request) is not LegacyOriginRequest or type(snapshot) is not LegacyDnsSnapshot:
        raise LegacyOriginValidationError("request and snapshot are invalid")
    if snapshot.result is not LegacyDnsResult.POSITIVE:
        raise LegacyOriginValidationError("DNS result is not positive")
    if request.service_name != snapshot.requested_name or request.origin_name != snapshot.origin_name:
        raise LegacyOriginValidationError("DNS result does not match caller policy")
    if snapshot.dnssec_status is DnssecStatus.BOGUS:
        raise LegacyOriginValidationError("DNSSEC validation failed")
    if previous_dnssec_status is DnssecStatus.SECURE and snapshot.dnssec_status is not DnssecStatus.SECURE:
        raise LegacyOriginValidationError("DNSSEC downgrade is forbidden")
    checked_sequence = _uint("sequence", sequence, 1, MAX_UINT64)
    if previous_digest is not None and (type(previous_digest) is not bytes or len(previous_digest) != 32):
        raise LegacyOriginValidationError("previous_digest is invalid")
    if not callable(validator):
        raise LegacyOriginValidationError("candidate validator is invalid")
    if not 1 <= len(snapshot.endpoints) <= request.max_endpoints:
        raise LegacyOriginValidationError("endpoint count is outside policy")

    networks = tuple(ip_network(value) for value in request.allowed_networks)
    identities: set[tuple[str, int, object]] = set()
    for endpoint in snapshot.endpoints:
        address = ip_address(endpoint.address)
        if endpoint.port not in request.allowed_ports or not any(
            address.version == network.version and address in network for network in networks
        ):
            raise LegacyOriginValidationError("endpoint is outside caller policy")
        identity = (endpoint.address, endpoint.port, endpoint.transport)
        if identity in identities:
            raise LegacyOriginValidationError("endpoint identities are duplicated")
        identities.add(identity)
        try:
            accepted = validator(request, endpoint)
        except Exception as exc:
            raise LegacyOriginValidationError(
                "candidate validation failed",
            ) from exc
        if accepted is not True:
            raise LegacyOriginValidationError("candidate validation failed")

    ttl = min(snapshot.ttl_seconds, PROTOTYPE_MAX_DNS_TTL_SECONDS)
    expires_at = snapshot.observed_at + ttl + PROTOTYPE_LAST_KNOWN_GOOD_SECONDS
    if expires_at > MAX_TIMESTAMP:
        raise LegacyOriginValidationError("snapshot validity is outside bounds")
    try:
        return DerivedOriginSet(
            service_id=request.service_id,
            service_record_generation=request.service_record_generation,
            origin_generation=1,
            sequence=checked_sequence,
            endpoints=snapshot.endpoints,
            publication_mode=PublicationMode.LEGACY_DNS,
            authority_kind=AuthorityKind.LOCAL_DERIVATION,
            issuer_id=request.issuer_id,
            not_before=snapshot.observed_at,
            expires_at=expires_at,
            dnssec_status=snapshot.dnssec_status,
            previous_digest=previous_digest,
        )
    except OriginSetError as exc:
        raise LegacyOriginValidationError("OriginSet candidate is invalid") from exc
