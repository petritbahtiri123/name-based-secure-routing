"""Extract public signed bytes for native tests; never generate keys/signatures.

This is a cryptographic primitive cross-check, not an authority or threshold
producer. Existing fixture trust context remains explicitly synthetic.
"""

import argparse
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import verify_sign1
from nbsr.protocol.registry import ErrorCode
from scripts.verify_federation_threshold_container_fixtures import (
    capability_session_binding,
    expected_signature_context,
)

ROOT = Path(__file__).resolve().parents[1]
SIGNED = "vectors/federation-v0.1-development-v2/signed-vectors.json"
THRESHOLD = "vectors/federation-v0.1-threshold-container/literal-fixtures.json"
OUTPUT = ROOT / "crates/nbsr-transport/tests/fixtures/connector-signature-primitives.json"


def build():
    rows = []

    def add(name, wire, payload, kid, public_key, purpose, meaning):
        verified = verify_sign1(wire, {kid: Ed25519PublicKey.from_public_bytes(public_key)}, ErrorCode.NBSR_E_RECORD_UNTRUSTED)
        assert verified.payload == payload and verified.kid == kid
        rows.append(dict(name=name, wire=wire.hex(), payload=payload.hex(), kid=kid.hex(), public_key=public_key.hex(),
                         fixture_purpose=purpose, authority_claim=meaning))

    signed = json.loads((ROOT / SIGNED).read_text(encoding="utf-8"))
    signers = {s["kid"]: s for s in signed["trusted_signers"]}
    for vector in signed["vectors"]:
        if vector["case"] not in ("valid-sign1", "wrong-key-purpose"):
            continue
        wire = bytes.fromhex(vector["cose_sign1_hex"])
        payload = decode_deterministic(wire[1:])[2]
        assert hashlib.sha256(payload).hexdigest() == vector["payload_sha256"]
        signer = signers[vector["kid_hex"]]
        add(vector["id"], wire, payload, bytes.fromhex(signer["kid"]), bytes.fromhex(signer["signing_public_key"]),
            signer["key_purpose"], "none: signature success is not object/purpose authorization")
    threshold = json.loads((ROOT / THRESHOLD).read_text(encoding="utf-8"))
    for fixture in threshold["fixtures"]:
        if fixture["name"] not in ("valid-global-trust-3-of-5", "valid-deny-only-emergency-2-of-5"):
            continue
        raw = bytes.fromhex(fixture["canonical_cbor_hex"])
        assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
        envelope = decode_deterministic(raw)
        context = fixture["validation_context"]
        authorities = {a["kid"]: a for a in context["accepted_authority_registry"]}
        for group in envelope[9]:
            expected = encode_deterministic(expected_signature_context(envelope, group[1], capability_session_binding(context)))
            for entry in group[2]:
                authority = authorities[entry[4].hex()]
                add(fixture["name"] + "/" + entry[4].hex(), entry[7], expected, entry[4],
                    bytes.fromhex(authority["public_key"]), authority["key_purpose"],
                    "none: per-signature check, not threshold or revocation authorization")
    return json.dumps(dict(format_version=1, scope="test-only cryptographic primitive; fixture trust; no runtime authority",
                           source_sha256={f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in (SIGNED, THRESHOLD)},
                           cases=rows), indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != data:
            raise SystemExit("native signature fixture drift")
    else:
        OUTPUT.write_text(data, encoding="utf-8")
    print(f"{len(json.loads(data)['cases'])} signature cases verified with Python; {'checked' if args.check else 'extracted'}")


if __name__ == "__main__":
    main()
