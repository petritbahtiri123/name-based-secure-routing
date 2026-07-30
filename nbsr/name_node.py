"""Synthetic-only WP2A Name Node core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from threading import RLock
from time import monotonic

from nbsr.legacy_origin import (
    CandidateValidator,
    LegacyDnsSnapshot,
    LegacyOriginCache,
    LegacyOriginCapacityError,
    LegacyOriginRequest,
    LegacyOriginUnavailable,
    LegacyOriginValidationError,
)
from nbsr.name_registry import SignedServiceRegistry
from nbsr.name_node_observability import NameNodeEvent
from nbsr.protocol import ErrorCode, ProtocolViolation, RouteIntent, ServiceRecord
from nbsr.protocol.fields import (
    normalize_presentation_name,
    require_bytes,
    require_canonical_name,
    require_ordered_unique_tuple,
    require_port,
    require_sequence,
    require_text_id,
    require_timestamp,
)
from nbsr.resolution_state import NameClassification, ResolutionBinding, ResolutionContextStore
from nbsr.synthetic import SyntheticAddressPool, SyntheticPoolExhausted


LegacySnapshotProvider = Callable[[LegacyOriginRequest, int], LegacyDnsSnapshot]


def _profile_error(message: str) -> ProtocolViolation:
    return ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, message)


def _require_policy_hash(value: object) -> bytes:
    return require_bytes(
        value,
        minimum=32,
        maximum=32,
        message="policy_hash must be exactly 32 bytes",
    )


def _require_strict_text_set(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise _profile_error("textual identifier set must be an immutable tuple")
    return require_ordered_unique_tuple(
        value,
        item_validator=require_text_id,
        minimum_items=1,
        maximum_items=16,
        message="invalid textual identifier set",
    )


def _require_strict_ports(value: object) -> tuple[int, ...]:
    if type(value) is not tuple:
        raise _profile_error("allowed_ports must be an immutable tuple")
    return require_ordered_unique_tuple(
        value,
        item_validator=require_port,
        minimum_items=1,
        maximum_items=32,
        message="invalid allowed_ports",
    )


def _require_networks(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= 32:
        raise _profile_error("allowed_networks must be a bounded immutable tuple")
    networks: list[str] = []
    try:
        for item in value:
            if type(item) is not str:
                raise ValueError
            network = ip_network(item, strict=True)
            if item != str(network) or network.prefixlen == 0:
                raise ValueError
            networks.append(item)
    except ValueError as exc:
        raise _profile_error("allowed_networks contains an invalid network") from exc
    if tuple(networks) != tuple(sorted(set(networks))):
        raise _profile_error("allowed_networks must be sorted and unique")
    return tuple(networks)


@dataclass(frozen=True, slots=True)
class NbsrServicePolicy:
    canonical_name: str
    source_operator_id: str
    source_edge_id: str
    policy_hash: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_name", require_canonical_name(self.canonical_name))
        object.__setattr__(self, "source_operator_id", require_text_id(self.source_operator_id))
        object.__setattr__(self, "source_edge_id", require_text_id(self.source_edge_id))
        object.__setattr__(self, "policy_hash", _require_policy_hash(self.policy_hash))


@dataclass(frozen=True, slots=True)
class LegacyServicePolicy:
    canonical_name: str
    service_id: str
    service_record_generation: int
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_set: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    policy_hash: bytes
    issuer_id: bytes
    origin_name: str
    allowed_networks: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_name", require_canonical_name(self.canonical_name))
        object.__setattr__(self, "service_id", require_text_id(self.service_id))
        object.__setattr__(
            self,
            "service_record_generation",
            require_sequence(self.service_record_generation),
        )
        for field_name in (
            "source_operator_id",
            "source_edge_id",
            "destination_operator_id",
        ):
            object.__setattr__(self, field_name, require_text_id(getattr(self, field_name)))
        object.__setattr__(
            self,
            "destination_edge_set",
            _require_strict_text_set(self.destination_edge_set),
        )
        object.__setattr__(self, "allowed_ports", _require_strict_ports(self.allowed_ports))
        object.__setattr__(self, "policy_hash", _require_policy_hash(self.policy_hash))
        object.__setattr__(
            self,
            "issuer_id",
            require_bytes(
                self.issuer_id,
                minimum=1,
                maximum=64,
                message="issuer_id is invalid",
            ),
        )
        object.__setattr__(self, "origin_name", require_canonical_name(self.origin_name))
        object.__setattr__(self, "allowed_networks", _require_networks(self.allowed_networks))


@dataclass(frozen=True, slots=True)
class NameResolution:
    classification: NameClassification
    canonical_name: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    route_id: bytes
    expires_at: int

    def __post_init__(self) -> None:
        if type(self.classification) is not NameClassification:
            raise _profile_error("classification must be a NameClassification")
        object.__setattr__(self, "canonical_name", require_canonical_name(self.canonical_name))
        try:
            ipv4 = ip_address(self.synthetic_ipv4)
            ipv6 = ip_address(self.synthetic_ipv6)
        except ValueError as exc:
            raise _profile_error("synthetic addresses are invalid") from exc
        if (
            not isinstance(ipv4, IPv4Address)
            or not isinstance(ipv6, IPv6Address)
            or str(ipv4) != self.synthetic_ipv4
            or str(ipv6) != self.synthetic_ipv6
        ):
            raise _profile_error("synthetic address families or text are invalid")
        object.__setattr__(
            self,
            "route_id",
            require_bytes(
                self.route_id,
                minimum=16,
                maximum=16,
                message="route_id must be exactly 16 bytes",
            ),
        )
        object.__setattr__(self, "expires_at", require_timestamp(self.expires_at))


class NameNode:
    """Classify configured names and commit synthetic-only route state."""

    def __init__(
        self,
        registry: SignedServiceRegistry,
        nbsr_policies: tuple[NbsrServicePolicy, ...],
        legacy_policies: tuple[LegacyServicePolicy, ...],
        snapshot_provider: LegacySnapshotProvider,
        candidate_validator: CandidateValidator,
        legacy_cache: LegacyOriginCache,
        synthetic_pool: SyntheticAddressPool,
        context_store: ResolutionContextStore,
        id_source: Callable[[int], bytes],
        *,
        route_intent_lifetime_seconds: int = 300,
        event_sink: Callable[[NameNodeEvent], None] | None = None,
        audit_key: bytes | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if type(nbsr_policies) is not tuple or any(type(policy) is not NbsrServicePolicy for policy in nbsr_policies):
            raise _profile_error("nbsr_policies must contain immutable policy objects")
        if type(legacy_policies) is not tuple or any(type(policy) is not LegacyServicePolicy for policy in legacy_policies):
            raise _profile_error("legacy_policies must contain immutable policy objects")
        self._nbsr_policies = self._index_policies(nbsr_policies)
        self._legacy_policies = self._index_policies(legacy_policies)
        if self._nbsr_policies.keys() & self._legacy_policies.keys():
            raise _profile_error("NBSR and legacy policy names must not overlap")
        if not callable(snapshot_provider) or not callable(candidate_validator) or not callable(id_source):
            raise _profile_error("Name Node dependencies must be callable")
        if type(route_intent_lifetime_seconds) is not int or not 1 <= route_intent_lifetime_seconds <= 300:
            raise _profile_error("RouteIntent lifetime must be from 1 to 300 seconds")
        if event_sink is not None:
            if not callable(event_sink):
                raise _profile_error("event_sink must be callable")
            if type(audit_key) is not bytes or not 32 <= len(audit_key) <= 64:
                raise _profile_error("audit_key must contain 32 to 64 bytes")
        if not callable(monotonic_clock):
            raise _profile_error("monotonic_clock must be callable")

        self._registry = registry
        self._snapshot_provider = snapshot_provider
        self._candidate_validator = candidate_validator
        self._legacy_cache = legacy_cache
        self._synthetic_pool = synthetic_pool
        self._context_store = context_store
        self._id_source = id_source
        self._route_intent_lifetime_seconds = route_intent_lifetime_seconds
        self._event_sink = event_sink
        self._audit_key = audit_key
        self._monotonic_clock = monotonic_clock
        self._issued_ids: set[bytes] = set()
        self._lock = RLock()

    @staticmethod
    def _index_policies[T: NbsrServicePolicy | LegacyServicePolicy](
        policies: tuple[T, ...],
    ) -> dict[str, T]:
        indexed: dict[str, T] = {}
        for policy in policies:
            if policy.canonical_name in indexed:
                raise _profile_error("Policy names must be unique")
            indexed[policy.canonical_name] = policy
        return indexed

    def resolve(self, presentation_name: str, *, now: int) -> NameResolution:
        started_at = self._safe_clock()
        canonical_name: str | None = None
        classification: NameClassification | None = None
        try:
            canonical_name = normalize_presentation_name(presentation_name)
            checked_now = require_timestamp(now, message="Invalid Name Node time")
            with self._lock:
                policy = self._nbsr_policies.get(canonical_name)
                if policy is not None:
                    classification = NameClassification.NBSR_SERVICE
                    resolution = self._resolve_nbsr(policy, checked_now)
                else:
                    legacy_policy = self._legacy_policies.get(canonical_name)
                    if legacy_policy is None:
                        raise ProtocolViolation(
                            ErrorCode.NBSR_E_NAME_NOT_FOUND,
                            "Name is not configured",
                        )
                    classification = NameClassification.LEGACY_SERVICE
                    resolution = self._resolve_legacy(legacy_policy, checked_now)
            self._emit_event(
                canonical_name=canonical_name,
                classification=resolution.classification,
                error_code=None,
                started_at=started_at,
            )
            return resolution
        except ProtocolViolation as exc:
            self._emit_event(
                canonical_name=canonical_name,
                classification=classification,
                error_code=exc.code,
                started_at=started_at,
            )
            raise
        except Exception as exc:
            violation = ProtocolViolation(
                ErrorCode.NBSR_E_INTERNAL,
                "Name resolution failed",
            )
            self._emit_event(
                canonical_name=canonical_name,
                classification=classification,
                error_code=violation.code,
                started_at=started_at,
            )
            raise violation from exc

    def _safe_clock(self) -> float:
        try:
            value = self._monotonic_clock()
            return float(value)
        except Exception:
            return 0.0

    def _emit_event(
        self,
        *,
        canonical_name: str | None,
        classification: NameClassification | None,
        error_code: ErrorCode | None,
        started_at: float,
    ) -> None:
        if self._event_sink is None or self._audit_key is None:
            return
        try:
            event = NameNodeEvent.create(
                audit_key=self._audit_key,
                canonical_name=canonical_name or "invalid.nbsr",
                event_kind="resolution-failed" if error_code is not None else "resolution-succeeded",
                classification=classification,
                error_code=error_code,
                duration_ms=max(0.0, (self._safe_clock() - started_at) * 1_000),
                capacity_exhausted=error_code
                in (
                    ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
                    ErrorCode.NBSR_E_OVER_CAPACITY,
                ),
            )
            self._event_sink(event)
        except Exception:
            pass

    def _resolve_nbsr(self, policy: NbsrServicePolicy, now: int) -> NameResolution:
        record = self._registry.resolve(policy.canonical_name, now=now)
        if record is None:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_RECORD_UNTRUSTED,
                "Configured NBSR service has no trusted record",
            )
        if type(record) is not ServiceRecord or record.canonical_name != policy.canonical_name:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_RECORD_UNTRUSTED,
                "Configured NBSR service record is invalid",
            )

        expires_at = min(
            record.not_after,
            now + self._route_intent_lifetime_seconds,
        )
        context_id, route_id, lease_id = self._next_identifiers()
        intent = RouteIntent(
            intent_version=1,
            resolution_context_digest=sha256(context_id).digest(),
            canonical_name=record.canonical_name,
            service_id=record.service_id,
            source_operator_id=policy.source_operator_id,
            source_edge_id=policy.source_edge_id,
            destination_operator_id=record.destination_operator_id,
            destination_edge_set=record.destination_edge_set,
            allowed_transports=record.transports,
            allowed_ports=record.ports,
            created_at=now,
            expires_at=expires_at,
            record_sequence=record.sequence,
            policy_hash=policy.policy_hash,
            route_id=route_id,
            lease_id=lease_id,
        )
        try:
            mapping = self._synthetic_pool.allocate(
                record.canonical_name,
                datetime.fromtimestamp(now, UTC),
                minimum_valid_for_seconds=expires_at - now,
            )
        except SyntheticPoolExhausted as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
                "Synthetic mapping capacity exceeded",
            ) from exc
        binding = ResolutionBinding(
            mapping=mapping,
            route_intent=intent,
            classification=NameClassification.NBSR_SERVICE,
            originset=None,
            resolution_context_id=context_id,
            expires_at=expires_at,
        )
        self._context_store.commit(binding, now=now)
        return NameResolution(
            classification=NameClassification.NBSR_SERVICE,
            canonical_name=record.canonical_name,
            synthetic_ipv4=mapping.ipv4,
            synthetic_ipv6=mapping.ipv6,
            route_id=route_id,
            expires_at=expires_at,
        )

    def _resolve_legacy(self, policy: LegacyServicePolicy, now: int) -> NameResolution:
        request = LegacyOriginRequest(
            service_name=policy.canonical_name,
            service_id=policy.service_id,
            service_record_generation=policy.service_record_generation,
            issuer_id=policy.issuer_id,
            origin_name=policy.origin_name,
            allowed_ports=policy.allowed_ports,
            allowed_networks=policy.allowed_networks,
        )
        try:
            snapshot = self._snapshot_provider(request, now)
            if type(snapshot) is not LegacyDnsSnapshot:
                raise LegacyOriginValidationError("snapshot provider returned an invalid value")
            view = self._legacy_cache.apply_snapshot(
                request,
                snapshot,
                validator=self._candidate_validator,
            )
        except LegacyOriginCapacityError as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
                "Legacy origin cache capacity exceeded",
            ) from exc
        except LegacyOriginUnavailable as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_ORIGIN_UNAVAILABLE,
                "Validated legacy origin state is unavailable",
            ) from exc
        except LegacyOriginValidationError as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Legacy origin profile is invalid",
            ) from exc
        except ProtocolViolation:
            raise
        except Exception as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_INTERNAL,
                "Legacy snapshot provider failed",
            ) from exc

        expires_at = min(
            view.originset.expires_at,
            now + self._route_intent_lifetime_seconds,
        )
        context_id, route_id, lease_id = self._next_identifiers()
        intent = RouteIntent(
            intent_version=1,
            resolution_context_digest=sha256(context_id).digest(),
            canonical_name=policy.canonical_name,
            service_id=policy.service_id,
            source_operator_id=policy.source_operator_id,
            source_edge_id=policy.source_edge_id,
            destination_operator_id=policy.destination_operator_id,
            destination_edge_set=policy.destination_edge_set,
            allowed_transports=("tcp",),
            allowed_ports=policy.allowed_ports,
            created_at=now,
            expires_at=expires_at,
            record_sequence=policy.service_record_generation,
            policy_hash=policy.policy_hash,
            route_id=route_id,
            lease_id=lease_id,
        )
        try:
            mapping = self._synthetic_pool.allocate(
                policy.canonical_name,
                datetime.fromtimestamp(now, UTC),
                minimum_valid_for_seconds=expires_at - now,
            )
        except SyntheticPoolExhausted as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
                "Synthetic mapping capacity exceeded",
            ) from exc
        binding = ResolutionBinding(
            mapping=mapping,
            route_intent=intent,
            classification=NameClassification.LEGACY_SERVICE,
            originset=view.originset,
            resolution_context_id=context_id,
            expires_at=expires_at,
        )
        self._context_store.commit(binding, now=now)
        return NameResolution(
            classification=NameClassification.LEGACY_SERVICE,
            canonical_name=policy.canonical_name,
            synthetic_ipv4=mapping.ipv4,
            synthetic_ipv6=mapping.ipv6,
            route_id=route_id,
            expires_at=expires_at,
        )

    def _next_identifiers(self) -> tuple[bytes, bytes, bytes]:
        try:
            identifiers = (
                self._id_source(32),
                self._id_source(16),
                self._id_source(16),
            )
        except Exception as exc:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_INTERNAL,
                "Identifier generation failed",
            ) from exc
        expected_lengths = (32, 16, 16)
        if any(type(value) is not bytes or len(value) != length for value, length in zip(identifiers, expected_lengths)):
            raise _profile_error("Identifier source returned an invalid value")
        if len(set(identifiers)) != len(identifiers) or any(value in self._issued_ids for value in identifiers):
            raise _profile_error("Identifier source repeated a value")
        self._issued_ids.update(identifiers)
        return identifiers
