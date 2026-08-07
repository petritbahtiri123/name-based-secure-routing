from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from nbsr.federation.delegation import DelegationScope
from nbsr.federation.fields import _Record, _authority_reference, _bytes, _common, _fail, _uint
from nbsr.federation.registry import AuthorityClass, KeyLifecycle, ObjectType


def _references(value: object, minimum: int, maximum: int, label: str) -> tuple[dict[int, object], ...]:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail(f"{label} violates its resource bound")
    checked = tuple(_authority_reference(item, label) for item in value)
    encoded_order = [(item[1], item[2], item[3], item[4] or b"") for item in checked]
    if encoded_order != sorted(encoded_order) or len(set(encoded_order)) != len(encoded_order):
        _fail(f"{label} must be sorted and unique")
    return checked


def _thresholds(value: object) -> dict[int, tuple[int, int]]:
    if type(value) is not dict or set(value) != {1, 2, 3}:
        _fail("thresholds must be a closed three-member map")
    result: dict[int, tuple[int, int]] = {}
    for key, pair in value.items():
        if type(pair) is not list or len(pair) != 2:
            _fail("threshold pair is malformed")
        numerator = _uint(pair[0], 1, 256, "threshold numerator")
        denominator = _uint(pair[1], numerator, 256, "threshold denominator")
        result[key] = (numerator, denominator)
    return result


@dataclass(frozen=True, slots=True)
class TrustTransitionBinding:
    digest: bytes
    candidate_digest: bytes
    accepted: bool
    authenticated: bool
    old_generation: int
    new_generation: int
    scope: Mapping[int, object]
    restore_or_narrow_only: bool

    def __post_init__(self) -> None:
        _fail("trust threshold transport packaging is not frozen")


@dataclass(frozen=True, slots=True)
class FederationTrustBundle(_Record):
    REQUIRED = set(range(1, 8)) | set(range(32, 42))
    ALLOWED = REQUIRED | {8, 31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> FederationTrustBundle:
        payload = cls._decode(raw)
        _common(payload, ObjectType.FederationTrustBundle, cls.REQUIRED, cls.ALLOWED)
        issuer = _authority_reference(payload[3], "issuer_id")
        if issuer[1] != AuthorityClass.FEDERATION_AUTHORITY:
            _fail("trust bundle issuer must be a federation authority")
        DelegationScope.from_mapping(payload[32])
        roots = _references(payload[33], 1, 32, "roots")
        purpose_keys = _references(payload[34], 1, 256, "purpose_keys")
        logs = _references(payload[35], 1, 32, "logs")
        witnesses = _references(payload[36], 0, 32, "witnesses")
        if any(item[1] != AuthorityClass.OPERATOR_IDENTITY_ROOT for item in roots):
            _fail("roots require identity-root authority")
        if any(item[1] != AuthorityClass.FEDERATION_AUTHORITY for item in purpose_keys):
            _fail("purpose keys require federation authority")
        if any(item[1] != AuthorityClass.TRANSPARENCY_LOG for item in logs):
            _fail("logs require transparency-log authority")
        if any(item[1] != AuthorityClass.WITNESS for item in witnesses):
            _fail("witnesses require witness authority")
        thresholds = _thresholds(payload[37])
        if thresholds[2][0] > len(witnesses) or thresholds[3][0] > len(logs):
            _fail("threshold exceeds configured authorities")
        if (
            type(payload[38]) is not list
            or not 1 <= len(payload[38]) <= 64
            or any(type(item) is not int or item < 1 for item in payload[38])
            or payload[38] != sorted(set(payload[38]))
        ):
            _fail("profiles must be sorted unique approved versions")
        _references(payload[39], 1, 64, "revocation_sources")
        _uint(payload[40], 0, 900, "max_staleness")
        if payload[41] is not None:
            _bytes(payload[41], 32, 32, "policy_reference")
        if payload[7] <= payload[6]:
            _fail("bundle validity window is invalid")
        return cls(MappingProxyType(payload))

    @property
    def scope(self) -> DelegationScope:
        return DelegationScope.from_mapping(self._payload[32])

    @property
    def profiles(self) -> frozenset[int]:
        return frozenset(self._payload[38])

    @property
    def max_staleness(self) -> int:
        return self._payload[40]

    def require_fresh(self, now: int) -> None:
        self.require_valid_at(now)
        if now - self.not_before > self.max_staleness:
            _fail("trust bundle is stale")

    def require_usable_keys(self, lifecycles: Mapping[bytes, KeyLifecycle]) -> None:
        for key in (self._payload[3], *self._payload[33], *self._payload[34], *self._payload[35], *self._payload[36], *self._payload[39]):
            if lifecycles.get(key[3]) is not KeyLifecycle.ACTIVE:
                _fail("trust authority key is not active")

    def require_newer_than(self, current: FederationTrustBundle, *, transition: TrustTransitionBinding | None = None) -> bool:
        candidate = (self.generation, self.sequence)
        accepted = (current.generation, current.sequence)
        if candidate < accepted:
            _fail("trust bundle rollback")
        if candidate == accepted:
            if self.digest == current.digest:
                return False
            _fail("equal-version trust bundle equivocation")
        if self._payload.get(8) != current.digest:
            _fail("trust bundle previous digest is invalid")
        new_generation = self.generation != current.generation
        if self.generation == current.generation:
            if self.sequence != current.sequence + 1:
                _fail("trust bundle sequence continuity is invalid")
        elif self.generation == current.generation + 1 and self.sequence == 1:
            if (
                not isinstance(transition, TrustTransitionBinding)
                or not transition.accepted
                or not transition.authenticated
                or type(transition.digest) is not bytes
                or len(transition.digest) != 32
                or transition.candidate_digest != self.digest
                or transition.old_generation != current.generation
                or transition.new_generation != self.generation
                or transition.scope != self.scope.to_mapping()
                or not transition.restore_or_narrow_only
            ):
                _fail("trust bundle generation transition is invalid")
        else:
            _fail("trust bundle generation continuity is invalid")
        current.scope.intersect(self.scope)
        for key in (33, 34, 35, 36, 39):
            if new_generation:
                old_classes = sorted(item[1] for item in current._payload[key])
                new_classes = sorted(item[1] for item in self._payload[key])
                if len(new_classes) > len(old_classes) or any(
                    new_classes.count(item) > old_classes.count(item) for item in set(new_classes)
                ):
                    _fail("trust bundle recovery would widen authority classes or count")
            elif not set(map(repr, self._payload[key])) <= set(map(repr, current._payload[key])):
                _fail("trust bundle update would widen authority")
        if not set(self._payload[38]) <= set(current._payload[38]):
            _fail("trust bundle update would widen supported profiles")
        for key in (1, 2, 3):
            old_num, old_den = _thresholds(current._payload[37])[key]
            new_num, new_den = _thresholds(self._payload[37])[key]
            if new_num < old_num or new_den > old_den:
                _fail("trust bundle update would weaken a threshold")
        if self.max_staleness > current.max_staleness:
            _fail("trust bundle update would widen staleness")
        return True


class TrustBundleStore:
    def __init__(self, current: FederationTrustBundle | None = None) -> None:
        self.current = current
        self.conflicts: tuple[FederationTrustBundle, ...] = ()

    def accept(self, candidate: FederationTrustBundle, *, transition: TrustTransitionBinding | None = None) -> str:
        if self.current is None:
            if (candidate.generation, candidate.sequence) != (1, 1) or 8 in candidate._payload:
                _fail("trust bundle genesis is invalid")
            self.current = candidate
            return "ACCEPT"
        try:
            changed = candidate.require_newer_than(self.current, transition=transition)
        except Exception as exc:
            if "equivocation" in str(exc):
                by_digest = {item.digest: item for item in (*self.conflicts, self.current, candidate)}
                self.conflicts = tuple(by_digest.values())
                return "QUARANTINE"
            raise
        if not changed:
            return "IDEMPOTENT"
        self.current = candidate
        return "ACCEPT"


@dataclass(frozen=True, slots=True)
class ComposedTrust:
    scope: DelegationScope
    profiles: frozenset[int]
    max_staleness: int
    policy_references: frozenset[bytes]


def compose_bundles(first: FederationTrustBundle, second: FederationTrustBundle) -> ComposedTrust:
    scope = first.scope.intersect(second.scope)
    profiles = first.profiles & second.profiles
    if not profiles:
        _fail("trust bundle composition has no supported profile")
    policies = frozenset(item for item in (first._payload[41], second._payload[41]) if item is not None)
    return ComposedTrust(scope, profiles, min(first.max_staleness, second.max_staleness), policies)
