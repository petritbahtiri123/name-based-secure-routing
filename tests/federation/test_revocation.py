from __future__ import annotations

import pytest

from nbsr.federation import EnforcementMode, FederationValidationError, ReasonCode
from nbsr.federation.revocation import _AUTHENTICATED_THRESHOLD_TOKEN, DependencyIndex, SemanticThresholdEvidence, TypedRevocationRecord
from nbsr.protocol.cbor import encode_deterministic


OPERATOR = b"O" * 32
SCOPE = {1: "service.example", 2: b"S" * 32, 3: None, 4: OPERATOR, 5: b"D" * 32, 6: "eu", 7: [[443, 443]], 8: [6], 9: [1], 10: False, 11: 0}


def threshold(record: TypedRevocationRecord, mode: int) -> SemanticThresholdEvidence:
    numerator, denominator = {1: (1, 1), 2: (3, 5), 3: (2, 5)}[mode]
    return SemanticThresholdEvidence._from_authenticated_validator(
        record.digest,
        mode,
        numerator,
        denominator,
        operator_id=OPERATOR if mode == 1 else None,
        authority_id=b"controller" if mode == 1 else None,
        token=_AUTHENTICATED_THRESHOLD_TOKEN,
    )


def revocation(**changes: object) -> TypedRevocationRecord:
    payload = {
        1: 13,
        2: 1,
        3: {1: 14, 2: b"controller", 3: b"rev", 4: OPERATOR},
        4: 1,
        5: 1,
        6: 100,
        7: 200,
        32: {1: 4, 2: b"target", 3: b"T" * 32},
        33: SCOPE,
        34: ReasonCode.ERR_REVOKED.value,
        35: False,
        36: EnforcementMode.DENY_NEW_USE.value,
        37: 1,
        38: None,
        39: {1: b"L" * 32, 2: b"C" * 32, 3: 1, 4: b"I" * 32},
    }
    payload.update({int(k): v for k, v in changes.items()})
    return TypedRevocationRecord.from_bytes(encode_deterministic(payload))


@pytest.mark.parametrize("target_type", list(range(1, 19)))
def test_all_approved_target_classes_bind_exact_type_id_and_digest(target_type: int) -> None:
    parsed = revocation(**{"32": {1: target_type, 2: b"target", 3: bytes([target_type]) * 32}})
    assert parsed.target == (target_type, b"target", bytes([target_type]) * 32)


def test_revocation_modes_validate_semantic_authority_and_reject_raw_packaging() -> None:
    controlled = revocation()
    controlled.authorize(threshold(controlled, 1))
    normal = revocation(**{"3": {1: 4, 2: b"normal", 3: b"rev", 4: OPERATOR}, "37": 2})
    normal.authorize(threshold(normal, 2))
    emergency = revocation(**{"3": {1: 4, 2: b"emergency", 3: b"rev", 4: OPERATOR}, "35": False, "36": 1, "37": 3, "7": 400})
    emergency.authorize(threshold(emergency, 3))
    with pytest.raises(FederationValidationError, match="packaging"):
        SemanticThresholdEvidence.from_transport(b"raw")
    with pytest.raises(FederationValidationError):
        controlled.authorize(threshold(normal, 2))


def test_terminal_compromise_has_no_expiry_and_cannot_resurrect() -> None:
    terminal = revocation(
        **{"32": {1: 2, 2: b"key", 3: b"K" * 32}, "34": ReasonCode.ERR_KEY_LIFECYCLE.value, "35": True, "36": 4, "7": 253402300799}
    )
    assert terminal.terminal
    with pytest.raises(FederationValidationError, match="terminal"):
        terminal.replace_with(revocation(**{"5": 2, "8": terminal.digest, "32": {1: 2, 2: b"key", 3: b"K" * 32}}))
    with pytest.raises(FederationValidationError):
        revocation(**{"35": True, "7": 200})


def test_temporary_suspension_and_restriction_may_expire_and_reference_replacement() -> None:
    temporary = revocation(**{"38": {1: 4, 2: b"replacement", 3: b"N" * 32}})
    assert temporary.expires_at == 200 and not temporary.terminal


def test_selective_dependency_invalidation_is_directional_and_emergency_overrides_overlap() -> None:
    index = DependencyIndex()
    index.add(b"parent", {b"root"})
    index.add(b"child", {b"parent"})
    index.add(b"service-a", {b"child"})
    index.add(b"service-b", {b"other"})
    index.add(b"endpoint", {b"operator"})
    assert index.invalidate({b"parent"}) == frozenset({b"parent", b"child", b"service-a"})
    assert index.invalidate({b"child"}) == frozenset({b"child", b"service-a"})
    assert b"service-b" not in index.invalidate({b"child"})
    assert b"operator" not in index.invalidate({b"endpoint"})
    assert index.invalidate({b"unrelated-trust"}) == frozenset({b"unrelated-trust"})
    assert index.authority_reduction({b"child"}) == frozenset({b"child", b"service-a"})
    assert index.enforcement({b"compromise"}, emergency=True) == EnforcementMode.TERMINATE_ACTIVE_USE


def test_invalid_mixed_modes_issuer_scope_and_generation_are_rejected() -> None:
    with pytest.raises(FederationValidationError):
        wrong = revocation(**{"3": {1: 14, 2: b"different", 3: b"rev", 4: OPERATOR}})
        wrong.authorize(threshold(wrong, 1))
    with pytest.raises(FederationValidationError):
        revocation(**{"37": 3, "35": False, "7": 401})
    current = revocation()
    with pytest.raises(FederationValidationError):
        current.replace_with(revocation(**{"5": 3, "8": current.digest}))


def test_replacement_reference_is_optional_and_emergency_is_bounded_nonterminal_deny_only() -> None:
    payload = dict(revocation()._payload)
    del payload[38]
    assert TypedRevocationRecord.from_bytes(encode_deterministic(payload))._payload.get(38) is None
    emergency = revocation(**{"35": False, "36": EnforcementMode.DENY_NEW_USE.value, "37": 3, "7": 400})
    emergency.authorize(threshold(emergency, 3))
    with pytest.raises(FederationValidationError):
        revocation(**{"35": False, "36": 1, "37": 3, "7": 401})
