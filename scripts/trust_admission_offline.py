"""Explicitly selected local trust admission fixture; never a runtime provider.

Trust provenance, session authentication and witness/transparency obligations
are supplied simulations. Only Option C signatures and byte bindings are real.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from nbsr.federation import KeyLifecycle
from nbsr.federation.trust import FederationTrustBundle, TrustBundleStore
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from scripts import render_federation_threshold_container as render
from scripts import verify_federation_threshold_container_fixtures as oracle

ROOT = Path(__file__).resolve().parents[1]
SELECTION = "trust-admission-offline-v1"
PROFILE_SHA256 = "d09e78c21a149e91a73f0da32b723a0038937da12c6543cbf1a7605c7e7acf08"
VECTOR = ROOT / "vectors/trust-admission-offline-v1/fixture.json"
OBLIGATIONS = {"provenance", "witness", "transparency"}


def profile():
    raw = render.PROFILE_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROFILE_SHA256:
        raise ValueError("historical profile drift")
    return json.loads(raw)


def admit(state, candidate_raw, proof, context):
    """Synchronous copy-on-accept fixture transaction; never mutate input store."""
    before = state.current.digest if state.current is not None else None
    crypto = "NOT_CHECKED"

    def result(decision, reason, after=state):
        return (
            {
                "crypto_decision": crypto,
                "semantic_decision": decision,
                "reason": reason,
                "before_digest": before.hex() if before else None,
                "after_digest": after.current.digest.hex() if after.current else None,
                "fixture_state_changed": after.current != state.current or after.conflicts != state.conflicts,
                "runtime_authority": False,
                "live_enabled": False,
            },
            after,
        )

    try:
        if context["selection"] != SELECTION or state.current is None:
            raise ValueError("explicit offline selection and supplied current bundle required")
        candidate = FederationTrustBundle.from_bytes(candidate_raw)
        if candidate.canonical_bytes() != candidate_raw:
            raise ValueError("noncanonical candidate")
        if type(proof) is not bytes or len(proof) > 65536:
            raise ValueError("proof bound")
        envelope = decode_deterministic(proof)
        value = decode_deterministic(candidate_raw)
        if candidate.generation != state.current.generation:
            raise ValueError("generation transition excluded")
        if (
            envelope[3] != 5
            or envelope[4] != candidate.digest
            or envelope[6] != render.digest(candidate.scope.to_mapping())
            or envelope[7] != {1: candidate.generation, 2: candidate.sequence, 3: value.get(8)}
            or envelope[5][3] != "global-trust-v1"
            or envelope[8][1] != 16396
            or envelope[8][7] != "replace"
        ):
            raise ValueError("candidate/operation binding")
        # This bounded slice excludes scope changes and high-risk root changes.
        if candidate.scope.to_mapping() != state.current.scope.to_mapping():
            raise ValueError("scope change excluded")
        current_value = decode_deterministic(state.current.canonical_bytes())
        if any(value[key] != current_value[key] for key in (3, 33, 34, 35, 36, 37, 38, 39, 41)):
            raise ValueError("trust configuration change excluded")
        now = context["validation"]["now"]
        candidate.require_fresh(now)
        state.current.require_fresh(now)
        candidate.require_usable_keys(context["lifecycles"])
        state.current.require_usable_keys(context["lifecycles"])
        crypto, reason, _ = oracle.verify_literal(proof, context["validation"], profile())
        if crypto != "ACCEPT":
            return result(crypto, reason)
        if any(
            context["lifecycles"].get(bytes.fromhex(row["kid"])) is not KeyLifecycle.ACTIVE
            for row in context["validation"]["accepted_authority_registry"]
        ):
            raise ValueError("governance roster key is not active")
        obligations = context.get("obligations")
        if type(obligations) is not dict or set(obligations) != OBLIGATIONS or any(v != "satisfied-fixture" for v in obligations.values()):
            return result("PENDING", "ERR_EVIDENCE_MISSING")
        # Candidate keys never supply the trusted governance roster. That roster
        # belongs to the caller's explicitly simulated validation context.
        updated = TrustBundleStore(state.current)
        updated.conflicts = state.conflicts
        decision = updated.accept(candidate)
        return result(decision, "NONE", updated)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        return result("REJECT", str(exc))


def sign_candidate(raw):
    """Fixture builder only: reuse public deterministic keys, never live keys."""
    candidate = FederationTrustBundle.from_bytes(raw)
    value = decode_deterministic(raw)
    envelope, validation = render.envelope(profile(), "global-trust-v1", [3])
    envelope[4] = candidate.digest
    envelope[6] = render.digest(candidate.scope.to_mapping())
    envelope[7] = {1: candidate.generation, 2: candidate.sequence, 3: value.get(8)}
    envelope[5] = render.policy("global-trust-v1", profile()["named_policies"]["global-trust-v1"], envelope[6])
    signed_context = oracle.expected_signature_context(envelope, "governance", oracle.capability_session_binding(validation))
    entries = [render.signer("governance", 4, 13, index, signed_context)[0] for index in range(1, 4)]
    envelope[9] = [{1: "governance", 2: sorted(entries, key=lambda e: (e[1], e[2], e[3], e[4]))}]
    return encode_deterministic(envelope), validation


def build_fixture():
    def ref(cls, actor, kid):
        return {1: cls, 2: actor, 3: kid, 4: actor}

    actor = b"A" * 32
    issuer = ref(4, actor, b"trust")
    scope = {
        1: "service.example",
        2: b"S" * 32,
        3: b"tenant",
        4: actor,
        5: b"B" * 32,
        6: "eu",
        7: [[443, 443]],
        8: [6],
        9: [1, 2],
        10: False,
        11: 2,
    }
    current = {
        1: 5,
        2: 1,
        3: issuer,
        4: 1,
        5: 1,
        6: 1750000000,
        7: 1750003600,
        32: scope,
        33: [ref(1, actor, b"root")],
        34: [issuer],
        35: [ref(5, b"L" * 32, b"log")],
        36: [ref(6, b"W" * 32, b"wit")],
        37: {1: [1, 1], 2: [1, 1], 3: [1, 1]},
        38: [1],
        39: [ref(7, actor, b"rev")],
        40: 900,
        41: b"P" * 32,
    }
    current_raw = encode_deterministic(current)
    candidate_raw = encode_deterministic({**current, 5: 2, 8: hashlib.sha256(current_raw).digest()})
    proof, validation = sign_candidate(candidate_raw)
    artifacts = {"current": current_raw, "candidate": candidate_raw, "proof": proof}
    sources = [
        "scripts/trust_admission_offline.py",
        "scripts/render_federation_threshold_container.py",
        "scripts/verify_federation_threshold_container_fixtures.py",
        "nbsr/federation/trust.py",
        "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json",
        "vectors/federation-v0.1-threshold-container/literal-fixtures.json",
    ]
    return {
        "selection": SELECTION,
        "base_commit": "840fef10d601f28336afde92f730b539eaf9154f",
        "runtime_enabled": False,
        "live_enabled": False,
        "artifacts": {name: {"hex": raw.hex(), "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in artifacts.items()},
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        "validation": validation,
        "active_kids": [kid.hex() for kid in (b"trust", b"root", b"log", b"wit", b"rev")]
        + [row["kid"] for row in validation["accepted_authority_registry"]],
        "obligations": {name: "satisfied-fixture" for name in sorted(OBLIGATIONS)},
    }


def inputs(fixture):
    artifacts = {}
    for name, item in fixture["artifacts"].items():
        raw = bytes.fromhex(item["hex"])
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("artifact drift")
        artifacts[name] = raw
    context = {
        "selection": fixture["selection"],
        "validation": fixture["validation"],
        "lifecycles": {bytes.fromhex(kid): KeyLifecycle.ACTIVE for kid in fixture["active_kids"]},
        "obligations": fixture["obligations"],
    }
    return TrustBundleStore(FederationTrustBundle.from_bytes(artifacts["current"])), context, artifacts["candidate"], artifacts["proof"]


def load_fixture():
    return json.loads(VECTOR.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write only the separate local fixture")
    args = parser.parse_args()
    fixture = build_fixture()
    if args.write:
        VECTOR.parent.mkdir(parents=True, exist_ok=True)
        VECTOR.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    else:
        assert fixture == load_fixture(), "retained fixture drift"
        state, context, candidate, proof = inputs(fixture)
        result, _ = admit(state, candidate, proof, context)
        assert result["semantic_decision"] == "ACCEPT", result
        print("PASS: offline composed fixture; no runtime authority")
