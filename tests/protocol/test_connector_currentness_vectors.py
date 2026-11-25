"""Offline draft wire vectors; never runtime authority."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_literal_currentness_vectors():
    from scripts.verify_connector_currentness_vectors import check

    assert check()[0] >= 5


def test_currentness_vector_scope_and_required_cases():
    data = json.loads((ROOT / "vectors/connector-currentness-draft1/vectors.json").read_text(encoding="utf-8"))
    assert data["runtime_authorized"] is False
    assert data["live_trust_authorized"] is False
    ids = {c["id"] for c in data["cases"]}
    assert {
        "valid",
        "age_5",
        "age_6",
        "expiry_equal",
        "swapped_signatures",
        "publisher_signature_tampered",
        "status_signature_tampered",
        "grant_key_mismatch",
        "status_floor_rollback",
        "previous_boot",
        "same_cut_extension",
        "duplicate_request_key",
    } <= ids
    assert len(ids) == len(data["cases"])


def test_generator_reproduces_literal_bytes():
    from scripts.generate_connector_currentness_vectors import build

    raw = (json.dumps(build(), indent=2) + "\n").encode("utf-8")
    assert raw == (ROOT / "vectors/connector-currentness-draft1/vectors.json").read_bytes()


def test_pair_has_two_independently_valid_signatures_and_distinct_keys():
    import cbor2
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    import pytest
    from scripts.verify_connector_currentness_vectors import PUB, AUTH

    data = json.loads((ROOT / "vectors/connector-currentness-draft1/vectors.json").read_text(encoding="utf-8"))
    case = next(c for c in data["cases"] if c["id"] == "valid")
    pair = cbor2.loads(bytes.fromhex(case["response_hex"]))
    assert PUB != AUTH
    payloads = []
    for wire, key, other in zip(pair, (PUB, AUTH), (AUTH, PUB), strict=True):
        tagged = cbor2.loads(wire)
        assert tagged.tag == 18
        protected, unprotected, payload, signature = tagged.value
        assert unprotected == {}
        transcript = cbor2.dumps(["Signature1", protected, b"", payload], canonical=True)
        Ed25519PublicKey.from_public_bytes(key).verify(signature, transcript)
        with pytest.raises(InvalidSignature):
            Ed25519PublicKey.from_public_bytes(other).verify(signature, transcript)
        payloads.append(cbor2.loads(payload))
    assert payloads[0][0] != payloads[1][0]
    assert payloads[0][3] == payloads[1][3]
    assert payloads[0][4] == payloads[1][4]
    assert payloads[0][7] == payloads[1][6]
