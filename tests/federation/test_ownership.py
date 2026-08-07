from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import (
    AuthorityClass,
    FederationAuthority,
    FederationValidationError,
    KeyLifecycle,
    KeyPurpose,
    ObjectType,
    verify_federation_sign1,
)
from nbsr.federation.ownership import NameOwnershipRecord, OwnershipTransitionBinding, derive_service_id
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


OWNER = b"O" * 32
NEW_OWNER = b"N" * 32


def authority(authority_class: AuthorityClass, actor: bytes, purpose: bytes = b"ownership-key") -> dict[int, object]:
    return {1: authority_class.value, 2: actor, 3: purpose, 4: actor if len(actor) == 32 else None}


def payload(**changes: object) -> dict[int, object]:
    name = "service.example"
    value: dict[int, object] = {
        1: ObjectType.NameOwnershipRecord.value,
        2: 1,
        3: authority(AuthorityClass.NAME_OWNER, OWNER),
        4: 1,
        5: 1,
        6: 100,
        7: 1_000,
        32: name,
        33: authority(AuthorityClass.NAME_OWNER, OWNER),
        34: derive_service_id(OWNER, name),
        35: hashlib.sha256(b"bootstrap").digest(),
        36: 0,
        37: None,
    }
    value.update({int(key): item for key, item in changes.items()})
    return value


def record(**changes: object) -> NameOwnershipRecord:
    return NameOwnershipRecord.from_bytes(encode_deterministic(payload(**changes)))


def test_valid_genesis_binds_canonical_name_stable_service_and_owner_authority() -> None:
    candidate = record()
    assert candidate.name_scope == "service.example"
    assert candidate.owner_operator_id == OWNER
    assert candidate.service_id.hex() == "c9e6b43b1b5820236970074203e304d8cc9817ff47ee66cbd16f494a0dc3de49"
    candidate.require_valid_at(100)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (32, "SERVICE.EXAMPLE"),
        (32, "t\u00e4st.example"),
        (32, "xn--invalid.example"),
        (34, b"wrong" * 6 + b"xx"),
        (35, b"short"),
        (36, 99),
        (37, {1: 3}),
        (127, b"unknown"),
    ],
)
def test_genesis_rejects_noncanonical_identity_bootstrap_lifecycle_and_unknown_fields(key: int, value: object) -> None:
    with pytest.raises(FederationValidationError):
        record(**{str(key): value})


def test_genesis_forbids_predecessor_and_update_requires_exact_predecessor() -> None:
    with pytest.raises(FederationValidationError):
        record(**{"8": b"P" * 32})
    current = record()
    update = payload(**{"5": 2, "8": current.digest})
    NameOwnershipRecord.from_bytes(encode_deterministic(update)).require_newer_than(current)
    update[8] = b"X" * 32
    with pytest.raises(FederationValidationError):
        NameOwnershipRecord.from_bytes(encode_deterministic(update)).require_newer_than(current)


def test_equal_version_is_idempotent_by_digest_and_equivocation_otherwise() -> None:
    current = record()
    assert current.require_newer_than(record()) is False
    conflicting = record(**{"7": 999})
    with pytest.raises(FederationValidationError, match="equivocat"):
        conflicting.require_newer_than(current)


def test_rollback_and_immutable_name_and_service_identity_reject() -> None:
    current = record(**{"5": 2, "8": b"P" * 32})
    with pytest.raises(FederationValidationError, match="rollback"):
        record().require_newer_than(current)
    for key, value in ((32, "other.example"), (34, b"S" * 32)):
        update = payload(**{"5": 2, "8": record().digest, str(key): value})
        with pytest.raises(FederationValidationError):
            NameOwnershipRecord.from_bytes(encode_deterministic(update)).require_newer_than(record())


def test_transfer_and_recovery_new_generation_require_exact_evidence_and_preserve_service_id() -> None:
    current = record()
    transfer_payload = payload(
        **{
            "3": authority(AuthorityClass.NAME_OWNER, NEW_OWNER),
            "4": 2,
            "5": 1,
            "8": current.digest,
            "33": authority(AuthorityClass.NAME_OWNER, NEW_OWNER),
            "36": 2,
        }
    )
    candidate = NameOwnershipRecord.from_bytes(encode_deterministic(transfer_payload))
    transfer = OwnershipTransitionBinding(
        digest=b"T" * 32,
        accepted=True,
        object_type=ObjectType.NameOwnershipRecord,
        transfer_state=2,
        service_id=current.service_id,
        name_scope=current.name_scope,
        old_owner_id=current.owner_operator_id,
        new_owner_id=NEW_OWNER,
        old_generation=1,
        new_generation=2,
        dual_authorized=True,
    )
    candidate.require_newer_than(current, transition=transfer)
    assert candidate.service_id == current.service_id
    recovery_payload = dict(transfer_payload)
    recovery_payload[36] = 3
    recovery = NameOwnershipRecord.from_bytes(encode_deterministic(recovery_payload))
    recovery_binding = OwnershipTransitionBinding(
        digest=b"R" * 32,
        accepted=True,
        object_type=ObjectType.NameOwnershipRecord,
        transfer_state=3,
        service_id=current.service_id,
        name_scope=current.name_scope,
        old_owner_id=current.owner_operator_id,
        new_owner_id=NEW_OWNER,
        old_generation=1,
        new_generation=2,
        dual_authorized=False,
    )
    recovery.require_newer_than(current, transition=recovery_binding)
    with pytest.raises(FederationValidationError):
        candidate.require_newer_than(current)
    for change in (
        {"accepted": False},
        {"object_type": ObjectType.DelegationRecord},
        {"service_id": b"X" * 32},
        {"new_generation": 3},
        {"dual_authorized": False},
    ):
        values = {name: getattr(transfer, name) for name in transfer.__dataclass_fields__}
        values.update(change)
        with pytest.raises(FederationValidationError):
            candidate.require_newer_than(current, transition=OwnershipTransitionBinding(**values))

    private = Ed25519PrivateKey.generate()
    raw = candidate.canonical_bytes()
    message = sign1(raw, b"ownership-key", private)
    signer = FederationAuthority(
        b"ownership-key",
        private.public_key(),
        NEW_OWNER,
        KeyPurpose.NAME_OWNERSHIP,
        KeyLifecycle.ACTIVE,
        1,
        1,
        0,
        1_000,
        False,
    )
    with pytest.raises(FederationValidationError, match="current"):
        verify_federation_sign1(message, signer, ObjectType.NameOwnershipRecord, 500, expected_key_purpose=KeyPurpose.NAME_OWNERSHIP)
    assert (
        verify_federation_sign1(
            message,
            signer,
            ObjectType.NameOwnershipRecord,
            500,
            expected_key_purpose=KeyPurpose.NAME_OWNERSHIP,
            current_record=current,
            transition=transfer,
        ).digest
        == candidate.digest
    )


def test_revocation_is_terminal_and_unknown_noncritical_extension_is_preserved() -> None:
    current = record()
    revoked_payload = payload(**{"5": 2, "8": current.digest, "37": {1: 3, 2: current.service_id, 3: current.digest}})
    revoked = NameOwnershipRecord.from_bytes(encode_deterministic(revoked_payload))
    revoked.require_newer_than(current)
    successor = dict(revoked_payload)
    successor.update({5: 3, 8: revoked.digest, 37: None})
    with pytest.raises(FederationValidationError, match="terminal"):
        NameOwnershipRecord.from_bytes(encode_deterministic(successor)).require_newer_than(revoked)

    noncritical = payload(**{"31": {1000: {1: 1, 2: False, 3: b"opaque"}}})
    raw = encode_deterministic(noncritical)
    assert NameOwnershipRecord.from_bytes(raw).canonical_bytes() == raw
    critical = payload(**{"31": {1000: {1: 1, 2: True, 3: b"opaque"}}})
    with pytest.raises(FederationValidationError):
        NameOwnershipRecord.from_bytes(encode_deterministic(critical))


def test_payload_resource_limit_rejects_before_decode() -> None:
    with pytest.raises(FederationValidationError, match="bound"):
        NameOwnershipRecord.from_bytes(b"x" * 32_769)


def test_task2_cose_authority_is_reused_for_exact_ownership_purpose_and_signer() -> None:
    private = Ed25519PrivateKey.generate()
    raw = encode_deterministic(payload())
    message = sign1(raw, b"ownership-key", private)
    signer = FederationAuthority(
        b"ownership-key",
        private.public_key(),
        OWNER,
        KeyPurpose.NAME_OWNERSHIP,
        KeyLifecycle.ACTIVE,
        1,
        1,
        0,
        1_000,
        False,
    )
    verified = verify_federation_sign1(
        message,
        signer,
        ObjectType.NameOwnershipRecord,
        500,
        expected_payload=raw,
        expected_key_purpose=KeyPurpose.NAME_OWNERSHIP,
    )
    assert verified.digest == NameOwnershipRecord.from_bytes(raw).digest
    wrong = FederationAuthority(
        signer.kid,
        signer.public_key,
        signer.operator_id,
        KeyPurpose.DELEGATION,
        signer.lifecycle,
        signer.generation,
        signer.sequence,
        signer.not_before,
        signer.expires_at,
        signer.revoked,
    )
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(message, wrong, ObjectType.NameOwnershipRecord, 500)
