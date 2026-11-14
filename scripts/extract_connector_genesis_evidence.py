"""Export/check PUBLIC TEST-ONLY signed genesis corpus using existing fixture oracle.
No generated secret, network, provider receipt, runtime authority or new trust policy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/test_connector_registration_authority_offline.py"
DEST = ROOT / "crates/nbsr-transport/tests/fixtures/connector-genesis-evidence.json"


def build():
    from nbsr.protocol.cbor import decode_deterministic as dec, encode_deterministic as enc
    oracle = runpy.run_path(str(SOURCE))
    fixture = oracle["fixture"]
    _, _, base = fixture()
    scope = dec(base["chain"][1].expected_payload)[34]
    # Outcomes follow existing semantics, never a newly selected name/governance policy.
    recipes = [
        ("exact", {}, scope, 1000, True, ""),
        ("lower_boundary", {}, scope, 900, True, ""),
        ("upper_boundary", {}, scope, 1900, True, ""),
        ("before_validity", {}, scope, 899, False, "valid"),
        ("after_validity", {}, scope, 1901, False, "valid"),
        ("narrow_requested_port", {"delegation": {34: scope | {7: [[443, 445]]}}}, scope, 1000, True, ""),
        ("widen_requested_port", {}, scope | {7: [[443, 444]]}, 1000, False, "widens"),
        ("widen_requested_protocol", {}, scope | {8: [6, 17]}, 1000, False, "widens"),
        ("widen_requested_action", {}, scope | {9: [24576, 24577]}, 1000, False, "widens"),
        ("wrong_genesis_service_id", {"root": {34: b"X" * 32}}, scope, 1000, False, "service_id"),
        ("direct_parent_digest", {"delegation": {35: b"P" * 32}}, scope, 1000, False, "parent_digest"),
        ("delegation_outlives_ownership", {"delegation": {7: 2001}}, scope, 1000, False, "bounded by ownership"),
        ("revoked_delegation", {"delegation": {37: {1: 4, 2: b"revoked", 3: None}}}, scope, 1000, False, "revoked"),
    ]
    cases = []
    for name, changes, request, now, accepted, error in recipes:
        _, _, context = fixture(**changes)
        chain = []
        for record in context["chain"]:
            chain.append({"wire": record.message.hex(), "payload": record.expected_payload.hex(),
                          "wire_sha256": hashlib.sha256(record.message).hexdigest(),
                          "payload_sha256": hashlib.sha256(record.expected_payload).hexdigest(),
                          "authority": {"operator_id": record.authority.operator_id.hex(),
                                        "purpose": int(record.authority.purpose)}})
        cases.append({"id": name, "chain": chain, "request_scope": enc(request).hex(),
                      "now": now, "accepted": accepted, "error_match": error})
    return {"id": "public-test-only-nor-direct-delegation-v1",
            "scope": "PUBLIC TEST ONLY, known bytes(range(32)) seed; no real credentials, live authority, registration receipt, READY, or governance approval. Ordinary LDH name only; no native semantic verifier claim.",
            "runtime_authorized": False, "live_trust_authorized": False,
            "public_key": oracle["PUB"].hex(),
            "source": SOURCE.relative_to(ROOT).as_posix(),
            "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "signer_context": "Explicit supplied test trust: kid=key, ACTIVE, gen/seq1, validity800..2100; purposes5/6. Not provisioning or currentness evidence.",
            "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="export using existing public-test-seed signing oracle")
    args = parser.parse_args()
    data = json.dumps(build(), indent=2) + "\n"
    if args.write:
        DEST.write_text(data, encoding="utf-8")
        print("Exported13 public-test-only signed genesis cases")
    else:
        assert DEST.read_text(encoding="utf-8") == data, "retained genesis corpus drift"
        print("Retained13 public-test-only signed genesis cases reproduce exactly")


if __name__ == "__main__":
    main()
