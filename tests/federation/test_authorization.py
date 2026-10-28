from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import (
    DecisionOutcome,
    FederationAuthority,
    FederationValidationError,
    KeyLifecycle,
    KeyPurpose,
    authenticate_bilateral_context,
)
from nbsr.federation.authorization import (
    AuthorizationEvidence,
    BilateralAuthorizer,
    FederationAuthorityProof,
    FederationAuthorizationContext,
)
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


SOURCE, DEST, SERVICE = b"S" * 32, b"D" * 32, b"V" * 32
BUNDLE, CHECKPOINT, POLICY, ROUTE = b"B" * 32, b"C" * 32, b"P" * 32, b"R" * 32
SCOPE = {1: "service.example", 2: SERVICE, 3: None, 4: SOURCE, 5: DEST, 6: "eu", 7: [[443, 443]], 8: [6], 9: [1], 10: False, 11: 0}


def proof(**changes: object) -> FederationAuthorityProof:
    payload = {
        1: 11,
        2: 1,
        32: b"proof",
        33: b"A" * 32,
        34: [b"1" * 32, b"2" * 32],
        35: SERVICE,
        36: SCOPE,
        37: SOURCE,
        38: DEST,
        39: BUNDLE,
        40: CHECKPOINT,
        41: b"R" * 32,
        42: 200,
    }
    payload.update({int(k): v for k, v in changes.items()})
    return FederationAuthorityProof.from_bytes(encode_deterministic(payload))


def context(authority_proof: FederationAuthorityProof | None = None, **changes: object) -> FederationAuthorizationContext:
    authority_proof = authority_proof or proof()
    dependencies = [[1, b"a" * 32], [3, b"b" * 32], [5, BUNDLE], [6, CHECKPOINT], [11, authority_proof.digest]]
    payload = {
        1: 12,
        2: 1,
        3: {1: 9, 2: SOURCE, 3: b"auth", 4: SOURCE},
        9: 100,
        32: b"context",
        33: SOURCE,
        34: DEST,
        35: SERVICE,
        36: authority_proof.digest,
        37: BUNDLE,
        38: CHECKPOINT,
        39: POLICY,
        40: SCOPE,
        41: 200,
        42: 1,
        43: 7,
        44: dependencies,
        45: hashlib.sha256(encode_deterministic(dependencies)).digest(),
        46: ROUTE,
    }
    payload.update({int(k): v for k, v in changes.items()})
    return FederationAuthorizationContext.from_bytes(encode_deterministic(payload))


def authenticated_context(value: FederationAuthorizationContext):
    source_private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    destination_private = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    source_authority = FederationAuthority(
        b"source-auth", source_private.public_key(), SOURCE, KeyPurpose.FEDERATION_AUTHORIZATION, KeyLifecycle.ACTIVE, 1, 1, 0, 300, False
    )
    destination_authority = FederationAuthority(
        b"destination-auth",
        destination_private.public_key(),
        DEST,
        KeyPurpose.FEDERATION_AUTHORIZATION,
        KeyLifecycle.ACTIVE,
        1,
        1,
        0,
        300,
        False,
    )
    return authenticate_bilateral_context(
        sign1(value.canonical_bytes(), b"source-auth", source_private),
        source_authority,
        sign1(value.canonical_bytes(), b"destination-auth", destination_private),
        destination_authority,
        150,
    )


def evidence(**changes: object) -> AuthorizationEvidence:
    base = dict(
        operator_id=SOURCE,
        peer_operator_id=DEST,
        endpoint_operator_id=SOURCE,
        service_id=SERVICE,
        authority_proof=proof(),
        proof_pending_until=None,
        ownership_root_digest=b"A" * 32,
        chain_digests=frozenset({b"1" * 32, b"2" * 32}),
        canonical_name="service.example",
        revocation_commitment=b"R" * 32,
        trust_bundle_digest=BUNDLE,
        trust_bundle_version=(1, 1),
        checkpoint_digest=CHECKPOINT,
        checkpoint_compatible=True,
        policy_digest=POLICY,
        allowed_protocols=frozenset({6}),
        allowed_ports=frozenset({443}),
        allowed_actions=frozenset({1}),
        revoked_dependencies=frozenset(),
        now=150,
    )
    base.update(changes)
    return AuthorizationEvidence(**base)


def test_authority_proof_exact_scope_freshness_and_one_shot_binding() -> None:
    candidate = proof()
    candidate.verify(
        now=150,
        ownership_root_digest=b"A" * 32,
        chain_digests={b"1" * 32, b"2" * 32},
        service_id=SERVICE,
        canonical_name="service.example",
        source_operator_id=SOURCE,
        destination_operator_id=DEST,
        trust_bundle_digest=BUNDLE,
        checkpoint_digest=CHECKPOINT,
        revocation_commitment=b"R" * 32,
    )
    with pytest.raises(FederationValidationError, match="immutable"):
        candidate.advance()
    mutations = [
        dict(service_id=b"X" * 32),
        dict(source_operator_id=b"X" * 32),
        dict(trust_bundle_digest=b"X" * 32),
        dict(checkpoint_digest=b"X" * 32),
        dict(now=201),
        dict(chain_digests={b"1" * 32}),
    ]
    for mutation in mutations:
        args = dict(
            now=150,
            ownership_root_digest=b"A" * 32,
            chain_digests={b"1" * 32, b"2" * 32},
            service_id=SERVICE,
            canonical_name="service.example",
            source_operator_id=SOURCE,
            destination_operator_id=DEST,
            trust_bundle_digest=BUNDLE,
            checkpoint_digest=CHECKPOINT,
            revocation_commitment=b"R" * 32,
        )
        args.update(mutation)
        with pytest.raises(FederationValidationError):
            candidate.verify(**args)


def test_context_binds_every_dependency_and_stays_beside_route_grant() -> None:
    candidate = context()
    assert candidate.route_context_digest == ROUTE
    assert not hasattr(candidate, "route_grant")
    candidate.verify(
        now=150,
        source_operator_id=SOURCE,
        destination_operator_id=DEST,
        service_id=SERVICE,
        authority_proof_digest=proof().digest,
        trust_bundle_digest=BUNDLE,
        checkpoint_digest=CHECKPOINT,
        policy_digest=POLICY,
        protocol=6,
        port=443,
        action=1,
        affected_version=(1, 7),
        route_context_digest=ROUTE,
    )
    with pytest.raises(FederationValidationError):
        context(**{"45": b"X" * 32})


def test_source_and_destination_authorize_independently() -> None:
    ctx = context()
    authorizer = BilateralAuthorizer()
    source = authorizer.authorize_source(authenticated_context(ctx), evidence())
    destination = authorizer.authorize_destination(
        authenticated_context(ctx), evidence(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    )
    assert source.outcome is DecisionOutcome.ACCEPT
    assert destination.outcome is DecisionOutcome.ACCEPT
    assert source is not destination
    rejected = authorizer.authorize_destination(
        authenticated_context(ctx), evidence(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=b"X" * 32)
    )
    assert rejected.outcome is DecisionOutcome.REJECT
    assert source.outcome is DecisionOutcome.ACCEPT


@pytest.mark.parametrize(
    "change",
    [
        {"operator_id": b"X" * 32},
        {"endpoint_operator_id": b"X" * 32},
        {"now": 201},
        {"checkpoint_compatible": False},
        {"policy_digest": b"X" * 32},
        {"allowed_protocols": frozenset({17})},
        {"allowed_ports": frozenset({80})},
        {"allowed_actions": frozenset({2})},
        {"revoked_dependencies": frozenset({BUNDLE})},
    ],
)
def test_each_side_rejects_wrong_or_stale_authority(change: dict[str, object]) -> None:
    ctx = context()
    result = BilateralAuthorizer().authorize_source(authenticated_context(ctx), evidence(**change))
    assert result.outcome is DecisionOutcome.REJECT


def test_context_replay_and_failover_operator_boundary() -> None:
    ctx = context()
    authorizer = BilateralAuthorizer()
    assert authorizer.authorize_source(authenticated_context(ctx), evidence()).outcome is DecisionOutcome.ACCEPT
    assert authorizer.authorize_source(authenticated_context(ctx), evidence()).outcome is DecisionOutcome.ACCEPT
    assert (
        BilateralAuthorizer().authorize_source(authenticated_context(ctx), evidence(endpoint_operator_id=SOURCE)).outcome
        is DecisionOutcome.ACCEPT
    )
    assert (
        BilateralAuthorizer().authorize_source(authenticated_context(ctx), evidence(endpoint_operator_id=b"X" * 32)).outcome
        is DecisionOutcome.REJECT
    )
    assert (
        BilateralAuthorizer(frozenset({ctx.digest})).authorize_source(authenticated_context(ctx), evidence()).outcome
        is DecisionOutcome.REJECT
    )


def test_destination_waits_for_source_and_requested_route_is_exact() -> None:
    ctx = context()
    authorizer = BilateralAuthorizer()
    destination = evidence(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    assert (
        authorizer.authorize_destination(
            authenticated_context(ctx), destination, protocol=6, port=443, action=1, route_context_digest=ROUTE
        ).outcome
        is DecisionOutcome.PENDING
    )
    assert (
        authorizer.authorize_source(
            authenticated_context(ctx), evidence(), protocol=6, port=443, action=1, route_context_digest=ROUTE
        ).outcome
        is DecisionOutcome.ACCEPT
    )
    assert (
        authorizer.authorize_destination(
            authenticated_context(ctx), destination, protocol=6, port=80, action=1, route_context_digest=ROUTE
        ).outcome
        is DecisionOutcome.REJECT
    )


def test_missing_proof_is_pending_until_bounded_deadline_and_retry_is_idempotent() -> None:
    ctx = context()
    authorizer = BilateralAuthorizer()
    missing = evidence(authority_proof=None, proof_pending_until=160)
    assert (
        authorizer.authorize_source(authenticated_context(ctx), missing, protocol=6, port=443, action=1, route_context_digest=ROUTE).outcome
        is DecisionOutcome.PENDING
    )
    assert (
        authorizer.authorize_source(
            authenticated_context(ctx), evidence(), protocol=6, port=443, action=1, route_context_digest=ROUTE
        ).outcome
        is DecisionOutcome.ACCEPT
    )
    assert (
        authorizer.authorize_source(
            authenticated_context(ctx), evidence(), protocol=6, port=443, action=1, route_context_digest=ROUTE
        ).outcome
        is DecisionOutcome.ACCEPT
    )


def test_authorization_rejects_internally_misbound_authority_proof() -> None:
    wrong = proof(**{"33": b"X" * 32})
    ctx = context(wrong)
    result = BilateralAuthorizer().authorize_source(
        authenticated_context(ctx),
        evidence(authority_proof=wrong),
        protocol=6,
        port=443,
        action=1,
        route_context_digest=ROUTE,
    )
    assert result.outcome is DecisionOutcome.REJECT


def test_bilateral_context_requires_both_signatures_and_exact_digest_ordering() -> None:
    first = context()
    second = context(**{"39": b"X" * 32})
    authorizer = BilateralAuthorizer()
    assert authorizer.authorize_source(authenticated_context(first), evidence()).outcome is DecisionOutcome.ACCEPT
    destination = evidence(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST, policy_digest=b"X" * 32)
    assert authorizer.authorize_destination(authenticated_context(second), destination).outcome is DecisionOutcome.PENDING


def test_empty_route_context_digest_rejects_instead_of_defaulting() -> None:
    value = context()
    result = BilateralAuthorizer().authorize_source(authenticated_context(value), evidence(), route_context_digest=b"")
    assert result.outcome is DecisionOutcome.REJECT


@pytest.mark.parametrize("side", ["source", "destination"])
@pytest.mark.parametrize(
    "change",
    [
        {"revoked_dependencies": frozenset({BUNDLE})},
        {"checkpoint_compatible": False},
        {"policy_digest": b"X" * 32},
        {"allowed_protocols": frozenset({17})},
        {"allowed_ports": frozenset({80})},
        {"allowed_actions": frozenset({2})},
        {"peer_operator_id": b"X" * 32},
        {"canonical_name": "other.example"},
        {"authority_proof": None},
    ],
)
def test_cached_accept_rechecks_current_authority(side: str, change: dict[str, object]) -> None:
    authenticated = authenticated_context(context())
    authorizer = BilateralAuthorizer()
    assert authorizer.authorize_source(authenticated, evidence()).outcome is DecisionOutcome.ACCEPT
    bindings = {} if side == "source" else dict(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    authorize = getattr(authorizer, f"authorize_{side}")
    assert authorize(authenticated, evidence(**bindings)).outcome is DecisionOutcome.ACCEPT
    # Evidence can change within the same logical second as an accepted retry.
    result = authorize(authenticated, evidence(**(bindings | change)))
    assert result.outcome is DecisionOutcome.REJECT


@pytest.mark.parametrize("side", ["source", "destination"])
def test_cached_accept_rechecks_pending_proof(side: str) -> None:
    authenticated = authenticated_context(context())
    authorizer = BilateralAuthorizer()
    assert authorizer.authorize_source(authenticated, evidence()).outcome is DecisionOutcome.ACCEPT
    bindings = {} if side == "source" else dict(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    authorize = getattr(authorizer, f"authorize_{side}")
    assert authorize(authenticated, evidence(**bindings)).outcome is DecisionOutcome.ACCEPT
    result = authorize(authenticated, evidence(**bindings, authority_proof=None, proof_pending_until=160))
    assert result.outcome is DecisionOutcome.PENDING


@pytest.mark.parametrize("side", ["source", "destination"])
def test_cached_accept_cannot_issue_attestations_after_revocation(side: str) -> None:
    from nbsr.federation.local_attestation import LocalAdmissionAttestor, LocalAdmissionAuthority

    attestor = LocalAdmissionAttestor(
        LocalAdmissionAuthority(b"source-local", Ed25519PrivateKey.from_private_bytes(bytes(range(32)))),
        LocalAdmissionAuthority(b"destination-local", Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))),
    )
    authenticated = authenticated_context(context())
    authorizer = BilateralAuthorizer()
    source = evidence()
    destination = evidence(operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    attestor.authorize_and_attest(authorizer, authenticated, source, destination, route_grant_digest=ROUTE, protocol=6, port=443)
    revoked = dict(revoked_dependencies=frozenset({BUNDLE}))
    if side == "source":
        source = replace(source, **revoked)
    else:
        destination = replace(destination, **revoked)
    with pytest.raises(FederationValidationError, match=f"{side} federation admission failed"):
        attestor.authorize_and_attest(authorizer, authenticated, source, destination, route_grant_digest=ROUTE, protocol=6, port=443)


@pytest.mark.parametrize("side", ["source", "destination"])
@pytest.mark.parametrize("change", ["tampered", "revoked", "expired", "purpose", "payload"])
def test_bilateral_authentication_rejects_invalid_signer_or_signature(side: str, change: str) -> None:
    authenticated = authenticated_context(context())
    source_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    destination_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    authorities = [authenticated.source_authority, authenticated.destination_authority]
    keys = [source_key, destination_key]
    messages = [sign1(authenticated.context.canonical_bytes(), authority.kid, key) for authority, key in zip(authorities, keys)]
    index = 0 if side == "source" else 1
    if change == "tampered":
        messages[index] = messages[index][:-1] + bytes([messages[index][-1] ^ 1])
    elif change == "revoked":
        authorities[index] = replace(authorities[index], revoked=True)
    elif change == "expired":
        authorities[index] = replace(authorities[index], expires_at=149)
    elif change == "purpose":
        authorities[index] = replace(authorities[index], purpose=KeyPurpose.IDENTITY_ROOT)
    else:
        messages[index] = sign1(context(**{"39": b"X" * 32}).canonical_bytes(), authorities[index].kid, keys[index])
    with pytest.raises(FederationValidationError):
        authenticate_bilateral_context(messages[0], authorities[0], messages[1], authorities[1], 150)
