"""Public signed genesis corpus: evidence primitives, never runtime readiness."""
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.federation.cose import FederationAuthority
from nbsr.federation.delegation import DelegationScope, DelegationVerifier, SignedFederationObject
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.registry import KeyLifecycle, KeyPurpose
from nbsr.protocol.cose import verify_sign1
from nbsr.protocol.registry import ErrorCode

FIXTURE = Path(__file__).resolve().parents[2] / "crates/nbsr-transport/tests/fixtures/connector-genesis-evidence.json"
PUBLIC = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"


def corpus():
    assert FIXTURE.is_file(), "retained signed genesis corpus missing"
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert value["id"] == "public-test-only-nor-direct-delegation-v1"
    assert value["runtime_authorized"] is False
    assert value["live_trust_authorized"] is False
    assert value["public_key"] == PUBLIC
    return value


def test_retained_genesis_corpus_signatures_and_semantic_results():
    value = corpus()
    ids = set()
    for case in value["cases"]:
        assert case["id"] not in ids
        ids.add(case["id"])
        assert len(case["chain"]) == 2
        chain = []
        for raw in case["chain"]:
            wire, payload = bytes.fromhex(raw["wire"]), bytes.fromhex(raw["payload"])
            assert hashlib.sha256(wire).hexdigest() == raw["wire_sha256"]
            assert hashlib.sha256(payload).hexdigest() == raw["payload_sha256"]
            key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC))
            # Even rejection vectors have genuinely valid public-test signatures.
            assert verify_sign1(wire, {b"key": key}, ErrorCode.NBSR_E_RECORD_UNTRUSTED).payload == payload
            a = raw["authority"]
            signer = FederationAuthority(b"key", key, bytes.fromhex(a["operator_id"]),
                                         KeyPurpose(a["purpose"]), KeyLifecycle.ACTIVE,
                                         1, 1, 800, 2100, False)
            chain.append(SignedFederationObject(wire, signer, payload))
        request = DelegationScope.from_bytes(bytes.fromhex(case["request_scope"]))
        if case["accepted"]:
            result = DelegationVerifier.verify(tuple(chain), request, case["now"])
            assert result.digest.hex() == case["chain"][-1]["payload_sha256"]
        else:
            with pytest.raises(FederationValidationError, match=case["error_match"]):
                DelegationVerifier.verify(tuple(chain), request, case["now"])
    assert ids == {
        "exact", "lower_boundary", "upper_boundary", "before_validity", "after_validity",
        "narrow_requested_port", "widen_requested_port", "widen_requested_protocol",
        "widen_requested_action", "wrong_genesis_service_id", "direct_parent_digest",
        "delegation_outlives_ownership", "revoked_delegation",
    }
    assert {case["id"] for case in value["cases"] if case["accepted"]} == {
        "exact", "lower_boundary", "upper_boundary", "narrow_requested_port",
    }
