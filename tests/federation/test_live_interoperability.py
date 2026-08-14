from __future__ import annotations

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation.authorization import BilateralAuthorizer
from nbsr.federation import (
    FederationAuthority,
    FederationValidationError,
    KeyLifecycle,
    KeyPurpose,
    authenticate_bilateral_context,
)
from nbsr.protocol.cose import sign1
from nbsr.federation.live_lab import LiveFederationAdmission
from nbsr.federation.local_attestation import LocalAdmissionAttestor, LocalAdmissionAuthority
from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.cose import verify_sign1
from nbsr.protocol.registry import ErrorCode
from nbsr.two_operator_lab import DestinationConnector, LimitProfile, OperatorPairRuntime, RouteTrust, VerifiedAuthority
from tests.federation.test_authorization import DEST, SERVICE, SOURCE, authenticated_context, context, evidence, proof
from tests.test_wp7_admission import profile, request
from pathlib import Path
import hashlib


SOURCE_LOCAL_KEY = Ed25519PrivateKey.from_private_bytes(b"S" * 32)
DESTINATION_LOCAL_KEY = Ed25519PrivateKey.from_private_bytes(b"D" * 32)


def _attestor() -> LocalAdmissionAttestor:
    return LocalAdmissionAttestor(
        LocalAdmissionAuthority(b"local-source", SOURCE_LOCAL_KEY),
        LocalAdmissionAuthority(b"local-destination", DESTINATION_LOCAL_KEY),
    )


def _wp7_lab():
    source = profile("isp-a", "source")
    destination = profile("isp-b", "destination")
    candidate = request(source, destination)
    trust = RouteTrust.from_profiles(
        source,
        destination,
        route_id=candidate.route_id,
        service_id=candidate.service_id,
        route_grant_digest=candidate.route_grant_digest,
    )
    authority = VerifiedAuthority(
        route_grant_digest=candidate.route_grant_digest,
        channel_authority_digest=candidate.channel_authority_digest,
        exporter_binding_digest=candidate.exporter_binding_digest,
        source_edge_id=candidate.source_edge_id,
        destination_edge_id=candidate.destination_edge_id,
        source_gateway_digest=candidate.source_gateway_digest,
        destination_gateway_digest=candidate.destination_gateway_digest,
        source_gateway_conformant=True,
        destination_gateway_conformant=True,
        source_continuity_digest=candidate.source_continuity_digest,
        destination_continuity_digest=candidate.destination_continuity_digest,
        source_continuity_status="current",
        destination_continuity_status="current",
        issued_at_ms=0,
        expires_at_ms=60_000,
    )
    runtime = OperatorPairRuntime(
        source,
        destination,
        limit_profile=LimitProfile(8, 8, 8, 8, 8, 8, 8, 1, 64, 32),
        source_audit_capacity=64,
        destination_audit_capacity=64,
        connector=DestinationConnector(
            operator_id=destination.operator_id,
            connector_id="isp-b-connector",
            private_destination="https://origin.internal.example/private",
        ),
        max_registered_contexts=1,
    )
    return runtime.register_context(expected_context=candidate, trust=trust, verified_authority=authority), candidate


def test_valid_cross_operator_federation_authorizes_wp7_route() -> None:
    authenticated = authenticated_context(context())
    lab, route = _wp7_lab()
    admission = LiveFederationAdmission(
        BilateralAuthorizer(),
        lab,
        source_operator_id=SOURCE,
        destination_operator_id=DEST,
        federation_service_id=SERVICE,
        wp7_service_id=route.service_id,
        attestor=_attestor(),
    )
    destination_evidence = replace(
        evidence(),
        operator_id=DEST,
        peer_operator_id=SOURCE,
        endpoint_operator_id=DEST,
    )

    verified = admission.authorize(
        authenticated,
        evidence(),
        destination_evidence,
        route,
        now_ms=150,
    )

    assert verified.source_operator_id == SOURCE
    assert verified.destination_operator_id == DEST
    assert verified.service_id == SERVICE
    assert verified.federation_context_digest == authenticated.context.digest
    assert verified.receipt.route_grant_digest == route.route_grant_digest
    assert lab.admitted_grant_count == 1
    source = verify_sign1(verified.source_attestation, {b"local-source": SOURCE_LOCAL_KEY.public_key()}, ErrorCode.NBSR_E_RECORD_UNTRUSTED)
    destination = verify_sign1(
        verified.destination_attestation, {b"local-destination": DESTINATION_LOCAL_KEY.public_key()}, ErrorCode.NBSR_E_RECORD_UNTRUSTED
    )
    assert decode_deterministic(source.payload)[1] == "nbsr-federation-source-admission"
    assert decode_deterministic(destination.payload)[1] == "nbsr-federation-destination-admission"


def test_local_source_attestation_cannot_satisfy_destination_authority() -> None:
    authenticated = authenticated_context(context())
    lab, route = _wp7_lab()
    destination_evidence = replace(evidence(), operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    verified = _admission(lab, route).authorize(authenticated, evidence(), destination_evidence, route, now_ms=150)
    with pytest.raises(Exception):
        verify_sign1(
            verified.source_attestation, {b"local-destination": DESTINATION_LOCAL_KEY.public_key()}, ErrorCode.NBSR_E_RECORD_UNTRUSTED
        )


def test_checked_local_attestations_are_outputs_of_the_authentic_f75_admission_path() -> None:
    source_wire = Path("vectors/wp8-local-admission/source.cose").read_bytes()
    destination_wire = Path("vectors/wp8-local-admission/destination.cose").read_bytes()
    source = decode_deterministic(
        verify_sign1(source_wire, {b"local-source": SOURCE_LOCAL_KEY.public_key()}, ErrorCode.NBSR_E_RECORD_UNTRUSTED).payload
    )
    destination = decode_deterministic(
        verify_sign1(
            destination_wire, {b"local-destination": DESTINATION_LOCAL_KEY.public_key()}, ErrorCode.NBSR_E_RECORD_UNTRUSTED
        ).payload
    )
    assert source[1] == "nbsr-federation-source-admission"
    assert destination[1] == "nbsr-federation-destination-admission"
    source_without_purpose = {**source, 1: None}
    destination_without_purpose = {**destination, 1: None}
    assert source_without_purpose == destination_without_purpose
    assert source[4].hex() == "63af737542a51a0f0d5ba43ca83224fcbad57af696971e6141a412d542310d6d"
    assert (source[6], source[7]) == (6, 8443)
    assert (source[10], source[11]) == (1_893_455_940, 1_893_456_300)
    assert source[9] == hashlib.sha256(Path("vectors/wp8-f75-route-open/federation-context.cbor").read_bytes()).digest()


def _admission(lab, route, *, authorizer=None, source_id=SOURCE, destination_id=DEST):
    return LiveFederationAdmission(
        authorizer or BilateralAuthorizer(),
        lab,
        source_operator_id=source_id,
        destination_operator_id=destination_id,
        federation_service_id=SERVICE,
        wp7_service_id=route.service_id,
        attestor=_attestor(),
    )


@pytest.mark.parametrize(
    ("case", "source_changes", "destination_changes", "route_changes"),
    [
        ("wrong-source-operator", {"operator_id": b"X" * 32}, {}, {}),
        ("wrong-destination-operator", {}, {"operator_id": b"X" * 32}, {}),
        ("wrong-peer-operator", {"peer_operator_id": b"X" * 32}, {}, {}),
        ("wrong-endpoint-operator", {}, {"endpoint_operator_id": b"X" * 32}, {}),
        ("wrong-service-authority", {"service_id": b"X" * 32}, {}, {}),
        ("expired-authority", {"now": 201}, {"now": 201}, {}),
        ("revoked-authority", {"revoked_dependencies": frozenset({b"a" * 32})}, {}, {}),
        ("incomplete-ownership", {"chain_digests": frozenset({b"1" * 32})}, {}, {}),
        ("malicious-trust-bundle", {"trust_bundle_digest": b"X" * 32}, {}, {}),
        ("split-view-checkpoint", {"checkpoint_compatible": False}, {}, {}),
        ("wrong-transport", {"allowed_protocols": frozenset({17})}, {}, {}),
        ("wrong-port-capability", {}, {"allowed_ports": frozenset({8443})}, {}),
        ("wrong-wp7-route", {}, {}, {"destination_operator": "isp-c"}),
    ],
)
def test_federation_rejection_precedes_wp7_state(
    case: str,
    source_changes: dict[str, object],
    destination_changes: dict[str, object],
    route_changes: dict[str, object],
) -> None:
    del case
    authenticated = authenticated_context(context())
    lab, route = _wp7_lab()
    source_evidence = replace(evidence(), **source_changes)
    destination_base = replace(
        evidence(),
        operator_id=DEST,
        peer_operator_id=SOURCE,
        endpoint_operator_id=DEST,
    )
    destination_evidence = replace(destination_base, **destination_changes)
    candidate = replace(route, **route_changes)

    with pytest.raises(FederationValidationError):
        _admission(lab, route).authorize(authenticated, source_evidence, destination_evidence, candidate, now_ms=150)

    assert lab.admitted_grant_count == 0


def test_replayed_federation_context_rejects_before_wp7_state() -> None:
    authenticated = authenticated_context(context())
    lab, route = _wp7_lab()
    authorizer = BilateralAuthorizer(accepted_context_digests=frozenset({authenticated.context.digest}))
    destination_evidence = replace(evidence(), operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)

    with pytest.raises(FederationValidationError, match="source federation admission failed"):
        _admission(lab, route, authorizer=authorizer).authorize(authenticated, evidence(), destination_evidence, route, now_ms=150)

    assert lab.admitted_grant_count == 0


def _rotated_authenticated(value, *, generation: int, revoked: bool = False):
    source_private = Ed25519PrivateKey.from_private_bytes(bytes(range(generation, generation + 32)))
    destination_private = Ed25519PrivateKey.from_private_bytes(bytes(range(generation + 32, generation + 64)))
    source_kid = f"source-auth-{generation}".encode("ascii")
    destination_kid = f"destination-auth-{generation}".encode("ascii")
    source_authority = FederationAuthority(
        source_kid,
        source_private.public_key(),
        SOURCE,
        KeyPurpose.FEDERATION_AUTHORIZATION,
        KeyLifecycle.ACTIVE,
        generation,
        1,
        0,
        300,
        revoked,
    )
    destination_authority = FederationAuthority(
        destination_kid,
        destination_private.public_key(),
        DEST,
        KeyPurpose.FEDERATION_AUTHORIZATION,
        KeyLifecycle.ACTIVE,
        generation,
        1,
        0,
        300,
        revoked,
    )
    return authenticate_bilateral_context(
        sign1(value.canonical_bytes(), source_kid, source_private),
        source_authority,
        sign1(value.canonical_bytes(), destination_kid, destination_private),
        destination_authority,
        150,
    )


def test_operational_signer_rotation_activates_new_key_and_rejects_revoked_old_key() -> None:
    candidate = context()
    rotated = _rotated_authenticated(candidate, generation=2)
    lab, route = _wp7_lab()
    destination_evidence = replace(evidence(), operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST)
    assert _admission(lab, route).authorize(rotated, evidence(), destination_evidence, route, now_ms=150)

    with pytest.raises(FederationValidationError):
        _rotated_authenticated(candidate, generation=1, revoked=True)


def test_trust_bundle_rotation_accepts_new_authenticated_bundle_and_rejects_stale_bundle() -> None:
    rotated_bundle = b"N" * 32
    authority_proof = proof(**{"39": rotated_bundle})
    candidate = context(authority_proof, **{"37": rotated_bundle})
    authenticated = authenticated_context(candidate)
    source_evidence = evidence(authority_proof=authority_proof, trust_bundle_digest=rotated_bundle)
    destination_evidence = replace(
        source_evidence,
        operator_id=DEST,
        peer_operator_id=SOURCE,
        endpoint_operator_id=DEST,
    )
    lab, route = _wp7_lab()
    assert _admission(lab, route).authorize(authenticated, source_evidence, destination_evidence, route, now_ms=150)

    stale_lab, stale_route = _wp7_lab()
    stale_source = replace(source_evidence, trust_bundle_digest=b"B" * 32)
    with pytest.raises(FederationValidationError):
        _admission(stale_lab, stale_route).authorize(authenticated, stale_source, destination_evidence, stale_route, now_ms=150)
    assert stale_lab.admitted_grant_count == 0
