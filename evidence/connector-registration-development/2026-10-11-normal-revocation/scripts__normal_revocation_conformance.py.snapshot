"""Explicit local Option C amendment. No receipt, mutation or runtime authority.

Membership, common-control and applicable witness outcomes below are fixture
inputs, not provenance verification. Reuses existing public deterministic keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from nbsr.federation import EnforcementMode, FederationValidationError, ReasonCode
from nbsr.federation.revocation import TypedRevocationRecord
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from scripts import render_federation_threshold_container as render
from scripts import verify_federation_threshold_container_fixtures as oracle

ROOT = Path(__file__).resolve().parents[1]
SELECTION = "normal-revocation-conformance-v1"
AMENDMENT = ROOT / "docs/protocol/registries/federation-v0.1-normal-revocation-conformance-v1.json"
VECTORS = ROOT / "vectors/federation-normal-revocation-conformance-v1/literal-fixtures.json"
NAME = "normal-revocation-v1"
GROUP = "normal-revocation"


def load_profile(selection: str) -> dict:
    if selection != SELECTION:
        raise ValueError("explicit local amendment selection required")
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    if amendment["runtime_enabled"] is not False or amendment["live_enabled"] is not False:
        raise ValueError("conformance cannot enable runtime")
    for name, expected in amendment["parent_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("historical parent drift")
    profile = json.loads(oracle.PROFILE_PATH.read_text(encoding="utf-8"))
    profile["named_policies"][NAME] = amendment["named_policy"]
    return profile


def outcome(decision: str, reason: str, enforcement: int | None = None) -> dict:
    return {"decision": decision, "reason": reason, "typed_enforcement": enforcement, "runtime_authority": False, "mutation": False}


def check_case(case: dict) -> dict:
    """Evaluate labelled fixture inputs only; never call semantic authorize()."""
    profile = load_profile(case["selection"])
    raw = bytes.fromhex(case["envelope_hex"])
    record_raw = bytes.fromhex(case["record_hex"])
    try:
        value = decode_deterministic(raw)
        payload = decode_deterministic(record_raw)
        record = TypedRevocationRecord.from_bytes(record_raw)
        if payload[37] != 2 or payload[3][1] != 4:
            return outcome("REJECT", "ERR_AUTHORITY")
        # Pin the single named group before calling the historical verifier.
        if value[5][3] != NAME or len(value[5][5]) != 1 or len(value[9]) != 1:
            return outcome("REJECT", "ERR_AUTHORITY")
        if value[4] != record.digest:
            return outcome("REJECT", "ERR_SIGNATURE_INVALID")
        if value[6] != render.digest(payload[33]):
            return outcome("REJECT", "ERR_SCOPE")
        if value[7] != {1: payload[4], 2: payload[5], 3: payload.get(8)}:
            return outcome("REJECT", "ERR_REPLAY")
        context = case["validation_context"]
        if not payload[6] <= context["now"] <= payload[7]:
            return outcome("REJECT", "ERR_FRESHNESS")
        decision, reason, _ = oracle.verify_literal(raw, context, profile)
        if decision != "ACCEPT":
            return outcome(decision, reason)
        # Distinct nominal organizations do not establish independent control.
        # This map is an explicit accepted-context FIXTURE, never a signer claim.
        controls = case["governing_fixture"]["control_domains"]
        eligible = value[5][5][0][6]
        if set(controls) != {item.hex() for item in eligible} or any(type(domain) is not str or not domain for domain in controls.values()):
            return outcome("REJECT", "ERR_AUTHORITY")
        if len(set(controls.values())) != 5 or len({controls[entry[2].hex()] for entry in value[9][0][2]}) < 3:
            return outcome("REJECT", "ERR_WITNESS_THRESHOLD")
        # Context-specific obligations are enumerated by the governing fixture,
        # not inferred from the envelope or a sender's routine/high-impact label.
        obligations = case["governing_fixture"]["applicable_obligations"]
        if type(obligations) is not dict or not obligations or any(status != "satisfied-fixture" for status in obligations.values()):
            return outcome("PENDING", "ERR_EVIDENCE_MISSING")
        return outcome("ACCEPT", "NONE", EnforcementMode(payload[36]).value)
    except (FederationValidationError, KeyError, TypeError, ValueError, IndexError):
        return outcome("REJECT", "ERR_SCHEMA")


def signed_case(count: int = 3, enforcement: int = 1, *, mode: int = 2, terminal: bool = False) -> dict:
    scope = {
        1: "service.example",
        2: b"S" * 32,
        3: None,
        4: b"O" * 32,
        5: b"D" * 32,
        6: "eu",
        7: [[443, 443]],
        8: [6],
        9: [1],
        10: False,
        11: 0,
    }
    payload = {
        1: 13,
        2: 1,
        3: {1: 4, 2: b"normal", 3: b"rev", 4: b"O" * 32},
        4: 1,
        5: 1,
        6: 1750000000,
        7: 253402300799 if terminal else 1750000300,
        32: {1: 4, 2: b"target", 3: b"T" * 32},
        33: scope,
        34: ReasonCode.ERR_REVOKED.value,
        35: terminal,
        36: enforcement,
        37: mode,
        38: None,
        39: {1: b"L" * 32, 2: b"C" * 32, 3: 1, 4: b"I" * 32},
    }
    value, validation = render.envelope(
        load_profile(SELECTION), NAME, [count], object_type=13, message_type=16407, scope_digest=render.digest(scope)
    )
    record_raw = encode_deterministic(payload)
    value[4] = hashlib.sha256(record_raw).digest()
    value[7] = {1: 1, 2: 1, 3: None}
    context = oracle.expected_signature_context(value, GROUP, oracle.capability_session_binding(validation))
    entries = [render.signer(GROUP, 4, 12, index, context)[0] for index in range(1, count + 1)]
    value[9][0][2] = sorted(entries, key=lambda item: (item[1], item[2], item[3], item[4]))
    return {
        "selection": SELECTION,
        "record_hex": record_raw.hex(),
        "envelope_hex": encode_deterministic(value).hex(),
        "validation_context": validation,
        "governing_fixture": {
            "control_domains": {render.authority_id(4, i).hex(): f"accepted-control-{i}" for i in range(1, 6)},
            "applicable_obligations": {"governing-context-transparency": "satisfied-fixture"},
        },
    }


def build_vectors() -> list[dict]:
    cases = []

    def add(name, case, decision="REJECT", reason="ERR_AUTHORITY", enforcement=None):
        case["name"] = name
        case["expected"] = outcome(decision, reason, enforcement)
        cases.append(case)

    for count in (3, 4, 5):
        add(f"valid-{count}-of-5", signed_case(count), "ACCEPT", "NONE", 1)
    for enforcement in range(5):
        add(f"typed-enforcement-{enforcement}", signed_case(enforcement=enforcement), "ACCEPT", "NONE", enforcement)
    add("normal-terminal-terminate", signed_case(enforcement=4, terminal=True), "ACCEPT", "NONE", 4)
    for count in (0, 1, 2):
        add(f"insufficient-{count}", signed_case(count), "PENDING", "ERR_EVIDENCE_MISSING" if count == 0 else "ERR_WITNESS_THRESHOLD")
    for mode in (1, 3):
        add(f"signed-mode-{mode}-not-normal", signed_case(mode=mode))
    base = signed_case()

    def altered(name, mutate, reason="ERR_AUTHORITY", decision="REJECT"):
        case = deepcopy(base)
        value = decode_deterministic(bytes.fromhex(case["envelope_hex"]))
        mutate(case, value)
        case["envelope_hex"] = encode_deterministic(value).hex()
        add(name, case, decision, reason)

    altered(
        "nominal-companies-common-control",
        lambda c, v: c["governing_fixture"].update(
            control_domains={key: "shared-controller" for key in c["governing_fixture"]["control_domains"]}
        ),
        "ERR_WITNESS_THRESHOLD",
    )
    altered("missing-control-provenance", lambda c, v: c["governing_fixture"].update(control_domains={}))
    altered(
        "unsigned-members-common-control",
        lambda c, v: c["governing_fixture"]["control_domains"].update(
            {render.authority_id(4, i).hex(): "accepted-control-1" for i in (4, 5)}
        ),
        "ERR_WITNESS_THRESHOLD",
    )
    altered("explicit-roster-required-by-inherited-oracle", lambda c, v: v[5][5][0].update({6: []}), "ERR_SCHEMA")
    altered(
        "missing-context-witness",
        lambda c, v: c["governing_fixture"]["applicable_obligations"].update(governing_context_witness="missing"),
        "ERR_EVIDENCE_MISSING",
        "PENDING",
    )
    altered("unknown-obligations", lambda c, v: c["governing_fixture"].update(applicable_obligations={}), "ERR_EVIDENCE_MISSING", "PENDING")
    altered("wrong-purpose", lambda c, v: v[9][0][2][0].update({3: 13}), "ERR_KEY_PURPOSE")
    altered("session-replay", lambda c, v: c["validation_context"].update(authenticated_session_transcript_digest="aa" * 32), "ERR_REPLAY")
    altered("request-replay", lambda c, v: c["validation_context"].update(expected_request_event_transition_id="bb" * 16), "ERR_REPLAY")
    altered("target-substitution", lambda c, v: v.update({4: b"X" * 32}), "ERR_SIGNATURE_INVALID")
    altered("scope-substitution", lambda c, v: v.update({6: b"X" * 32}), "ERR_SCOPE")
    altered("lineage-substitution", lambda c, v: v[7].update({2: 2}), "ERR_REPLAY")
    altered("roster-shrink", lambda c, v: c["validation_context"]["accepted_authority_registry"].pop())
    altered("controller-substitution", lambda c, v: v[9][0][2][0].update({1: 14}))
    for name in ("global-trust-v1", "deny-only-emergency-v1"):
        altered(f"policy-substitution-{name}", lambda c, v, name=name: v[5].update({3: name}))
    altered("expired-record", lambda c, v: c["validation_context"].update(now=1750000301), "ERR_FRESHNESS")
    altered("revoked-signer", lambda c, v: c["validation_context"]["accepted_authority_registry"][0].update(revoked=True), "ERR_REVOKED")
    altered("extra-group", lambda c, v: v[9].append(deepcopy(v[9][0])))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    cases = build_vectors()
    for case in cases:
        actual = check_case(case)
        if actual != case["expected"]:
            raise ValueError(f"{case['name']}: {actual} != {case['expected']}")
    text = (
        json.dumps(
            {
                "scope": "local conformance only; all provenance/witness inputs simulated",
                "runtime_enabled": False,
                "live_enabled": False,
                "cases": cases,
            },
            indent=2,
        )
        + "\n"
    )
    if args.check:
        if not VECTORS.exists() or VECTORS.read_text(encoding="utf-8") != text:
            raise ValueError("literal fixtures drift")
    else:
        VECTORS.parent.mkdir(parents=True, exist_ok=True)
        VECTORS.write_text(text, encoding="utf-8")
    print(f"{len(cases)} normal revocation local conformance cases pass; runtime disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
