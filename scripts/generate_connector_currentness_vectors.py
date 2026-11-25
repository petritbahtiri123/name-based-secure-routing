"""Generate draft offline vectors with openly known deterministic test seeds.

No randomness, real keys, network, runtime provider or registry mutation.
Seeds 01*32 and 02*32 are already public fixtures in revocation_inclusion_v2.py.
The checker shares fixture inputs/encoding, never generation/expected-outcome logic.
"""

import argparse
from copy import deepcopy
import json

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nbsr.protocol.cbor import encode_deterministic as enc
from nbsr.protocol.cose import sign1
from scripts.verify_connector_currentness_vectors import (
    VECTORS,
    REQUEST,
    RESPONSE,
    STATUS,
    digest,
    fixture,
)


def build():
    pub_key = Ed25519PrivateKey.from_private_bytes(bytes([1]) * 32)
    status_key = Ed25519PrivateKey.from_private_bytes(bytes([2]) * 32)
    request, grant, state = fixture()
    state_digest = digest(["NBSR-Connector-Currentness-State-draft1", 1, request[2], state])
    p = {0: RESPONSE, 1: 1, 2: request[2], 3: digest(request), 4: request[4], 5: digest(grant), 6: state, 7: state_digest, 8: 1002, 9: 1030}
    a = {
        0: STATUS,
        1: 1,
        2: request[2],
        3: digest(request),
        4: request[4],
        5: digest(grant),
        6: state_digest,
        7: 2,
        8: b"A" * 32,
        9: 1000,
        10: 1002,
        11: 1030,
        12: "authorized",
    }
    cases = []

    def emit(name, expected="OFFLINE_VECTOR_VALID", mutate=None, raw_mutate=None, clock=None, mode="receive", variant="default"):
        r, g, x, y = (deepcopy(obj) for obj in (request, grant, p, a))
        if variant != "default":
            r, g, st = fixture(variant)
            h = digest(["NBSR-Connector-Currentness-State-draft1", 1, r[2], st])
            for obj in (x, y):
                obj.update({2: r[2], 3: digest(r), 5: digest(g)})
            x.update({6: st, 7: h})
            y[6] = h
        if mutate:
            mutate(r, g, x, y)

        # cbor2 permits intentionally invalid encodings for negative fixtures.
        def encode(obj):
            return cbor2.dumps(obj, canonical=True)

        raw = encode(r)
        pair = [sign1(encode(x), g[2], pub_key), sign1(encode(y), g[9], status_key)]
        raw_response = encode(pair)
        raw_grant = encode(g)
        if raw_mutate:
            raw, raw_response, raw_grant = raw_mutate(raw, raw_response, raw_grant)
        cases.append(
            {
                "id": name,
                "expected": expected,
                "mode": mode,
                "fixture": variant,
                "clock": clock or {"L": 1003, "U": 1004, "elapsed_ms": 1000},
                "request_hex": raw.hex(),
                "grant_hex": raw_grant.hex(),
                "response_hex": raw_response.hex(),
            }
        )

    emit("valid")
    emit("grant_lifetime_24h", variant="grant_24h")
    emit("protected_kid_64", variant="kid_64")
    for variant in ("grant_over_24h", "grant_not_yet_valid", "grant_expired", "anchor_expired", "evidence_expired"):
        emit(variant, "freshness", variant=variant)
    emit("age_5", clock={"L": 1003, "U": 1005, "elapsed_ms": 1000})
    emit("zero_uncertainty", clock={"L": 1004, "U": 1004, "elapsed_ms": 1000})
    emit("just_before_attempt_deadline", clock={"L": 1003, "U": 1004, "elapsed_ms": 2999})
    emit("offline_before_expiry", mode="use", clock={"L": 1028, "U": 1029, "elapsed_ms": 25999})
    emit("shorter_validity", mutate=lambda r, g, x, y: (x.update({9: 1010}), y.update({11: 1010})))
    emit("same_cut_no_extension", mode="same_cut_refresh", mutate=lambda r, g, x, y: (x.update({9: 1020}), y.update({11: 1020})))
    for name, clock in {
        "age_6": {"L": 1004, "U": 1006, "elapsed_ms": 1000},
        "uncertainty_3": {"L": 1002, "U": 1005, "elapsed_ms": 1000},
        "inverted_clock": {"L": 1005, "U": 1004, "elapsed_ms": 1000},
        "coverage_in_future": {"L": 999, "U": 1001, "elapsed_ms": 1000},
        "attempt_deadline_equal": {"L": 1003, "U": 1004, "elapsed_ms": 3000},
        "attempt_late": {"L": 1003, "U": 1004, "elapsed_ms": 3001},
    }.items():
        emit(name, "freshness", clock=clock)
    emit("expiry_equal", "freshness", mode="use", clock={"L": 1028, "U": 1030, "elapsed_ms": 25000})
    emit("monotonic_expiry_equal", "freshness", mode="use", clock={"L": 1028, "U": 1029, "elapsed_ms": 26000})
    emit("same_cut_extension", "freshness", mode="same_cut_refresh")
    emit(
        "same_cut_refresh_stale",
        "freshness",
        mode="same_cut_refresh",
        mutate=lambda r, g, x, y: (x.update({9: 1020}), y.update({11: 1020})),
        clock={"L": 1004, "U": 1006, "elapsed_ms": 1000},
    )
    emit(
        "same_cut_refresh_late",
        "freshness",
        mode="same_cut_refresh",
        mutate=lambda r, g, x, y: (x.update({9: 1020}), y.update({11: 1020})),
        clock={"L": 1003, "U": 1004, "elapsed_ms": 3000},
    )
    emit("boolean_clock", "schema", clock={"L": True, "U": 1004, "elapsed_ms": 1})
    emit("unknown_mode", "schema", mode="restart_restored")

    for which, size in [("request", 6), ("grant", 10), ("publisher", 10), ("status", 13)]:
        index = {"request": 0, "grant": 1, "publisher": 2, "status": 3}[which]

        def change(r, g, x, y, index=index, size=size):
            (r, g, x, y)[index][size] = 0

        emit(which + "_unknown_key", "schema", mutate=change)

        def missing(r, g, x, y, index=index):
            (r, g, x, y)[index].pop(0)

        emit(which + "_missing_key", "schema", mutate=missing)

    for name, mutation, reason in [
        ("request_domain", lambda r, g, x, y: r.update({0: STATUS}), "binding"),
        ("request_version_bool", lambda r, g, x, y: r.update({1: True}), "binding"),
        ("request_scope", lambda r, g, x, y: r[3].update({0: b"X" * 32}), "binding"),
        ("gateway_normalization", lambda r, g, x, y: r[3].update({2: " Gateway "}), "wire"),
        ("previous_boot", lambda r, g, x, y: r.update({4: b"B" * 32}), "binding"),
        ("retained_commitment", lambda r, g, x, y: r.update({5: b"B" * 32}), "binding"),
        ("grant_key_mismatch", lambda r, g, x, y: g.update({3: bytes([0]) * 32}), "authorization"),
        ("grant_status_kid", lambda r, g, x, y: g.update({9: b"publisher"}), "authorization"),
        ("grant_domain_missing", lambda r, g, x, y: g.update({5: []}), "authorization"),
        ("grant_epoch_rollback", lambda r, g, x, y: g.update({8: 0}), "authorization"),
        ("grant_expires_extended", lambda r, g, x, y: g.update({7: 900 + 86401}), "authorization"),
        ("grant_expired_substitution", lambda r, g, x, y: g.update({7: 1000}), "authorization"),
        ("grant_scope_substitution", lambda r, g, x, y: g[4].update({1: b"X" * 32}), "authorization"),
        ("publisher_domain", lambda r, g, x, y: x.update({0: REQUEST}), "binding"),
        ("publisher_version_bool", lambda r, g, x, y: x.update({1: True}), "binding"),
        ("status_domain", lambda r, g, x, y: y.update({0: RESPONSE}), "binding"),
        ("status_literal", lambda r, g, x, y: y.update({12: "revoked"}), "authorization"),
        ("status_floor_rollback", lambda r, g, x, y: y.update({7: 1}), "rollback"),
        ("status_floor_conflict", lambda r, g, x, y: y.update({8: b"B" * 32}), "rollback"),
        ("status_revision_without_contract", lambda r, g, x, y: y.update({7: 3}), "rollback"),
        ("coverage_timestamp_only_advance", lambda r, g, x, y: x[6][2][0].update({5: 1001}), "rollback"),
        ("status_cut_without_revision", lambda r, g, x, y: y.update({9: 1001}), "rollback"),
        ("missing_coverage", lambda r, g, x, y: x[6].update({2: []}), "state"),
        ("wrong_source", lambda r, g, x, y: x[6][2][0].update({1: b"X" * 32}), "state"),
        ("coverage_epoch_reset", lambda r, g, x, y: x[6][2][0].update({2: 0}), "state"),
        ("duplicate_artifact", lambda r, g, x, y: x[6][1].append(deepcopy(x[6][1][0])), "state"),
        ("unresolved_policy", lambda r, g, x, y: x[6].update({5: [["unknown", 2, b"X" * 32]]}), "state"),
        ("artifact_omitted", lambda r, g, x, y: x[6].update({1: []}), "state"),
        ("artifact_bytes_changed", lambda r, g, x, y: x[6][1][0].update({1: b"bad"}), "state"),
        ("publisher_future_issued", lambda r, g, x, y: x.update({8: 1005}), "freshness"),
        ("status_future_issued", lambda r, g, x, y: y.update({10: 1005}), "freshness"),
        ("publisher_lifetime_31", lambda r, g, x, y: x.update({9: 1031}), "freshness"),
        ("status_lifetime_31", lambda r, g, x, y: y.update({11: 1031}), "freshness"),
        ("publisher_expiry_equal", lambda r, g, x, y: x.update({9: 1004}), "freshness"),
        ("status_expiry_equal", lambda r, g, x, y: y.update({11: 1004}), "freshness"),
        ("issued_before_cut", lambda r, g, x, y: x.update({8: 999}), "freshness"),
        ("timestamp_bool", lambda r, g, x, y: y.update({10: True}), "schema"),
        ("timestamp_overflow", lambda r, g, x, y: x.update({8: 253402300800}), "schema"),
        ("artifacts_65", lambda r, g, x, y: x[6].update({1: x[6][1] * 65}), "bounds"),
        ("domains_17", lambda r, g, x, y: x[6].update({2: x[6][2] * 17}), "bounds"),
    ]:
        emit(name, reason, mutate=mutation)
    for obj, index in [("publisher", 2), ("status", 3)]:
        for field in (2, 3, 4, 5, 7 if obj == "publisher" else 6):

            def changed(r, g, x, y, index=index, field=field):
                (r, g, x, y)[index][field] = b"X" * 32

            emit(f"{obj}_binding_{field}", "binding", mutate=changed)

    def pair_change(fn):
        def raw(r, b, g):
            pair = cbor2.loads(b)
            return r, cbor2.dumps(fn(pair), canonical=True), g

        return raw

    emit("swapped_signatures", "signature", raw_mutate=pair_change(lambda pair: list(reversed(pair))))
    emit("missing_status", "schema", raw_mutate=pair_change(lambda pair: pair[:1]))
    emit("extra_signature", "schema", raw_mutate=pair_change(lambda pair: pair + [pair[0]]))
    for i, name in enumerate(("publisher", "status")):

        def tamper(pair, i=i):
            wire = bytearray(pair[i])
            wire[-1] ^= 1
            pair[i] = bytes(wire)
            return pair

        emit(name + "_signature_tampered", "signature", raw_mutate=pair_change(tamper))

        def bad_header(pair, i=i):
            obj = cbor2.loads(pair[i]).value
            obj[1] = {4: b"unprotected-kid"}
            pair[i] = cbor2.dumps(cbor2.CBORTag(18, obj), canonical=True)
            return pair

        emit(name + "_unprotected_header", "signature", raw_mutate=pair_change(bad_header))
    for label, protected in [
        ("wrong_alg", enc({1: -7, 4: b"publisher"})),
        ("missing_kid", enc({1: -8})),
        ("empty_kid", enc({1: -8, 4: b""})),
        ("kid_65", enc({1: -8, 4: b"p" * 65})),
        ("unknown_header", enc({1: -8, 4: b"publisher", 99: 0})),
    ]:

        def altered(pair, protected=protected):
            obj = cbor2.loads(pair[0]).value
            obj[0] = protected
            obj[3] = pub_key.sign(enc(["Signature1", protected, b"", obj[2]]))
            pair[0] = cbor2.dumps(cbor2.CBORTag(18, obj), canonical=True)
            return pair

        emit(label, "signature", raw_mutate=pair_change(altered))
    emit("null_request_challenge", "binding", mutate=lambda r, g, x, y: r.update({4: None}))
    emit("float_time", "wire", mutate=lambda r, g, x, y: x.update({8: 1002.0}))
    emit("boolean_state_key", "schema", mutate=lambda r, g, x, y: x[6].update({False: x[6].pop(0)}))
    emit("publisher_self_status", "signature", raw_mutate=pair_change(lambda pair: [pair[0], sign1(enc(a), b"status", pub_key)]))
    emit("request_trailing_bytes", "wire", raw_mutate=lambda r, b, g: (r + b"\x00", b, g))
    emit("response_trailing_bytes", "wire", raw_mutate=lambda r, b, g: (r, b + b"\x00", g))
    emit("duplicate_request_key", "wire", raw_mutate=lambda r, b, g: (b"\xa7" + r[1:] + b"\x01\x01", b, g))
    emit("nonminimal_request_key", "wire", raw_mutate=lambda r, b, g: (r[:1] + b"\x18\x00" + r[2:], b, g))
    emit("indefinite_request", "wire", raw_mutate=lambda r, b, g: (b"\xbf" + r[1:] + b"\xff", b, g))
    emit("request_4097", "bounds", raw_mutate=lambda r, b, g: (r + b"\x00" * (4097 - len(r)), b, g))
    emit("response_65537", "bounds", raw_mutate=lambda r, b, g: (r, b + b"\x00" * (65537 - len(b)), g))
    return {
        "profile": "nbsr-connector-currentness-draft1",
        "runtime_authorized": False,
        "live_trust_authorized": False,
        "scope": "Outer wire/signatures/fixture authorization/time only. Not complete governance or real freshness.",
        "fixture_trust": "Public seeds 01*32 and 02*32; deterministic Q*32 challenge is NOT a live CSPRNG challenge.",
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build(), indent=2) + "\n").encode("utf-8")
    if args.check:
        if not VECTORS.is_file() or VECTORS.read_bytes() != raw:
            raise SystemExit("literal vector drift")
        print("Literal vectors reproducible")
    else:
        VECTORS.parent.mkdir(parents=True, exist_ok=True)
        VECTORS.write_bytes(raw)


if __name__ == "__main__":
    main()
