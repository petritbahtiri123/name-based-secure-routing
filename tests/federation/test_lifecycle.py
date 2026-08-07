from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import FederationAuthority, FederationValidationError, KeyLifecycle, KeyPurpose, OperatorLifecycle, RecoveryStage
from nbsr.federation.lifecycle import (
    _AUTHENTICATED_RECOVERY_TOKEN,
    AppealDecisionRecord,
    ConflictEvidence,
    ConflictResolutionRecord,
    OperatorLifecycleRecord,
    RecoveryTransitionRecord,
    SemanticRecoveryEvidence,
)
from nbsr.protocol.cbor import encode_deterministic


OPERATOR = b"O" * 32
SCOPE = {1: "service.example", 2: b"S" * 32, 3: None, 4: OPERATOR, 5: b"D" * 32, 6: "eu", 7: [[443, 443]], 8: [6], 9: [1], 10: False, 11: 0}
TRANS = {1: b"L" * 32, 2: b"C" * 32, 3: 1, 4: b"I" * 32}


def authority(kid: bytes, purpose: KeyPurpose, seed: int) -> FederationAuthority:
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return FederationAuthority(kid, private.public_key(), bytes([seed]) * 32, purpose, KeyLifecycle.ACTIVE, 1, 1, 0, 1000, False)


def recovery_evidence(record: RecoveryTransitionRecord) -> SemanticRecoveryEvidence:
    return SemanticRecoveryEvidence._from_authenticated_validator(
        record.digest,
        (authority(b"recovery", KeyPurpose.RECOVERY, 1), authority(b"recovery-2", KeyPurpose.RECOVERY, 2)),
        (authority(b"registry", KeyPurpose.REGISTRY_SIGNING, 3),),
        (authority(b"witness-1", KeyPurpose.WITNESS, 4), authority(b"witness-2", KeyPurpose.WITNESS, 5)),
        token=_AUTHENTICATED_RECOVERY_TOKEN,
    )


def lifecycle(state: OperatorLifecycle, **changes: object) -> OperatorLifecycleRecord:
    payload = {
        1: 15,
        2: 1,
        3: {1: 3, 2: b"registry", 3: b"gov", 4: OPERATOR},
        4: 1,
        5: 1,
        6: 100,
        7: 200,
        32: OPERATOR,
        33: state.value,
        35: SCOPE,
        36: 0,
        37: [],
        38: TRANS,
    }
    if state is OperatorLifecycle.RECOVERY:
        payload[34] = RecoveryStage.RECOVERY_PENDING.value
    payload.update({int(k): v for k, v in changes.items()})
    return OperatorLifecycleRecord.from_bytes(encode_deterministic(payload))


ALLOWED = {
    (1, 2),
    (1, 11),
    (2, 3),
    (2, 11),
    (3, 4),
    (3, 5),
    (3, 11),
    (4, 5),
    (4, 6),
    (4, 7),
    (4, 8),
    (4, 9),
    (4, 10),
    (5, 6),
    (5, 7),
    (5, 8),
    (5, 9),
    (5, 10),
    (6, 5),
    (6, 7),
    (6, 8),
    (6, 9),
    (6, 10),
    (7, 8),
    (7, 9),
    (7, 10),
    (8, 5),
    (8, 9),
    (8, 10),
}


@pytest.mark.parametrize("old,new", [(a, b) for a in range(1, 12) for b in range(1, 12) if a != b])
def test_every_allowed_and_forbidden_operator_transition(old: int, new: int) -> None:
    current = lifecycle(OperatorLifecycle(old))
    changes = {"5": 2, "8": current.digest, "33": new}
    if new == OperatorLifecycle.RECOVERY:
        changes["34"] = RecoveryStage.RECOVERY_PENDING.value
    candidate = lifecycle(OperatorLifecycle(new), **changes)
    if (old, new) in ALLOWED:
        assert candidate.require_newer_than(current)
    else:
        with pytest.raises(FederationValidationError, match="forbidden"):
            candidate.require_newer_than(current)


def test_recovery_stage_exists_only_in_recovery_and_evidence_is_staged() -> None:
    with pytest.raises(FederationValidationError):
        lifecycle(OperatorLifecycle.ACTIVE, **{"34": 1})
    with pytest.raises(FederationValidationError):
        lifecycle(OperatorLifecycle.RECOVERY, **{"34": 2, "37": []})
    assert lifecycle(OperatorLifecycle.RECOVERY, **{"34": 3, "37": [b"E" * 32]}).recovery_stage is RecoveryStage.REENTRY_RESTRICTED
    payload = dict(lifecycle(OperatorLifecycle.ACTIVE)._payload)
    del payload[37]
    assert OperatorLifecycleRecord.from_bytes(encode_deterministic(payload)).recovery_stage is None


def recovery(**changes: object) -> RecoveryTransitionRecord:
    target = {1: 2, 2: b"old-key", 3: b"K" * 32}
    replacement = {1: 2, 2: b"new-key", 3: b"N" * 32}
    approvals = [{1: 2, 2: 2, 3: b"recovery", 4: b"A" * 32, 5: b"P" * 32}, {1: 3, 2: 2, 3: b"registry", 4: b"B" * 32, 5: b"P" * 32}]
    payload = {
        1: 16,
        2: 1,
        3: {1: 2, 2: b"recovery", 3: b"recovery", 4: OPERATOR},
        9: 100,
        32: b"transition",
        33: OPERATOR,
        34: [target],
        35: 1,
        36: 2,
        37: [target],
        38: [replacement],
        39: b"Q" * 32,
        40: False,
        41: SCOPE,
        42: approvals,
        43: TRANS,
        44: 1,
        45: SCOPE,
    }
    payload.update({int(k): v for k, v in changes.items()})
    return RecoveryTransitionRecord.from_bytes(encode_deterministic(payload))


def test_recovery_binds_lineage_replacements_thresholds_evidence_and_no_scope_expansion() -> None:
    parsed = recovery()
    parsed.validate_semantic_thresholds(recovery_evidence(parsed), compromised_kids=set())
    assert parsed.continuity_preserving
    assert recovery(**{"39": None, "40": True}).lineage_breaking
    with pytest.raises(FederationValidationError):
        parsed.validate_semantic_thresholds(recovery_evidence(parsed), compromised_kids={b"recovery"})
    wider = dict(SCOPE)
    wider[7] = [[1, 65535]]
    with pytest.raises(FederationValidationError):
        recovery(**{"45": wider})
    with pytest.raises(FederationValidationError, match="packaging"):
        RecoveryTransitionRecord.from_threshold_transport(b"raw")


def conflict() -> ConflictEvidence:
    return ConflictEvidence.from_bytes(
        encode_deterministic(
            {
                1: 14,
                2: 1,
                32: b"conflict",
                33: b"evidence",
                34: 1,
                35: SCOPE,
                36: 5,
                37: [b"A" * 32, b"B" * 32],
                38: [[1, 1], [1, 1]],
                39: [b"C" * 32, b"D" * 32],
                40: [b"P" * 32, b"Q" * 32],
                41: 100,
                42: True,
                43: 1,
            }
        )
    )


def test_conflict_retains_both_branches_quarantines_and_has_no_timestamp_winner() -> None:
    parsed = conflict()
    assert parsed.branches == (b"A" * 32, b"B" * 32)
    assert parsed.quarantine
    with pytest.raises(FederationValidationError, match="immutable"):
        parsed.choose_winner("latest")


def test_resolution_preserves_losing_evidence_and_appeal_never_restores_authority() -> None:
    resolution = ConflictResolutionRecord.from_bytes(
        encode_deterministic(
            {
                1: 17,
                2: 1,
                3: {1: 11, 2: b"panel", 3: b"gov", 4: None},
                9: 100,
                32: b"decision",
                33: b"conflict",
                34: b"E" * 32,
                35: SCOPE,
                36: 2,
                37: [{1: 5, 2: b"loser", 3: b"A" * 32}],
                38: [{1: 5, 2: b"winner", 3: b"B" * 32}],
                39: 1,
                40: 2,
                41: [b"R" * 32],
                42: None,
                43: 200,
                44: [],
                45: None,
                46: TRANS,
            }
        )
    )
    assert resolution.preserves_losing_evidence(conflict())
    appeal = AppealDecisionRecord.from_bytes(
        encode_deterministic(
            {
                1: 18,
                2: 1,
                3: {1: 12, 2: b"appeal", 3: b"gov", 4: None},
                9: 110,
                32: b"appeal-decision",
                33: b"appeal",
                34: resolution.digest,
                35: b"E" * 32,
                36: 1,
                37: SCOPE,
                38: 1,
                39: 1,
                40: [],
                41: [],
                42: [{1: 5, 2: b"winner", 3: b"B" * 32}],
                43: [],
                44: [],
                45: None,
                46: TRANS,
            }
        )
    )
    assert not appeal.restores_authority
    assert not appeal.resurrects_terminal_authority
    assert appeal.previous_decision_digest is None


def test_conflict_arrays_and_governance_required_fields_are_strict() -> None:
    malformed = dict(conflict()._payload)
    malformed[38] = [[1]]
    with pytest.raises(FederationValidationError):
        ConflictEvidence.from_bytes(encode_deterministic(malformed))


def test_recovery_requires_two_of_three_distinct_authenticated_recovery_approvals() -> None:
    with pytest.raises(FederationValidationError):
        SemanticRecoveryEvidence._from_authenticated_validator(
            recovery().digest,
            (authority(b"recovery", KeyPurpose.RECOVERY, 1),),
            (authority(b"registry", KeyPurpose.REGISTRY_SIGNING, 3),),
            (authority(b"witness-1", KeyPurpose.WITNESS, 4), authority(b"witness-2", KeyPurpose.WITNESS, 5)),
            token=_AUTHENTICATED_RECOVERY_TOKEN,
        )
