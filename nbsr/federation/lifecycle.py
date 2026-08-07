from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from nbsr.federation.delegation import DelegationScope
from nbsr.federation.fields import (
    _OPERATOR_TRANSITIONS,
    _Record,
    _authority_reference,
    _authority_target,
    _bytes,
    _closed_map,
    _common,
    _fail,
    _scope_narrow_or_equal,
    _uint,
)
from nbsr.federation.registry import ObjectType, OperatorLifecycle, RecoveryStage
from nbsr.federation.registry import KeyLifecycle, KeyPurpose
from nbsr.federation.cose import FederationAuthority


_AUTHENTICATED_RECOVERY_TOKEN = object()


def _base(payload: dict[int, object], kind: ObjectType, required: set[int], allowed: set[int]) -> None:
    if not required <= set(payload) or set(payload) - allowed or payload.get(1) != kind or payload.get(2) != 1:
        _fail("payload has missing, unknown, or invalid fields")


def _transparency(value: object) -> None:
    item = _closed_map(value, {1, 2, 3, 4}, "transparency reference")
    _bytes(item[1], 32, 32, "log")
    _bytes(item[2], 32, 32, "checkpoint")
    _uint(item[3], 0, (1 << 64) - 1, "tree size")
    if item[4] is not None:
        _bytes(item[4], 32, 32, "proof")


def _targets(value: object, label: str, minimum: int = 0) -> tuple[dict[int, object], ...]:
    if type(value) is not list or not minimum <= len(value) <= 256:
        _fail(f"{label} cardinality is invalid")
    items = tuple(_authority_target(item, label) for item in value)
    return items


def _signatures(value: object) -> tuple[dict[int, object], ...]:
    if type(value) is not list or len(value) > 64:
        _fail("signature references are malformed")
    for item in value:
        checked = _closed_map(item, {1, 2, 3, 4, 5}, "signature reference")
        _uint(checked[1], 1, 14, "authority")
        _uint(checked[2], 1, 14, "purpose")
        _bytes(checked[3], 1, 64, "kid")
        _bytes(checked[4], 32, 32, "COSE digest")
        _bytes(checked[5], 32, 32, "payload digest")
    return tuple(value)


@dataclass(frozen=True, slots=True, init=False)
class SemanticRecoveryEvidence:
    record_digest: bytes
    recovery_kids: frozenset[bytes]
    registry_kids: frozenset[bytes]
    witness_kids: frozenset[bytes]

    @classmethod
    def _from_authenticated_validator(
        cls,
        record_digest: bytes,
        recovery: tuple[FederationAuthority, ...],
        registry: tuple[FederationAuthority, ...],
        witnesses: tuple[FederationAuthority, ...],
        *,
        token: object,
    ) -> SemanticRecoveryEvidence:
        if token is not _AUTHENTICATED_RECOVERY_TOKEN:
            _fail("semantic recovery evidence must come from the authenticated validator")
        groups = ((recovery, KeyPurpose.RECOVERY, 2), (registry, KeyPurpose.REGISTRY_SIGNING, 1), (witnesses, KeyPurpose.WITNESS, 2))
        for authorities, purpose, minimum in groups:
            if (
                len(authorities) < minimum
                or len({item.kid for item in authorities}) != len(authorities)
                or any(item.purpose is not purpose or item.lifecycle is not KeyLifecycle.ACTIVE or item.revoked for item in authorities)
            ):
                _fail("recovery semantic evidence lacks distinct authenticated active authorities")
        all_kids = [item.kid for authorities, _, _ in groups for item in authorities]
        if len(set(all_kids)) != len(all_kids):
            _fail("one signer cannot satisfy multiple recovery threshold sets")
        result = object.__new__(cls)
        values = (
            record_digest,
            frozenset(item.kid for item in recovery),
            frozenset(item.kid for item in registry),
            frozenset(item.kid for item in witnesses),
        )
        for name, value in zip(cls.__dataclass_fields__, values, strict=True):
            object.__setattr__(result, name, value)
        return result


@dataclass(frozen=True, slots=True)
class OperatorLifecycleRecord(_Record):
    REQUIRED = set(range(1, 8)) | {32, 33, 35, 36, 38}
    ALLOWED = REQUIRED | {8, 31, 34, 37}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> OperatorLifecycleRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.OperatorLifecycleRecord, cls.REQUIRED, cls.ALLOWED)
        _bytes(payload[32], 32, 32, "operator")
        _uint(payload[33], 1, 11, "lifecycle")
        DelegationScope.from_mapping(payload[35])
        _uint(payload[36], 0, 31, "reason")
        if 37 in payload and (type(payload[37]) is not list or any(type(x) is not bytes or len(x) != 32 for x in payload[37])):
            _fail("reentry evidence is invalid")
        _transparency(payload[38])
        if payload[33] == OperatorLifecycle.RECOVERY:
            if 34 not in payload:
                _fail("recovery stage required")
            _uint(payload[34], 1, 3, "recovery stage")
            if payload[34] in {2, 3} and not payload.get(37):
                _fail("verified recovery requires reentry evidence")
        elif 37 in payload and payload[37]:
            _fail("reentry evidence is forbidden outside staged recovery")
        elif 34 in payload:
            _fail("recovery stage forbidden")
        return cls(MappingProxyType(payload))

    @property
    def recovery_stage(self) -> RecoveryStage | None:
        return RecoveryStage(self._payload[34]) if 34 in self._payload else None

    def require_newer_than(self, current: OperatorLifecycleRecord) -> bool:
        self._require_lineage(current)
        if self._payload[33] not in _OPERATOR_TRANSITIONS[current._payload[33]]:
            _fail("operator lifecycle transition is forbidden")
        return True


@dataclass(frozen=True, slots=True)
class RecoveryTransitionRecord(_Record):
    REQUIRED = {1, 2, 3, 9, *range(32, 46)}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> RecoveryTransitionRecord:
        p = cls._decode(raw)
        _base(p, ObjectType.RecoveryTransitionRecord, cls.REQUIRED, cls.ALLOWED)
        _authority_reference(p[3], "issuer")
        _uint(p[9], 0, 253_402_300_799, "effective")
        _bytes(p[32], 1, 64, "transition")
        _bytes(p[33], 32, 32, "operator")
        affected = _targets(p[34], "affected", 1)
        _uint(p[35], 1, (1 << 64) - 1, "old generation")
        _uint(p[36], p[35] + 1, (1 << 64) - 1, "new generation")
        revoked = _targets(p[37], "revoked", 1)
        replacements = _targets(p[38], "replacement", 1)
        if p[39] is not None:
            _bytes(p[39], 32, 32, "continuity")
        if type(p[40]) is not bool or (p[39] is None) != p[40]:
            _fail("continuity or explicit break must be selected exactly")
        scope = DelegationScope.from_mapping(p[41])
        _signatures(p[42])
        _transparency(p[43])
        _uint(p[44], 1, 3, "recovery stage")
        restrictions = DelegationScope.from_mapping(p[45])
        if not _scope_narrow_or_equal(restrictions.to_mapping(), scope.to_mapping()):
            _fail("recovery activation scope expansion")
        if {repr(x) for x in revoked} != {repr(x) for x in affected} or any(x[2] in {y[2] for y in revoked} for x in replacements):
            _fail("recovery lineage replacements are invalid")
        return cls(MappingProxyType(p))

    @property
    def continuity_preserving(self) -> bool:
        return not self._payload[40]

    @property
    def lineage_breaking(self) -> bool:
        return self._payload[40]

    def validate_semantic_thresholds(self, evidence: SemanticRecoveryEvidence, *, compromised_kids: set[bytes]) -> None:
        kids = {x[3] for x in self._payload[42]}
        if (
            not isinstance(evidence, SemanticRecoveryEvidence)
            or evidence.record_digest != self.digest
            or len(evidence.recovery_kids) < 2
            or len(evidence.registry_kids) < 1
            or len(evidence.witness_kids) < 2
            or (kids | evidence.recovery_kids | evidence.registry_kids | evidence.witness_kids) & compromised_kids
        ):
            _fail("recovery semantic threshold evidence is invalid")

    @classmethod
    def from_threshold_transport(cls, raw: bytes) -> RecoveryTransitionRecord:
        _fail("recovery threshold transport packaging is unfrozen")


@dataclass(frozen=True, slots=True)
class ConflictEvidence(_Record):
    REQUIRED = {1, 2, *range(32, 44)}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> ConflictEvidence:
        p = cls._decode(raw)
        _base(p, ObjectType.ConflictEvidence, cls.REQUIRED, cls.ALLOWED)
        _bytes(p[32], 1, 64, "conflict")
        _bytes(p[33], 1, 64, "evidence")
        _uint(p[34], 1, 5, "class")
        DelegationScope.from_mapping(p[35])
        _uint(p[36], 1, 18, "object class")
        for key in (37, 39, 40):
            if type(p[key]) is not list or not 2 <= len(p[key]) <= 256 or any(type(x) is not bytes or len(x) != 32 for x in p[key]):
                _fail("conflict branches are malformed")
        if (
            type(p[38]) is not list
            or len(p[38]) != len(p[37])
            or len(p[39]) != len(p[37])
            or len(p[40]) != len(p[37])
            or any(
                type(version) is not list or len(version) != 2 or any(type(item) is not int or item < 1 for item in version)
                for version in p[38]
            )
        ):
            _fail("claimed versions are malformed")
        _uint(p[41], 0, 253_402_300_799, "observed")
        if p[42] is not True:
            _fail("conflict must recommend quarantine")
        _uint(p[43], 1, 3, "privacy")
        return cls(MappingProxyType(p))

    @property
    def branches(self) -> tuple[bytes, ...]:
        return tuple(self._payload[37])

    @property
    def quarantine(self) -> bool:
        return self._payload[42]

    def choose_winner(self, rule: str) -> None:
        _fail("conflict evidence is immutable and timestamps never choose a winner")


@dataclass(frozen=True, slots=True)
class ConflictResolutionRecord(_Record):
    REQUIRED = {1, 2, 3, 9, *range(32, 47)}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> ConflictResolutionRecord:
        p = cls._decode(raw)
        _base(p, ObjectType.ConflictResolutionRecord, cls.REQUIRED, cls.ALLOWED)
        _authority_reference(p[3], "issuer")
        _bytes(p[32], 1, 64, "decision")
        _bytes(p[33], 1, 64, "conflict")
        _bytes(p[34], 32, 32, "evidence set")
        DelegationScope.from_mapping(p[35])
        _uint(p[36], 1, 5, "outcome")
        _targets(p[37], "invalidated")
        _targets(p[38], "preserved")
        _uint(p[39], 1, (1 << 64) - 1, "affected generation")
        _uint(p[40], 1, (1 << 64) - 1, "affected sequence")
        if type(p[41]) is not list or len(p[41]) > 256 or any(type(item) is not bytes or len(item) != 32 for item in p[41]):
            _fail("revocation digests are malformed")
        if p[42] is not None:
            _bytes(p[42], 32, 32, "recovery requirement digest")
        _uint(p[43], p[9], 253_402_300_799, "appeal deadline")
        _signatures(p[44])
        if p[45] is not None:
            _bytes(p[45], 32, 32, "previous decision")
        _transparency(p[46])
        return cls(MappingProxyType(p))

    def preserves_losing_evidence(self, evidence: ConflictEvidence) -> bool:
        return self._payload[33] == evidence._payload[32] and bool(evidence.branches)


@dataclass(frozen=True, slots=True)
class AppealDecisionRecord(_Record):
    REQUIRED = {1, 2, 3, 9, *range(32, 47)}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> AppealDecisionRecord:
        p = cls._decode(raw)
        _base(p, ObjectType.AppealDecisionRecord, cls.REQUIRED, cls.ALLOWED)
        _authority_reference(p[3], "issuer")
        for key in (32, 33):
            _bytes(p[key], 1, 64, "decision")
        for key in (34, 35):
            _bytes(p[key], 32, 32, "digest")
        _uint(p[36], 1, 4, "appellant standing")
        DelegationScope.from_mapping(p[37])
        _uint(p[38], 1, 5, "appeal grounds")
        _uint(p[39], 1, 5, "appeal outcome")
        if type(p[40]) is not list or len(p[40]) > 256:
            _fail("lifecycle transitions are malformed")
        for transition in p[40]:
            item = _closed_map(transition, {1, 2, 3, 4}, "lifecycle transition")
            _authority_target(item[1], "lifecycle target")
            _uint(item[2], 1, 11, "from state")
            _uint(item[3], 1, 11, "to state")
            if (item[3] == OperatorLifecycle.RECOVERY) != (item[4] is not None):
                _fail("recovery stage must exactly match RECOVERY transition")
            if item[4] is not None:
                _uint(item[4], 1, 3, "recovery stage")
        _targets(p[41], "invalidated")
        _targets(p[42], "preserved")
        _targets(p[43], "followup")
        _signatures(p[44])
        if p[45] is not None:
            _bytes(p[45], 32, 32, "previous decision")
        _transparency(p[46])
        return cls(MappingProxyType(p))

    @property
    def restores_authority(self) -> bool:
        return False

    @property
    def resurrects_terminal_authority(self) -> bool:
        return False

    @property
    def previous_decision_digest(self) -> bytes | None:
        return self._payload[45]
