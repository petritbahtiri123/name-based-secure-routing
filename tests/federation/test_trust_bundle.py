from __future__ import annotations

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
from nbsr.federation.trust import FederationTrustBundle, TrustBundleStore, TrustTransitionBinding, compose_bundles
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


A = b"A" * 32


def ref(cls: AuthorityClass, actor: bytes, kid: bytes, purpose: KeyPurpose) -> dict[int, object]:
    del purpose
    return {1: cls.value, 2: actor, 3: kid, 4: actor}


def scope(**changes: object) -> dict[int, object]:
    value = {
        1: "service.example",
        2: b"S" * 32,
        3: b"tenant",
        4: A,
        5: b"B" * 32,
        6: "eu",
        7: [[443, 443]],
        8: [6],
        9: [1, 2],
        10: False,
        11: 2,
    }
    value.update({int(k): v for k, v in changes.items()})
    return value


def bundle(**changes: object) -> FederationTrustBundle:
    issuer = ref(AuthorityClass.FEDERATION_AUTHORITY, A, b"trust", KeyPurpose.TRUST_BUNDLE)
    value: dict[int, object] = {
        1: ObjectType.FederationTrustBundle.value,
        2: 1,
        3: issuer,
        4: 1,
        5: 1,
        6: 100,
        7: 2000,
        32: scope(),
        33: [ref(AuthorityClass.OPERATOR_IDENTITY_ROOT, A, b"root", KeyPurpose.IDENTITY_ROOT)],
        34: [issuer],
        35: [ref(AuthorityClass.TRANSPARENCY_LOG, b"L" * 32, b"log", KeyPurpose.TRANSPARENCY_LOG)],
        36: [ref(AuthorityClass.WITNESS, b"W" * 32, b"wit", KeyPurpose.WITNESS)],
        37: {1: [1, 1], 2: [1, 1], 3: [1, 1]},
        38: [1],
        39: [ref(AuthorityClass.TARGET_CONTROLLER, A, b"rev", KeyPurpose.REVOCATION)],
        40: 900,
        41: b"P" * 32,
    }
    value.update({int(k): v for k, v in changes.items()})
    return FederationTrustBundle.from_bytes(encode_deterministic(value))


def test_bundle_genesis_fields_freshness_extensions_and_resource_bounds() -> None:
    parsed = bundle()
    parsed.require_fresh(400)
    parsed.require_usable_keys({kid: KeyLifecycle.ACTIVE for kid in (b"trust", b"root", b"log", b"wit", b"rev")})
    with pytest.raises(FederationValidationError, match="stale"):
        parsed.require_fresh(1001)
    with pytest.raises(FederationValidationError, match="critical"):
        bundle(**{"31": {1000: {1: 1, 2: True, 3: b"x"}}})
    with pytest.raises(FederationValidationError):
        bundle(
            **{"33": [ref(AuthorityClass.OPERATOR_IDENTITY_ROOT, bytes([i]) * 32, bytes([i]), KeyPurpose.IDENTITY_ROOT) for i in range(33)]}
        )


def test_bundle_update_idempotency_rollback_equivocation_and_generation_transition() -> None:
    genesis = bundle()
    store = TrustBundleStore()
    assert store.accept(genesis) == "ACCEPT"
    assert store.accept(genesis) == "IDEMPOTENT"
    updated = bundle(**{"5": 2, "8": genesis.digest, "40": 300})
    assert store.accept(updated) == "ACCEPT"
    with pytest.raises(FederationValidationError, match="rollback"):
        store.accept(genesis)
    equivocation = bundle(**{"5": 2, "8": genesis.digest, "41": None})
    assert store.accept(equivocation) == "QUARANTINE"
    assert len(store.conflicts) == 2
    assert store.current is updated
    next_generation = bundle(**{"4": 2, "5": 1, "8": updated.digest, "40": 300})
    with pytest.raises(FederationValidationError, match="packaging"):
        TrustTransitionBinding(b"T" * 32, next_generation.digest, True, True, 1, 2, scope(), True)
    with pytest.raises(FederationValidationError, match="transition"):
        TrustBundleStore(updated).accept(next_generation)


def test_updates_require_previous_digest_and_cannot_widen_authority() -> None:
    genesis = bundle()
    with pytest.raises(FederationValidationError, match="previous"):
        TrustBundleStore(genesis).accept(bundle(**{"5": 2}))
    wider = bundle(**{"5": 2, "8": genesis.digest, "38": [1, 2]})
    with pytest.raises(FederationValidationError, match="widen"):
        TrustBundleStore(genesis).accept(wider)


def test_composition_intersects_every_restriction() -> None:
    first = bundle()
    second = bundle(**{"40": 300, "37": {1: [1, 1], 2: [1, 1], 3: [1, 1]}, "41": None})
    composed = compose_bundles(first, second)
    assert composed.max_staleness == 300
    assert composed.profiles == frozenset({1})
    assert composed.policy_references == frozenset({b"P" * 32})


@pytest.mark.parametrize("state", [KeyLifecycle.NEXT, KeyLifecycle.RETIRING, KeyLifecycle.RETIRED, KeyLifecycle.REVOKED])
def test_non_active_bundle_keys_cannot_create_authority(state: KeyLifecycle) -> None:
    with pytest.raises(FederationValidationError, match="active"):
        bundle().require_usable_keys({b"trust": state, b"root": KeyLifecycle.ACTIVE})


def test_every_trust_participant_must_be_active() -> None:
    lifecycles = {kid: KeyLifecycle.ACTIVE for kid in (b"trust", b"root", b"log", b"wit", b"rev")}
    for kid in tuple(lifecycles):
        candidate = dict(lifecycles)
        candidate[kid] = KeyLifecycle.REVOKED
        with pytest.raises(FederationValidationError, match="active"):
            bundle().require_usable_keys(candidate)


def test_generation_transition_must_be_authenticated_and_bind_candidate_digest() -> None:
    current = bundle()
    candidate = bundle(**{"4": 2, "5": 1, "8": current.digest})
    with pytest.raises(FederationValidationError, match="packaging"):
        TrustTransitionBinding(b"T" * 32, b"X" * 32, True, False, 1, 2, scope(), True)
    with pytest.raises(FederationValidationError, match="transition"):
        TrustBundleStore(current).accept(candidate)


def test_bundle_store_retains_all_equivocation_branches() -> None:
    current = bundle()
    store = TrustBundleStore(current)
    first = bundle(**{"41": None})
    second = bundle(**{"40": 300})
    assert store.accept(first) == "QUARANTINE"
    assert store.accept(second) == "QUARANTINE"
    assert {item.digest for item in store.conflicts} == {current.digest, first.digest, second.digest}


def test_single_sign1_cannot_satisfy_trust_authority_and_witness_thresholds() -> None:
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    parsed = bundle()
    authority = FederationAuthority(b"trust", private.public_key(), A, KeyPurpose.TRUST_BUNDLE, KeyLifecycle.ACTIVE, 1, 1, 0, 2000, False)
    with pytest.raises(FederationValidationError, match="packaging"):
        verify_federation_sign1(
            sign1(parsed.canonical_bytes(), b"trust", private),
            authority,
            ObjectType.FederationTrustBundle,
            100,
            expected_key_purpose=KeyPurpose.TRUST_BUNDLE,
        )


def test_new_generation_rotation_fails_closed_until_threshold_packaging_is_frozen() -> None:
    current = bundle()
    rotated = bundle(
        **{
            "4": 2,
            "5": 1,
            "8": current.digest,
            "33": [ref(AuthorityClass.OPERATOR_IDENTITY_ROOT, b"N" * 32, b"new-root", KeyPurpose.IDENTITY_ROOT)],
        }
    )
    with pytest.raises(FederationValidationError, match="packaging"):
        TrustTransitionBinding(b"T" * 32, rotated.digest, True, True, 1, 2, scope(), True)
    with pytest.raises(FederationValidationError, match="transition"):
        TrustBundleStore(current).accept(rotated)
