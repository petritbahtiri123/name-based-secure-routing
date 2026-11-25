"""Public-fixture-only checker for the currentness draft. No Authority/permit API.

Scope/keys/coverage/floors/clock are fixed or injected TEST inputs. The inner KAR
is an existing purpose-3 fixture, not a complete connector governing inventory.
This checker cannot establish provisioning, source completeness or live freshness.
"""

import argparse
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from nbsr.protocol.cbor import decode_deterministic as dec, encode_deterministic as enc
from nbsr.protocol.cose import verify_sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.fields import require_text_id
from nbsr.protocol.registry import ErrorCode

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "vectors/connector-currentness-draft1/vectors.json"
REQUEST = "NBSR-Connector-Currentness-Request-draft1"
RESPONSE = "NBSR-Connector-Currentness-Response-draft1"
STATUS = "NBSR-Connector-Publisher-Status-draft1"
PUB = bytes.fromhex("8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c")
AUTH = bytes.fromhex("8139770ea87d175f56a35466c34c7ecccb8d8a91b4ee37a25df60f5b8fc9b394")
MAX_TIME = 253402300799


def digest(value):
    return hashlib.sha256(enc(value)).digest()


def fixture(variant="default"):
    """Explicit test inputs, not an authenticated provisioning package."""
    kar = json.loads((ROOT / "crates/nbsr-transport/tests/fixtures/connector-kar-genesis-positive.json").read_text(encoding="utf-8"))
    scope = {0: b"O" * 32, 1: b"S" * 32, 2: "gateway-test", 3: b"P" * 32, 4: "connector-registration-development-v1"}
    domain, source = b"D" * 32, b"F" * 32
    ref = ["nbsr-federation-dev-v1", 2, bytes.fromhex(kar["payload_sha256"])]
    grant = {
        0: "NBSR-Connector-Publisher-Grant-draft1",
        1: 1,
        2: b"publisher",
        3: PUB,
        4: scope,
        5: [domain],
        6: 900,
        7: 1800,
        8: 1,
        9: b"status",
    }
    if variant in ("grant_24h", "grant_over_24h"):
        grant[7] = grant[6] + (86400 if variant == "grant_24h" else 86401)
    elif variant == "grant_not_yet_valid":
        grant[6] = 1004
    elif variant == "grant_expired":
        grant[7] = 1004
    elif variant == "kid_64":
        grant[2], grant[9] = b"p" * 64, b"s" * 64
    elif variant not in ("default", "anchor_expired", "evidence_expired"):
        raise Rejected("fixture selection")
    package = enc({0: "SUPPLIED-TEST-TRUST-ONLY", 1: grant, 2: AUTH})
    context = digest(["NBSR-Connector-Provisioning-Context-draft1", 1, package])
    floor = [[domain, 1, 1, b"C" * 32]]
    request = {
        0: REQUEST,
        1: 1,
        2: context,
        3: scope,
        4: b"Q" * 32,
        5: digest(["NBSR-Connector-Retained-State-draft1", 1, context, floor, [], []]),
    }
    state = {
        0: scope,
        1: [{0: ref, 1: bytes.fromhex(kar["wire"])}],
        2: [{0: domain, 1: source, 2: 1, 3: 1, 4: b"C" * 32, 5: 1000, 6: [ref]}],
        3: [],
        4: [],
        5: [ref],
    }
    return request, grant, state


class Rejected(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise Rejected(reason)


def integer(x, low=0, high=2**64 - 1):
    return type(x) is int and low <= x <= high


def exact(m, size):
    need(type(m) is dict and all(type(k) is int for k in m) and set(m) == set(range(size)), "schema")


def signed(wire, kid, public):
    need(type(wire) is bytes, "schema")
    try:
        verified = verify_sign1(wire, {kid: Ed25519PublicKey.from_public_bytes(public)}, ErrorCode.NBSR_E_RECORD_UNTRUSTED)
    except ProtocolViolation as exc:
        raise Rejected("signature") from exc
    return dec(verified.payload)


def sorted_refs(items, available):
    need(type(items) is list, "schema")
    encoded = [enc(r) for r in items]
    need(encoded == sorted(set(encoded)) and all(r in available for r in encoded), "state")


def evaluate(case):
    """Compare one literal against supplied test trust. Returns only a fixture label."""
    expected_request, expected_grant, expected_state = fixture(case.get("fixture", "default"))
    raw, response, grant_raw = (bytes.fromhex(case[k]) for k in ("request_hex", "response_hex", "grant_hex"))
    need(len(raw) <= 4096 and len(response) <= 65536, "bounds")
    request, grant, pair = dec(raw), dec(grant_raw), dec(response)
    exact(request, 6)
    need(request[0] == REQUEST and type(request[1]) is int and request[1] == 1, "binding")
    exact(request[3], 5)
    require_text_id(request[3][2])
    # Exact expected scope also rejects text normalization and ID type changes.
    need(request == expected_request, "binding")
    exact(grant, 10)
    need(all(type(grant[k]) is int for k in (1, 6, 7, 8)), "authorization")
    need(grant == expected_grant and PUB != AUTH, "authorization")
    need(type(pair) is list and len(pair) == 2, "schema")
    p = signed(pair[0], grant[2], PUB)
    a = signed(pair[1], grant[9], AUTH)
    exact(p, 10)
    exact(a, 13)
    need(p[0] == RESPONSE and a[0] == STATUS and type(p[1]) is int and type(a[1]) is int and p[1] == a[1] == 1, "binding")
    for obj in (p, a):
        need(
            obj[2] == request[2] and obj[3] == hashlib.sha256(raw).digest() and obj[4] == request[4] and obj[5] == digest(grant), "binding"
        )
    need(a[12] == "authorized", "authorization")
    state = p[6]
    exact(state, 6)
    exact(state[0], 5)
    need(state[0] == request[3], "binding")
    need(type(state[1]) is list and type(state[2]) is list, "schema")
    need(len(state[1]) <= 64 and len(state[2]) <= 16, "bounds")
    refs = []
    for artifact in state[1]:
        exact(artifact, 2)
        # Exact retained signed KAR, independently checked by its existing verifier.
        need(artifact == expected_state[1][0], "state")
        refs.append(enc(artifact[0]))
    need(refs == sorted(set(refs)) and refs, "state")
    for k in (3, 4, 5):
        sorted_refs(state[k], refs)
    need(state[3] == state[4] == [] and state[5] == expected_state[5], "state")
    need(len(state[2]) == 1, "state")
    coverage = state[2][0]
    exact(coverage, 7)
    for k in (0, 1, 2, 3, 4, 6):
        need(type(coverage[k]) is type(expected_state[2][0][k]) and coverage[k] == expected_state[2][0][k], "state")
    need(integer(coverage[5], 0, MAX_TIME), "schema")
    # This retained test cut cannot be advanced by changing only its timestamp.
    need(coverage[5] == 1000, "rollback")
    state_hash = digest(["NBSR-Connector-Currentness-State-draft1", 1, request[2], state])
    need(p[7] == a[6] == state_hash, "binding")
    need(integer(a[7], 1) and type(a[8]) is bytes and len(a[8]) == 32, "schema")
    need(a[7] == 2 and a[8] == b"A" * 32, "rollback")
    need(integer(a[9], 0, MAX_TIME), "schema")
    need(a[9] == 1000, "rollback")
    for obj, keys in ((p, (8, 9)), (a, (10, 11))):
        need(all(integer(obj[k], 0, MAX_TIME) for k in keys), "schema")
    clock = case["clock"]
    need(set(clock) == {"L", "U", "elapsed_ms"}, "schema")
    need(all(integer(clock[k], 0, MAX_TIME if k != "elapsed_ms" else 2**64 - 1) for k in clock), "schema")
    lower, upper = clock["L"], clock["U"]
    need(lower <= upper and upper - lower <= 2, "freshness")
    need(coverage[5] <= lower and a[9] <= lower, "freshness")
    for issued, until, cut in ((p[8], p[9], coverage[5]), (a[10], a[11], a[9])):
        need(cut <= issued <= upper and until <= min(issued + 30, cut + 30), "freshness")
    need(grant[6] <= lower and grant[7] - grant[6] <= 86400, "freshness")
    # Key/evidence limits are explicit fixed fixture inputs, not production trust.
    anchor_end = 1004 if case.get("fixture") == "anchor_expired" else 1800
    evidence_end = 1004 if case.get("fixture") == "evidence_expired" else 2000
    end = min(p[9], a[11], coverage[5] + 30, a[9] + 30, grant[7], anchor_end, evidence_end)
    need(upper < end, "freshness")
    mode = case.get("mode", "receive")
    if mode in ("receive", "same_cut_refresh"):
        need(upper - min(coverage[5], a[9]) <= 5 and clock["elapsed_ms"] < 3000, "freshness")
        if mode == "same_cut_refresh":
            # Earlier installation had E=1020; the same cut cannot extend it.
            need(end <= 1020, "freshness")
    elif mode == "use":
        # Simulated installation at U=1004, monotonic elapsed=0, E=1030.
        need(p[9] == a[11] == 1030 and clock["elapsed_ms"] < 26000, "freshness")
    else:
        raise Rejected("schema")
    return "OFFLINE_VECTOR_VALID"


def outcome(case):
    try:
        return evaluate(case)
    except Rejected as exc:
        return str(exc)
    except ProtocolViolation:
        return "wire"


def check():
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    need(
        data["profile"] == "nbsr-connector-currentness-draft1"
        and data["runtime_authorized"] is False
        and data["live_trust_authorized"] is False,
        "manifest",
    )
    from scripts.check_connector_kar_positive import check as check_inner

    check_inner()  # Public retained bytes only; no signing or key generation.
    ids = set()
    positive = 0
    for case in data["cases"]:
        need(case["id"] not in ids, "duplicate case")
        ids.add(case["id"])
        actual = outcome(case)
        need(actual == case["expected"], f"{case['id']}: expected {case['expected']}, got {actual}")
        positive += actual == "OFFLINE_VECTOR_VALID"
    return positive, len(ids) - positive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    good, bad = check()
    print(f"{good} positive, {bad} negative; OFFLINE VECTORS ONLY")
