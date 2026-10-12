"""Generate/check TEST-LOCAL CRP-1 artifacts; no assigned wire envelope or trust.

Public TLS exporter input is deterministic test material, not a credential.
Stateful scenarios execute via the manifest's pytest nodes; shared bytes are
codec/transcript fixtures, not invented signed registration authority.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nbsr.connector_registration_offline import (  # noqa: E402
    ACCEPT_DOMAIN,
    CONTEXT_DOMAIN,
    EXPORTER_LABEL,
    accept_digest,
    canonical,
    frame,
)
from scripts.generate_wp4_exporter_vectors import expand_label  # noqa: E402

PACKAGE = ROOT / "vectors/connector-registration-v1-counter"
PROFILE_TEST = "tests/protocol/test_connector_registration_vectors.py::"
MODEL_TEST = "tests/test_connector_control_model.py::"
FED_TEST = "tests/test_connector_federation_model.py::"

NODES = [
    [PROFILE_TEST + "test_crp01_register"],
    [PROFILE_TEST + "test_crp02_renew_extends_lease_preserves_handle"],
    [PROFILE_TEST + "test_crp03_retry_and_superseded_rejection"],
    [PROFILE_TEST + "test_crp04_withdraw"],
    [PROFILE_TEST + "test_crp05_wrong_principal_pin", FED_TEST + "test_existing_crypto_boundary_rejects_invalid_fixture"],
    [PROFILE_TEST + "test_crp06_missing_registration_authority"],
    [PROFILE_TEST + "test_crp07_scope_and_policy"],
    [PROFILE_TEST + "test_crp08_authority_rechecked_at_commit", FED_TEST + "test_gap_independent_expiry_boundary_before_at_after"],
    [PROFILE_TEST + "test_crp09_verifier_stale_lineage_rejects", PROFILE_TEST + "test_authority_revision_changed_before_commit_rejects"],
    [PROFILE_TEST + "test_crp10_cross_connection"],
    [PROFILE_TEST + "test_crp11_bad_binding"],
    [PROFILE_TEST + "test_crp12_challenge_expiry"],
    [PROFILE_TEST + "test_crp13_conflicting_retry"],
    [PROFILE_TEST + "test_crp14_duplicate_owner"],
    [PROFILE_TEST + "test_crp15_lease_expires_between_challenge_and_commit"],
    [PROFILE_TEST + "test_crp16_lost_response_retry_and_disconnect"],
    [PROFILE_TEST + "test_crp17_stale_cleanup"],
    [PROFILE_TEST + "test_crp18_failed_cleanup"],
    [
        MODEL_TEST + "test_admission_only_expiry_preserves_active_until_finite_grace",
        MODEL_TEST + "test_late_poll_cannot_restart_expiry_grace",
    ],
    [
        PROFILE_TEST + "test_crp20_denial_invalidates_cached_success",
        MODEL_TEST + "test_repeat_deny_then_terminate_never_downgrades",
        MODEL_TEST + "test_terminate_cancels_work_but_releases_only_confirmed_cleanup",
    ],
    [
        FED_TEST + "test_fresh_verified_recovery_restores_eligibility_without_replay",
        FED_TEST + "test_recovery_cannot_resurrect_started_drain",
    ],
    [
        FED_TEST + "test_gap_timed_semantic_fixture_no_early_effect_or_expiry_resurrection",
        FED_TEST + "test_wrong_owner_or_context_has_no_effect",
    ],
    [
        PROFILE_TEST + "test_crp23_parser",
        PROFILE_TEST + "test_crp23_control_only",
        PROFILE_TEST + "test_crp23_connect_budget",
        PROFILE_TEST + "test_crp23_pending_capacity_and_sequence",
        PROFILE_TEST + "test_crp23_frame_boundaries",
        PROFILE_TEST + "test_crp23_invalid_frames",
    ],
    [PROFILE_TEST + "test_crp24_service_isolation", FED_TEST + "test_gap_two_live_owners_have_independent_dependency_effects"],
]


def counter_traces():
    """Explicit expected replay/cache transitions, independently checked by Node."""

    def step(kind, counter, outcome, high, retained, pending=None, changed=False, prefix="73" * 8):
        return {
            "kind": kind,
            "request_id_hex": prefix + counter.to_bytes(8, "big").hex(),
            "changed_body": changed,
            "expected": outcome,
            "high_water": str(high),
            "retained": retained,
            "pending": None if pending is None else str(pending),
        }

    renewals = []
    for n in range(1, 11):
        renewals += [step("request", n, "CHALLENGE", n, min(n - 1, 4), n), step("proof", n, "ACCEPT", n, min(n, 4))]
    renewals += [
        step("request", 1, "REPLAY", 10, 4),
        step("request", 10, "ACCEPT", 10, 4),
        step("request", 10, "REPLAY", 10, 4, changed=True),
    ]
    maximum = 2**64 - 1
    return [
        {"name": "ten_operations_evict_without_reexecution", "seed_high_water": "0", "steps": renewals},
        {
            "name": "pending_retry_capacity",
            "seed_high_water": "0",
            "steps": [
                step("request", 1, "CHALLENGE", 1, 0, 1),
                step("request", 2, "OVER_CAPACITY", 1, 0, 1),
                step("request", 1, "CHALLENGE", 1, 0, 1),
                step("proof", 1, "ACCEPT", 1, 1),
            ],
        },
        {
            "name": "counter_exhaustion_fixture",
            "seed_high_water": str(maximum - 1),
            "steps": [
                step("request", maximum, "CHALLENGE", maximum, 0, maximum),
                step("proof", maximum, "ACCEPT", maximum, 1),
                step("request", 0, "REPLAY", maximum, 1),
                step("request", 1, "REPLAY", maximum, 1),
            ],
        },
        {
            "name": "prefix_and_start",
            "seed_high_water": "0",
            "steps": [
                step("request", 1, "REPLAY", 0, 0, prefix="78" * 8),
                step("request", 2, "REPLAY", 0, 0),
                step("request", 1, "CHALLENGE", 1, 0, 1),
            ],
        },
    ]


def build():
    proposal = json.loads((ROOT / "docs/protocol/connector-registration-v1-vector-proposal.json").read_text(encoding="utf-8"))
    refs = [[2, b"k" * 32], [4, b"d" * 32]]
    request = {
        0: 1,
        1: "register",
        2: "connector.fixture",
        3: b"v" * 32,
        4: b"o" * 32,
        5: b"g" * 32,
        6: "gateway.fixture",
        7: b"fixture-key",
        8: b"t" * 32,
        9: b"k" * 32,
        10: refs,
        11: sha256(canonical(refs)).digest(),
        12: b"p" * 32,
        13: 60,
        14: 100,
        15: None,
    }
    raw = canonical(request)
    rd = sha256(raw).digest()
    session = b"s" * 16
    rid = session[:8] + (1).to_bytes(8, "big")
    challenge = {0: 1, 1: rd, 2: b"n" * 32, 3: 105}
    context = canonical([CONTEXT_DOMAIN, 1, session, rid, rd, challenge[2], request[4], request[5], request[6], request[8], request[12]])
    # Same established TLS 1.3/HKDF-SHA256 mechanism as WP4, new CRP-1 domain.
    master = bytes(range(32))
    derived = expand_label(master, EXPORTER_LABEL, sha256(b"").digest(), 32)
    exported = expand_label(derived, b"exporter", sha256(context).digest(), 32)
    proof = {0: 1, 1: rd, 2: challenge[2], 3: exported}
    accept = {0: 1, 1: rd, 2: b"r" * 16, 3: b"e" * 16, 4: 1, 5: 100, 6: 160, 7: 130, 8: request[11], 9: request[12]}
    ad = accept_digest(session, rid, accept)
    artifacts = {
        "request.cbor": raw,
        "request.frame": frame(raw),
        "challenge.cbor": canonical(challenge),
        "context.cbor": context,
        "fixture-exporter-master.bin": master,
        "exporter.bin": exported,
        "proof.cbor": canonical(proof),
        "accept.cbor": canonical(accept),
        "accept-digest.bin": ad,
        "withdraw.cbor": canonical({0: 1, 1: b"r" * 16, 2: b"e" * 16, 3: 1, 4: ad}),
        "reject.cbor": canonical({0: 1, 1: rd, 2: {0: 1, 1: 3, 2: rid, 3: False}}),
        "invalid-bool-lease.cbor": canonical(request | {13: True}),
        "invalid-unknown-key.cbor": canonical(request | {16: 0}),
        "invalid-trailing.cbor": raw + b"\x00",
        "invalid-duplicate.cbor": b"\xa2\x00\x01\x00\x01",
        "invalid-nonpreferred.cbor": b"\xa1\x00\x18\x01",
        "invalid-indefinite.cbor": b"\xbf\xff",
        "invalid-exporter.bin": bytes([exported[0] ^ 1]) + exported[1:],
    }
    artifacts["counter-traces.json"] = (json.dumps(counter_traces(), indent=2) + "\n").encode()
    cases = []
    for spec, nodes in zip(proposal["cases"], NODES, strict=True):
        cases.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "pytest_nodes": nodes,
                "expected": spec["expected_outcome"],
                "layer": "offline scenario; not assigned-wire conformance",
            }
        )
    manifest = {
        "profile": "connector-registration-v1-draft2",
        "status": "OFFLINE TEST-LOCAL ONLY",
        "runtime_authorized": False,
        "allocation_markers": proposal["allocation_markers"],
        "limits": proposal["limits_proposed"],
        "case_count": 24,
        "counter_amendment": {
            "request_id": "session_id[0:8] || uint64_be(operation_counter)",
            "first_counter": "1",
            "maximum_counter": str(2**64 - 1),
            "next_counter": "high_water + 1; no wrap",
            "retained_results": 4,
            "pending": 1,
            "envelope_directions": "independent monotonic uint64",
            "new_operation_consumption": "after structural/session/counter/pending checks, before authority verification",
            "eviction": "oldest completed outcome; never pending; current acceptance digest stored separately",
        },
        "cases": cases,
        "exporter_label": EXPORTER_LABEL.decode(),
        "context_domain": CONTEXT_DOMAIN,
        "accept_domain": ACCEPT_DOMAIN,
        "session_id_hex": session.hex(),
        "request_id_hex": rid.hex(),
        "fixture_authority": {
            "kind": "synthetic OfflineDecision; not authenticated registration authority",
            "admission_ceiling": 1000,
            "revision": 1,
            "clock_skew_seconds": 0,
            "governing_profile": "explicit-offline-registration-fixture",
            "record_refs_hex": [r[1].hex() for r in refs],
            "real_bilateral_checks": "tests/test_connector_federation_model.py; separate existing crypto fixture, not registration-action proof",
        },
        "nonclaims": [
            "no TLS handshake",
            "no signed registration-action fixture until allocation",
            "no authenticated event producer",
            "no carrier envelope identifiers",
            "operation counter is connector-profile correlation, not authority generation or a registry allocation",
            "clock skew 0 is a test input, not an assigned production policy",
        ],
        "artifacts": {name: {"bytes": len(data), "sha256": sha256(data).hexdigest()} for name, data in sorted(artifacts.items())},
    }
    artifacts["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = build()
    if args.check:
        mismatches = [name for name, data in expected.items() if not (PACKAGE / name).is_file() or (PACKAGE / name).read_bytes() != data]
        if mismatches:
            raise SystemExit("missing/different: " + ", ".join(mismatches))
        print(f"CRP-1 deterministic artifacts match: {len(expected)} files; 24 scenario specifications")
    else:
        PACKAGE.mkdir(exist_ok=True)
        for name, data in expected.items():
            (PACKAGE / name).write_bytes(data)
        print(f"Wrote {len(expected)} test-local files; no allocations or runtime trust")


if __name__ == "__main__":
    main()
