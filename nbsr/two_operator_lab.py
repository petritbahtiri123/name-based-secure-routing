"""Immutable WP7 two-operator lab configuration and trust validation.

This deterministic model is configuration-neutral: it does not serialize a
wire format, resolve endpoints, or allocate any resources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


MAX_UINT64 = 2**64 - 1
_OPERATOR_FIELDS = frozenset(
    {
        "operator_id",
        "identity_fingerprint",
        "policy_fingerprint",
        "audit_fingerprint",
        "policy_digest",
        "gateway_profile_digest",
        "continuity_digest",
        "policy_version",
    }
)
_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_HEX_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")


class LabRejected(ValueError):
    """A two-operator lab configuration or context is not trustworthy."""


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != _OPERATOR_FIELDS or not all(type(key) is str for key in value):
        raise LabRejected("operator profile must contain exactly the approved fields")
    return value


def _id(value: object, label: str) -> str:
    if type(value) is not str or len(value) > 64 or _ID_RE.fullmatch(value) is None:
        raise LabRejected(f"{label} must be a canonical bounded identifier")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _HEX_DIGEST_RE.fullmatch(value) is None:
        raise LabRejected(f"{label} must be a canonical SHA-256 digest")
    return value


def _version(value: object, label: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_UINT64:
        raise LabRejected(f"{label} is outside the uint64 range")
    return value


@dataclass(frozen=True, slots=True)
class OperatorProfile:
    """One operator's immutable local configuration and authority digests."""

    operator_id: str
    identity_fingerprint: str
    policy_fingerprint: str
    audit_fingerprint: str
    policy_digest: str
    gateway_profile_digest: str
    continuity_digest: str
    policy_version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _id(self.operator_id, "operator_id"))
        for field in (
            "identity_fingerprint",
            "policy_fingerprint",
            "audit_fingerprint",
            "policy_digest",
            "gateway_profile_digest",
            "continuity_digest",
        ):
            object.__setattr__(self, field, _digest(getattr(self, field), field))
        object.__setattr__(self, "policy_version", _version(self.policy_version, "policy_version"))
        if len({self.identity_fingerprint, self.policy_fingerprint, self.audit_fingerprint}) != 3:
            raise LabRejected("operator key fingerprints must be unique by purpose")

    @classmethod
    def from_dict(cls, value: object) -> OperatorProfile:
        data = _mapping(value)
        return cls(**data)

    @property
    def key_fingerprints(self) -> tuple[str, str, str]:
        return (self.identity_fingerprint, self.policy_fingerprint, self.audit_fingerprint)


def _validate_profile_pair(source: OperatorProfile, destination: OperatorProfile) -> None:
    if type(source) is not OperatorProfile or type(destination) is not OperatorProfile:
        raise LabRejected("operator profiles are invalid")
    if source.operator_id == destination.operator_id:
        raise LabRejected("source and destination operators must be distinct")
    if len(set((*source.key_fingerprints, *destination.key_fingerprints))) != 6:
        raise LabRejected("operator key fingerprints must be unique across operators and purposes")


@dataclass(frozen=True, slots=True)
class RouteTrust:
    """The sole injected cross-operator trust tuple for a lab route."""

    source_operator: str
    source_identity_fingerprint: str
    destination_operator: str
    destination_identity_fingerprint: str
    route_id: str
    service_id: str
    route_grant_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_operator", _id(self.source_operator, "source_operator"))
        object.__setattr__(self, "source_identity_fingerprint", _digest(self.source_identity_fingerprint, "source_identity_fingerprint"))
        object.__setattr__(self, "destination_operator", _id(self.destination_operator, "destination_operator"))
        object.__setattr__(self, "destination_identity_fingerprint", _digest(self.destination_identity_fingerprint, "destination_identity_fingerprint"))
        object.__setattr__(self, "route_id", _id(self.route_id, "route_id"))
        object.__setattr__(self, "service_id", _id(self.service_id, "service_id"))
        object.__setattr__(self, "route_grant_digest", _digest(self.route_grant_digest, "route_grant_digest"))
        if self.source_operator == self.destination_operator:
            raise LabRejected("trust tuple requires distinct operators")

    @classmethod
    def from_profiles(
        cls,
        source: OperatorProfile,
        destination: OperatorProfile,
        *,
        route_id: str,
        service_id: str,
        route_grant_digest: str,
    ) -> RouteTrust:
        _validate_profile_pair(source, destination)
        return cls(
            source.operator_id,
            source.identity_fingerprint,
            destination.operator_id,
            destination.identity_fingerprint,
            route_id,
            service_id,
            route_grant_digest,
        )


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    """Opaque, already-authenticated context for exact local validation only."""

    source_operator: str
    destination_operator: str
    tenant_id: str
    subscriber_pseudonym: str
    name_id: str
    route_id: str
    service_id: str
    channel_id: str
    tunnel_id: str
    source_edge_id: str
    destination_edge_id: str
    route_grant_digest: str
    source_policy_digest: str
    destination_policy_digest: str
    source_gateway_digest: str
    destination_gateway_digest: str
    source_continuity_digest: str
    destination_continuity_digest: str
    source_policy_version: int
    destination_policy_version: int

    def __post_init__(self) -> None:
        for field in (
            "source_operator",
            "destination_operator",
            "tenant_id",
            "name_id",
            "route_id",
            "service_id",
            "channel_id",
            "tunnel_id",
            "source_edge_id",
            "destination_edge_id",
        ):
            object.__setattr__(self, field, _id(getattr(self, field), field))
        object.__setattr__(self, "subscriber_pseudonym", _digest(self.subscriber_pseudonym, "subscriber_pseudonym"))
        for field in (
            "route_grant_digest",
            "source_policy_digest",
            "destination_policy_digest",
            "source_gateway_digest",
            "destination_gateway_digest",
            "source_continuity_digest",
            "destination_continuity_digest",
        ):
            object.__setattr__(self, field, _digest(getattr(self, field), field))
        object.__setattr__(self, "source_policy_version", _version(self.source_policy_version, "source_policy_version"))
        object.__setattr__(self, "destination_policy_version", _version(self.destination_policy_version, "destination_policy_version"))
        if self.source_operator == self.destination_operator:
            raise LabRejected("admission context requires distinct operators")

    def validate(self, source: OperatorProfile, destination: OperatorProfile, trust: RouteTrust) -> None:
        """Fail closed unless every owned local fact and trust tuple matches exactly."""
        _validate_profile_pair(source, destination)
        if type(trust) is not RouteTrust:
            raise LabRejected("route trust is invalid")
        if (self.source_operator, self.destination_operator) != (source.operator_id, destination.operator_id):
            raise LabRejected("source operator or destination operator does not match its profile")
        if (self.source_policy_digest, self.source_policy_version) != (source.policy_digest, source.policy_version):
            raise LabRejected("source policy digest or policy version is stale")
        if (self.destination_policy_digest, self.destination_policy_version) != (destination.policy_digest, destination.policy_version):
            raise LabRejected("destination policy digest or policy version is stale")
        if self.source_gateway_digest != source.gateway_profile_digest:
            raise LabRejected("source gateway digest does not match its profile")
        if self.destination_gateway_digest != destination.gateway_profile_digest:
            raise LabRejected("destination gateway digest does not match its profile")
        if self.source_continuity_digest != source.continuity_digest or self.destination_continuity_digest != destination.continuity_digest:
            raise LabRejected("continuity digest does not match its profile")
        expected = (
            source.operator_id,
            source.identity_fingerprint,
            destination.operator_id,
            destination.identity_fingerprint,
            self.route_id,
            self.service_id,
            self.route_grant_digest,
        )
        actual = (
            trust.source_operator,
            trust.source_identity_fingerprint,
            trust.destination_operator,
            trust.destination_identity_fingerprint,
            trust.route_id,
            trust.service_id,
            trust.route_grant_digest,
        )
        if actual != expected:
            raise LabRejected("route trust tuple does not match the admission context")
