from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cose import sign1
from nbsr.federation.authorization import AuthorizationEvidence, BilateralAuthorizer, FederationAuthorityProof, FederationAuthorizationContext
from nbsr.federation.cose import FederationAuthority, authenticate_bilateral_context
from nbsr.federation.fields import KeyLifecycle
from nbsr.federation.registry import KeyPurpose
from nbsr.federation.local_attestation import LocalAdmissionAttestor, LocalAdmissionAuthority
from nbsr.federation.ownership import derive_service_id
from wp8_f75_vectors.package import _authority_proof_bytes, _federation_context_bytes, build_package


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vectors" / "wp8-local-admission"
SERVICE = derive_service_id(b"S" * 32, "service.example")


def admitted_attestations() -> tuple[bytes, bytes]:
    proof = FederationAuthorityProof.from_bytes(_authority_proof_bytes())
    context = FederationAuthorizationContext.from_bytes(_federation_context_bytes())
    source_private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    destination_private = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    source_authority = FederationAuthority(b"source-auth", source_private.public_key(), b"S" * 32, KeyPurpose.FEDERATION_AUTHORIZATION, KeyLifecycle.ACTIVE, 1, 1, 0, 1_893_456_300, False)
    destination_authority = FederationAuthority(b"destination-auth", destination_private.public_key(), b"D" * 32, KeyPurpose.FEDERATION_AUTHORIZATION, KeyLifecycle.ACTIVE, 1, 1, 0, 1_893_456_300, False)
    authenticated = authenticate_bilateral_context(
        sign1(context.canonical_bytes(), b"source-auth", source_private), source_authority,
        sign1(context.canonical_bytes(), b"destination-auth", destination_private), destination_authority,
        1_893_456_000,
    )
    evidence = AuthorizationEvidence(
        operator_id=b"S" * 32, peer_operator_id=b"D" * 32, endpoint_operator_id=b"S" * 32,
        service_id=SERVICE, authority_proof=proof, proof_pending_until=None,
        ownership_root_digest=b"A" * 32, chain_digests=frozenset({b"1" * 32, b"2" * 32}),
        canonical_name="service.example", revocation_commitment=b"R" * 32,
        trust_bundle_digest=b"B" * 32, trust_bundle_version=(1, 1), checkpoint_digest=b"C" * 32,
        checkpoint_compatible=True, policy_digest=b"P" * 32, allowed_protocols=frozenset({6}),
        allowed_ports=frozenset({8443}), allowed_actions=frozenset({1}), revoked_dependencies=frozenset(),
        now=1_893_456_000,
    )
    destination_evidence = replace(evidence, operator_id=b"D" * 32, peer_operator_id=b"S" * 32, endpoint_operator_id=b"D" * 32)
    package = build_package()
    route_grant_digest = hashlib.sha256(package["route-grant.cose"]).digest()
    attestor = LocalAdmissionAttestor(
        LocalAdmissionAuthority(b"local-source", Ed25519PrivateKey.from_private_bytes(b"S" * 32)),
        LocalAdmissionAuthority(b"local-destination", Ed25519PrivateKey.from_private_bytes(b"D" * 32)),
    )
    return attestor.authorize_and_attest(
        BilateralAuthorizer(), authenticated, evidence, destination_evidence,
        route_grant_digest=route_grant_digest, protocol=6, port=8443,
    )


def artifacts() -> dict[str, bytes]:
    source, destination = admitted_attestations()
    result: dict[str, bytes] = {"source.cose": source, "destination.cose": destination}
    manifest = {
        "format": "nbsr-wp8-local-admission-attestations-v1",
        "artifacts": [
            {"path": name, "length": len(wire), "sha256": hashlib.sha256(wire).hexdigest()}
            for name, wire in sorted(result.items())
        ],
    }
    result["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    expected = artifacts()
    if args.check:
        actual = {path.name: path.read_bytes() for path in OUT.iterdir() if path.is_file()}
        if actual != expected:
            raise SystemExit("local admission attestation artifacts drifted")
        print(f"WP8 local admission attestations: {len(expected)} files verified")
        return
    for name, wire in expected.items():
        (OUT / name).write_bytes(wire)


if __name__ == "__main__":
    main()
