from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from nbsr.federation.delegation import DelegationScope
from nbsr.federation.fields import _Record, _authority_reference, _authority_target, _bytes, _closed_map, _common, _fail, _uint
from nbsr.federation.registry import AuthorityClass, EnforcementMode, ObjectType, ReasonCode


_AUTHENTICATED_THRESHOLD_TOKEN = object()


def _transparency(value: object) -> None:
    item = _closed_map(value, {1, 2, 3, 4}, "transparency reference")
    _bytes(item[1], 32, 32, "log ID")
    _bytes(item[2], 32, 32, "checkpoint digest")
    _uint(item[3], 0, (1 << 64) - 1, "tree size")
    if item[4] is not None:
        _bytes(item[4], 32, 32, "inclusion proof digest")


@dataclass(frozen=True, slots=True, init=False)
class SemanticThresholdEvidence:
    record_digest: bytes
    mode: int
    numerator: int
    denominator: int
    authenticated: bool
    operator_id: bytes | None = None
    authority_id: bytes | None = None

    @classmethod
    def _from_authenticated_validator(
        cls,
        record_digest: bytes,
        mode: int,
        numerator: int,
        denominator: int,
        *,
        operator_id: bytes | None = None,
        authority_id: bytes | None = None,
        token: object,
    ) -> SemanticThresholdEvidence:
        if token is not _AUTHENTICATED_THRESHOLD_TOKEN:
            _fail("semantic revocation evidence must come from the authenticated validator")
        _bytes(record_digest, 32, 32, "authenticated record digest")
        result = object.__new__(cls)
        values = (record_digest, mode, numerator, denominator, True, operator_id, authority_id)
        for name, value in zip(cls.__dataclass_fields__, values, strict=True):
            object.__setattr__(result, name, value)
        return result

    @classmethod
    def from_transport(cls, raw: bytes) -> SemanticThresholdEvidence:
        _fail("threshold transport packaging is unfrozen")


@dataclass(frozen=True, slots=True)
class TypedRevocationRecord(_Record):
    REQUIRED = set(range(1, 8)) | set(range(32, 38)) | {39}
    ALLOWED = REQUIRED | {8, 31, 38}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> TypedRevocationRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.TypedRevocationRecord, cls.REQUIRED, cls.ALLOWED)
        _authority_reference(payload[3], "issuer")
        _authority_target(payload[32], "target")
        DelegationScope.from_mapping(payload[33])
        _uint(payload[34], min(item.value for item in ReasonCode), max(item.value for item in ReasonCode), "reason")
        if type(payload[35]) is not bool:
            _fail("terminal flag must be boolean")
        _uint(payload[36], 0, 4, "enforcement mode")
        _uint(payload[37], 1, 3, "revocation authority mode")
        if payload.get(38) is not None:
            _authority_target(payload[38], "replacement reference")
        _transparency(payload[39])
        if payload[35] and payload[7] != 253_402_300_799:
            _fail("terminal revocation may not expire")
        if payload[37] == 3 and (payload[35] or payload[36] != EnforcementMode.DENY_NEW_USE or payload[7] - payload[6] > 300):
            _fail("emergency mode is nonterminal deny-only for at most 300 seconds")
        return cls(MappingProxyType(payload))

    @property
    def target(self) -> tuple[int, bytes, bytes | None]:
        return (self._payload[32][1], self._payload[32][2], self._payload[32][3])

    @property
    def terminal(self) -> bool:
        return self._payload[35]

    def authorize(self, evidence: SemanticThresholdEvidence) -> None:
        issuer = self._payload[3]
        if (
            not isinstance(evidence, SemanticThresholdEvidence)
            or evidence.record_digest != self.digest
            or not evidence.authenticated
            or evidence.mode != self._payload[37]
        ):
            _fail("revocation authority mode mismatch")
        if evidence.mode == 1 and (
            issuer[1] != AuthorityClass.TARGET_CONTROLLER or issuer[2] != evidence.authority_id or issuer[4] != evidence.operator_id
        ):
            _fail("target-controller authority is invalid")
        if evidence.mode == 2 and (evidence.numerator, evidence.denominator) != (3, 5):
            _fail("normal threshold is invalid")
        if evidence.mode == 3 and (evidence.numerator, evidence.denominator) != (2, 5):
            _fail("emergency threshold is invalid")

    def replace_with(self, candidate: TypedRevocationRecord) -> None:
        if self.terminal:
            _fail("terminal tombstone cannot resurrect")
        self._require_lineage(candidate) if False else candidate._require_lineage(self)


class DependencyIndex:
    def __init__(self) -> None:
        self._dependencies: dict[bytes, frozenset[bytes]] = {}

    def add(self, item: bytes, dependencies: set[bytes]) -> None:
        self._dependencies[item] = frozenset(dependencies)

    def invalidate(self, revoked: set[bytes]) -> frozenset[bytes]:
        affected = set(revoked)
        while True:
            added = {item for item, dependencies in self._dependencies.items() if dependencies & affected}
            if added <= affected:
                return frozenset(affected)
            affected |= added

    def authority_reduction(self, revoked: set[bytes]) -> frozenset[bytes]:
        return self.invalidate(revoked)

    def enforcement(self, revoked: set[bytes], *, emergency: bool) -> EnforcementMode:
        return EnforcementMode.TERMINATE_ACTIVE_USE if emergency else EnforcementMode.DENY_NEW_USE
