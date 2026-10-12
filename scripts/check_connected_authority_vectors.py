"""Independent local oracle/export; existing public deterministic fixture keys only."""

import argparse
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from nbsr.federation.trust import FederationTrustBundle
from nbsr.protocol.cbor import decode_deterministic as dec, encode_deterministic as enc
from scripts import verify_federation_threshold_container_fixtures as oracle
from scripts.revocation_inclusion_v2 import AMENDMENT, make_fixture, verify_package

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "vectors/connector-authority-local-v1/cases.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def authority(a, organization):
    return {
        "id": a.operator_id.hex(),
        "kid": a.kid.hex(),
        "purpose": int(a.purpose),
        "key": a.public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex(),
        "not_before": a.not_before,
        "expires": a.expires_at,
        "active": True,
        "revoked": a.revoked,
        "organization": organization,
    }


def build():
    raw, ctx, initial = make_fixture(enforcement=1)
    p = dec(raw)
    r = dec(p[3])
    envelope = dec(p[4])

    def ref(cls, actor, kid):
        return {1: cls, 2: actor, 3: kid, 4: actor}

    rows = ctx["validation"]["accepted_authority_registry"]
    issuer = ref(4, b"O" * 32, b"trust")
    bundle = {
        1: 5,
        2: 1,
        3: issuer,
        4: 1,
        5: 1,
        6: ctx["validation"]["now"] - 1,
        7: ctx["validation"]["now"] + 300,
        32: r[33],
        33: [ref(1, b"O" * 32, b"root")],
        34: sorted(
            [ref(4, bytes.fromhex(x["authority_id"]), bytes.fromhex(x["kid"])) for x in rows], key=lambda x: (x[1], x[2], x[3], x[4])
        ),
        35: [ref(5, ctx["log_authority"].operator_id, ctx["log_authority"].kid)],
        36: [ref(6, a.operator_id, a.kid) for a, _ in ctx["witness_authorities"]],
        37: {1: [3, 5], 2: [2, 3], 3: [1, 1]},
        38: [1],
        39: [ref(14, b"O" * 32, b"controller")],
        40: 900,
        41: envelope[5][2],
    }
    parsed = FederationTrustBundle.from_bytes(enc(bundle))
    parsed.require_fresh(ctx["validation"]["now"])
    trust = {
        "label": "SuppliedTestTrust",
        "profile": p[2],
        "bundle": enc(bundle).hex(),
        "bundle_digest": digest(enc(bundle)),
        "policy": enc(envelope[5]).hex(),
        "scope": enc(r[33]).hex(),
        "target": enc(r[32]).hex(),
        # Local supplied dependency inventory; no claim of registration authority.
        "dependency_inventory": enc([r[32]]).hex(),
        "issuer": enc(r[3]).hex(),
        "anchor": dec(p[9][1:])[2].hex(),
        "session_binding": oracle.capability_session_binding(ctx["validation"]).hex(),
        "signers": [
            {
                "id": x["authority_id"],
                "kid": x["kid"],
                "key": x["public_key"],
                "organization": x["organization_id"],
                "control": ctx["control_domains"][x["authority_id"]],
                "purpose": x["key_purpose"],
                "class": x["authority_class"],
                "not_before": x["not_before"],
                "expires": x["expires_at"],
                "active": True,
                "revoked": x["revoked"],
            }
            for x in rows
        ],
        "log": authority(ctx["log_authority"], "log"),
        "witnesses": [
            {**authority(a, org), "replay": ctx["witness_replays"][a.operator_id].hex()} for a, org in ctx["witness_authorities"]
        ],
        "required_witnesses": 2,
        "maximum_staleness": 900,
        "governing_obligations": ctx["obligations"],
        "now": ctx["validation"]["now"],
    }
    cases = []

    def add(name, data, context, start, supported=True):
        result, _ = verify_package(data, context, start)
        cases.append(
            {
                "name": name,
                "wire": data.hex(),
                "accepted": result["decision"] == "ACCEPT" and supported,
                "python_decision": result["decision"],
            }
        )

    for effect in range(5):
        data, context, start = make_fixture(enforcement=effect)
        add({1: "deny", 4: "terminate"}.get(effect, f"unsupported-{effect}"), data, context, start, effect in (1, 4))
    for count in (2, 4, 5):
        data, context, start = make_fixture(count=count)
        add("two-signers" if count == 2 else f"signers-{count}", data, context, start)
    bad = dec(raw)
    bad[5] = bad[5][:-1] + bytes([bad[5][-1] ^ 1])
    add("bad-signature", enc(bad), ctx, initial)
    bad = dec(raw)
    bad[8] = bad[8][:1]
    add("missing-witness", enc(bad), ctx, initial)
    bad = dec(raw)
    bad[3] += b"\x00"
    add("changed-record", enc(bad), ctx, initial)
    for name, changes in (
        ("finite-terminal", {35: True}),
        ("invalid-reason", {34: 32}),
        ("boolean-reason", {34: False}),
        ("zero-validity", {6: ctx["validation"]["now"], 7: ctx["validation"]["now"]}),
        ("timestamp-overflow", {7: 253402300800}),
    ):
        data, context, start = make_fixture(record_changes=changes)
        add(name, data, context, start)
    data, context, start = make_fixture(terminal=True)
    add("valid-terminal", data, context, start)
    data, context, start = make_fixture(anchor_timestamp=ctx["validation"]["now"] - 901)
    add("old-retained-anchor", data, context, start)
    cases[-1]["supplied_anchor"] = dec(dec(data)[9][1:])[2].hex()
    replays = []
    for effect in (1, 4):
        first, context, start = make_fixture(enforcement=effect)
        fresh, fresh_context, _ = make_fixture(enforcement=effect, event_id=b"fresh-event-id-02")
        assert dec(first)[3] == dec(fresh)[3]
        result, state = verify_package(first, context, start)
        assert result["decision"] == "ACCEPT"
        result, updated = verify_package(fresh, fresh_context, state)
        assert result["decision"] == "IDEMPOTENT" and len(updated.requests) == 2
        replays.append({"effect": effect, "first": first.hex(), "fresh": fresh.hex(), "decision": result["decision"]})
    return {
        "profile": "connector-authority-local-v1",
        "runtime_enabled": False,
        "live_enabled": False,
        "parent_sha256": {str(AMENDMENT.relative_to(ROOT)).replace("\\", "/"): digest(AMENDMENT.read_bytes())},
        "trust": trust,
        "cases": cases,
        "replays": replays,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build()
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if args.check:
        if DEST.read_bytes() != data:
            raise ValueError("connected vector drift")
    else:
        DEST.parent.mkdir(exist_ok=True)
        DEST.write_bytes(data)
    print(f"{len(value['cases'])} connected vector cases and {len(value['replays'])} replay pairs checked; no runtime authority")


if __name__ == "__main__":
    main()
