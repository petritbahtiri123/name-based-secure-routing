from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import (
    AuthorityClass,
    FederationAuthority,
    FederationProfile,
    FederationValidationError,
    KeyLifecycle,
    KeyPurpose,
)
from nbsr.federation.delegation import DelegationRecord, DelegationScope, DelegationVerifier, SignedFederationObject
from nbsr.federation.ownership import NameOwnershipRecord, derive_service_id
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


ROOT_SERVICE_ID = derive_service_id(b"A" * 32, "service.example")


def ref(cls: AuthorityClass, actor: bytes) -> dict[int, object]:
    return {1: cls.value, 2: actor, 3: b"key", 4: actor}


def scope(depth: int, *, ports: list[list[int]] | None = None, protocols: list[int] | None = None) -> dict[int, object]:
    return {
        1: "service.example",
        2: ROOT_SERVICE_ID,
        3: b"tenant",
        4: b"A" * 32,
        5: b"B" * 32,
        6: "eu",
        7: ports or [[443, 443]],
        8: protocols or [6],
        9: [1],
        10: depth > 0,
        11: depth,
    }


def ownership(*, revoked: bool = False) -> NameOwnershipRecord:
    owner = b"A" * 32
    service_id = derive_service_id(owner, "service.example")
    payload = {
        1: 3,
        2: 1,
        3: ref(AuthorityClass.NAME_OWNER, owner),
        4: 1,
        5: 1,
        6: 0,
        7: 10_000,
        32: "service.example",
        33: ref(AuthorityClass.NAME_OWNER, owner),
        34: service_id,
        35: None,
        36: 0,
        37: None,
    }
    if revoked:
        payload[37] = {1: 3, 2: service_id, 3: None}
    return NameOwnershipRecord.from_bytes(encode_deterministic(payload))


def chain(length: int) -> tuple[NameOwnershipRecord | DelegationRecord, ...]:
    root = ownership()
    result: list[NameOwnershipRecord | DelegationRecord] = [root]
    parent_digest: bytes | None = None
    actor = b"A" * 32
    for index in range(length):
        delegatee = bytes([67 + index]) * 32
        payload = {
            1: 4,
            2: 1,
            3: ref(AuthorityClass.NAME_OWNER if index == 0 else AuthorityClass.DELEGATE, actor),
            4: 1,
            5: 1,
            6: 0,
            7: 9_000 - index,
            32: ref(AuthorityClass.NAME_OWNER if index == 0 else AuthorityClass.DELEGATE, actor),
            33: ref(AuthorityClass.DELEGATE, delegatee),
            34: scope(FederationProfile.max_delegation_depth - index),
            36: None,
            37: None,
        }
        if parent_digest is not None:
            payload[35] = parent_digest
        item = DelegationRecord.from_bytes(encode_deterministic(payload))
        result.append(item)
        parent_digest = item.digest
        actor = delegatee
    return tuple(result)


def test_valid_one_level_and_exact_maximum_depth_are_accepted_iteratively() -> None:
    for length in (1, FederationProfile.max_delegation_depth):
        values = chain(length)
        request = DelegationScope.from_mapping(scope(FederationProfile.max_delegation_depth - length))
        assert DelegationVerifier.verify_semantics(values, request, 500) == values[-1]


def test_one_level_over_depth_and_chain_object_bound_reject() -> None:
    with pytest.raises(FederationValidationError, match="depth"):
        DelegationVerifier.verify_semantics(chain(FederationProfile.max_delegation_depth + 1), DelegationScope.from_mapping(scope(0)), 500)
    oversized = tuple([ownership()] * (FederationProfile.max_chain_objects + 1))
    with pytest.raises(FederationValidationError, match="chain"):
        DelegationVerifier.verify_semantics(oversized, DelegationScope.from_mapping(scope(0)), 500)


def test_loop_repeated_actor_repeated_digest_broken_ancestry_and_sibling_isolation_reject() -> None:
    valid = chain(2)
    for broken in ((valid[0], valid[1], valid[1]),):
        with pytest.raises(FederationValidationError):
            DelegationVerifier.verify_semantics(broken, DelegationScope.from_mapping(scope(6)), 500)
    broken_payload = dict(valid[2]._payload)
    broken_payload[35] = b"X" * 32
    broken = DelegationRecord.from_bytes(encode_deterministic(broken_payload))
    with pytest.raises(FederationValidationError, match="broken ancestry"):
        DelegationVerifier.verify_semantics((valid[0], valid[1], broken), DelegationScope.from_mapping(scope(6)), 500)
    assert DelegationVerifier.verify_semantics((valid[0], valid[2], valid[1]), DelegationScope.from_mapping(scope(7)), 500) == valid[1]


def test_partial_service_port_protocol_and_successive_scope_widening_are_checked() -> None:
    valid = list(chain(2))
    narrow = DelegationScope.from_mapping(scope(6, ports=[[443, 443]], protocols=[6]))
    assert DelegationVerifier.verify_semantics(tuple(valid), narrow, 500) == valid[-1]
    child = valid[-1]
    bad_payload = dict(child._payload)
    bad_payload[34] = scope(6, ports=[[80, 80], [443, 443]], protocols=[6, 17])
    bad_payload[35] = valid[1].digest
    bad = DelegationRecord.from_bytes(encode_deterministic(bad_payload))
    with pytest.raises(FederationValidationError, match="scope"):
        DelegationVerifier.verify_semantics((valid[0], valid[1], bad), narrow, 500)


def test_every_delegation_scope_is_bound_to_the_ownership_name_and_service() -> None:
    valid = list(chain(1))
    for key, value in ((1, "other.example"), (2, b"X" * 32)):
        bad_payload = dict(valid[1]._payload)
        bad_payload[34] = dict(bad_payload[34])
        bad_payload[34][key] = value
        bad = DelegationRecord.from_bytes(encode_deterministic(bad_payload))
        with pytest.raises(FederationValidationError, match="ownership scope"):
            DelegationVerifier.verify_semantics((valid[0], bad), DelegationScope.from_mapping(bad_payload[34]), 500)


def test_forbidden_subdelegation_terminal_ancestor_and_parent_revocation_invalidate_child_only() -> None:
    values = list(chain(2))
    parent_payload = dict(values[1]._payload)
    parent_payload[34] = dict(parent_payload[34])
    parent_payload[34][10] = False
    parent = DelegationRecord.from_bytes(encode_deterministic(parent_payload))
    child_payload = dict(values[2]._payload)
    child_payload[35] = parent.digest
    child = DelegationRecord.from_bytes(encode_deterministic(child_payload))
    with pytest.raises(FederationValidationError, match="subdelegation"):
        DelegationVerifier.verify_semantics((values[0], parent, child), DelegationScope.from_mapping(scope(6)), 500)

    revoked_payload = dict(values[1]._payload)
    revoked_payload[37] = {1: 4, 2: parent.delegatee_id, 3: parent.digest}
    revoked = DelegationRecord.from_bytes(encode_deterministic(revoked_payload))
    revoked_child_payload = dict(values[2]._payload)
    revoked_child_payload[35] = revoked.digest
    revoked_child = DelegationRecord.from_bytes(encode_deterministic(revoked_child_payload))
    with pytest.raises(FederationValidationError, match="revoked"):
        DelegationVerifier.verify_semantics((values[0], revoked, revoked_child), DelegationScope.from_mapping(scope(6)), 500)
    assert DelegationVerifier.verify_semantics((values[0], parent), DelegationScope.from_mapping(scope(7) | {10: False}), 500) == parent


def test_graph_node_and_traversal_bounds_and_failure_precedence_are_deterministic() -> None:
    request = DelegationScope.from_mapping(scope(0))
    with pytest.raises(FederationValidationError, match="graph"):
        DelegationVerifier.verify_semantics(tuple(), request, 500)
    with pytest.raises(FederationValidationError, match="graph"):
        DelegationVerifier.verify_semantics(tuple([ownership()] * (FederationProfile.max_graph_nodes + 1)), request, 500)


def test_authority_verifier_rejects_unsigned_semantic_records() -> None:
    with pytest.raises(FederationValidationError, match="signed"):
        DelegationVerifier.verify(chain(1), DelegationScope.from_mapping(scope(7)), 500)


def test_authority_verifier_checks_every_exact_purpose_sign1_before_returning_authority() -> None:
    values = chain(1)
    private = Ed25519PrivateKey.generate()
    owner_authority = FederationAuthority(
        b"key", private.public_key(), b"A" * 32, KeyPurpose.NAME_OWNERSHIP, KeyLifecycle.ACTIVE, 1, 1, 0, 10_000, False
    )
    delegation_authority = FederationAuthority(
        b"key", private.public_key(), b"A" * 32, KeyPurpose.DELEGATION, KeyLifecycle.ACTIVE, 1, 1, 0, 10_000, False
    )
    signed = (
        SignedFederationObject(sign1(values[0].canonical_bytes(), b"key", private), owner_authority, values[0].canonical_bytes()),
        SignedFederationObject(sign1(values[1].canonical_bytes(), b"key", private), delegation_authority, values[1].canonical_bytes()),
    )
    request = DelegationScope.from_mapping(scope(7))
    assert DelegationVerifier.verify(signed, request, 500).digest == values[1].digest
    with pytest.raises(FederationValidationError):
        DelegationVerifier.verify(
            (signed[0], SignedFederationObject(signed[1].message, owner_authority, signed[1].expected_payload)), request, 500
        )
