"""Verify one retained test-only genesis signature; never sign or create keys."""

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.federation.cose import FederationAuthority, verify_federation_sign1
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.registry import KeyLifecycle, KeyPurpose, ObjectType
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "crates/nbsr-transport/tests/fixtures/connector-kar-genesis-positive.json"
PAYLOAD_HASH = "714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed"
PUBLIC = bytes.fromhex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")


def check():
    assert FIXTURE.is_file(), "approved composed-positive fixture is missing"
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["id"] == "test-only-kar-genesis-purpose3-positive-v1"
    assert fixture["runtime_authorized"] is False
    wire, payload = (bytes.fromhex(fixture[k]) for k in ("wire", "payload"))
    assert hashlib.sha256(payload).hexdigest() == PAYLOAD_HASH == fixture["payload_sha256"]
    assert hashlib.sha256(wire).hexdigest() == fixture["wire_sha256"]
    recipes = json.loads((ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json").read_text())
    recipe = next(r for r in recipes["fixtures"] if r["name"] == "valid-root-authorized-genesis")
    assert payload == bytes.fromhex(recipe["canonical_cbor_hex"])
    root = FederationAuthority(b"root-kid", Ed25519PublicKey.from_public_bytes(PUBLIC),
                               b"O" * 32, KeyPurpose.IDENTITY_ROOT, KeyLifecycle.ACTIVE,
                               1, 1, 900, 2100, False)

    def verify(message=wire, authority=root, now=1500, expected=payload, purpose=KeyPurpose.REGISTRY_SIGNING):
        return verify_federation_sign1(message, authority, ObjectType.KeyAuthorizationRecord,
                                      now, expected_payload=expected, expected_key_purpose=purpose)

    positive = 0
    for now in (1000, 1500, 2000):
        assert verify(now=now).canonical_bytes() == payload
        positive += 1
    assert verify(authority=replace(root, expires_at=1500)).canonical_bytes() == payload
    positive += 1
    negatives = [{"now": 999}, {"now": 2001}, {"expected": payload + b"\0"},
                 {"purpose": KeyPurpose.REVOCATION}, {"purpose": KeyPurpose.FEDERATION_TRANSPORT}]
    for changes in ({"kid": b"other"}, {"operator_id": b"X" * 32},
                    {"public_key": Ed25519PublicKey.from_public_bytes(b"K" * 32)},
                    {"purpose": KeyPurpose.REGISTRY_SIGNING}, {"lifecycle": KeyLifecycle.REVOKED},
                    {"revoked": True}, {"not_before": 1501}, {"expires_at": 1499}):
        negatives.append({"authority": replace(root, **changes)})
    altered = bytearray(wire)
    altered[-1] ^= 1
    negatives.append({"message": bytes(altered)})
    body = decode_deterministic(wire[1:])
    body[2] = payload[:-1] + bytes([payload[-1] ^ 1])
    negatives.append({"message": b"\xd2" + encode_deterministic(body), "expected": body[2]})
    body[2] = None
    negatives += [{"message": b"\xd2" + encode_deterministic(body)},
                  {"message": wire + b"\0"}, {"message": b"\xd8\x12" + wire[1:]}]
    for case in negatives:
        try:
            verify(**case)
        except FederationValidationError:
            pass
        else:
            raise AssertionError(f"unexpected acceptance: {tuple(case)}")
    return positive, len(negatives)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    positive, negative = check()
    print(f"KAR retained signature checked: {positive} positive, {negative} negative; supplied test trust only")


if __name__ == "__main__":
    main()
