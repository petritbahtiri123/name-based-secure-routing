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
    verify_federation_sign1,
)
from nbsr.federation.transparency import (
    EMPTY_TREE_ROOT,
    ConsistencyProof,
    InclusionProof,
    TransparencyCheckpoint,
    TransparencyVerifier,
    leaf_hash,
)
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


LOG = b"L" * 32
SCOPE = {
    1: "service.example",
    2: b"S" * 32,
    3: b"tenant",
    4: b"A" * 32,
    5: b"B" * 32,
    6: "eu",
    7: [[443, 443]],
    8: [6],
    9: [1],
    10: False,
    11: 1,
}


def checkpoint(**changes: object) -> TransparencyCheckpoint:
    value = {
        1: 6,
        2: 1,
        3: {1: AuthorityClass.TRANSPARENCY_LOG.value, 2: LOG, 3: b"log-key", 4: LOG},
        4: 1,
        5: 1,
        32: LOG,
        33: SCOPE,
        34: 0,
        35: EMPTY_TREE_ROOT,
        36: 0,
        37: b"log-key",
        38: None,
        39: None,
    }
    value.update({int(k): v for k, v in changes.items()})
    return TransparencyCheckpoint.from_bytes(encode_deterministic(value))


def test_genesis_checkpoint_and_log_continuity_not_object_lineage() -> None:
    genesis = checkpoint()
    verifier = TransparencyVerifier()
    assert verifier.accept_checkpoint(genesis, now=0) == "ACCEPT"
    grown = checkpoint(**{"5": 2, "34": 1, "35": leaf_hash(b"a"), "36": 60, "38": genesis.digest})
    proof = ConsistencyProof.from_bytes(
        encode_deterministic(
            {
                1: 8,
                2: 1,
                32: LOG,
                33: SCOPE,
                34: genesis.digest,
                35: grown.digest,
                36: 0,
                37: 1,
                38: EMPTY_TREE_ROOT,
                39: leaf_hash(b"a"),
                40: [],
                41: 1,
            }
        )
    )
    assert verifier.accept_checkpoint(grown, now=60, consistency=proof) == "ACCEPT"
    assert 8 not in grown._payload


def test_checkpoint_freshness_rollback_split_view_generation_and_extensions() -> None:
    genesis = checkpoint()
    with pytest.raises(FederationValidationError, match="stale"):
        genesis.require_fresh(901, maximum_staleness=900)
    accepted = checkpoint(**{"34": 1, "35": leaf_hash(b"a"), "38": genesis.digest})
    verifier = TransparencyVerifier(accepted)
    split = checkpoint(**{"34": 1, "35": b"X" * 32, "38": genesis.digest})
    assert verifier.accept_checkpoint(split, now=0) == "QUARANTINE"
    assert len(verifier.conflicts) == 2
    with pytest.raises(FederationValidationError, match="generation"):
        verifier.accept_checkpoint(checkpoint(**{"4": 2, "5": 2, "34": 2, "35": b"Y" * 32, "38": accepted.digest}), now=0)
    with pytest.raises(FederationValidationError, match="critical"):
        checkpoint(**{"31": {1000: {1: 1, 2: True, 3: b"x"}}})


def test_inclusion_proof_binds_exact_checkpoint_leaf_scope_and_path() -> None:
    cp = checkpoint(**{"34": 1, "35": leaf_hash(b"a"), "38": b"G" * 32})
    proof = InclusionProof.from_bytes(
        encode_deterministic(
            {
                1: 7,
                2: 1,
                32: LOG,
                33: SCOPE,
                34: cp.digest,
                35: 1,
                36: 0,
                37: leaf_hash(b"a"),
                38: [],
                39: 1,
                40: ObjectType.FederationTrustBundle.value,
            }
        )
    )
    proof.verify(cp, canonical_leaf=b"a", now=0, maximum_staleness=900)
    with pytest.raises(FederationValidationError):
        proof.verify(checkpoint(), canonical_leaf=b"a", now=0, maximum_staleness=900)
    with pytest.raises(FederationValidationError):
        proof.verify(cp, canonical_leaf=b"b", now=0, maximum_staleness=900)
    with pytest.raises(ValueError, match="proof"):
        InclusionProof.from_bytes(
            encode_deterministic(
                {1: 7, 2: 1, 32: LOG, 33: SCOPE, 34: cp.digest, 35: 1, 36: 0, 37: leaf_hash(b"a"), 38: [b"x"], 39: 1, 40: None}
            )
        )


def test_consistency_proof_exact_binding_equal_growth_shrink_and_fork() -> None:
    old = checkpoint()
    new = checkpoint(**{"5": 2, "34": 1, "35": leaf_hash(b"a"), "38": old.digest})
    proof = ConsistencyProof.from_bytes(
        encode_deterministic(
            {
                1: 8,
                2: 1,
                32: LOG,
                33: SCOPE,
                34: old.digest,
                35: new.digest,
                36: 0,
                37: 1,
                38: EMPTY_TREE_ROOT,
                39: leaf_hash(b"a"),
                40: [],
                41: 1,
            }
        )
    )
    proof.verify(old, new)
    with pytest.raises(FederationValidationError):
        proof.verify(new, old)
    bad = ConsistencyProof.from_bytes(
        encode_deterministic(
            {
                1: 8,
                2: 1,
                32: LOG,
                33: SCOPE,
                34: old.digest,
                35: new.digest,
                36: 0,
                37: 1,
                38: EMPTY_TREE_ROOT,
                39: b"X" * 32,
                40: [],
                41: 1,
            }
        )
    )
    with pytest.raises(FederationValidationError):
        bad.verify(old, new)


def test_signed_checkpoint_reuses_exact_task2_kid_purpose_lifecycle_and_authority() -> None:
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    payload = checkpoint().canonical_bytes()
    message = sign1(payload, b"log-key", private)
    authority = FederationAuthority(
        b"log-key", private.public_key(), LOG, KeyPurpose.TRANSPARENCY_LOG, KeyLifecycle.ACTIVE, 1, 1, 0, 100, False
    )
    assert (
        verify_federation_sign1(
            message, authority, ObjectType.TransparencyCheckpoint, 0, expected_key_purpose=KeyPurpose.TRANSPARENCY_LOG
        ).digest
        == checkpoint().digest
    )
    with pytest.raises(FederationValidationError, match="purpose"):
        verify_federation_sign1(
            message,
            replace(authority, purpose=KeyPurpose.WITNESS),
            ObjectType.TransparencyCheckpoint,
            0,
            expected_key_purpose=KeyPurpose.TRANSPARENCY_LOG,
        )


def test_checkpoint_requires_exact_previous_checkpoint_digest() -> None:
    old = checkpoint()
    candidate = checkpoint(**{"5": 2, "34": 1, "35": leaf_hash(b"a"), "38": b"X" * 32})
    proof = ConsistencyProof.from_bytes(
        encode_deterministic(
            {
                1: 8,
                2: 1,
                32: LOG,
                33: SCOPE,
                34: old.digest,
                35: candidate.digest,
                36: 0,
                37: 1,
                38: EMPTY_TREE_ROOT,
                39: leaf_hash(b"a"),
                40: [],
                41: 1,
            }
        )
    )
    with pytest.raises(FederationValidationError, match="previous"):
        TransparencyVerifier(old).accept_checkpoint(candidate, now=0, consistency=proof)


def test_checkpoint_verifier_retains_all_split_view_branches() -> None:
    base = checkpoint(**{"34": 1, "35": leaf_hash(b"a"), "38": b"G" * 32})
    verifier = TransparencyVerifier(base)
    first = checkpoint(**{"34": 1, "35": b"X" * 32, "38": b"G" * 32})
    second = checkpoint(**{"34": 1, "35": b"Y" * 32, "38": b"G" * 32})
    assert verifier.accept_checkpoint(first, now=0) == "QUARANTINE"
    assert verifier.accept_checkpoint(second, now=0) == "QUARANTINE"
    assert {item.digest for item in verifier.conflicts} == {base.digest, first.digest, second.digest}
