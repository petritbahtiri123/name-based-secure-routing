from __future__ import annotations

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import (
    AuthorityClass,
    FederationAuthority,
    FederationValidationError,
    KeyLifecycle,
    KeyPurpose,
    ObjectType,
    RecoveryTransitionBinding,
    verify_federation_sign1,
)
from nbsr.federation.delegation import DelegationRecord, DelegationScope
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


A = b"A" * 32
B = b"B" * 32


def authority(cls: AuthorityClass, actor: bytes, kid: bytes = b"delegation-key") -> dict[int, object]:
    return {1: cls.value, 2: actor, 3: kid, 4: actor}


def scope(**changes: object) -> dict[int, object]:
    value: dict[int, object] = {
        1: "service.example",
        2: b"S" * 32,
        3: b"tenant",
        4: A,
        5: B,
        6: "eu-central",
        7: [[80, 80], [443, 443], [8000, 8099]],
        8: [6, 17],
        9: [1, 2, 3],
        10: True,
        11: 8,
    }
    value.update({int(key): item for key, item in changes.items()})
    return value


def payload(**changes: object) -> dict[int, object]:
    value: dict[int, object] = {
        1: ObjectType.DelegationRecord.value,
        2: 1,
        3: authority(AuthorityClass.NAME_OWNER, A),
        4: 1,
        5: 1,
        6: 100,
        7: 900,
        32: authority(AuthorityClass.NAME_OWNER, A),
        33: authority(AuthorityClass.DELEGATE, B),
        34: scope(),
        36: None,
        37: None,
    }
    value.update({int(key): item for key, item in changes.items()})
    return value


def test_scope_is_closed_canonical_and_covers_every_dimension() -> None:
    parsed = DelegationScope.from_mapping(scope())
    assert parsed.to_mapping() == scope()
    assert parsed == DelegationScope.from_bytes(parsed.canonical_bytes())
    for key in range(1, 12):
        malformed = scope()
        malformed.pop(key)
        with pytest.raises(FederationValidationError):
            DelegationScope.from_mapping(malformed)
    with pytest.raises(FederationValidationError):
        DelegationScope.from_mapping({**scope(), 12: None})


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        (1, None),
        (2, None),
        (3, None),
        (4, None),
        (5, None),
        (6, None),
        (8, [6, 6]),
        (9, [3, 2]),
        (11, 9),
    ],
)
def test_null_or_malformed_field_never_widens_parent(key: int, bad: object) -> None:
    parent = DelegationScope.from_mapping(scope())
    child = scope()
    child[key] = bad
    with pytest.raises(FederationValidationError):
        parent.intersect(DelegationScope.from_mapping(child))


def test_scope_equal_strict_narrowing_prohibited_widening_and_deterministic_intersection() -> None:
    parent = DelegationScope.from_mapping(scope())
    narrow = DelegationScope.from_mapping(scope(**{"7": [[443, 443], [8010, 8019]], "8": [6], "9": [2], "10": False, "11": 7}))
    assert parent.intersect(parent) == parent
    assert parent.intersect(narrow) == narrow
    assert narrow.is_strict_narrowing_of(parent)
    with pytest.raises(FederationValidationError):
        narrow.intersect(parent)
    assert parent.intersect(DelegationScope.from_mapping(scope(**{"10": False}))).to_mapping()[10] is False


@pytest.mark.parametrize("ranges", [[[443, 443], [80, 80]], [[80, 100], [100, 120]], [[80, 100], [101, 120]], [[0, 80]], [[80, 65_536]]])
def test_port_ranges_require_normalized_sorted_disjoint_nonadjacent_form(ranges: list[list[int]]) -> None:
    with pytest.raises(FederationValidationError):
        DelegationScope.from_mapping(scope(**{"7": ranges}))


def test_direct_child_update_recovery_revocation_and_continuity() -> None:
    direct = DelegationRecord.from_bytes(encode_deterministic(payload()))
    child_payload = payload(
        **{
            "3": authority(AuthorityClass.DELEGATE, B),
            "32": authority(AuthorityClass.DELEGATE, B),
            "33": authority(AuthorityClass.DELEGATE, b"C" * 32),
            "34": scope(**{"10": False, "11": 7}),
            "35": direct.digest,
        }
    )
    child = DelegationRecord.from_bytes(encode_deterministic(child_payload))
    child.require_parent(direct)
    update_payload = dict(child_payload)
    update_payload.update({5: 2, 8: child.digest})
    update = DelegationRecord.from_bytes(encode_deterministic(update_payload))
    update.require_newer_than(child)
    recovery_payload = dict(update_payload)
    recovery_payload.update({4: 2, 5: 1, 8: update.digest})
    recovery = DelegationRecord.from_bytes(encode_deterministic(recovery_payload))
    binding = RecoveryTransitionBinding(
        digest=b"R" * 32,
        operator_id=recovery.delegator_id,
        key_purpose=KeyPurpose.DELEGATION,
        old_generation=1,
        new_generation=2,
        accepted=True,
        object_type=ObjectType.DelegationRecord,
        scope=recovery.scope.to_mapping(),
    )
    recovery.require_newer_than(update, recovery_transition=binding)
    with pytest.raises(FederationValidationError):
        recovery.require_newer_than(update, recovery_transition=replace(binding, accepted=False))
    private = Ed25519PrivateKey.generate()
    raw = recovery.canonical_bytes()
    message = sign1(raw, b"delegation-key", private)
    signer = FederationAuthority(
        b"delegation-key",
        private.public_key(),
        recovery.delegator_id,
        KeyPurpose.DELEGATION,
        KeyLifecycle.ACTIVE,
        1,
        1,
        0,
        1_000,
        False,
    )
    with pytest.raises(FederationValidationError, match="current"):
        verify_federation_sign1(message, signer, ObjectType.DelegationRecord, 500, expected_key_purpose=KeyPurpose.DELEGATION)
    assert (
        verify_federation_sign1(
            message,
            signer,
            ObjectType.DelegationRecord,
            500,
            expected_key_purpose=KeyPurpose.DELEGATION,
            current_record=update,
            transition=binding,
        ).digest
        == recovery.digest
    )
    revoked_payload = dict(update_payload)
    revoked_payload[37] = {1: 4, 2: child.delegatee_id, 3: child.digest}
    revoked = DelegationRecord.from_bytes(encode_deterministic(revoked_payload))
    revoked.require_newer_than(child)


def test_wrong_class_parent_stale_validity_rollback_equivocation_and_critical_extension_reject() -> None:
    direct = DelegationRecord.from_bytes(encode_deterministic(payload()))
    for mutation in (
        {32: authority(AuthorityClass.SOURCE_OPERATOR, A)},
        {33: authority(AuthorityClass.NAME_OWNER, B)},
        {35: b"wrong" * 6 + b"xx"},
        {31: {1000: {1: 1, 2: True, 3: b"opaque"}}},
    ):
        with pytest.raises(FederationValidationError):
            DelegationRecord.from_bytes(encode_deterministic(payload(**{str(k): v for k, v in mutation.items()})))
    direct.require_valid_at(100)
    with pytest.raises(FederationValidationError):
        direct.require_valid_at(901)
    same_version = DelegationRecord.from_bytes(encode_deterministic(payload(**{"7": 899})))
    with pytest.raises(FederationValidationError, match="equivocat"):
        same_version.require_newer_than(direct)


def test_task2_cose_authority_is_reused_for_exact_delegation_purpose_and_signer() -> None:
    private = Ed25519PrivateKey.generate()
    raw = encode_deterministic(payload())
    message = sign1(raw, b"delegation-key", private)
    signer = FederationAuthority(
        b"delegation-key", private.public_key(), A, KeyPurpose.DELEGATION, KeyLifecycle.ACTIVE, 1, 1, 0, 1_000, False
    )
    verified = verify_federation_sign1(
        message, signer, ObjectType.DelegationRecord, 500, expected_payload=raw, expected_key_purpose=KeyPurpose.DELEGATION
    )
    assert verified.digest == DelegationRecord.from_bytes(raw).digest
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(message, replace(signer, purpose=KeyPurpose.NAME_OWNERSHIP), ObjectType.DelegationRecord, 500)
