from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import FederationAuthority, FederationValidationError, KeyLifecycle, KeyPurpose, authenticate_witness_sign1
from nbsr.federation.transparency import (
    EMPTY_TREE_ROOT,
    AuthenticatedWitness,
    TransparencyCheckpoint,
    WitnessStatement,
    verify_witness_threshold,
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


def checkpoint() -> TransparencyCheckpoint:
    return TransparencyCheckpoint.from_bytes(
        encode_deterministic(
            {
                1: 6,
                2: 1,
                3: {1: 5, 2: LOG, 3: b"log", 4: LOG},
                4: 1,
                5: 1,
                32: LOG,
                33: SCOPE,
                34: 0,
                35: EMPTY_TREE_ROOT,
                36: 0,
                37: b"log",
                38: None,
                39: None,
            }
        )
    )


def witness(identity: int, *, result: int = 1) -> WitnessStatement:
    cp = checkpoint()
    return WitnessStatement.from_bytes(
        encode_deterministic(
            {
                1: 9,
                2: 1,
                32: bytes([identity]) * 32,
                33: LOG,
                34: SCOPE,
                35: cp.digest,
                36: 0,
                37: EMPTY_TREE_ROOT,
                38: 10,
                39: result,
                40: bytes([identity]) * 16,
                41: bytes([identity]),
                42: 100,
            }
        )
    )


def authenticated(identity: int, organization: str, *, result: int = 1) -> AuthenticatedWitness:
    private = Ed25519PrivateKey.from_private_bytes(bytes([identity]) * 32)
    statement = witness(identity, result=result)
    authority = FederationAuthority(
        bytes([identity]), private.public_key(), bytes([identity]) * 32, KeyPurpose.WITNESS, KeyLifecycle.ACTIVE, 1, 1, 0, 100, False
    )
    return authenticate_witness_sign1(sign1(statement.canonical_bytes(), bytes([identity]), private), authority, organization, 50)


def threshold(evidence: list[AuthenticatedWitness], required: int) -> int:
    contexts = {item.authority_identity: item.statement._payload[40] for item in evidence}
    configured = {item.authority_identity: (item.organization, item.signer_kid) for item in evidence}
    for identity in range(1, (3 if required == 2 else 5) + 1):
        configured.setdefault(bytes([identity]) * 32, (f"unused-{identity}", bytes([identity])))
    return verify_witness_threshold(evidence, checkpoint(), required, now=50, replay_contexts=contexts, configured_witnesses=configured)


def test_witness_statement_exact_checkpoint_replay_validity_and_result() -> None:
    statement = witness(1)
    statement.verify_observation(checkpoint(), now=50, expected_replay_context=b"\x01" * 16, expected_kid=b"\x01")
    with pytest.raises(FederationValidationError):
        statement.verify_observation(checkpoint(), now=101, expected_replay_context=b"\x01" * 16, expected_kid=b"\x01")
    with pytest.raises(FederationValidationError):
        witness(1, result=2).verify_observation(checkpoint(), now=50, expected_replay_context=b"\x01" * 16, expected_kid=b"\x01")


def test_ordinary_threshold_is_two_of_three_independent_organizations() -> None:
    with pytest.raises(FederationValidationError, match="threshold"):
        threshold([authenticated(1, "one")], 2)
    assert threshold([authenticated(1, "one"), authenticated(2, "two")], 2) == 2
    with pytest.raises(FederationValidationError, match="organization"):
        threshold([authenticated(1, "same"), authenticated(2, "same")], 2)


def test_high_risk_threshold_is_three_of_five_and_duplicates_do_not_count() -> None:
    statements = [authenticated(i, f"org-{i}") for i in range(1, 4)]
    assert threshold(statements, 3) == 3
    with pytest.raises(FederationValidationError, match="duplicate"):
        threshold([statements[0], statements[0], statements[1]], 3)


def test_conflicting_authenticated_witnesses_quarantine_without_winner() -> None:
    with pytest.raises(FederationValidationError, match="conflicting"):
        threshold([authenticated(1, "one"), authenticated(2, "two", result=2)], 2)


def test_threshold_rejects_weak_policy_expired_replayed_unconfigured_or_misattributed_witness() -> None:
    cp = checkpoint()
    evidence = [authenticated(1, "one"), authenticated(2, "two")]
    configured = {
        b"\x01" * 32: ("one", b"\x01"),
        b"\x02" * 32: ("two", b"\x02"),
        b"\x03" * 32: ("three", b"\x03"),
    }
    contexts = {b"\x01" * 32: b"\x01" * 16, b"\x02" * 32: b"\x02" * 16}
    for required in (0, 1):
        with pytest.raises(FederationValidationError, match="threshold"):
            verify_witness_threshold(evidence, cp, required, now=50, replay_contexts=contexts, configured_witnesses=configured)
    with pytest.raises(FederationValidationError):
        verify_witness_threshold(evidence, cp, 2, now=101, replay_contexts=contexts, configured_witnesses=configured)
    with pytest.raises(FederationValidationError):
        verify_witness_threshold(
            evidence, cp, 2, now=50, replay_contexts={**contexts, b"\x01" * 32: b"Z" * 16}, configured_witnesses=configured
        )
    with pytest.raises(FederationValidationError):
        verify_witness_threshold(
            evidence,
            cp,
            2,
            now=50,
            replay_contexts=contexts,
            configured_witnesses={
                b"\x01" * 32: ("one", b"\x01"),
                b"\x03" * 32: ("three", b"\x03"),
                b"\x04" * 32: ("four", b"\x04"),
            },
        )
    with pytest.raises(FederationValidationError):
        AuthenticatedWitness(witness(1), b"Z" * 32, "one", b"\x01")
