from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from nbsr.federation.fields import (
    RecoveryTransitionBinding,
    _Record,
    _authority_reference,
    _authority_target,
    _bytes,
    _common,
    _delegation_scope,
    _fail,
)
from nbsr.federation.ownership import NameOwnershipRecord
from nbsr.federation.profile import FederationProfile
from nbsr.federation.registry import AuthorityClass, ObjectType
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


@dataclass(frozen=True, slots=True)
class DelegationScope:
    _scope: Mapping[int, object]

    @classmethod
    def from_mapping(cls, value: Mapping[int, object]) -> DelegationScope:
        if type(value) is not dict:
            _fail("delegation scope must be a map")
        checked = _delegation_scope(dict(value))
        return cls(MappingProxyType(checked))

    @classmethod
    def from_bytes(cls, raw: bytes) -> DelegationScope:
        if type(raw) is not bytes or len(raw) > 2048:
            _fail("delegation scope exceeds its composite bound")
        try:
            decoded = decode_deterministic(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("delegation scope is not deterministic CBOR") from exc
        return cls.from_mapping(decoded)

    def to_mapping(self) -> dict[int, object]:
        return {
            key: ([list(pair) for pair in value] if key == 7 else list(value) if key in {8, 9} else value)
            for key, value in self._scope.items()
        }

    def canonical_bytes(self) -> bytes:
        return encode_deterministic(self.to_mapping())

    def intersect(self, child: DelegationScope) -> DelegationScope:
        if not isinstance(child, DelegationScope):
            _fail("child delegation scope is invalid")
        parent = self._scope
        candidate = child._scope
        if any(candidate[key] != parent[key] for key in range(1, 7)):
            _fail("child scope changes an exact constrained dimension")
        for start, end in candidate[7]:
            if not any(old_start <= start <= end <= old_end for old_start, old_end in parent[7]):
                _fail("child port scope widens parent scope")
        if not set(candidate[8]) <= set(parent[8]) or not set(candidate[9]) <= set(parent[9]):
            _fail("child protocol or action scope widens parent scope")
        if not parent[10] and candidate[10]:
            _fail("child cannot restore subdelegation authority")
        if candidate[11] > parent[11]:
            _fail("child remaining depth widens parent scope")
        return child

    def is_strict_narrowing_of(self, parent: DelegationScope) -> bool:
        parent.intersect(self)
        return self != parent


@dataclass(frozen=True, slots=True)
class DelegationRecord(_Record):
    REQUIRED = {1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 36, 37}
    ALLOWED = REQUIRED | {8, 31, 35}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> DelegationRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.DelegationRecord, cls.REQUIRED, cls.ALLOWED)
        issuer = _authority_reference(payload[3], "issuer_id")
        delegator = _authority_reference(payload[32], "delegator")
        delegatee = _authority_reference(payload[33], "delegatee")
        if delegator[1] not in {AuthorityClass.NAME_OWNER, AuthorityClass.DELEGATE} or issuer != delegator:
            _fail("delegator must be the exact NAME_OWNER or DELEGATE issuer")
        if delegatee[1] != AuthorityClass.DELEGATE:
            _fail("delegatee authority class must be DELEGATE")
        if delegator[4] is None or delegator[2] != delegator[4] or delegatee[4] is None or delegatee[2] != delegatee[4]:
            _fail("delegation actors must bind exact Operator IDs")
        _delegation_scope(payload[34])
        if 35 in payload:
            _bytes(payload[35], 32, 32, "parent_digest")
        if payload[4] == 1 and payload[5] == 1:
            if delegator[1] == AuthorityClass.NAME_OWNER and 35 in payload:
                _fail("direct delegation genesis forbids parent_digest")
            if delegator[1] == AuthorityClass.DELEGATE and 35 not in payload:
                _fail("child delegation genesis requires parent_digest")
        if payload[36] is not None:
            _bytes(payload[36], 32, 32, "policy_reference")
        if payload[37] is not None:
            _authority_target(payload[37], "revocation_reference")
        return cls(MappingProxyType(payload))

    @property
    def operator_id(self) -> bytes:
        return self._payload[32][4]

    @property
    def delegator_id(self) -> bytes:
        return self._payload[32][4]

    @property
    def delegatee_id(self) -> bytes:
        return self._payload[33][4]

    @property
    def scope(self) -> DelegationScope:
        return DelegationScope.from_mapping(dict(self._payload[34]))

    @property
    def parent_digest(self) -> bytes | None:
        return self._payload.get(35)

    @property
    def revoked(self) -> bool:
        return self._payload[37] is not None

    def require_parent(self, parent: DelegationRecord) -> None:
        if self.parent_digest != parent.digest or self.delegator_id != parent.delegatee_id:
            _fail("delegation parent ancestry is invalid")
        if not parent.scope._scope[10]:
            _fail("parent forbids subdelegation")
        if self.expires_at > parent.expires_at or self.not_before < parent.not_before:
            _fail("child validity is not bounded by parent")
        parent.scope.intersect(self.scope)
        if self.scope._scope[11] >= parent.scope._scope[11]:
            _fail("child remaining depth must decrease")

    def require_newer_than(self, current: DelegationRecord, *, recovery_transition: RecoveryTransitionBinding | None = None) -> bool:
        candidate = (self.generation, self.sequence)
        accepted = (current.generation, current.sequence)
        if candidate < accepted:
            _fail("delegation update is a rollback")
        if candidate == accepted:
            if self.digest == current.digest:
                return False
            _fail("equal-version delegation record equivocates")
        if current.revoked:
            _fail("terminal delegation state cannot be resurrected")
        if (
            self.delegator_id != current.delegator_id
            or self.delegatee_id != current.delegatee_id
            or self.parent_digest != current.parent_digest
        ):
            _fail("delegation identity or parent changed")
        current.scope.intersect(self.scope)
        if self.generation == current.generation:
            if self.sequence != current.sequence + 1 or self._payload.get(8) != current.digest:
                _fail("ordinary delegation continuity is invalid")
        elif self.generation == current.generation + 1 and self.sequence == 1 and self._payload.get(8) == current.digest:
            if (
                not isinstance(recovery_transition, RecoveryTransitionBinding)
                or type(recovery_transition.digest) is not bytes
                or len(recovery_transition.digest) != 32
                or not recovery_transition.accepted
                or recovery_transition.object_type != ObjectType.DelegationRecord
                or recovery_transition.operator_id != self.delegator_id
                or recovery_transition.key_purpose != 6
                or recovery_transition.old_generation != current.generation
                or recovery_transition.new_generation != self.generation
                or recovery_transition.scope != self.scope.to_mapping()
            ):
                _fail("delegation recovery transition binding is invalid")
        else:
            _fail("delegation recovery continuity is invalid")
        return True


@dataclass(frozen=True, slots=True)
class SignedFederationObject:
    message: bytes
    authority: object
    expected_payload: bytes
    current_record: NameOwnershipRecord | DelegationRecord | None = None
    transition: object | None = None


class DelegationVerifier:
    @staticmethod
    def verify_semantics(
        chain: Sequence[NameOwnershipRecord | DelegationRecord],
        request: DelegationScope,
        now: int,
    ) -> DelegationRecord:
        """Validate already-parsed graph semantics without granting authority."""
        if not 2 <= len(chain) <= FederationProfile.max_graph_nodes:
            _fail("delegation graph node count exceeds the bound")
        roots = [item for item in chain if isinstance(item, NameOwnershipRecord)]
        if len(roots) != 1:
            _fail("delegation chain lacks an ownership root")
        root = roots[0]
        leaf = chain[-1]
        if not isinstance(leaf, DelegationRecord):
            _fail("delegation graph leaf has the wrong object class")
        by_digest: dict[bytes, NameOwnershipRecord | DelegationRecord] = {}
        for item in chain:
            if not isinstance(item, (NameOwnershipRecord, DelegationRecord)):
                _fail("delegation graph contains a wrong object class")
            if item.digest in by_digest:
                _fail("delegation graph repeats a digest")
            by_digest[item.digest] = item

        reverse_path: list[DelegationRecord] = []
        traversal_seen: set[bytes] = set()
        cursor = leaf
        while True:
            if cursor.digest in traversal_seen:
                _fail("delegation graph contains a loop")
            traversal_seen.add(cursor.digest)
            reverse_path.append(cursor)
            if len(reverse_path) > FederationProfile.max_graph_depth:
                _fail("delegation traversal depth exceeds the bound")
            if cursor.parent_digest is None:
                break
            parent = by_digest.get(cursor.parent_digest)
            if not isinstance(parent, DelegationRecord):
                _fail("delegation graph has broken ancestry")
            cursor.require_parent(parent)
            cursor = parent

        path = list(reversed(reverse_path))
        if len(path) > FederationProfile.max_delegation_depth or len(path) + 1 > FederationProfile.max_chain_objects:
            _fail("delegation depth exceeds the bound")
        root.require_valid_at(now)
        if root.revoked:
            _fail("ownership root is revoked")
        seen_digests = {root.digest}
        seen_actors = {root.owner_operator_id}
        parent: DelegationRecord | None = None
        for item in path:
            if item.digest in seen_digests:
                _fail("delegation chain repeats a digest")
            if item.delegatee_id in seen_actors:
                _fail("delegation chain repeats an actor")
            item.require_valid_at(now)
            if item.revoked:
                _fail("delegation ancestor is revoked")
            if item.scope._scope[1] != root.name_scope or item.scope._scope[2] != root.service_id:
                _fail("delegation does not match the ownership scope")
            if parent is None:
                if item.parent_digest is not None or item.delegator_id != root.owner_operator_id:
                    _fail("direct delegation ancestry is invalid")
                if item.not_before < root.not_before or item.expires_at > root.expires_at:
                    _fail("direct delegation validity is not bounded by ownership")
            else:
                item.require_parent(parent)
            seen_digests.add(item.digest)
            seen_actors.add(item.delegatee_id)
            parent = item
        assert parent is not None
        parent.scope.intersect(request)
        return parent

    @staticmethod
    def verify(chain: Sequence[SignedFederationObject], request: DelegationScope, now: int) -> DelegationRecord:
        from nbsr.federation.cose import verify_federation_sign1
        from nbsr.federation.registry import KeyPurpose

        if any(not isinstance(item, SignedFederationObject) for item in chain):
            _fail("signed ownership/delegation objects are required for authority verification")
        verified: list[NameOwnershipRecord | DelegationRecord] = []
        for index, item in enumerate(chain):
            object_type = ObjectType.NameOwnershipRecord if index == 0 else ObjectType.DelegationRecord
            purpose = KeyPurpose.NAME_OWNERSHIP if index == 0 else KeyPurpose.DELEGATION
            record = verify_federation_sign1(
                item.message,
                item.authority,
                object_type,
                now,
                expected_payload=item.expected_payload,
                expected_key_purpose=purpose,
                current_record=item.current_record,
                transition=item.transition,
            )
            if not isinstance(record, (NameOwnershipRecord, DelegationRecord)):
                _fail("signed chain object has the wrong class")
            verified.append(record)
        return DelegationVerifier.verify_semantics(tuple(verified), request, now)
