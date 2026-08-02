"""Immutable WP7 two-operator lab configuration and trust validation.

This deterministic model is configuration-neutral: it does not serialize a
wire format, resolve endpoints, or allocate any resources.
"""

from __future__ import annotations

import re
from hashlib import sha256
from dataclasses import dataclass, field as dataclass_field
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

    def __init__(self, message: str, *, code: str = "lab-rejected") -> None:
        super().__init__(message)
        self.code = code


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


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    """A privacy-safe record of one admitted opaque lab context."""

    source_operator: str
    destination_operator: str
    tenant_id: str
    subscriber_pseudonym: str
    name_id: str
    route_id: str
    service_id: str
    channel_id: str
    tunnel_id: str
    route_grant_digest: str
    admitted_at_ms: int


@dataclass(frozen=True, slots=True)
class TwoOperatorLab:
    """Deterministically admit opaque contexts through separate operator gates."""

    source: OperatorProfile
    destination: OperatorProfile
    trust: RouteTrust
    expected_context: AdmissionContext
    _admitted_grants: frozenset[tuple[str, str, str, str, str]] = dataclass_field(
        default_factory=frozenset,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if type(self.expected_context) is not AdmissionContext:
            raise LabRejected("expected admission context is invalid", code="admission-context-invalid")
        self.expected_context.validate(self.source, self.destination, self.trust)

    @property
    def admitted_grant_count(self) -> int:
        """Return the number of successful opaque grant admissions."""
        return len(self._admitted_grants)

    @staticmethod
    def _reject(code: str) -> None:
        raise LabRejected(code.replace("-", " "), code=code)

    def source_gate(self, request: AdmissionContext) -> None:
        """Validate only the facts owned by the source operator."""
        expected = self.expected_context
        if request.source_operator != self.source.operator_id:
            self._reject("source-operator-mismatch")
        if request.tenant_id != expected.tenant_id:
            self._reject("source-tenant-mismatch")
        if request.subscriber_pseudonym != expected.subscriber_pseudonym:
            self._reject("source-subscriber-mismatch")
        if request.name_id != expected.name_id:
            self._reject("source-name-mismatch")
        if request.source_edge_id != expected.source_edge_id:
            self._reject("source-edge-mismatch")
        if (request.source_policy_digest, request.source_policy_version) != (
            self.source.policy_digest,
            self.source.policy_version,
        ):
            self._reject("source-policy-mismatch")
        if request.source_gateway_digest != self.source.gateway_profile_digest:
            self._reject("source-gateway-mismatch")
        if request.source_continuity_digest != self.source.continuity_digest:
            self._reject("source-continuity-denied")
        if (request.route_id, request.service_id, request.route_grant_digest) != (
            expected.route_id,
            expected.service_id,
            expected.route_grant_digest,
        ):
            self._reject("source-route-grant-mismatch")

    def destination_gate(self, request: AdmissionContext) -> None:
        """Independently validate only the facts owned by the destination operator."""
        expected = self.expected_context
        if request.destination_operator != self.destination.operator_id:
            self._reject("destination-operator-mismatch")
        if request.tenant_id != expected.tenant_id:
            self._reject("destination-tenant-mismatch")
        if request.service_id != expected.service_id:
            self._reject("destination-service-mismatch")
        if request.route_id != expected.route_id:
            self._reject("destination-route-mismatch")
        if request.channel_id != expected.channel_id:
            self._reject("destination-channel-mismatch")
        if request.tunnel_id != expected.tunnel_id:
            self._reject("destination-tunnel-mismatch")
        if request.destination_edge_id != expected.destination_edge_id:
            self._reject("destination-edge-mismatch")
        if (request.destination_policy_digest, request.destination_policy_version) != (
            self.destination.policy_digest,
            self.destination.policy_version,
        ):
            self._reject("destination-policy-mismatch")
        if request.destination_gateway_digest != self.destination.gateway_profile_digest:
            self._reject("destination-gateway-mismatch")
        if request.destination_continuity_digest != self.destination.continuity_digest:
            self._reject("destination-continuity-denied")
        if (
            self.trust.source_operator,
            self.trust.source_identity_fingerprint,
            self.trust.destination_operator,
            self.trust.destination_identity_fingerprint,
            self.trust.route_id,
            self.trust.service_id,
            self.trust.route_grant_digest,
        ) != (
            self.source.operator_id,
            self.source.identity_fingerprint,
            self.destination.operator_id,
            self.destination.identity_fingerprint,
            request.route_id,
            request.service_id,
            request.route_grant_digest,
        ):
            self._reject("destination-route-trust-mismatch")

    def admit(self, request: AdmissionContext, now_ms: int) -> AdmissionReceipt:
        """Admit a request only after both gates pass, then record its opaque grant."""
        if type(request) is not AdmissionContext:
            self._reject("source-context-invalid")
        if type(now_ms) is not int or not 0 <= now_ms <= MAX_UINT64:
            self._reject("admission-clock-invalid")
        self.source_gate(request)
        self.destination_gate(request)
        grant_key = (
            request.source_operator,
            request.destination_operator,
            request.route_id,
            request.service_id,
            request.route_grant_digest,
        )
        if grant_key in self._admitted_grants:
            self._reject("destination-route-grant-replayed")
        object.__setattr__(self, "_admitted_grants", self._admitted_grants | frozenset((grant_key,)))
        return AdmissionReceipt(
            source_operator=request.source_operator,
            destination_operator=request.destination_operator,
            tenant_id=request.tenant_id,
            subscriber_pseudonym=request.subscriber_pseudonym,
            name_id=request.name_id,
            route_id=request.route_id,
            service_id=request.service_id,
            channel_id=request.channel_id,
            tunnel_id=request.tunnel_id,
            route_grant_digest=request.route_grant_digest,
            admitted_at_ms=now_ms,
        )

    def admit_audited(
        self,
        request: AdmissionContext,
        *,
        now_ms: int,
        source_audit: "AuditLog",
        destination_audit: "AuditLog",
    ) -> AdmissionReceipt:
        """Admit only when both independent local audit logs can record first."""
        if type(source_audit) is not AuditLog or type(destination_audit) is not AuditLog:
            self._reject("audit-log-invalid")
        if (source_audit.operator_id, destination_audit.operator_id) != (self.source.operator_id, self.destination.operator_id):
            self._reject("audit-operator-mismatch")
        if type(request) is not AdmissionContext:
            self._reject("source-context-invalid")
        if type(now_ms) is not int or not 0 <= now_ms <= MAX_UINT64:
            self._reject("admission-clock-invalid")
        self.source_gate(request)
        self.destination_gate(request)
        grant_key = (
            request.source_operator,
            request.destination_operator,
            request.route_id,
            request.service_id,
            request.route_grant_digest,
        )
        if grant_key in self._admitted_grants:
            self._reject("destination-route-grant-replayed")
        source_audit._preflight()
        destination_audit._preflight()
        source_audit.record(action="admitted", subject_digest=request.route_grant_digest)
        destination_audit.record(action="admitted", subject_digest=request.route_grant_digest)
        object.__setattr__(self, "_admitted_grants", self._admitted_grants | frozenset((grant_key,)))
        return AdmissionReceipt(
            source_operator=request.source_operator,
            destination_operator=request.destination_operator,
            tenant_id=request.tenant_id,
            subscriber_pseudonym=request.subscriber_pseudonym,
            name_id=request.name_id,
            route_id=request.route_id,
            service_id=request.service_id,
            channel_id=request.channel_id,
            tunnel_id=request.tunnel_id,
            route_grant_digest=request.route_grant_digest,
            admitted_at_ms=now_ms,
        )


def _positive_uint64(value: object, label: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_UINT64:
        raise LabRejected(f"{label} must be a positive uint64", code=f"{label}-invalid")
    return value


@dataclass(frozen=True, slots=True)
class LimitProfile:
    """Closed, positive limits for the storage-neutral two-operator lab."""

    client_capacity: int
    name_capacity: int
    route_capacity: int
    service_capacity: int
    channel_capacity: int
    tunnel_capacity: int
    operator_capacity: int
    refill_per_ms: int
    max_buckets: int
    max_active_allocations: int

    def __post_init__(self) -> None:
        for field in (
            "client_capacity",
            "name_capacity",
            "route_capacity",
            "service_capacity",
            "channel_capacity",
            "tunnel_capacity",
            "operator_capacity",
            "refill_per_ms",
            "max_buckets",
            "max_active_allocations",
        ):
            object.__setattr__(self, field, _positive_uint64(getattr(self, field), field))

    def capacity_for(self, scope: str) -> int:
        if scope not in {"client", "name", "route", "service", "channel", "tunnel", "operator"}:
            raise LabRejected("limit scope is invalid", code="limit-scope-invalid")
        return getattr(self, f"{scope}_capacity")


class TokenBucket:
    """A caller-clocked, saturating uint64 token bucket with no fractions."""

    __slots__ = ("capacity", "refill_per_ms", "_last_ms", "_tokens")

    def __init__(self, *, capacity: int, refill_per_ms: int, now_ms: int) -> None:
        self.capacity = _positive_uint64(capacity, "token-bucket-capacity")
        self.refill_per_ms = _positive_uint64(refill_per_ms, "token-bucket-refill")
        if type(now_ms) is not int or not 0 <= now_ms <= MAX_UINT64:
            raise LabRejected("token bucket clock is not uint64", code="token-bucket-clock-invalid")
        self._last_ms = now_ms
        self._tokens = self.capacity

    @property
    def tokens(self) -> int:
        return self._tokens

    @property
    def last_ms(self) -> int:
        return self._last_ms

    def _project(self, amount: int, now_ms: int) -> tuple[int, int]:
        amount = _positive_uint64(amount, "token-bucket-amount")
        if type(now_ms) is not int or not 0 <= now_ms <= MAX_UINT64:
            raise LabRejected("token bucket clock is not uint64", code="token-bucket-clock-invalid")
        if now_ms < self._last_ms:
            raise LabRejected("token bucket clock rolled back", code="token-bucket-clock-rollback")
        elapsed = now_ms - self._last_ms
        missing = self.capacity - self._tokens
        if missing == 0 or elapsed == 0:
            available = self._tokens
        else:
            refill_needed_ms = (missing + self.refill_per_ms - 1) // self.refill_per_ms
            if elapsed >= refill_needed_ms:
                available = self.capacity
            else:
                available = self._tokens + elapsed * self.refill_per_ms
        if amount > available:
            raise LabRejected("token bucket limit exceeded", code="token-bucket-limit")
        return available - amount, now_ms

    def consume(self, *, amount: int, now_ms: int) -> None:
        """Consume only after a uint64 monotonic-time projection can admit it."""
        tokens, last_ms = self._project(amount, now_ms)
        self._tokens = tokens
        self._last_ms = last_ms


class ResourceLimiter:
    """Atomically apply all owned limit scopes and bounded fair allocations."""

    __slots__ = ("profile", "_buckets", "_active_allocations")

    def __init__(self, profile: LimitProfile) -> None:
        if type(profile) is not LimitProfile:
            raise LabRejected("limit profile is invalid", code="limit-profile-invalid")
        self.profile = profile
        self._buckets: dict[tuple[str, tuple[str, ...]], TokenBucket] = {}
        self._active_allocations: frozenset[tuple[str, ...]] = frozenset()

    @property
    def active_allocation_count(self) -> int:
        return len(self._active_allocations)

    def _scope_keys(self, request: AdmissionContext) -> tuple[tuple[str, tuple[str, ...]], ...]:
        if type(request) is not AdmissionContext:
            raise LabRejected("limit context is invalid", code="limit-context-invalid")
        source_owner = (request.source_operator, request.tenant_id)
        destination_owner = (request.destination_operator, request.tenant_id)
        return (
            ("client", (*source_owner, request.subscriber_pseudonym)),
            ("name", (*source_owner, request.name_id)),
            ("route", (*destination_owner, request.route_id)),
            ("service", (*destination_owner, request.service_id)),
            ("channel", (*destination_owner, request.channel_id)),
            ("tunnel", (*destination_owner, request.tunnel_id)),
            ("operator", (request.source_operator,)),
            ("operator", (request.destination_operator,)),
        )

    def consume(self, request: AdmissionContext, *, amount: int, now_ms: int) -> None:
        """Preflight every scope, then mutate every bucket together or none."""
        amount = _positive_uint64(amount, "limit-amount")
        keys = self._scope_keys(request)
        new_keys = tuple(key for key in keys if key not in self._buckets)
        if len(self._buckets) + len(new_keys) > self.profile.max_buckets:
            raise LabRejected("limit bucket capacity exhausted", code="limit-bucket-capacity")

        plans: list[tuple[tuple[str, tuple[str, ...]], int, int]] = []
        for scope, key in keys:
            bucket_key = (scope, key)
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = TokenBucket(capacity=self.profile.capacity_for(scope), refill_per_ms=self.profile.refill_per_ms, now_ms=now_ms)
            try:
                tokens, last_ms = bucket._project(amount, now_ms)
            except LabRejected as rejected:
                if rejected.code == "token-bucket-limit":
                    raise LabRejected(f"{scope} limit exceeded", code=f"{scope}-limit") from None
                raise
            plans.append((bucket_key, tokens, last_ms))

        for bucket_key, tokens, last_ms in plans:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                scope, _ = bucket_key
                bucket = TokenBucket(capacity=self.profile.capacity_for(scope), refill_per_ms=self.profile.refill_per_ms, now_ms=now_ms)
                self._buckets[bucket_key] = bucket
            bucket._tokens = tokens
            bucket._last_ms = last_ms

    @staticmethod
    def _allocation_key(request: AdmissionContext) -> tuple[str, ...]:
        return (
            request.source_operator,
            request.destination_operator,
            request.tenant_id,
            request.subscriber_pseudonym,
            request.name_id,
            request.service_id,
            request.route_id,
            request.channel_id,
            request.tunnel_id,
        )

    @staticmethod
    def _owner_subscriber(entry: tuple[str, ...], owner: str) -> tuple[str, ...]:
        if owner == "source":
            return (entry[0], entry[2], entry[3])
        return (entry[1], entry[2], entry[0], entry[3])

    def _preflight_owner_allocation(self, request: AdmissionContext, owner: str) -> None:
        if owner == "source":
            operator_index = 0
            operator = request.source_operator
        else:
            operator_index = 1
            operator = request.destination_operator
        owner_allocations = tuple(entry for entry in self._active_allocations if entry[operator_index] == operator)
        if len(owner_allocations) >= self.profile.operator_capacity:
            raise LabRejected(f"{owner} operator allocation capacity exhausted", code=f"{owner}-operator-allocation-capacity")
        subscriber = self._owner_subscriber(self._allocation_key(request), owner)
        active_subscribers = {self._owner_subscriber(entry, owner) for entry in owner_allocations}
        active_subscribers.add(subscriber)
        fair_share = max(1, self.profile.operator_capacity // len(active_subscribers))
        fair_share = min(fair_share, self.profile.client_capacity)
        subscriber_allocations = sum(self._owner_subscriber(entry, owner) == subscriber for entry in owner_allocations)
        if subscriber_allocations >= fair_share:
            raise LabRejected(f"{owner} subscriber fair share exhausted", code=f"{owner}-subscriber-fair-share")

    def allocate(self, request: AdmissionContext) -> None:
        """Reserve one exact bounded allocation under both owners' fair shares."""
        self._scope_keys(request)
        allocation = self._allocation_key(request)
        if allocation in self._active_allocations:
            return
        if len(self._active_allocations) >= self.profile.max_active_allocations:
            raise LabRejected("allocation capacity exhausted", code="allocation-capacity")
        self._preflight_owner_allocation(request, "source")
        self._preflight_owner_allocation(request, "destination")
        self._active_allocations = self._active_allocations | frozenset((allocation,))

    def release(self, request: AdmissionContext) -> None:
        """Release exactly one owned allocation; unknown releases fail closed."""
        self._scope_keys(request)
        allocation = self._allocation_key(request)
        if allocation not in self._active_allocations:
            raise LabRejected("allocation is not active", code="allocation-not-active")
        self._active_allocations = self._active_allocations - frozenset((allocation,))


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One opaque, operator-owned audit event with a monotonic uint64 sequence."""

    sequence: int
    operator_id: str
    action: str
    subject_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _version(self.sequence, "audit-sequence"))
        object.__setattr__(self, "operator_id", _id(self.operator_id, "audit-operator"))
        object.__setattr__(self, "action", _id(self.action, "audit-action"))
        object.__setattr__(self, "subject_digest", _digest(self.subject_digest, "audit-subject"))


class AuditLog:
    """A bounded, append-only local audit log with no fallback destination."""

    __slots__ = ("operator_id", "capacity", "_events", "_next_sequence", "_sequence_exhausted", "_sealed")

    def __init__(self, *, operator_id: str, capacity: int, next_sequence: int = 1) -> None:
        object.__setattr__(self, "operator_id", _id(operator_id, "audit-operator"))
        object.__setattr__(self, "capacity", _positive_uint64(capacity, "audit-capacity"))
        object.__setattr__(self, "_events", ())
        object.__setattr__(self, "_next_sequence", _version(next_sequence, "audit-sequence"))
        object.__setattr__(self, "_sequence_exhausted", False)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("audit log state is private")
        object.__setattr__(self, name, value)

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """Return an immutable local snapshot rather than mutable audit storage."""
        return self._events

    def _preflight(self) -> None:
        if len(self._events) >= self.capacity:
            raise LabRejected("audit capacity exhausted", code="audit-capacity")
        if self._sequence_exhausted:
            raise LabRejected("audit sequence exhausted", code="audit-sequence-exhausted")

    def record(self, *, action: str, subject_digest: str) -> AuditEvent:
        """Append locally or fail before returning any operation success to a caller."""
        self._preflight()
        event = AuditEvent(
            sequence=self._next_sequence,
            operator_id=self.operator_id,
            action=action,
            subject_digest=subject_digest,
        )
        object.__setattr__(self, "_events", self._events + (event,))
        if event.sequence == MAX_UINT64:
            object.__setattr__(self, "_sequence_exhausted", True)
        else:
            object.__setattr__(self, "_next_sequence", event.sequence + 1)
        return event


@dataclass(frozen=True, slots=True)
class ConnectorReceipt:
    """A public connector receipt deliberately limited to opaque digests."""

    operator_id: str
    route_grant_digest: str
    connector_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _id(self.operator_id, "connector-operator"))
        object.__setattr__(self, "route_grant_digest", _digest(self.route_grant_digest, "connector-grant"))
        object.__setattr__(self, "connector_digest", _digest(self.connector_digest, "connector-digest"))


class DestinationConnector:
    """The sole WP7 object allowed to retain an ISP-B private destination."""

    __slots__ = ("operator_id", "_private_destination", "_sealed")

    def __init__(self, *, operator_id: str, private_destination: str) -> None:
        object.__setattr__(self, "operator_id", _id(operator_id, "connector-operator"))
        if type(private_destination) is not str or not 1 <= len(private_destination) <= 512:
            raise LabRejected("connector destination is invalid", code="connector-destination-invalid")
        object.__setattr__(self, "_private_destination", private_destination)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("connector state is private")
        object.__setattr__(self, name, value)

    def connect(self, *, operator_id: str, route_grant_digest: str) -> ConnectorReceipt:
        """Return only an opaque receipt; this deterministic model makes no connection."""
        if _id(operator_id, "connector-request-operator") != self.operator_id:
            raise LabRejected("connector operator rejected", code="connector-operator-rejected")
        return ConnectorReceipt(
            operator_id=self.operator_id,
            route_grant_digest=route_grant_digest,
            connector_digest=sha256(self._private_destination.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class OperatorReport:
    """A safe aggregate report with neither endpoint data nor raw audit subjects."""

    operator_id: str
    admitted: int
    denied: int
    overloads: int
    audit_event_count: int
    audit_tail_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _id(self.operator_id, "report-operator"))
        for field in ("admitted", "denied", "overloads", "audit_event_count"):
            value = getattr(self, field)
            if type(value) is not int or not 0 <= value <= MAX_UINT64:
                raise LabRejected("report count is outside the uint64 range", code="report-count-invalid")
        object.__setattr__(self, "audit_tail_digest", _digest(self.audit_tail_digest, "report-audit-tail"))

    @classmethod
    def from_audit(cls, audit: AuditLog, *, admitted: int, denied: int, overloads: int) -> OperatorReport:
        if type(audit) is not AuditLog:
            raise LabRejected("report audit is invalid", code="report-audit-invalid")
        events = audit.events
        tail = events[-1].sequence if events else 0
        audit_tail_digest = sha256(f"{audit.operator_id}:{len(events)}:{tail}".encode("ascii")).hexdigest()
        return cls(
            operator_id=audit.operator_id,
            admitted=admitted,
            denied=denied,
            overloads=overloads,
            audit_event_count=len(events),
            audit_tail_digest=audit_tail_digest,
        )


_TOPOLOGY_FIELDS = frozenset({"schema", "operators", "connector_id", "edges"})
_TOPOLOGY_SCHEMA = "nbsr-wp7-two-operator-lab-v1"
_CANONICAL_OPERATORS = ("isp-a", "isp-b")
_CANONICAL_CONNECTOR = "isp-b-connector"
_CANONICAL_EDGES = (("isp-a", "isp-b-connector"), ("isp-b-connector", "isp-b"))


@dataclass(frozen=True, slots=True)
class LabTopology:
    """The closed three-node WP7 topology; it cannot represent a direct ISP edge."""

    operators: tuple[str, str]
    connector_id: str
    edges: tuple[tuple[str, str], tuple[str, str]]

    def __post_init__(self) -> None:
        if self.operators != _CANONICAL_OPERATORS:
            raise LabRejected("topology operators must be the canonical bounded pair", code="topology-operators-invalid")
        if self.connector_id != _CANONICAL_CONNECTOR:
            raise LabRejected("topology connector is not canonical", code="topology-connector-invalid")
        if self.edges != _CANONICAL_EDGES:
            if any(edge == _CANONICAL_OPERATORS for edge in self.edges):
                raise LabRejected("topology direct operator edge is forbidden", code="topology-direct-edge")
            raise LabRejected("topology edges are not canonical", code="topology-edges-invalid")

    @classmethod
    def from_dict(cls, value: object) -> LabTopology:
        if not isinstance(value, dict) or set(value) != _TOPOLOGY_FIELDS or not all(type(key) is str for key in value):
            raise LabRejected("topology must contain exactly the approved fields", code="topology-schema-invalid")
        if value["schema"] != _TOPOLOGY_SCHEMA:
            raise LabRejected("topology schema is invalid", code="topology-schema-invalid")
        operators = value["operators"]
        if type(operators) is not list or len(operators) != 2:
            raise LabRejected("topology operators must be the canonical bounded pair", code="topology-operators-invalid")
        if not all(type(item) is str for item in operators):
            raise LabRejected("topology operators must be identifiers", code="topology-operators-invalid")
        connector_id = _id(value["connector_id"], "topology-connector")
        edges = value["edges"]
        if type(edges) is not list or len(edges) != 2:
            raise LabRejected("topology edges must be the canonical bounded pair", code="topology-edges-invalid")
        parsed_edges: list[tuple[str, str]] = []
        for edge in edges:
            if not isinstance(edge, dict) or set(edge) != {"source", "destination"}:
                raise LabRejected("topology edge is invalid", code="topology-edge-invalid")
            parsed_edges.append((_id(edge["source"], "topology-edge-source"), _id(edge["destination"], "topology-edge-destination")))
        if _CANONICAL_OPERATORS in parsed_edges:
            raise LabRejected("topology direct operator edge is forbidden", code="topology-direct-edge")
        return cls(operators=tuple(operators), connector_id=connector_id, edges=tuple(parsed_edges))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class RawScanResult:
    """Deterministic simulated reachability with no connector or origin discovery."""

    reachable_nodes: tuple[str, str, str]
    direct_operator_edges: tuple[()]
    discovered_connector_digests: tuple[()]


def simulate_raw_scan(topology: LabTopology) -> RawScanResult:
    """Simulate a bounded raw scan of the public topology, never an origin probe."""
    if type(topology) is not LabTopology:
        raise LabRejected("scan topology is invalid", code="scan-topology-invalid")
    return RawScanResult(
        reachable_nodes=(topology.operators[0], topology.connector_id, topology.operators[1]),
        direct_operator_edges=(),
        discovered_connector_digests=(),
    )
