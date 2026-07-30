from dataclasses import replace
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.name_registry import SignedServiceRegistry
from nbsr.protocol import (
    Revocation,
    RevocationMode,
    RevocationReason,
    RevocationTargetType,
    ServiceRecord,
    decode_deterministic,
    encode_deterministic,
    encode_model,
    sign1,
)
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


NOW = 1_785_000_000
OWNER_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
OTHER_OWNER_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
REVOCATION_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(2, 34)))
OWNER_KID = b"owner-key"
OTHER_OWNER_KID = b"other-owner"
REVOCATION_KID = b"revocation-key"


def service_record(
    *,
    canonical_name: str = "api.example.com",
    sequence: int = 7,
    owner_key_id: bytes = OWNER_KID,
    not_before: int = NOW,
    not_after: int = NOW + 3_600,
) -> ServiceRecord:
    return ServiceRecord(
        record_version=1,
        canonical_name=canonical_name,
        sequence=sequence,
        owner_key_id=owner_key_id,
        service_id="svc_api",
        destination_operator_id="op_example",
        destination_edge_set=("edge-a",),
        origin_connector_id="connector-a",
        transports=("tcp",),
        ports=(443,),
        route_profiles=("nbsr-quic-1",),
        publication_mode="nbsr-secure-only",
        not_before=not_before,
        not_after=not_after,
        revocation_ref="revset_2026_211",
    )


def registry_with_trust(*, max_records: int = 1_024) -> SignedServiceRegistry:
    return SignedServiceRegistry(
        {OWNER_KID: OWNER_KEY.public_key(), OTHER_OWNER_KID: OTHER_OWNER_KEY.public_key()},
        {REVOCATION_KID: REVOCATION_KEY.public_key()},
        max_records=max_records,
    )


def signed_record(
    record: ServiceRecord,
    *,
    key: Ed25519PrivateKey = OWNER_KEY,
    kid: bytes = OWNER_KID,
) -> bytes:
    return sign1(encode_model(record), kid, key)


def install_record(
    registry: SignedServiceRegistry,
    *,
    sequence: int = 7,
    canonical_name: str = "api.example.com",
    now: int = NOW,
) -> ServiceRecord:
    record = service_record(canonical_name=canonical_name, sequence=sequence)
    return registry.install_record(signed_record(record), now=now)


def revocation(
    record: ServiceRecord,
    *,
    generation: int = 3,
    target_type: RevocationTargetType = RevocationTargetType.SERVICE_RECORD,
    target_id: bytes | None = None,
    target_sequence: int | None = None,
    issuer_key_id: bytes = REVOCATION_KID,
    not_before: int = NOW,
    expires_at: int | None = None,
    reason_code: RevocationReason = RevocationReason.ADMINISTRATIVE,
) -> Revocation:
    return Revocation(
        revocation_version=1,
        revocation_id=generation.to_bytes(16, "big"),
        issuer_key_id=issuer_key_id,
        generation=generation,
        target_type=target_type,
        target_id=target_id if target_id is not None else sha256(record.canonical_name.encode("ascii")).digest(),
        mode=RevocationMode.DENY_NEW_USE,
        not_before=not_before,
        expires_at=expires_at,
        target_sequence=target_sequence,
        reason_code=reason_code,
    )


def signed_revocation(
    statement: Revocation,
    *,
    key: Ed25519PrivateKey = REVOCATION_KEY,
    kid: bytes = REVOCATION_KID,
) -> bytes:
    return sign1(encode_model(statement), kid, key)


def apply_service_revocation(
    registry: SignedServiceRegistry,
    record: ServiceRecord,
    *,
    generation: int = 3,
    target_sequence: int | None = None,
    expires_at: int | None = None,
    now: int = NOW,
) -> Revocation:
    statement = revocation(
        record,
        generation=generation,
        target_sequence=target_sequence,
        expires_at=expires_at,
    )
    return registry.apply_revocation(signed_revocation(statement), now=now)


def test_registry_accepts_valid_owner_bound_record_atomically() -> None:
    registry = registry_with_trust()
    record = service_record(sequence=7)

    accepted = registry.install_record(signed_record(record), now=record.not_before)

    assert accepted == record
    assert registry.resolve(record.canonical_name, now=record.not_before) == record


def test_failed_replacement_preserves_last_accepted_record() -> None:
    registry = registry_with_trust()
    first = install_record(registry, sequence=7)
    stale = signed_record(service_record(sequence=7))

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(stale, now=first.not_before)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE
    assert registry.resolve(first.canonical_name, now=first.not_before) == first


@pytest.mark.parametrize("sequence", (6, 7))
def test_registry_rejects_lower_or_same_sequence(sequence: int) -> None:
    registry = registry_with_trust()
    first = install_record(registry, sequence=7)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(signed_record(service_record(sequence=sequence)), now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE
    assert registry.resolve(first.canonical_name, now=NOW) == first


@pytest.mark.parametrize(
    ("message", "expected_code"),
    (
        (
            signed_record(service_record(), key=OTHER_OWNER_KEY, kid=OWNER_KID),
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ),
        (
            signed_record(service_record(), key=OTHER_OWNER_KEY, kid=OTHER_OWNER_KID),
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ),
        (
            signed_record(service_record(owner_key_id=OTHER_OWNER_KID)),
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ),
    ),
    ids=("wrong-signature", "unknown-owner-for-name", "payload-kid-mismatch"),
)
def test_registry_rejects_untrusted_or_mismatched_record(
    message: bytes,
    expected_code: ErrorCode,
) -> None:
    registry = registry_with_trust()

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(message, now=NOW)

    assert rejected.value.code is expected_code
    assert registry.resolve("api.example.com", now=NOW) is None


def test_registry_rejects_unknown_record_kid() -> None:
    registry = registry_with_trust()
    message = signed_record(
        service_record(owner_key_id=b"unknown-owner"),
        key=OTHER_OWNER_KEY,
        kid=b"unknown-owner",
    )

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(message, now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_UNTRUSTED
    assert registry.resolve("api.example.com", now=NOW) is None


def test_registry_rejects_signed_noncanonical_name_without_mutation() -> None:
    registry = registry_with_trust()
    payload = decode_deterministic(encode_model(service_record()))
    payload[1] = "API.example.com"
    message = sign1(encode_deterministic(payload), OWNER_KID, OWNER_KEY)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(message, now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_NAME_INVALID
    assert registry.resolve("api.example.com", now=NOW) is None


@pytest.mark.parametrize(
    ("record", "now"),
    (
        (service_record(not_before=NOW + 1), NOW),
        (service_record(not_after=NOW + 1), NOW + 1),
    ),
    ids=("not-yet-valid", "expired"),
)
def test_registry_rejects_record_outside_validity_window(
    record: ServiceRecord,
    now: int,
) -> None:
    registry = registry_with_trust()

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(signed_record(record), now=now)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_UNTRUSTED
    assert registry.resolve(record.canonical_name, now=NOW) is None


def test_record_capacity_rejects_new_name_without_mutation() -> None:
    registry = registry_with_trust(max_records=1)
    first = install_record(registry)
    second = service_record(canonical_name="other.example.com", sequence=1)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(signed_record(second), now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_OVER_CAPACITY
    assert registry.resolve(first.canonical_name, now=NOW) == first
    assert registry.resolve(second.canonical_name, now=NOW) is None


def test_replacement_at_capacity_is_allowed_and_updates_atomically() -> None:
    registry = registry_with_trust(max_records=1)
    install_record(registry, sequence=7)
    replacement = service_record(sequence=8)

    accepted = registry.install_record(signed_record(replacement), now=NOW)

    assert accepted == replacement
    assert registry.resolve(replacement.canonical_name, now=NOW) == replacement


def test_sequence_tombstone_survives_record_expiry() -> None:
    registry = registry_with_trust()
    first = service_record(sequence=7, not_after=NOW + 1)
    registry.install_record(signed_record(first), now=NOW)
    stale = replace(first, sequence=6, not_before=NOW + 1, not_after=NOW + 101)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(signed_record(stale), now=NOW + 1)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE


def test_constructor_copies_and_validates_trust_contexts() -> None:
    record_keys = {OWNER_KID: OWNER_KEY.public_key()}
    revocation_keys = {REVOCATION_KID: REVOCATION_KEY.public_key()}
    registry = SignedServiceRegistry(
        record_keys,
        revocation_keys,
    )
    record_keys.clear()
    revocation_keys.clear()

    record = registry.install_record(signed_record(service_record()), now=NOW)
    assert registry.apply_revocation(
        signed_revocation(revocation(record)),
        now=NOW,
    )

    with pytest.raises((TypeError, ValueError)):
        SignedServiceRegistry({b"": OWNER_KEY.public_key()}, {})
    with pytest.raises((TypeError, ValueError)):
        SignedServiceRegistry({OWNER_KID: object()}, {})
    with pytest.raises((TypeError, ValueError)):
        SignedServiceRegistry({}, {b"": REVOCATION_KEY.public_key()})
    with pytest.raises((TypeError, ValueError)):
        SignedServiceRegistry({}, {REVOCATION_KID: object()})
    with pytest.raises((TypeError, ValueError)):
        SignedServiceRegistry({}, {}, max_records=True)
    with pytest.raises((TypeError, ValueError)):
        SignedServiceRegistry({}, {}, max_records=0)


def test_broad_revocation_blocks_higher_record_sequence_while_active() -> None:
    registry = registry_with_trust()
    record = install_record(registry, sequence=7)
    apply_service_revocation(registry, record, generation=3, target_sequence=None)
    install_record(registry, sequence=8)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.resolve(record.canonical_name, now=NOW + 1)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_REVOKED


def test_exact_sequence_revocation_does_not_block_newer_record() -> None:
    registry = registry_with_trust()
    record = install_record(registry, sequence=7)
    apply_service_revocation(registry, record, target_sequence=7)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.resolve(record.canonical_name, now=NOW)
    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_REVOKED

    replacement = install_record(registry, sequence=8)
    assert registry.resolve(record.canonical_name, now=NOW) == replacement


def test_revocation_generation_tombstone_rejects_replay_after_expiry() -> None:
    registry = registry_with_trust()
    record = install_record(registry, sequence=7)
    apply_service_revocation(
        registry,
        record,
        generation=3,
        expires_at=NOW + 2,
    )
    replay = revocation(
        record,
        generation=2,
        not_before=NOW + 2,
        expires_at=NOW + 100,
    )

    assert registry.resolve(record.canonical_name, now=NOW + 2) == record
    with pytest.raises(ProtocolViolation) as rejected:
        registry.apply_revocation(signed_revocation(replay), now=NOW + 2)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE


def test_revocation_target_sequence_must_match_current_record() -> None:
    registry = registry_with_trust()
    record = install_record(registry, sequence=7)
    statement = revocation(record, target_sequence=6)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.apply_revocation(signed_revocation(statement), now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE
    assert registry.resolve(record.canonical_name, now=NOW) == record


@pytest.mark.parametrize(
    "statement",
    (
        revocation(service_record(), target_id=b"x" * 32),
        revocation(
            service_record(),
            target_type=RevocationTargetType.ROUTE,
            target_sequence=None,
        ),
    ),
    ids=("wrong-target-digest", "wrong-target-type"),
)
def test_registry_rejects_wrong_revocation_target_atomically(
    statement: Revocation,
) -> None:
    registry = registry_with_trust()
    record = install_record(registry)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.apply_revocation(signed_revocation(statement), now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED
    assert registry.resolve(record.canonical_name, now=NOW) == record


def test_failed_revocation_does_not_advance_generation_tombstone() -> None:
    registry = registry_with_trust()
    record = install_record(registry)
    wrong_target = revocation(record, generation=4, target_id=b"x" * 32)

    with pytest.raises(ProtocolViolation):
        registry.apply_revocation(signed_revocation(wrong_target), now=NOW)

    accepted = apply_service_revocation(registry, record, generation=3)
    assert accepted.generation == 3


def test_registry_rejects_revocation_issuer_kid_mismatch() -> None:
    registry = registry_with_trust()
    record = install_record(registry)
    statement = revocation(record, issuer_key_id=b"other-revocation-key")

    with pytest.raises(ProtocolViolation) as rejected:
        registry.apply_revocation(signed_revocation(statement), now=NOW)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_UNTRUSTED
    assert registry.resolve(record.canonical_name, now=NOW) == record


def test_key_compromise_revocation_cannot_expire() -> None:
    record = service_record()

    with pytest.raises(ProtocolViolation) as rejected:
        revocation(
            record,
            expires_at=NOW + 100,
            reason_code=RevocationReason.KEY_COMPROMISE,
        )

    assert rejected.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED


def test_resolve_distinguishes_absent_expired_and_revoked_records() -> None:
    registry = registry_with_trust()
    record = service_record(not_after=NOW + 2)
    registry.install_record(signed_record(record), now=NOW)

    assert registry.resolve("missing.example.com", now=NOW) is None
    with pytest.raises(ProtocolViolation) as expired:
        registry.resolve(record.canonical_name, now=NOW + 2)
    assert expired.value.code is ErrorCode.NBSR_E_RECORD_UNTRUSTED

    replacement = replace(record, sequence=8, not_before=NOW + 2, not_after=NOW + 102)
    registry.install_record(signed_record(replacement), now=NOW + 2)
    apply_service_revocation(registry, replacement, now=NOW + 2)
    with pytest.raises(ProtocolViolation) as revoked:
        registry.resolve(record.canonical_name, now=NOW + 2)
    assert revoked.value.code is ErrorCode.NBSR_E_RECORD_REVOKED
