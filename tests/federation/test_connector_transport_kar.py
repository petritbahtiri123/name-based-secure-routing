"""Retained public test-seed KAR conformance; never live registration authority."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.federation.cose import FederationAuthority, verify_federation_sign1
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.registry import KeyLifecycle, KeyPurpose, ObjectType

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "crates/nbsr-transport/tests/fixtures/connector-kar-transport-positive.json"


def material():
    assert FIXTURE.is_file(), "retained purpose14 conformance fixture missing"
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["id"] == "public-test-only-kar-transport-purpose14-v1"
    assert data["runtime_authorized"] is False
    assert data["live_trust_authorized"] is False
    assert data["public_key"] == "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
    assert data["payload_sha256"] == "335f1b59b11997e0355bcd357cfae0f3a8c9c0b0db8db88e8f1ba0d3d5789b69"
    wire, payload = (bytes.fromhex(data[k]) for k in ("wire", "payload"))
    for key, raw in (("wire", wire), ("payload", payload)):
        assert hashlib.sha256(raw).hexdigest() == data[key + "_sha256"]
    root = FederationAuthority(b"key", Ed25519PublicKey.from_public_bytes(bytes.fromhex(data["public_key"])),
                               b"C" * 32, KeyPurpose.IDENTITY_ROOT, KeyLifecycle.ACTIVE,
                               1, 1, 800, 2100, False)
    return wire, payload, root


@pytest.mark.parametrize("now", [900, 1000, 1800])
def test_retained_transport_kar_inclusive_validity(now):
    wire, payload, root = material()
    record = verify_federation_sign1(wire, root, ObjectType.KeyAuthorizationRecord, now,
                                    expected_payload=payload, expected_key_purpose=KeyPurpose.FEDERATION_TRANSPORT)
    assert record.public_key == root.public_key.public_bytes_raw()
    assert record.operator_id == b"C" * 32
    assert record.key_id == b"transport-key"


@pytest.mark.parametrize("now,purpose,tamper", [
    (899, KeyPurpose.FEDERATION_TRANSPORT, False),
    (1801, KeyPurpose.FEDERATION_TRANSPORT, False),
    (1000, KeyPurpose.REVOCATION, False),
    (1000, KeyPurpose.FEDERATION_TRANSPORT, True),
])
def test_retained_transport_kar_rejections(now, purpose, tamper):
    wire, payload, root = material()
    if tamper:
        wire = wire[:-1] + bytes([wire[-1] ^ 1])
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(wire, root, ObjectType.KeyAuthorizationRecord, now,
                               expected_payload=payload, expected_key_purpose=purpose)


@pytest.mark.parametrize("changes", [
    {"operator_id": b"X" * 32}, {"kid": b"other"},
    {"purpose": KeyPurpose.FEDERATION_TRANSPORT}, {"revoked": True},
    {"not_before": 1001}, {"expires_at": 999},
])
def test_retained_transport_kar_wrong_root_rejects(changes):
    wire, payload, root = material()
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(wire, replace(root, **changes), ObjectType.KeyAuthorizationRecord, 1000,
                               expected_payload=payload, expected_key_purpose=KeyPurpose.FEDERATION_TRANSPORT)
