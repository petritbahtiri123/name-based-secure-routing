from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation.authorization import (
    AuthorizationEvidence,
    BilateralAuthorizer,
    FederationAuthorityProof,
    FederationAuthorizationContext,
)
from nbsr.federation.cose import FederationAuthority, authenticate_bilateral_context
from nbsr.federation.fields import KeyLifecycle
from nbsr.federation.local_attestation import LocalAdmissionAttestor, LocalAdmissionAuthority
from nbsr.federation.ownership import derive_service_id
from nbsr.federation.registry import KeyPurpose
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1
from nbsr.protocol.models import RouteGrant
from nbsr.protocol.schemas import encode_model
from scripts.core_v02_vectors.fixtures import FIXTURES


SOURCE_OPERATOR = b"S" * 32
DESTINATION_OPERATOR = b"D" * 32
OPENED_AT = 1_893_456_000
PROFILE_ID = "nbsr-federation-dev-v1"


@dataclass(frozen=True)
class ServiceAuthority:
    canonical_name: str
    route_request_id: bytes
    channel_id: bytes
    route_id: bytes
    route_grant: bytes
    federation_context: bytes
    source_attestation: bytes
    destination_attestation: bytes
    route_open_body: bytes


def _id(prefix: int, index: int) -> bytes:
    return bytes([prefix]) + index.to_bytes(15, "big")


def _proof(name: str, service_id: bytes) -> bytes:
    scope = {
        1: name,
        2: b"V" * 32,
        3: None,
        4: SOURCE_OPERATOR,
        5: DESTINATION_OPERATOR,
        6: "eu",
        7: [[8443, 8443]],
        8: [6],
        9: [1],
        10: False,
        11: 0,
    }
    return encode_deterministic(
        {
            1: 11,
            2: 1,
            32: b"proof",
            33: b"A" * 32,
            34: [b"1" * 32, b"2" * 32],
            35: service_id,
            36: scope,
            37: SOURCE_OPERATOR,
            38: DESTINATION_OPERATOR,
            39: b"B" * 32,
            40: b"C" * 32,
            41: b"R" * 32,
            42: 1_893_456_300,
        }
    )


def _context(name: str, service_id: bytes, proof: bytes) -> bytes:
    proof_digest = sha256(proof).digest()
    dependencies = [[1, b"a" * 32], [3, b"b" * 32], [5, b"B" * 32], [6, b"C" * 32], [11, proof_digest]]
    scope = {
        1: name,
        2: service_id,
        3: None,
        4: SOURCE_OPERATOR,
        5: DESTINATION_OPERATOR,
        6: "eu",
        7: [[8443, 8443]],
        8: [6],
        9: [1],
        10: False,
        11: 0,
    }
    return encode_deterministic(
        {
            1: 12,
            2: 1,
            3: {1: 9, 2: SOURCE_OPERATOR, 3: b"auth", 4: SOURCE_OPERATOR},
            9: 1_893_455_940,
            32: b"context",
            33: SOURCE_OPERATOR,
            34: DESTINATION_OPERATOR,
            35: service_id,
            36: proof_digest,
            37: b"B" * 32,
            38: b"C" * 32,
            39: b"P" * 32,
            40: scope,
            41: 1_893_456_300,
            42: 1,
            43: 7,
            44: dependencies,
            45: sha256(encode_deterministic(dependencies)).digest(),
            46: b"R" * 32,
        }
    )


def build_authority_set(count: int) -> tuple[ServiceAuthority, ...]:
    if not 1 <= count <= 32:
        raise ValueError("service authority count must be in 1..32")
    route_private = Ed25519PrivateKey.from_private_bytes(FIXTURES.route_grant_seed)
    session_private = Ed25519PrivateKey.from_private_bytes(FIXTURES.session_seed)
    source_context_private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    destination_context_private = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    source_authority = FederationAuthority(
        b"source-auth",
        source_context_private.public_key(),
        SOURCE_OPERATOR,
        KeyPurpose.FEDERATION_AUTHORIZATION,
        KeyLifecycle.ACTIVE,
        1,
        1,
        0,
        1_893_456_300,
        False,
    )
    destination_authority = FederationAuthority(
        b"destination-auth",
        destination_context_private.public_key(),
        DESTINATION_OPERATOR,
        KeyPurpose.FEDERATION_AUTHORIZATION,
        KeyLifecycle.ACTIVE,
        1,
        1,
        0,
        1_893_456_300,
        False,
    )
    attestor = LocalAdmissionAttestor(
        LocalAdmissionAuthority(b"local-source", Ed25519PrivateKey.from_private_bytes(b"S" * 32)),
        LocalAdmissionAuthority(b"local-destination", Ed25519PrivateKey.from_private_bytes(b"D" * 32)),
    )
    result: list[ServiceAuthority] = []
    for index in range(count):
        name = f"service-{index:02d}.example"
        service_id = derive_service_id(SOURCE_OPERATOR, name)
        proof_wire = _proof(name, service_id)
        context_wire = _context(name, service_id, proof_wire)
        context = FederationAuthorizationContext.from_bytes(context_wire)
        authenticated = authenticate_bilateral_context(
            sign1(context.canonical_bytes(), b"source-auth", source_context_private),
            source_authority,
            sign1(context.canonical_bytes(), b"destination-auth", destination_context_private),
            destination_authority,
            OPENED_AT,
        )
        route_id = _id(0x20, index)
        channel_id = _id(0x40, index)
        request_id = _id(0x70, index)
        grant = RouteGrant(
            grant_version=1,
            route_id=route_id,
            name_digest=sha256(name.encode("ascii")).digest(),
            service_id=name,
            source_operator_id="nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r",
            source_edge_id="source.edge",
            destination_operator_id="nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg",
            destination_edge_set=("destination.edge",),
            allowed_transports=("tcp",),
            allowed_ports=(8443,),
            client_session_key_thumbprint=FIXTURES.client_session_key_thumbprint,
            not_before=1_893_455_940,
            expires_at=1_893_456_300,
            lease_id=_id(0x30, index),
            record_sequence=42,
            policy_hash=FIXTURES.policy_hash,
            unique_nonce=_id(0x50, index),
        )
        grant_wire = sign1(encode_model(grant), FIXTURES.kid, route_private)
        grant_digest = sha256(grant_wire).digest()
        proof = FederationAuthorityProof.from_bytes(proof_wire)
        evidence = AuthorizationEvidence(
            operator_id=SOURCE_OPERATOR,
            peer_operator_id=DESTINATION_OPERATOR,
            endpoint_operator_id=SOURCE_OPERATOR,
            service_id=service_id,
            authority_proof=proof,
            proof_pending_until=None,
            ownership_root_digest=b"A" * 32,
            chain_digests=frozenset({b"1" * 32, b"2" * 32}),
            canonical_name=name,
            revocation_commitment=b"R" * 32,
            trust_bundle_digest=b"B" * 32,
            trust_bundle_version=(1, 1),
            checkpoint_digest=b"C" * 32,
            checkpoint_compatible=True,
            policy_digest=b"P" * 32,
            allowed_protocols=frozenset({6}),
            allowed_ports=frozenset({8443}),
            allowed_actions=frozenset({1}),
            revoked_dependencies=frozenset(),
            now=OPENED_AT,
        )
        source_attestation, destination_attestation = attestor.authorize_and_attest(
            BilateralAuthorizer(),
            authenticated,
            evidence,
            replace(
                evidence, operator_id=DESTINATION_OPERATOR, peer_operator_id=SOURCE_OPERATOR, endpoint_operator_id=DESTINATION_OPERATOR
            ),
            route_grant_digest=grant_digest,
            protocol=6,
            port=8443,
        )
        context_digest = sha256(context_wire).digest()
        transcript = [
            "NBSR-FED-ROUTE-OPEN",
            2,
            2,
            [1, 1, 1, PROFILE_ID],
            FIXTURES.session_id,
            request_id,
            channel_id,
            route_id,
            "destination.edge",
            FIXTURES.edge_nonce,
            "tcp",
            name,
            8443,
            grant_digest,
            OPENED_AT,
            context_digest,
        ]
        route_body = {
            0: 2,
            1: channel_id,
            2: grant_wire,
            3: FIXTURES.edge_nonce,
            4: "tcp",
            5: 8443,
            6: OPENED_AT,
            7: session_private.sign(encode_deterministic(transcript)),
            8: {0: 1, 1: 1, 2: 1, 3: PROFILE_ID, 4: grant_digest, 5: context_digest},
        }
        result.append(
            ServiceAuthority(
                name,
                request_id,
                channel_id,
                route_id,
                grant_wire,
                context_wire,
                source_attestation,
                destination_attestation,
                encode_deterministic(route_body),
            )
        )
    return tuple(result)


def write_authority_set(root: Path, count: int) -> tuple[ServiceAuthority, ...]:
    services = build_authority_set(count)
    root.mkdir(parents=True, exist_ok=True)
    for index, service in enumerate(services):
        directory = root / f"{index:02d}"
        directory.mkdir(exist_ok=True)
        (directory / "name.txt").write_text(service.canonical_name + "\n", encoding="ascii", newline="\n")
        (directory / "route-open-body.cbor").write_bytes(service.route_open_body)
        (directory / "federation-context.cbor").write_bytes(service.federation_context)
        (directory / "source.cose").write_bytes(service.source_attestation)
        (directory / "destination.cose").write_bytes(service.destination_attestation)
        (directory / "request-id.bin").write_bytes(service.route_request_id)
        (directory / "channel-id.bin").write_bytes(service.channel_id)
        (directory / "route-id.bin").write_bytes(service.route_id)
        (directory / "grant-digest.bin").write_bytes(sha256(service.route_grant).digest())
    return services
