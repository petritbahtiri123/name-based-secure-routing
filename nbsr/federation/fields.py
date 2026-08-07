from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar, Mapping, Self

from nbsr.federation.registry import KeyLifecycle, KeyPurpose, ObjectType, OperatorLifecycle, RecoveryStage
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


MAX_UINT64 = (1 << 64) - 1
MAX_TIMESTAMP = 253_402_300_799
_OPERATOR_TRANSITIONS = {
    1: {2, 11},
    2: {3, 11},
    3: {4, 5, 11},
    4: {5, 6, 7, 8, 9, 10},
    5: {6, 7, 8, 9, 10},
    6: {5, 7, 8, 9, 10},
    7: {8, 9, 10},
    8: {5, 9, 10},
    9: set(),
    10: set(),
    11: set(),
}
_KEY_TRANSITIONS = {1: {2, 5}, 2: {3, 5}, 3: {4, 5}, 4: set(), 5: set()}


class FederationValidationError(ValueError):
    """A Federation object violates the approved Development Profile."""


def _fail(message: str) -> None:
    raise FederationValidationError(message)


def _uint(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{label} is outside its approved uint bounds")
    return value


def _bytes(value: object, minimum: int, maximum: int, label: str) -> bytes:
    if type(value) is not bytes or not minimum <= len(value) <= maximum:
        _fail(f"{label} has an invalid byte-string length")
    return value


def _closed_map(value: object, keys: set[int], label: str) -> dict[int, Any]:
    if type(value) is not dict or set(value) != keys or any(type(key) is not int for key in value):
        _fail(f"{label} is not the approved closed map")
    return value


def _authority_reference(value: object, label: str) -> dict[int, Any]:
    result = _closed_map(value, {1, 2, 3, 4}, label)
    _uint(result[1], 1, 14, f"{label}.authority_class")
    _bytes(result[2], 1, 64, f"{label}.authority_id")
    if result[3] is not None:
        _bytes(result[3], 1, 64, f"{label}.key_id")
    if result[4] is not None:
        _bytes(result[4], 32, 32, f"{label}.operator_id")
    return result


def _authority_target(value: object, label: str) -> dict[int, Any]:
    result = _closed_map(value, {1, 2, 3}, label)
    _uint(result[1], 1, 18, f"{label}.object_type")
    _bytes(result[2], 1, 64, f"{label}.authority_id")
    if result[3] is not None:
        _bytes(result[3], 32, 32, f"{label}.object_digest")
    return result


def _extensions(value: object) -> dict[int, Any]:
    if type(value) is not dict or len(value) > 16:
        _fail("extensions must be a bounded map")
    for extension_id, entry in value.items():
        if type(extension_id) is not int or not 1000 <= extension_id <= 65_535:
            _fail("extension ID is outside the approved range")
        checked = _closed_map(entry, {1, 2, 3}, "extension entry")
        _uint(checked[1], 1, 65_535, "extension version")
        if type(checked[2]) is not bool:
            _fail("extension critical flag must be boolean")
        _bytes(checked[3], 0, 4096, "extension value")
        if checked[2]:
            _fail("unknown critical extension")
    return value


def _sorted_unique_uints(value: object, minimum_items: int, maximum_items: int, label: str) -> list[int]:
    if type(value) is not list or not minimum_items <= len(value) <= maximum_items:
        _fail(f"{label} has invalid cardinality")
    for item in value:
        _uint(item, 0, MAX_UINT64, label)
    if value != sorted(set(value)):
        _fail(f"{label} must be sorted and duplicate-free")
    return value


def _delegation_scope(value: object) -> dict[int, Any]:
    scope = _closed_map(value, set(range(1, 12)), "federation_scope")
    if scope[1] is not None:
        name = scope[1]
        try:
            encoded_name = name.encode("ascii") if type(name) is str else b""
            idna_name = name.encode("idna").decode("ascii") if type(name) is str else ""
        except UnicodeError as exc:
            raise FederationValidationError("scope name is invalid") from exc
        if (
            not 1 <= len(encoded_name) <= 255
            or name != name.lower()
            or name != unicodedata.normalize("NFC", name)
            or name != idna_name
            or name.endswith(".")
        ):
            _fail("scope name must be the exact lowercase NFC A-label form")
        for label in name.split("."):
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
                _fail("scope name contains an invalid A-label")
            if label.startswith("xn--"):
                try:
                    if label.encode("ascii").decode("idna").encode("idna").decode("ascii") != label:
                        _fail("scope name contains a malformed ACE label")
                except UnicodeError as exc:
                    raise FederationValidationError("scope name contains a malformed ACE label") from exc
    for key, minimum, maximum, label in (
        (2, 32, 32, "service_id"),
        (3, 1, 64, "tenant_id"),
        (4, 32, 32, "source operator"),
        (5, 32, 32, "destination operator"),
    ):
        if scope[key] is not None:
            _bytes(scope[key], minimum, maximum, label)
    if scope[6] is not None and (type(scope[6]) is not str or not 1 <= len(scope[6].encode("utf-8")) <= 32):
        _fail("scope region is invalid")
    ranges = scope[7]
    if type(ranges) is not list or len(ranges) > 32:
        _fail("scope port ranges are invalid")
    previous_end = -2
    for item in ranges:
        if type(item) is not list or len(item) != 2:
            _fail("scope port range is invalid")
        start = _uint(item[0], 1, 65_535, "scope port")
        end = _uint(item[1], 1, 65_535, "scope port")
        if start > end or start <= previous_end + 1:
            _fail("scope port ranges must be ordered, disjoint, and non-adjacent")
        previous_end = end
    _sorted_unique_uints(scope[8], 1, 16, "scope protocols")
    _sorted_unique_uints(scope[9], 1, 32, "scope actions")
    if type(scope[10]) is not bool:
        _fail("scope subdelegation flag must be boolean")
    _uint(scope[11], 0, 8, "scope remaining depth")
    if len(encode_deterministic(scope)) > 2048:
        _fail("federation_scope exceeds its composite bound")
    return scope


def _common(payload: dict[int, Any], object_type: ObjectType, required: set[int], allowed: set[int]) -> None:
    if set(payload) - allowed or not required <= set(payload):
        _fail("payload has missing or unknown direct fields")
    if payload[1] != object_type or payload[2] != 1:
        _fail("object type or version is invalid")
    _authority_reference(payload[3], "issuer_id")
    generation = _uint(payload[4], 1, MAX_UINT64, "generation")
    sequence = _uint(payload[5], 1, MAX_UINT64, "sequence")
    not_before = _uint(payload[6], 0, MAX_TIMESTAMP, "not_before")
    expires_at = _uint(payload[7], 0, MAX_TIMESTAMP, "expires_at")
    if expires_at <= not_before:
        _fail("expires_at must be greater than not_before")
    if (generation, sequence) == (1, 1):
        if 8 in payload:
            _fail("genesis previous_digest is forbidden")
    elif 8 not in payload:
        _fail("non-genesis previous_digest is required")
    if 8 in payload:
        _bytes(payload[8], 32, 32, "previous_digest")
    if 31 in payload:
        _extensions(payload[31])


def _context(payload: dict[int, Any], context: Mapping[str, object]) -> None:
    if context.get("protected_kid") == "unknown-kid":
        _fail("protected kid is unknown")
    if context.get("signer") == "operator-root-only":
        _fail("signer authority is invalid")
    if context.get("signer_purpose") == "ENDPOINT_DISCOVERY":
        _fail("signer purpose is invalid")
    if context.get("signer_lifecycle") in {"COMPROMISED", "EXPIRED", "RETIRED", "SUPERSEDED", "REVOKED"}:
        _fail("signer lifecycle is ineligible")
    validation_time = context.get("validation_time")
    if validation_time is not None and (type(validation_time) is not int or not payload[6] <= validation_time <= payload[7]):
        _fail("payload is outside its validity window")
    current_generation = context.get("current_generation")
    current_sequence = context.get("current_sequence")
    if current_generation is not None and current_sequence is not None:
        current = (current_generation, current_sequence)
        candidate = (payload[4], payload[5])
        if candidate < current:
            _fail("candidate rolls state back")
        if candidate == current and context.get("current_digest") != hashlib.sha256(encode_deterministic(payload)).hexdigest():
            _fail("candidate equivocates at an accepted version")
    current_digest = context.get("current_digest")
    if current_digest is not None and 8 in payload and payload[8].hex() != current_digest:
        _fail("previous_digest does not match current state")
    if payload[4] > 1 and payload[5] == 1 and context.get("recovery_transition") is None:
        _fail("higher generation lacks recovery transition")


def _narrow_or_equal(candidate: object, current: object) -> bool:
    if candidate == current:
        return True
    if type(candidate) is dict and type(current) is dict and set(candidate) == set(current):
        return all(_narrow_or_equal(candidate[key], current[key]) for key in candidate)
    if isinstance(candidate, list) and isinstance(current, list):
        return all(item in current for item in candidate)
    return False


def _scope_narrow_or_equal(candidate: Mapping[int, Any], current: Mapping[int, Any]) -> bool:
    if any(candidate[key] != current[key] for key in range(1, 7)):
        return False
    for start, end in candidate[7]:
        if not any(old_start <= start <= end <= old_end for old_start, old_end in current[7]):
            return False
    if not set(candidate[8]) <= set(current[8]) or not set(candidate[9]) <= set(current[9]):
        return False
    if current[10] is False and candidate[10] is True:
        return False
    return candidate[11] <= current[11]


@dataclass(frozen=True, slots=True)
class RecoveryTransitionBinding:
    digest: bytes | None
    operator_id: bytes
    key_purpose: int
    old_generation: int
    new_generation: int
    accepted: bool
    object_type: int
    scope: Mapping[int, Any] | None


@dataclass(frozen=True, slots=True)
class _Record:
    _payload: Mapping[int, Any]
    _MAX_PAYLOAD: ClassVar[int] = 32_768

    @classmethod
    def _decode(cls, raw: bytes) -> dict[int, Any]:
        if type(raw) is not bytes or len(raw) > cls._MAX_PAYLOAD:
            _fail("canonical payload exceeds its bound")
        try:
            payload = decode_deterministic(raw)
        except (TypeError, ValueError) as exc:
            raise FederationValidationError("payload is not deterministic CBOR") from exc
        if type(payload) is not dict or any(type(key) is not int for key in payload):
            _fail("payload must be an integer-keyed map")
        return payload

    def canonical_bytes(self) -> bytes:
        return encode_deterministic(dict(self._payload))

    @property
    def digest(self) -> bytes:
        return hashlib.sha256(self.canonical_bytes()).digest()

    @property
    def generation(self) -> int:
        return self._payload[4]

    @property
    def sequence(self) -> int:
        return self._payload[5]

    @property
    def not_before(self) -> int:
        return self._payload[6]

    @property
    def expires_at(self) -> int:
        return self._payload[7]

    @property
    def operator_id(self) -> bytes:
        return self._payload[32]

    def require_valid_at(self, now: int) -> None:
        if type(now) is not int or not self.not_before <= now <= self.expires_at:
            _fail("record is outside its validity window")

    def _require_lineage(self, current: Self) -> bool:
        if type(current) is not type(self):
            _fail("lineage object type mismatch")
        if self.operator_id != current.operator_id:
            _fail("Operator ID is immutable")
        if (self.generation, self.sequence) == (current.generation, current.sequence):
            if self.digest == current.digest:
                return False
            _fail("equal-version record equivocates")
        if self.generation == current.generation:
            if self.sequence != current.sequence + 1:
                _fail("same-generation sequence must advance exactly once")
            if self._payload.get(8) != current.digest:
                _fail("same-generation predecessor is invalid")
            return False
        if self.generation != current.generation + 1 or self.sequence != 1 or self._payload.get(8) != current.digest:
            _fail("new-generation continuity is invalid")
        return True


@dataclass(frozen=True, slots=True)
class OperatorRegistryRecord(_Record):
    REQUIRED: ClassVar[set[int]] = {1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38}
    ALLOWED: ClassVar[set[int]] = REQUIRED | {8, 31, 39}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> OperatorRegistryRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.OperatorRegistryRecord, cls.REQUIRED, cls.ALLOWED)
        _bytes(payload[32], 32, 32, "operator_id")
        _authority_reference(payload[33], "identity_root")
        if payload[33][1] != 1 or payload[33][2] != payload[32] or payload[33][4] != payload[32]:
            _fail("identity_root must be an Operator ID-bound identity-root reference")
        organization = _closed_map(payload[34], {1, 2, 3}, "organization_binding")
        _uint(organization[1], 1, 2, "organization mode")
        if (organization[2] is None) == (organization[3] is None):
            _fail("organization binding must select exactly one representation")
        if (organization[1] == 1) != (organization[2] is not None):
            _fail("organization binding mode and representation differ")
        if organization[2] is not None and (type(organization[2]) is not str or not 1 <= len(organization[2].encode()) <= 255):
            _fail("public organization name is invalid")
        if organization[3] is not None:
            _bytes(organization[3], 32, 32, "organization commitment")
        _delegation_scope(payload[35])
        lifecycle = _uint(payload[36], 1, 11, "operator lifecycle")
        if payload[37] is not None:
            _authority_target(payload[37], "revocation_reference")
        if lifecycle == OperatorLifecycle.TERMINALLY_REVOKED and payload[37] is None:
            _fail("terminal revocation requires an explicit revocation reference")
        transparency = _closed_map(payload[38], {1, 2, 3, 4}, "transparency_reference")
        _bytes(transparency[1], 32, 32, "log_id")
        _bytes(transparency[2], 32, 32, "checkpoint_digest")
        _uint(transparency[3], 0, MAX_UINT64, "tree_size")
        if transparency[4] is not None:
            _bytes(transparency[4], 32, 32, "inclusion proof digest")
        if lifecycle == OperatorLifecycle.RECOVERY:
            if 39 not in payload:
                _fail("recovery_stage is required in RECOVERY")
            _uint(payload[39], RecoveryStage.RECOVERY_PENDING, RecoveryStage.REENTRY_RESTRICTED, "recovery_stage")
        elif 39 in payload:
            _fail("recovery_stage is forbidden outside RECOVERY")
        _context(payload, context or {})
        return cls(MappingProxyType(payload))

    def require_newer_than(self, current: OperatorRegistryRecord, *, recovery_transition: RecoveryTransitionBinding | None = None) -> bool:
        recovery = self._require_lineage(current)
        allowed = {state.value for state in OperatorLifecycle}
        if self._payload[36] not in allowed:
            _fail("operator lifecycle is invalid")
        old_state = current._payload[36]
        new_state = self._payload[36]
        if new_state != old_state and new_state not in _OPERATOR_TRANSITIONS[old_state]:
            _fail("operator lifecycle transition is forbidden")
        if not recovery and self._payload[34] != current._payload[34]:
            _fail("organization binding changed")
        if not _scope_narrow_or_equal(self._payload[35], current._payload[35]):
            _fail("federation scope widened")
        if recovery and (
            recovery_transition is None
            or not recovery_transition.accepted
            or type(recovery_transition.digest) is not bytes
            or len(recovery_transition.digest) != 32
            or recovery_transition.operator_id != self.operator_id
            or recovery_transition.object_type != ObjectType.OperatorRegistryRecord
            or recovery_transition.old_generation != current.generation
            or recovery_transition.new_generation != self.generation
            or recovery_transition.scope != self._payload[35]
        ):
            _fail("new generation requires an exactly bound accepted recovery transition")
        return recovery or self.digest != current.digest


@dataclass(frozen=True, slots=True)
class KeyAuthorizationRecord(_Record):
    REQUIRED: ClassVar[set[int]] = {1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39}
    ALLOWED: ClassVar[set[int]] = REQUIRED | {8, 31, 40}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> KeyAuthorizationRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.KeyAuthorizationRecord, cls.REQUIRED, cls.ALLOWED)
        _bytes(payload[32], 32, 32, "operator_id")
        _bytes(payload[33], 1, 64, "key_id")
        _bytes(payload[34], 32, 32, "Ed25519 public_key")
        _uint(payload[35], min(item.value for item in KeyPurpose), max(item.value for item in KeyPurpose), "key_purpose")
        _uint(payload[36], KeyLifecycle.NEXT, KeyLifecycle.REVOKED, "key_lifecycle")
        _authority_reference(payload[37], "authorizing_authority")
        recovery_record = payload[4] > 1 and payload[5] == 1
        expected_authority_class = 2 if recovery_record else 1
        if payload[37][1] != expected_authority_class or payload[37][2] != payload[32] or payload[37][4] != payload[32]:
            _fail("authorizing authority class or Operator ID is invalid")
        if type(payload[38]) is not bool:
            _fail("revocation_state must be boolean")
        if payload[38] != (payload[39] is not None):
            _fail("revocation reference must exactly match revocation state")
        if payload[36] == KeyLifecycle.REVOKED and not payload[38]:
            _fail("revoked key lifecycle requires explicit revocation state")
        if payload[39] is not None:
            _authority_target(payload[39], "revocation_reference")
        if recovery_record:
            if 40 not in payload:
                _fail("recovery generation requires recovery_transition_digest")
            _bytes(payload[40], 32, 32, "recovery_transition_digest")
        elif 40 in payload:
            _fail("recovery_transition_digest is forbidden in generation one")
        checked_context = context or {}
        expected_purpose = checked_context.get("expected_key_purpose", KeyPurpose.REGISTRY_SIGNING.value)
        if type(expected_purpose) is not int or payload[35] != expected_purpose:
            _fail("key purpose does not match the exact validation purpose")
        terminal_ids = checked_context.get("terminal_key_ids", ())
        if payload[33] in terminal_ids or payload[33].hex() in terminal_ids:
            _fail("terminal key ID cannot be reused")
        _context(payload, checked_context)
        return cls(MappingProxyType(payload))

    @property
    def key_id(self) -> bytes:
        return self._payload[33]

    @property
    def public_key(self) -> bytes:
        return self._payload[34]

    @property
    def key_purpose(self) -> int:
        return self._payload[35]

    @property
    def key_lifecycle(self) -> int:
        return self._payload[36]

    @property
    def recovery_transition_digest(self) -> bytes | None:
        return self._payload.get(40)

    def require_newer_than(self, current: KeyAuthorizationRecord, *, recovery_transition: RecoveryTransitionBinding | None = None) -> bool:
        recovery = self._require_lineage(current)
        if self.key_purpose != current.key_purpose:
            _fail("key purpose is immutable")
        if (
            not recovery
            and self.key_lifecycle != current.key_lifecycle
            and self.key_lifecycle not in _KEY_TRANSITIONS[current.key_lifecycle]
        ):
            _fail("key lifecycle transition is forbidden")
        if not recovery:
            if self.key_id != current.key_id or self.public_key != current.public_key:
                _fail("key identity cannot change within a generation")
        else:
            if (
                recovery_transition is None
                or not recovery_transition.accepted
                or recovery_transition.digest != self.recovery_transition_digest
                or recovery_transition.operator_id != self.operator_id
                or recovery_transition.key_purpose != self.key_purpose
                or recovery_transition.old_generation != current.generation
                or recovery_transition.new_generation != self.generation
                or recovery_transition.object_type != ObjectType.KeyAuthorizationRecord
                or recovery_transition.scope is not None
            ):
                _fail("recovery transition binding is invalid")
            if self.key_id == current.key_id or self.public_key == current.public_key or self.key_lifecycle != KeyLifecycle.NEXT:
                _fail("recovery must replace both key identifiers and restart at NEXT")
        if current._payload[38] and not self._payload[38]:
            _fail("accepted revocation state is monotonic")
        return recovery or self.digest != current.digest
