"""Immutable, bounded resolution context state for the WP2 Name Node."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_address
from threading import RLock

from nbsr.originset import DerivedOriginSet
from nbsr.protocol import ErrorCode, ProtocolViolation, RouteIntent
from nbsr.protocol.fields import require_timestamp
from nbsr.synthetic import SyntheticMapping


_MAX_ENTRIES = 1_000_000


def _profile_error(message: str) -> ProtocolViolation:
    return ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, message)


def _require_synthetic_mapping(value: object) -> SyntheticMapping:
    if type(value) is not SyntheticMapping:
        raise _profile_error("mapping must be an immutable SyntheticMapping")
    if type(value.hostname) is not str or type(value.ipv4) is not str or type(value.ipv6) is not str:
        raise _profile_error("SyntheticMapping fields have invalid types")
    try:
        ipv4 = ip_address(value.ipv4)
        ipv6 = ip_address(value.ipv6)
    except ValueError as exc:
        raise _profile_error("SyntheticMapping contains an invalid address") from exc
    if not isinstance(ipv4, IPv4Address) or not isinstance(ipv6, IPv6Address):
        raise _profile_error("SyntheticMapping address families are invalid")
    if str(ipv4) != value.ipv4 or str(ipv6) != value.ipv6:
        raise _profile_error("SyntheticMapping addresses must use canonical text")
    if type(value.expires_at) is not datetime or value.expires_at.utcoffset() is None:
        raise _profile_error("SyntheticMapping expiry must be timezone-aware")
    return value


class NameClassification(StrEnum):
    NBSR_SERVICE = "nbsr-service"
    LEGACY_SERVICE = "legacy-service"


@dataclass(frozen=True, slots=True)
class ResolutionBinding:
    mapping: SyntheticMapping
    route_intent: RouteIntent
    classification: NameClassification
    originset: DerivedOriginSet | None
    resolution_context_id: bytes = field(repr=False)
    expires_at: int

    def __post_init__(self) -> None:
        checked_mapping = _require_synthetic_mapping(self.mapping)
        if type(self.route_intent) is not RouteIntent:
            raise _profile_error("route_intent must be an immutable RouteIntent")
        if type(self.classification) is not NameClassification:
            raise _profile_error("classification must be a NameClassification")
        if type(self.resolution_context_id) is not bytes or len(self.resolution_context_id) != 32:
            raise _profile_error("resolution_context_id must be exactly 32 bytes")
        if sha256(self.resolution_context_id).digest() != self.route_intent.resolution_context_digest:
            raise _profile_error("resolution_context_id digest does not match RouteIntent")
        if checked_mapping.hostname != self.route_intent.canonical_name:
            raise _profile_error("SyntheticMapping and RouteIntent names do not match")

        checked_expiry = require_timestamp(
            self.expires_at,
            message="Invalid ResolutionBinding expiry",
        )
        if checked_expiry <= self.route_intent.created_at:
            raise _profile_error("ResolutionBinding has an invalid validity window")
        if checked_expiry > self.route_intent.expires_at:
            raise _profile_error("ResolutionBinding outlives its RouteIntent")
        if checked_expiry > checked_mapping.expires_at.timestamp():
            raise _profile_error("ResolutionBinding outlives its SyntheticMapping")

        if self.classification is NameClassification.NBSR_SERVICE:
            if self.originset is not None:
                raise _profile_error("NBSR service binding cannot contain an OriginSet")
        else:
            if type(self.originset) is not DerivedOriginSet:
                raise _profile_error("Legacy service binding requires a DerivedOriginSet")
            if self.originset.service_id != self.route_intent.service_id:
                raise _profile_error("OriginSet service does not match RouteIntent")
            if self.originset.service_record_generation != self.route_intent.record_sequence:
                raise _profile_error("OriginSet generation does not match RouteIntent")

        object.__setattr__(self, "expires_at", checked_expiry)


class ResolutionContextStore:
    """Bounded name and address indexes updated under one lock."""

    def __init__(self, *, max_entries: int) -> None:
        if type(max_entries) is not int or not 1 <= max_entries <= _MAX_ENTRIES:
            raise ValueError("max_entries must be an integer from 1 to 1000000")
        self._max_entries = max_entries
        self._by_name: dict[str, ResolutionBinding] = {}
        self._by_address: dict[str, ResolutionBinding] = {}
        self._lock = RLock()

    def commit(self, binding: ResolutionBinding, *, now: int) -> None:
        checked_now = require_timestamp(now, message="Invalid ResolutionContextStore time")
        if type(binding) is not ResolutionBinding:
            raise _profile_error("binding must be an immutable ResolutionBinding")
        if not binding.route_intent.created_at <= checked_now < binding.expires_at:
            raise _profile_error("ResolutionBinding is not valid at commit time")

        with self._lock:
            self._expire_locked(checked_now)
            current = self._by_name.get(binding.mapping.hostname)
            candidate_pair = (binding.mapping.ipv4, binding.mapping.ipv6)
            if current is not None:
                current_pair = (current.mapping.ipv4, current.mapping.ipv6)
                if candidate_pair != current_pair:
                    raise _profile_error("Live synthetic mapping pair cannot change")

            for address in candidate_pair:
                conflicting = self._by_address.get(address)
                if conflicting is not None and conflicting.mapping.hostname != binding.mapping.hostname:
                    raise _profile_error("Synthetic address is already bound to another name")

            if current is None and len(self._by_name) >= self._max_entries:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_HANDLE_EXHAUSTED,
                    "Resolution context capacity exceeded",
                )

            self._by_name[binding.mapping.hostname] = binding
            self._by_address[binding.mapping.ipv4] = binding
            self._by_address[binding.mapping.ipv6] = binding

    def lookup(self, synthetic_address: str, *, now: int) -> ResolutionBinding | None:
        checked_now = require_timestamp(now, message="Invalid ResolutionContextStore time")
        if type(synthetic_address) is not str:
            raise _profile_error("synthetic_address must be an IP address string")
        try:
            checked_address = str(ip_address(synthetic_address))
        except ValueError as exc:
            raise _profile_error("synthetic_address must be an IP address string") from exc

        with self._lock:
            self._expire_locked(checked_now)
            return self._by_address.get(checked_address)

    def _expire_locked(self, now: int) -> None:
        expired_names = [name for name, binding in self._by_name.items() if binding.expires_at <= now]
        for name in expired_names:
            binding = self._by_name.pop(name)
            self._by_address.pop(binding.mapping.ipv4, None)
            self._by_address.pop(binding.mapping.ipv6, None)
