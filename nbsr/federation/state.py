from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from nbsr.federation.authorization import FederationResult
from nbsr.federation.profile import FederationProfile
from nbsr.federation.registry import DecisionOutcome, EnforcementMode, ReasonCode


_FRESH_ALLOWED = frozenset({"existing_session", "same_pair_reuse", "known_service", "known_endpoint_failover", "existing_context"})
_RESTRICTED_ALLOWED = frozenset({"existing_session", "same_pair_reuse", "same_authority_renewal", "existing_context"})
_EXPANSION = frozenset(
    {
        "new_authority",
        "new_trust",
        "first_discovery",
        "ownership_transfer",
        "new_delegation",
        "root_change",
        "key_activation",
        "recovery_completion",
        "operator_admission",
        "unknown_checkpoint",
    }
)
MAX_STATE_RECORDS = 4_096


@dataclass(frozen=True, slots=True, order=True)
class AcceptedFederationObject:
    key: str
    generation: int
    sequence: int
    object_digest: bytes
    object_kind: str
    operator_id: bytes
    peer_operator_id: bytes
    service_id: bytes
    dependencies: tuple[bytes, ...]
    valid_until: int | None
    source_fresh_at: int
    terminal: bool


@dataclass(frozen=True, slots=True, order=True)
class StaticRecoveryPolicy:
    policy_digest: bytes
    operators: tuple[bytes, bytes]
    service_id: bytes
    scope: str
    allowed_triggers: tuple[str, ...]
    activated_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class FederationEvent:
    key: str
    generation: int
    sequence: int
    object_digest: bytes
    object_kind: str
    operator_id: bytes
    peer_operator_id: bytes
    service_id: bytes
    previous_digest: bytes | None = None
    dependencies: tuple[bytes, ...] = ()
    valid_until: int | None = None
    source_fresh_at: int | None = None
    terminal: bool = False
    compromised: bool = False
    replay_digest: bytes | None = None
    validation_failures: tuple[ReasonCode, ...] = ()
    pending_until: int | None = None
    operation: str = "apply"
    requires_prior_authority: bool = False
    recovery_of: str | None = None
    static_policy_digest: bytes | None = None
    outage_trigger: str | None = None
    authority_expansion: bool = False


def _hex(value: bytes | None) -> str | None:
    return None if value is None else value.hex()


def _accepted_value(item: AcceptedFederationObject) -> dict[str, object]:
    return {
        "dependencies": [value.hex() for value in item.dependencies],
        "digest": item.object_digest.hex(),
        "fresh": item.source_fresh_at,
        "generation": item.generation,
        "key": item.key,
        "kind": item.object_kind,
        "operator": item.operator_id.hex(),
        "peer": item.peer_operator_id.hex(),
        "sequence": item.sequence,
        "service": item.service_id.hex(),
        "terminal": item.terminal,
        "valid_until": item.valid_until,
    }


@dataclass(frozen=True, slots=True)
class FederationState:
    accepted: tuple[AcceptedFederationObject, ...] = ()
    tombstones: tuple[str, ...] = ()
    quarantine: tuple[tuple[str, tuple[bytes, ...]], ...] = ()
    pending: tuple[tuple[str, int], ...] = ()
    replay: tuple[tuple[bytes, int], ...] = ()
    static_policies: tuple[StaticRecoveryPolicy, ...] = ()

    def __post_init__(self) -> None:
        if any(
            type(item.generation) is not int
            or item.generation < 1
            or type(item.sequence) is not int
            or item.sequence < 1
            or any(
                type(value) is not bytes or len(value) != 32
                for value in (item.object_digest, item.operator_id, item.peer_operator_id, item.service_id)
            )
            or type(item.terminal) is not bool
            or type(item.source_fresh_at) is not int
            or item.source_fresh_at < 0
            or len(item.dependencies) > FederationProfile.max_array_items
            for item in self.accepted
        ):
            raise ValueError("accepted federation state is invalid")
        if any(
            len(values) > MAX_STATE_RECORDS
            for values in (self.accepted, self.tombstones, self.quarantine, self.pending, self.replay, self.static_policies)
        ):
            raise ValueError("federation state exceeds retained record limit")
        if any(type(value) is not str or not value for value in self.tombstones):
            raise ValueError("terminal tombstone state is invalid")
        if any(type(key) is not str or not key or type(until) is not int or until < 0 for key, until in self.pending):
            raise ValueError("pending evidence state is invalid")
        if any(
            type(key) is not str or not key or len(digests) < 2 or any(type(value) is not bytes or len(value) != 32 for value in digests)
            for key, digests in self.quarantine
        ):
            raise ValueError("quarantine evidence state is invalid")
        if any(type(value) is not bytes or len(value) != 32 or type(seen) is not int or seen < 0 for value, seen in self.replay):
            raise ValueError("replay state is invalid")
        if any(
            type(item.policy_digest) is not bytes
            or len(item.policy_digest) != 32
            or len(item.operators) != 2
            or any(type(value) is not bytes or len(value) != 32 for value in item.operators)
            or type(item.service_id) is not bytes
            or len(item.service_id) != 32
            or type(item.scope) is not str
            or not item.scope
            or not item.allowed_triggers
            or any(type(value) is not str or not value for value in item.allowed_triggers)
            or type(item.activated_at) is not int
            or type(item.expires_at) is not int
            or item.activated_at < 0
            or item.expires_at <= item.activated_at
            for item in self.static_policies
        ):
            raise ValueError("static recovery policy state is invalid")
        if self.accepted != tuple(sorted(self.accepted, key=lambda item: item.key)) or len({item.key for item in self.accepted}) != len(
            self.accepted
        ):
            raise ValueError("accepted federation state must be sorted and unique")
        if self.tombstones != tuple(sorted(set(self.tombstones))):
            raise ValueError("terminal tombstones must be sorted and unique")
        if self.quarantine != tuple(sorted(self.quarantine)) or self.pending != tuple(sorted(self.pending)):
            raise ValueError("retained evidence must be canonical")
        if self.replay != tuple(sorted(self.replay)) or len({key for key, _ in self.replay}) != len(self.replay):
            raise ValueError("replay state must be sorted and unique")

    @classmethod
    def empty(cls, *, static_policies: tuple[StaticRecoveryPolicy, ...] = ()) -> FederationState:
        return cls(static_policies=tuple(sorted(static_policies)))

    @property
    def digest(self) -> bytes:
        value = {
            "accepted": [_accepted_value(item) for item in self.accepted],
            "pending": [[key, until] for key, until in self.pending],
            "quarantine": [[key, [digest.hex() for digest in digests]] for key, digests in self.quarantine],
            "replay": [[digest.hex(), seen] for digest, seen in self.replay],
            "static": [
                {
                    "activated": item.activated_at,
                    "digest": item.policy_digest.hex(),
                    "expires": item.expires_at,
                    "operators": [value.hex() for value in item.operators],
                    "scope": item.scope,
                    "service": item.service_id.hex(),
                    "triggers": list(item.allowed_triggers),
                }
                for item in self.static_policies
            ],
            "tombstones": list(self.tombstones),
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
        return hashlib.sha256(encoded).digest()

    def _result(
        self, outcome: DecisionOutcome, reason: ReasonCode, enforcement: EnforcementMode = EnforcementMode.NONE, **values: object
    ) -> FederationResult:
        return FederationResult(outcome, reason, enforcement, self.digest, **values)  # type: ignore[arg-type]

    def apply(self, event: FederationEvent, now: int) -> tuple[FederationState, FederationResult]:
        if type(event) is not FederationEvent or type(now) is not int or now < 0:
            return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_PARSE)
        if event.validation_failures:
            reason = min(event.validation_failures, key=int)
            if reason is ReasonCode.ERR_EVIDENCE_MISSING and event.pending_until is not None and now <= event.pending_until:
                return self, self._result(DecisionOutcome.PENDING, reason, EnforcementMode.DENY_NEW_USE, retry_at=event.pending_until)
            return self, self._result(DecisionOutcome.REJECT, reason, EnforcementMode.DENY_NEW_USE)
        if event.requires_prior_authority and not self.accepted:
            return self, self._result(DecisionOutcome.PENDING, ReasonCode.ERR_EVIDENCE_MISSING, EnforcementMode.DENY_NEW_USE)
        current = next((item for item in self.accepted if item.key == event.key), None)
        if current is not None and (event.generation, event.sequence) < (current.generation, current.sequence):
            return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_ROLLBACK, EnforcementMode.DENY_NEW_USE)
        if event.replay_digest is not None and event.replay_digest in dict(self.replay):
            return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_REPLAY, EnforcementMode.DENY_NEW_USE)
        if event.operation == "static_recovery":
            return self, self._static_recovery(event, now)
        freshness = current.source_fresh_at if current is not None else event.source_fresh_at
        if event.operation != "apply" and event.operation != "reconcile" and freshness is not None:
            age = now - freshness
            if event.compromised or event.key in self.tombstones:
                return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_REVOKED, EnforcementMode.TERMINATE_ACTIVE_USE)
            if current is None or (
                event.object_digest != current.object_digest
                or event.generation != current.generation
                or event.sequence != current.sequence
                or event.operator_id != current.operator_id
                or event.peer_operator_id != current.peer_operator_id
                or event.service_id != current.service_id
                or tuple(sorted(set(event.dependencies))) != current.dependencies
            ):
                return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_AUTHORITY, EnforcementMode.DENY_NEW_USE)
            if event.operation in _EXPANSION or event.authority_expansion:
                return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_OUTAGE_POLICY, EnforcementMode.DENY_NEW_USE)
            if age < FederationProfile.trust_freshness_seconds and event.operation in _FRESH_ALLOWED:
                return self, self._result(DecisionOutcome.ACCEPT, ReasonCode.NONE)
            if age < FederationProfile.degraded_staleness_seconds and event.operation in _RESTRICTED_ALLOWED:
                return self, self._result(
                    DecisionOutcome.RESTRICTED,
                    ReasonCode.ERR_FRESHNESS,
                    EnforcementMode.REAUTHENTICATE,
                    retry_at=freshness + FederationProfile.degraded_staleness_seconds,
                    audit=("restricted-degraded-mode",),
                )
            return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_OUTAGE_POLICY, EnforcementMode.DRAIN)

        if current is not None:
            candidate_version = (event.generation, event.sequence)
            current_version = (current.generation, current.sequence)
            if candidate_version < current_version:
                return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_ROLLBACK, EnforcementMode.DENY_NEW_USE)
            if candidate_version == current_version:
                if event.object_digest == current.object_digest:
                    return self, self._result(DecisionOutcome.ACCEPT, ReasonCode.NONE)
                quarantine = dict(self.quarantine)
                evidence = tuple(sorted(set(quarantine.get(event.key, ()) + (current.object_digest, event.object_digest))))
                if quarantine.get(event.key) == evidence:
                    return self, self._result(
                        DecisionOutcome.QUARANTINE,
                        ReasonCode.ERR_EQUIVOCATION,
                        EnforcementMode.DENY_NEW_USE,
                        evidence=evidence,
                    )
                quarantine[event.key] = evidence
                successor = self._replace(quarantine=tuple(sorted(quarantine.items())))
                return successor, FederationResult(
                    DecisionOutcome.QUARANTINE,
                    ReasonCode.ERR_EQUIVOCATION,
                    EnforcementMode.DENY_NEW_USE,
                    successor.digest,
                    True,
                    evidence=evidence,
                )
            if event.previous_digest != current.object_digest:
                return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_CONTINUITY, EnforcementMode.DENY_NEW_USE)
            if not (
                event.generation == current.generation
                and event.sequence == current.sequence + 1
                or event.generation == current.generation + 1
                and event.sequence == 1
            ):
                return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_CONTINUITY, EnforcementMode.DENY_NEW_USE)
        elif not (event.generation == 1 and event.sequence == 1 or event.sequence == 1 and event.recovery_of in self.tombstones):
            return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_CONTINUITY, EnforcementMode.DENY_NEW_USE)

        if event.key in self.tombstones:
            return self, self._result(DecisionOutcome.REJECT, ReasonCode.ERR_TERMINAL_STATE, EnforcementMode.TERMINATE_ACTIVE_USE)
        if event.compromised:
            return self, self._result(
                DecisionOutcome.REJECT,
                ReasonCode.ERR_REVOKED,
                EnforcementMode.TERMINATE_ACTIVE_USE,
                invalidated_dependencies=tuple(sorted(event.dependencies)),
            )
        record = AcceptedFederationObject(
            event.key,
            event.generation,
            event.sequence,
            event.object_digest,
            event.object_kind,
            event.operator_id,
            event.peer_operator_id,
            event.service_id,
            tuple(sorted(set(event.dependencies))),
            event.valid_until,
            now if event.source_fresh_at is None else event.source_fresh_at,
            event.terminal,
        )
        accepted = {item.key: item for item in self.accepted}
        accepted[event.key] = record
        tombstones = set(self.tombstones)
        if event.terminal:
            tombstones.add(event.key)
        replay = dict(self.replay)
        if event.replay_digest is not None:
            replay[event.replay_digest] = now
        successor = self._replace(
            accepted=tuple(sorted(accepted.values(), key=lambda item: item.key)),
            tombstones=tuple(sorted(tombstones)),
            replay=tuple(sorted(replay.items())),
        )
        invalidated = tuple(sorted(event.dependencies)) if event.compromised or event.terminal else ()
        enforcement = EnforcementMode.TERMINATE_ACTIVE_USE if event.compromised else EnforcementMode.NONE
        audit = ("federation-recovered", "static-operation-reconciled") if event.operation == "reconcile" else ()
        return successor, FederationResult(
            DecisionOutcome.ACCEPT,
            ReasonCode.NONE,
            enforcement,
            successor.digest,
            True,
            (event.object_digest,),
            invalidated_dependencies=invalidated,
            audit=audit,
        )

    def _static_recovery(self, event: FederationEvent, now: int) -> FederationResult:
        if event.key in self.tombstones:
            return self._result(DecisionOutcome.REJECT, ReasonCode.ERR_REVOKED, EnforcementMode.TERMINATE_ACTIVE_USE)
        policy = next((item for item in self.static_policies if item.policy_digest == event.static_policy_digest), None)
        valid = (
            policy is not None
            and policy.activated_at + FederationProfile.static_recovery_warning_seconds <= now < policy.expires_at
            and now < policy.activated_at + FederationProfile.static_recovery_expiry_seconds
            and (event.operator_id, event.peer_operator_id) == policy.operators
            and event.service_id == policy.service_id
            and event.key == policy.scope
            and event.outage_trigger in policy.allowed_triggers
            and not event.authority_expansion
            and event.key not in self.tombstones
        )
        if not valid:
            return self._result(DecisionOutcome.REJECT, ReasonCode.ERR_RECOVERY_INVALID, EnforcementMode.DENY_NEW_USE)
        return self._result(
            DecisionOutcome.RESTRICTED,
            ReasonCode.ERR_OUTAGE_POLICY,
            EnforcementMode.DENY_NEW_USE,
            retry_at=policy.expires_at,
            audit=("static-recovery-active", "federation-retry-continuing"),
        )

    def compact(self, now: int) -> FederationState:
        replay = tuple((digest, seen) for digest, seen in self.replay if now - seen <= FederationProfile.replay_retention_min_seconds)
        return self if replay == self.replay else self._replace(replay=replay)

    def _replace(self, **changes: object) -> FederationState:
        values = {
            "accepted": self.accepted,
            "tombstones": self.tombstones,
            "quarantine": self.quarantine,
            "pending": self.pending,
            "replay": self.replay,
            "static_policies": self.static_policies,
        }
        values.update(changes)
        return FederationState(**values)  # type: ignore[arg-type]
