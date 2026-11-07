"""Read-only verification of five retained purpose-12 KARs. Never signs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.federation.cose import FederationAuthority, verify_federation_sign1
from nbsr.federation.identity import OperatorId
from nbsr.federation.registry import KeyLifecycle, KeyPurpose, ObjectType
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic

PIN = "54e6e22985c0ae5aef84ffaa72d4ce502dc5494df6cf9f977e6dd9bf9ca49fb0"
PARENT = "3d255c15f853980b88ee505a1db461e01c2425f6b984542419847d344493698c"


def check(root: Path | None = None) -> dict[str, object]:
    root = root or Path(__file__).resolve().parents[1]
    raw = (root / "crates/nbsr-transport/tests/fixtures/connector-normal-kar-v2.json").read_bytes()
    old_raw = (root / "vectors/connector-authority-local-v1/cases.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PIN
    assert hashlib.sha256(old_raw).hexdigest() == PARENT
    trust, old = json.loads(raw), json.loads(old_raw)["trust"]
    assert trust["context_version"] == "normal-roster-kar-v2"
    assert {k for k in trust if trust.get(k) != old.get(k)} == {
        "bundle", "bundle_digest", "normal_kar", "context_version"
    }
    assert len(trust["normal_kar"]) == len(trust["signers"]) == 5
    bundle = decode_deterministic(bytes.fromhex(trust["bundle"]))
    old_bundle = decode_deterministic(bytes.fromhex(old["bundle"]))
    assert {k for k in bundle if bundle[k] != old_bundle[k]} == {33, 34}
    assert hashlib.sha256(bytes.fromhex(trust["bundle"])).hexdigest() == trust["bundle_digest"]
    roots, children = [], []
    for row, child in zip(trust["normal_kar"], trust["signers"], strict=True):
        r = row["root"]
        operator = OperatorId.from_genesis_key(bytes.fromhex(r["key"])).binary
        assert row["operator"] == r["operator"] == operator.hex()
        assert row["authority"] == child["id"] != operator.hex()
        assert all(row[k] == child[k] for k in ("kid", "key", "organization", "control"))
        authority = FederationAuthority(
            kid=bytes.fromhex(r["kid"]), public_key=Ed25519PublicKey.from_public_bytes(bytes.fromhex(r["key"])),
            operator_id=operator, purpose=KeyPurpose.IDENTITY_ROOT, lifecycle=KeyLifecycle.ACTIVE,
            generation=1, sequence=1, not_before=r["not_before"], expires_at=r["expires"], revoked=False,
        )
        payload, wire = bytes.fromhex(row["payload"]), bytes.fromhex(row["wire"])
        decoded = decode_deterministic(payload)
        assert decoded[33] == bytes.fromhex(child["kid"])
        assert decoded[34] == bytes.fromhex(child["key"])
        assert decoded[35] == 12 and decoded[36] == 2 and decoded[38] is False and decoded[39] is None
        for now in (1700000000, 1750000100, 1900000000):
            verify_federation_sign1(wire, authority, ObjectType.KeyAuthorizationRecord, now,
                                   expected_payload=payload, expected_key_purpose=KeyPurpose.REVOCATION)
        roots.append({1: 1, 2: operator, 3: bytes.fromhex(r["kid"]), 4: operator})
        children.append({1: 4, 2: bytes.fromhex(child["id"]), 3: bytes.fromhex(child["kid"]), 4: operator})
    assert bundle[33] == sorted(roots, key=encode_deterministic)
    assert bundle[34] == sorted(children, key=encode_deterministic)
    return {"context_sha256": PIN, "parent_sha256": PARENT, "verified_KARs": 5,
            "composed_boundary_checks": 15, "signatures_created": 0, "runtime_enabled": False}


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
