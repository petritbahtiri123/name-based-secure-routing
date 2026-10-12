from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from nbsr.federation.delegation import DelegationScope
from nbsr.federation.fields import _Record, _authority_reference, _bytes, _extensions, _fail, _uint
from nbsr.federation.registry import AuthorityClass, ObjectType


MAX_PROOF_PATH = 64
EMPTY_TREE_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(canonical_leaf: bytes) -> bytes:
    if type(canonical_leaf) is not bytes:
        raise ValueError("canonical leaf must be bytes")
    return hashlib.sha256(b"\x00" + canonical_leaf).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    if type(left) is not bytes or len(left) != 32 or type(right) is not bytes or len(right) != 32:
        raise ValueError("Merkle node children must be 32-byte digests")
    return hashlib.sha256(b"\x01" + left + right).digest()


def _largest_power_of_two_less_than(value: int) -> int:
    return 1 << ((value - 1).bit_length() - 1)


def _root_from_hashes(hashes: Sequence[bytes]) -> bytes:
    count = len(hashes)
    if count == 0:
        return EMPTY_TREE_ROOT
    if count == 1:
        return hashes[0]
    split = _largest_power_of_two_less_than(count)
    return node_hash(_root_from_hashes(hashes[:split]), _root_from_hashes(hashes[split:]))


def merkle_root(canonical_leaves: Sequence[bytes]) -> bytes:
    if len(canonical_leaves) > 65_536:
        raise ValueError("Merkle leaf count exceeds the resource limit")
    return _root_from_hashes([leaf_hash(item) for item in canonical_leaves])


def _proof_path(path: Sequence[bytes]) -> tuple[bytes, ...]:
    if not isinstance(path, (list, tuple)) or len(path) > MAX_PROOF_PATH:
        raise ValueError("proof path is malformed or excessive")
    if any(type(item) is not bytes or len(item) != 32 for item in path):
        raise ValueError("proof path contains a malformed digest")
    return tuple(path)


def verify_inclusion(
    leaf_digest: bytes,
    leaf_index: int,
    tree_size: int,
    proof_path: Sequence[bytes],
    expected_root: bytes,
) -> bool:
    path = _proof_path(proof_path)
    if type(leaf_digest) is not bytes or len(leaf_digest) != 32 or type(expected_root) is not bytes or len(expected_root) != 32:
        raise ValueError("inclusion proof digest is malformed")
    if type(leaf_index) is not int or type(tree_size) is not int or tree_size < 1 or not 0 <= leaf_index < tree_size:
        return False
    digest = leaf_digest
    index = leaf_index
    last = tree_size - 1
    used = 0
    while last:
        if used >= len(path):
            return False
        sibling = path[used]
        if index & 1:
            digest = node_hash(sibling, digest)
        elif index < last:
            digest = node_hash(digest, sibling)
        else:
            used -= 1
        index >>= 1
        last >>= 1
        used += 1
    return used == len(path) and digest == expected_root


def verify_consistency(
    old_size: int,
    new_size: int,
    old_root: bytes,
    new_root: bytes,
    proof_path: Sequence[bytes],
) -> bool:
    path = _proof_path(proof_path)
    if any(type(item) is not bytes or len(item) != 32 for item in (old_root, new_root)):
        raise ValueError("consistency proof digest is malformed")
    if type(old_size) is not int or type(new_size) is not int or old_size < 0 or new_size < old_size:
        return False
    if old_size == 0:
        return old_root == EMPTY_TREE_ROOT and not path
    if old_size == new_size:
        return old_root == new_root and not path
    fn = old_size - 1
    sn = new_size - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    if old_size & (old_size - 1) == 0:
        old_hash = old_root
        new_hash = old_root
    else:
        if not path:
            return False
        old_hash = new_hash = path[0]
        path = path[1:]
    used = 0
    while fn:
        if used >= len(path):
            return False
        sibling = path[used]
        if fn & 1 or fn == sn:
            old_hash = node_hash(sibling, old_hash)
            new_hash = node_hash(sibling, new_hash)
            while fn and not fn & 1:
                fn >>= 1
                sn >>= 1
        elif fn < sn:
            new_hash = node_hash(new_hash, sibling)
        fn >>= 1
        sn >>= 1
        used += 1
    while sn:
        if used >= len(path):
            return False
        new_hash = node_hash(new_hash, path[used])
        sn >>= 1
        used += 1
    return used == len(path) and old_hash == old_root and new_hash == new_root


def _scope(value: object) -> DelegationScope:
    return DelegationScope.from_mapping(value)


def _basic(payload: dict[int, object], object_type: ObjectType, required: set[int], allowed: set[int]) -> None:
    if set(payload) - allowed or not required <= set(payload) or payload[1] != object_type or payload[2] != 1:
        _fail("payload has missing, unknown, or invalid base fields")
    if 31 in payload:
        _extensions(payload[31])


@dataclass(frozen=True, slots=True)
class TransparencyCheckpoint(_Record):
    REQUIRED = {1, 2, 3, 4, 5, 32, 33, 34, 35, 36, 37, 38, 39}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> TransparencyCheckpoint:
        payload = cls._decode(raw)
        _basic(payload, ObjectType.TransparencyCheckpoint, cls.REQUIRED, cls.ALLOWED)
        _uint(payload[4], 1, (1 << 64) - 1, "generation")
        _uint(payload[5], 1, (1 << 64) - 1, "sequence")
        issuer = _authority_reference(payload[3], "checkpoint issuer")
        if issuer[1] != AuthorityClass.TRANSPARENCY_LOG or issuer[3] != payload[37]:
            _fail("checkpoint signer is not the exact transparency log")
        _bytes(payload[32], 32, 32, "log_id")
        if issuer[2] != payload[32] or issuer[4] != payload[32]:
            _fail("checkpoint log ID and issuer differ")
        _scope(payload[33])
        _uint(payload[34], 0, (1 << 64) - 1, "tree_size")
        _bytes(payload[35], 32, 32, "merkle_root")
        _uint(payload[36], 0, 253402300799, "timestamp")
        _bytes(payload[37], 1, 64, "signing_key_id")
        if payload[34] == 0:
            if payload[35] != EMPTY_TREE_ROOT or payload[38] is not None:
                _fail("genesis checkpoint is invalid")
        else:
            _bytes(payload[38], 32, 32, "previous_checkpoint_digest")
        if payload[39] is not None:
            _bytes(payload[39], 32, 32, "witness_policy_digest")
        return cls(MappingProxyType(payload))

    @property
    def log_id(self) -> bytes:
        return self._payload[32]

    @property
    def scope(self) -> DelegationScope:
        return _scope(self._payload[33])

    @property
    def tree_size(self) -> int:
        return self._payload[34]

    @property
    def root(self) -> bytes:
        return self._payload[35]

    @property
    def timestamp(self) -> int:
        return self._payload[36]

    def require_fresh(self, now: int, *, maximum_staleness: int) -> None:
        if type(now) is not int or type(maximum_staleness) is not int or now < self.timestamp or now - self.timestamp > maximum_staleness:
            _fail("checkpoint is stale")


@dataclass(frozen=True, slots=True)
class InclusionProof(_Record):
    REQUIRED = {1, 2, 32, 33, 34, 35, 36, 37, 38, 39, 40}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> InclusionProof:
        payload = cls._decode(raw)
        _basic(payload, ObjectType.InclusionProof, cls.REQUIRED, cls.ALLOWED)
        _bytes(payload[32], 32, 32, "log_id")
        _scope(payload[33])
        _bytes(payload[34], 32, 32, "checkpoint_digest")
        size = _uint(payload[35], 1, (1 << 64) - 1, "tree_size")
        _uint(payload[36], 0, size - 1, "leaf_index")
        _bytes(payload[37], 32, 32, "leaf_digest")
        _proof_path(payload[38])
        if payload[39] != 1:
            _fail("unsupported hash profile")
        if payload[40] is not None:
            try:
                ObjectType(payload[40])
            except (TypeError, ValueError):
                _fail("unsupported proof object class")
        return cls(MappingProxyType(payload))

    def verify(self, checkpoint: TransparencyCheckpoint, *, canonical_leaf: bytes, now: int, maximum_staleness: int) -> None:
        if (
            not isinstance(checkpoint, TransparencyCheckpoint)
            or self._payload[34] != checkpoint.digest
            or self._payload[32] != checkpoint.log_id
            or self._payload[33] != checkpoint.scope.to_mapping()
            or self._payload[35] != checkpoint.tree_size
        ):
            _fail("inclusion proof checkpoint binding is invalid")
        checkpoint.require_fresh(now, maximum_staleness=maximum_staleness)
        if leaf_hash(canonical_leaf) != self._payload[37] or not verify_inclusion(
            self._payload[37], self._payload[36], self._payload[35], self._payload[38], checkpoint.root
        ):
            _fail("inclusion proof verification failed")


@dataclass(frozen=True, slots=True)
class ConsistencyProof(_Record):
    REQUIRED = {1, 2, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> ConsistencyProof:
        payload = cls._decode(raw)
        _basic(payload, ObjectType.ConsistencyProof, cls.REQUIRED, cls.ALLOWED)
        _bytes(payload[32], 32, 32, "log_id")
        _scope(payload[33])
        for key in (34, 35, 38, 39):
            _bytes(payload[key], 32, 32, "consistency digest")
        old_size = _uint(payload[36], 0, (1 << 64) - 1, "old_tree_size")
        _uint(payload[37], old_size, (1 << 64) - 1, "new_tree_size")
        _proof_path(payload[40])
        if payload[41] != 1:
            _fail("unsupported hash profile")
        return cls(MappingProxyType(payload))

    def verify(self, old: TransparencyCheckpoint, new: TransparencyCheckpoint) -> None:
        if not isinstance(old, TransparencyCheckpoint) or not isinstance(new, TransparencyCheckpoint):
            _fail("consistency checkpoint context is invalid")
        expected = (old.log_id, old.scope.to_mapping(), old.digest, new.digest, old.tree_size, new.tree_size, old.root, new.root)
        actual = tuple(self._payload[key] for key in (32, 33, 34, 35, 36, 37, 38, 39))
        if actual != expected or not verify_consistency(old.tree_size, new.tree_size, old.root, new.root, self._payload[40]):
            _fail("consistency proof verification failed")


@dataclass(frozen=True, slots=True)
class WitnessStatement(_Record):
    REQUIRED = {1, 2, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> WitnessStatement:
        payload = cls._decode(raw)
        _basic(payload, ObjectType.WitnessStatement, cls.REQUIRED, cls.ALLOWED)
        for key in (32, 33, 35, 37):
            _bytes(payload[key], 32, 32, "witness digest or ID")
        _scope(payload[34])
        _uint(payload[36], 0, (1 << 64) - 1, "tree_size")
        observed = _uint(payload[38], 0, 253402300799, "observed_at")
        _uint(payload[39], 1, 2, "verification_result")
        _bytes(payload[40], 16, 64, "replay_context")
        _bytes(payload[41], 1, 64, "signing_key_id")
        _uint(payload[42], observed, 253402300799, "valid_until")
        return cls(MappingProxyType(payload))

    def verify_observation(
        self, checkpoint: TransparencyCheckpoint, *, now: int, expected_replay_context: bytes, expected_kid: bytes
    ) -> None:
        if tuple(self._payload[key] for key in (33, 34, 35, 36, 37)) != (
            checkpoint.log_id,
            checkpoint.scope.to_mapping(),
            checkpoint.digest,
            checkpoint.tree_size,
            checkpoint.root,
        ):
            _fail("witness checkpoint binding is invalid")
        if (
            self._payload[40] != expected_replay_context
            or self._payload[41] != expected_kid
            or not self._payload[38] <= now <= self._payload[42]
        ):
            _fail("witness replay, key, or validity context is invalid")
        if self._payload[39] != 1:
            _fail("conflicting witness statement")


_AUTHENTICATED_WITNESS_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedWitness:
    statement: WitnessStatement
    authority_identity: bytes
    organization: str
    signer_kid: bytes
    _provenance: object

    def __init__(self, *_: object, **__: object) -> None:
        _fail("authenticated witness evidence must come from the COSE verifier")

    @classmethod
    def _from_cose_verifier(
        cls, statement: WitnessStatement, authority_identity: bytes, organization: str, signer_kid: bytes, token: object
    ) -> AuthenticatedWitness:
        if token is not _AUTHENTICATED_WITNESS_TOKEN:
            _fail("authenticated witness provenance is invalid")
        instance = object.__new__(cls)
        object.__setattr__(instance, "statement", statement)
        object.__setattr__(instance, "authority_identity", authority_identity)
        object.__setattr__(instance, "organization", organization)
        object.__setattr__(instance, "signer_kid", signer_kid)
        object.__setattr__(instance, "_provenance", token)
        return instance


def verify_witness_threshold(
    evidence: Sequence[AuthenticatedWitness],
    checkpoint: TransparencyCheckpoint,
    required: int,
    *,
    now: int,
    replay_contexts: Mapping[bytes, bytes],
    configured_witnesses: Mapping[bytes, tuple[str, bytes]],
) -> int:
    if required not in {2, 3}:
        _fail("witness threshold policy is not approved")
    if len(configured_witnesses) != (3 if required == 2 else 5):
        _fail("witness threshold denominator is not approved")
    identities: set[bytes] = set()
    organizations: set[str] = set()
    for item in evidence:
        if not isinstance(item, AuthenticatedWitness) or item._provenance is not _AUTHENTICATED_WITNESS_TOKEN:
            _fail("witness evidence is not authenticated for witness purpose")
        if item.authority_identity in identities:
            _fail("duplicate witness authority")
        if item.statement._payload[32] != item.authority_identity:
            _fail("witness authority identity is misattributed")
        configured_organization = configured_witnesses.get(item.authority_identity)
        if configured_organization is None or configured_organization != (item.organization, item.signer_kid):
            _fail("witness is not configured by the accepted trust bundle")
        replay_context = replay_contexts.get(item.authority_identity)
        if replay_context is None:
            _fail("witness replay context is unavailable")
        item.statement.verify_observation(
            checkpoint,
            now=now,
            expected_replay_context=replay_context,
            expected_kid=item.signer_kid,
        )
        identities.add(item.authority_identity)
        if item.organization in organizations:
            _fail("witness organization diversity is insufficient")
        organizations.add(item.organization)
        if item.statement._payload[39] != 1:
            _fail("conflicting witness statements require quarantine")
        if tuple(item.statement._payload[key] for key in (33, 34, 35, 36, 37)) != (
            checkpoint.log_id,
            checkpoint.scope.to_mapping(),
            checkpoint.digest,
            checkpoint.tree_size,
            checkpoint.root,
        ):
            _fail("witness statement binds a different checkpoint")
    if len(identities) < required:
        _fail("witness threshold is insufficient")
    return len(identities)


class TransparencyVerifier:
    def __init__(self, current: TransparencyCheckpoint | None = None) -> None:
        self.current = current
        self.conflicts: tuple[TransparencyCheckpoint, ...] = ()

    def accept_checkpoint(
        self, candidate: TransparencyCheckpoint, *, now: int, consistency: ConsistencyProof | None = None, maximum_staleness: int = 900
    ) -> str:
        if self.current is None:
            if (candidate.generation, candidate.sequence, candidate.tree_size) != (1, 1, 0):
                _fail("checkpoint genesis is invalid")
            candidate.require_fresh(now, maximum_staleness=maximum_staleness)
            self.current = candidate
            return "ACCEPT"
        current = self.current
        if candidate.log_id != current.log_id or candidate.scope != current.scope:
            _fail("checkpoint log or scope changed")
        if candidate.tree_size == current.tree_size:
            if candidate.root != current.root:
                by_digest = {item.digest: item for item in (*self.conflicts, current, candidate)}
                self.conflicts = tuple(by_digest.values())
                return "QUARANTINE"
            if candidate.digest == current.digest:
                return "IDEMPOTENT"
        if candidate.tree_size < current.tree_size or (candidate.generation, candidate.sequence) <= (current.generation, current.sequence):
            _fail("checkpoint rollback")
        if candidate._payload[38] != current.digest:
            _fail("checkpoint previous digest is invalid")
        if candidate.generation == current.generation:
            if candidate.sequence != current.sequence + 1:
                _fail("checkpoint sequence continuity is invalid")
        elif not (candidate.generation == current.generation + 1 and candidate.sequence == 1):
            _fail("checkpoint generation transition is invalid")
        if consistency is None:
            _fail("stale checkpoint requires consistency proof")
        consistency.verify(current, candidate)
        candidate.require_fresh(now, maximum_staleness=maximum_staleness)
        self.current = candidate
        return "ACCEPT"
