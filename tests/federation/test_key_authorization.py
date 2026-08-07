from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nbsr.federation.fields import (
    FederationValidationError,
    KeyAuthorizationRecord,
    OperatorRegistryRecord,
    RecoveryTransitionBinding,
)
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json"


def _fixtures(object_type: str) -> list[dict[str, object]]:
    package = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return [fixture for fixture in package["fixtures"] if fixture["object_type"] == object_type]


@pytest.mark.parametrize("fixture", _fixtures("OperatorRegistryRecord"), ids=lambda fixture: str(fixture["name"]))
def test_operator_registry_literal_payloads_are_byte_exact(fixture: dict[str, object]) -> None:
    raw = bytes.fromhex(str(fixture["canonical_cbor_hex"]))
    assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
    if fixture["expected_outcome"] == "ACCEPT":
        record = OperatorRegistryRecord.from_bytes(raw, context=fixture["validation_context"])
        assert record.canonical_bytes() == raw
        assert record.digest == hashlib.sha256(raw).digest()
    else:
        with pytest.raises(FederationValidationError):
            OperatorRegistryRecord.from_bytes(raw, context=fixture["validation_context"])


@pytest.mark.parametrize("fixture", _fixtures("KeyAuthorizationRecord"), ids=lambda fixture: str(fixture["name"]))
def test_key_authorization_literal_payloads_are_byte_exact(fixture: dict[str, object]) -> None:
    raw = bytes.fromhex(str(fixture["canonical_cbor_hex"]))
    assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
    if fixture["expected_outcome"] == "ACCEPT":
        record = KeyAuthorizationRecord.from_bytes(raw, context=fixture["validation_context"])
        assert record.canonical_bytes() == raw
        assert record.digest == hashlib.sha256(raw).digest()
    else:
        with pytest.raises(FederationValidationError):
            KeyAuthorizationRecord.from_bytes(raw, context=fixture["validation_context"])


def _accepted(name: str, object_type: str = "KeyAuthorizationRecord") -> bytes:
    fixture = next(item for item in _fixtures(object_type) if item["name"] == name)
    return bytes.fromhex(str(fixture["canonical_cbor_hex"]))


def _mutate(raw: bytes, key: int, value: object) -> bytes:
    payload = decode_deterministic(raw)
    payload[key] = value
    return encode_deterministic(payload)


def test_key_authorization_enforces_validity_and_exact_purpose() -> None:
    raw = _accepted("valid-root-authorized-genesis")
    record = KeyAuthorizationRecord.from_bytes(raw)
    record.require_valid_at(record.not_before)
    with pytest.raises(FederationValidationError):
        record.require_valid_at(record.expires_at + 1)
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(_mutate(raw, 35, 999))


def test_key_authorization_requires_exact_predecessor_and_immutable_identity_and_purpose() -> None:
    current = KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"))
    update = decode_deterministic(current.canonical_bytes())
    update[5] = 2
    update[8] = current.digest
    candidate = KeyAuthorizationRecord.from_bytes(encode_deterministic(update))
    candidate.require_newer_than(current)
    for key, value in ((8, b"x" * 32), (32, b"x" * 32), (35, 4)):
        broken = dict(update)
        broken[key] = value
        with pytest.raises(FederationValidationError):
            KeyAuthorizationRecord.from_bytes(encode_deterministic(broken)).require_newer_than(current)


def test_key_replacement_is_forbidden_within_generation_and_allowed_by_bound_recovery() -> None:
    current = KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"))
    same_generation = decode_deterministic(current.canonical_bytes())
    same_generation.update({5: 2, 8: current.digest, 33: b"replacement", 34: b"R" * 32})
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(same_generation)).require_newer_than(current)

    current = KeyAuthorizationRecord.from_bytes(_accepted("valid-rotation-update"))
    recovery = KeyAuthorizationRecord.from_bytes(
        _accepted("valid-recovery-authorized-new-generation"), context={"recovery_transition": "52" * 32}
    )
    binding = RecoveryTransitionBinding(
        digest=recovery.recovery_transition_digest,
        operator_id=recovery.operator_id,
        key_purpose=recovery.key_purpose,
        old_generation=current.generation,
        new_generation=recovery.generation,
        accepted=True,
        object_type=2,
        scope=None,
    )
    recovery.require_newer_than(current, recovery_transition=binding)


def test_terminal_key_id_cannot_be_reused() -> None:
    record = KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"))
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(record.canonical_bytes(), context={"terminal_key_ids": [record.key_id.hex()]})


@pytest.mark.parametrize("state", ["COMPROMISED", "EXPIRED", "RETIRED", "SUPERSEDED", "REVOKED"])
def test_ineligible_signer_lifecycle_is_rejected(state: str) -> None:
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"), context={"signer_lifecycle": state})


def test_operator_registry_requires_contextual_recovery_stage_and_explicit_revocation_reference() -> None:
    genesis = _accepted("valid-genesis", "OperatorRegistryRecord")
    payload = decode_deterministic(genesis)
    payload[36] = 8
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(payload))
    payload[39] = 1
    OperatorRegistryRecord.from_bytes(encode_deterministic(payload))


def test_unknown_direct_field_and_critical_extension_are_rejected_but_noncritical_preserved() -> None:
    raw = _accepted("valid-genesis", "OperatorRegistryRecord")
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(_mutate(raw, 127, b"unknown"))
    noncritical = _mutate(raw, 31, {1000: {1: 1, 2: False, 3: b"opaque"}})
    assert OperatorRegistryRecord.from_bytes(noncritical).canonical_bytes() == noncritical
    critical = _mutate(raw, 31, {1000: {1: 1, 2: True, 3: b"opaque"}})
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(critical)


def test_payload_size_bound_is_enforced_before_decode() -> None:
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(b"x" * 32_769)


def test_operator_and_key_lifecycle_transitions_are_closed() -> None:
    operator = OperatorRegistryRecord.from_bytes(_accepted("valid-genesis", "OperatorRegistryRecord"))
    operator_update = decode_deterministic(_accepted("valid-same-generation-update", "OperatorRegistryRecord"))
    operator_update[36] = 5
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(operator_update)).require_newer_than(operator)

    key = KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"))
    key_update = decode_deterministic(_accepted("valid-rotation-update"))
    key_update[36] = 4
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(key_update)).require_newer_than(key)


def test_revoked_or_terminal_state_requires_explicit_revocation_reference() -> None:
    operator = decode_deterministic(_accepted("valid-genesis", "OperatorRegistryRecord"))
    operator[36] = 10
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(operator))

    key = decode_deterministic(_accepted("valid-root-authorized-genesis"))
    key[36] = 5
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(key))


def test_delegation_scope_is_closed_canonical_and_cannot_widen() -> None:
    raw = _accepted("valid-genesis", "OperatorRegistryRecord")
    payload = decode_deterministic(raw)
    malformed = dict(payload)
    malformed[35] = {1: "example.test"}
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(malformed))

    malformed[35] = dict(payload[35])
    malformed[35][7] = [[443, 443], [80, 80]]
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(malformed))

    current = OperatorRegistryRecord.from_bytes(raw)
    update = decode_deterministic(_accepted("valid-same-generation-update", "OperatorRegistryRecord"))
    update[35] = dict(update[35])
    update[35][10] = True
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(update)).require_newer_than(current)


def test_operator_recovery_binds_operator_type_scope_generations_and_evidence() -> None:
    current_payload = decode_deterministic(_accepted("valid-recovery-new-generation", "OperatorRegistryRecord"))
    current_payload.update({4: 1, 5: 4})
    current_payload.pop(39)
    current_payload[36] = 5
    current_payload[8] = b"P" * 32
    current = OperatorRegistryRecord.from_bytes(encode_deterministic(current_payload))
    candidate_payload = decode_deterministic(_accepted("valid-recovery-new-generation", "OperatorRegistryRecord"))
    candidate_payload[8] = current.digest
    candidate = OperatorRegistryRecord.from_bytes(encode_deterministic(candidate_payload), context={"recovery_transition": "52" * 32})
    valid = RecoveryTransitionBinding(
        digest=b"R" * 32,
        operator_id=candidate.operator_id,
        key_purpose=0,
        old_generation=1,
        new_generation=2,
        accepted=True,
        object_type=1,
        scope=candidate_payload[35],
    )
    candidate.require_newer_than(current, recovery_transition=valid)
    for changes in (
        {"operator_id": b"x" * 32},
        {"object_type": 2},
        {"old_generation": 0},
        {"new_generation": 3},
        {"digest": None},
        {"scope": {1: None}},
    ):
        values = {name: getattr(valid, name) for name in valid.__dataclass_fields__}
        values.update(changes)
        with pytest.raises(FederationValidationError):
            candidate.require_newer_than(current, recovery_transition=RecoveryTransitionBinding(**values))


def test_key_recovery_requires_new_key_id_and_public_key() -> None:
    current = KeyAuthorizationRecord.from_bytes(_accepted("valid-rotation-update"))
    raw = decode_deterministic(_accepted("valid-recovery-authorized-new-generation"))
    for key in (33, 34):
        mutation = dict(raw)
        mutation[key] = current._payload[key]
        candidate = KeyAuthorizationRecord.from_bytes(encode_deterministic(mutation), context={"recovery_transition": "52" * 32})
        binding = RecoveryTransitionBinding(
            candidate.recovery_transition_digest,
            candidate.operator_id,
            candidate.key_purpose,
            1,
            2,
            True,
            object_type=2,
            scope=None,
        )
        with pytest.raises(FederationValidationError):
            candidate.require_newer_than(current, recovery_transition=binding)


def test_any_single_approved_key_purpose_is_accepted_and_remains_immutable() -> None:
    raw = decode_deterministic(_accepted("valid-root-authorized-genesis"))
    raw[35] = 9
    record = KeyAuthorizationRecord.from_bytes(encode_deterministic(raw), context={"expected_key_purpose": 9})
    assert record.key_purpose == 9


def test_higher_generation_requires_recovery_context_before_acceptance() -> None:
    for name, object_type, record_type in (
        ("valid-recovery-new-generation", "OperatorRegistryRecord", OperatorRegistryRecord),
        ("valid-recovery-authorized-new-generation", "KeyAuthorizationRecord", KeyAuthorizationRecord),
    ):
        with pytest.raises(FederationValidationError):
            record_type.from_bytes(_accepted(name, object_type))


def test_identity_root_and_normal_authorizer_classes_are_exact() -> None:
    operator = decode_deterministic(_accepted("valid-genesis", "OperatorRegistryRecord"))
    operator[33] = dict(operator[33])
    operator[33][1] = 10
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(operator))

    key = decode_deterministic(_accepted("valid-root-authorized-genesis"))
    key[37] = dict(key[37])
    key[37][1] = 10
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(key))


def test_organization_mode_matches_selected_representation() -> None:
    operator = decode_deterministic(_accepted("valid-genesis", "OperatorRegistryRecord"))
    operator[34] = {1: 2, 2: "leak.example", 3: None}
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(operator))


def test_context_validation_rejects_before_not_before() -> None:
    raw = _accepted("valid-root-authorized-genesis")
    record = decode_deterministic(raw)
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(raw, context={"validation_time": record[6] - 1})


@pytest.mark.parametrize(
    "name_scope",
    ["EXAMPLE.TEST", "täst.example", "e\u0301xample.test", "bad_name.test", "-bad.test", "bad-.test", "xn--.test"],
)
def test_scope_name_requires_exact_lowercase_nfc_alabel(name_scope: str) -> None:
    operator = decode_deterministic(_accepted("valid-genesis", "OperatorRegistryRecord"))
    operator[35] = dict(operator[35])
    operator[35][1] = name_scope
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(operator))


def test_operator_and_key_authority_ids_bind_exact_operator_id() -> None:
    operator = decode_deterministic(_accepted("valid-genesis", "OperatorRegistryRecord"))
    operator[33] = dict(operator[33])
    operator[33][2] = b"unrelated"
    with pytest.raises(FederationValidationError):
        OperatorRegistryRecord.from_bytes(encode_deterministic(operator))

    key = decode_deterministic(_accepted("valid-root-authorized-genesis"))
    key[37] = dict(key[37])
    key[37][2] = b"unrelated"
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(key))


def test_post_recovery_same_generation_updates_use_normal_authority_without_recovery_evidence() -> None:
    key_recovery_payload = decode_deterministic(_accepted("valid-recovery-authorized-new-generation"))
    key_recovery = KeyAuthorizationRecord.from_bytes(encode_deterministic(key_recovery_payload), context={"recovery_transition": "52" * 32})
    key_update = dict(key_recovery_payload)
    key_update.update(
        {
            3: {1: 1, 2: key_recovery.operator_id, 3: b"root-kid", 4: key_recovery.operator_id},
            5: 2,
            8: key_recovery.digest,
            36: 2,
            37: {1: 1, 2: key_recovery.operator_id, 3: b"root-kid", 4: key_recovery.operator_id},
        }
    )
    key_update.pop(40)
    key_candidate = KeyAuthorizationRecord.from_bytes(encode_deterministic(key_update))
    key_candidate.require_newer_than(key_recovery)

    operator_recovery_payload = decode_deterministic(_accepted("valid-recovery-new-generation", "OperatorRegistryRecord"))
    operator_recovery = OperatorRegistryRecord.from_bytes(
        encode_deterministic(operator_recovery_payload), context={"recovery_transition": "52" * 32}
    )
    operator_update = dict(operator_recovery_payload)
    operator_update.update({5: 2, 8: operator_recovery.digest, 36: 5})
    operator_update.pop(39)
    operator_candidate = OperatorRegistryRecord.from_bytes(encode_deterministic(operator_update))
    operator_candidate.require_newer_than(operator_recovery)


def test_identical_state_is_idempotent_but_conflicting_equal_version_is_rejected() -> None:
    current = KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"))
    assert current.require_newer_than(current) is False
    conflict = decode_deterministic(current.canonical_bytes())
    conflict[7] += 1
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(conflict)).require_newer_than(current)


def test_revocation_state_is_monotonic_and_terminal_ids_accept_bytes() -> None:
    current_payload = decode_deterministic(_accepted("valid-root-authorized-genesis"))
    current_payload[38] = True
    current_payload[39] = {1: 2, 2: b"revoked", 3: None}
    current = KeyAuthorizationRecord.from_bytes(encode_deterministic(current_payload))
    update = decode_deterministic(current.canonical_bytes())
    update.update({5: 2, 8: current.digest, 38: False, 39: None})
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(encode_deterministic(update)).require_newer_than(current)
    with pytest.raises(FederationValidationError):
        KeyAuthorizationRecord.from_bytes(_accepted("valid-root-authorized-genesis"), context={"terminal_key_ids": {current.key_id}})
