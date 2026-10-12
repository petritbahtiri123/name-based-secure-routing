"""Approved v2 local conformance only. No runtime provider or durable state.

Signatures and Merkle membership cover the exact original v2 record bytes.
The immutable returned state is a test transaction oracle, not deployed storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import FederationAuthority, FederationValidationError, KeyLifecycle, KeyPurpose, ObjectType
from nbsr.federation.cose import authenticate_witness_sign1, verify_federation_sign1
from nbsr.federation.revocation import TypedRevocationRecord
from nbsr.federation.transparency import EMPTY_TREE_ROOT, TransparencyVerifier, leaf_hash, node_hash, verify_witness_threshold
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1
from scripts import normal_revocation_conformance as normal
from scripts import render_federation_threshold_container as render
from scripts import verify_federation_threshold_container_fixtures as oracle

PROFILE = "nbsr-federation-revocation-inclusion-dev-v1"
ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = ROOT / "docs/protocol/registries/revocation-inclusion-local-v2.json"
VECTORS = ROOT / "vectors/revocation-inclusion-local-v2/packages.json"


@dataclass(frozen=True)
class FixtureState:
    floor: bytes
    record: bytes | None = None
    retained_revocations: frozenset[bytes] = frozenset()
    requests: tuple[tuple[bytes, bytes], ...] = ()


def load_profile():
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    if amendment["profile"] != PROFILE or amendment["runtime_enabled"] is not False or amendment["live_enabled"] is not False:
        raise ValueError("invalid local amendment")
    for name, expected in amendment["parent_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("parent drift")
    return normal.load_profile(normal.SELECTION)


def parse_record(raw):
    if type(raw) is not bytes or len(raw) > 32768:
        raise ValueError("record size")
    value = decode_deterministic(raw)
    if type(value) is not dict or any(type(k) is not int for k in value) or type(value.get(2)) is not int or value[2] != 2:
        raise ValueError("v2 required")
    if type(value.get(1)) is not int or value[1] != 13 or value.get(37) != 2:
        raise ValueError("normal class/mode required")
    # Reuse v1 field validators for the unchanged fields ONLY. This temporary
    # syntax view is never signed, hashed, logged, returned as authority, or used
    # for record identity/lineage. All binding operations below use original raw.
    TypedRevocationRecord.from_bytes(encode_deterministic({**value, 2: 1}))
    if value[3][1] != 4 or value[39][4] is not None:
        raise ValueError("normal issuer/prior anchor required")
    return value


def verify_package(raw, context, state):
    """Every rejection returns the exact input state; commit is the final step."""

    def result(decision, reason, enforcement=None, changed=False):
        return {
            "decision": decision,
            "reason": reason,
            "typed_enforcement": enforcement,
            "runtime_authority": False,
            "fixture_state_changed": changed,
        }

    try:
        if type(raw) is not bytes or len(raw) > 65536 or type(state) is not FixtureState:
            raise ValueError("package bound/state")
        if context["profile"] != PROFILE:
            raise ValueError("explicit profile required")
        package = decode_deterministic(raw)
        if type(package) is not dict or set(package) != set(range(1, 10)) or any(type(k) is not int for k in package):
            raise ValueError("closed package")
        if type(package[1]) is not int or package[1] != 1 or package[2] != PROFILE:
            raise ValueError("package version/profile")
        if any(type(package[k]) is not bytes for k in (3, 4, 5, 6, 7, 9)):
            raise ValueError("artifact bytes")
        if type(package[8]) is not list or not 2 <= len(package[8]) <= 5 or any(type(x) is not bytes for x in package[8]):
            raise ValueError("witness bounds")
        record = parse_record(package[3])
        digest = hashlib.sha256(package[3]).digest()
        value = decode_deterministic(package[4])
        if value[5][3] != normal.NAME or len(value[5][5]) != 1 or len(value[9]) != 1:
            raise ValueError("single approved normal group")
        if value[4] != digest or value[6] != render.digest(record[33]) or value[7] != {1: record[4], 2: record[5], 3: record.get(8)}:
            raise ValueError("record binding")
        now = context["validation"]["now"]
        if type(now) is not int or not record[6] <= now <= record[7]:
            raise ValueError("record freshness")
        decision, reason, _ = oracle.verify_literal(package[4], context["validation"], load_profile(), expected_profile_id=PROFILE)
        if decision != "ACCEPT":
            return result(decision, reason), state
        controls = context["control_domains"]
        if (
            set(controls) != {v.hex() for v in value[5][5][0][6]}
            or any(type(v) is not str or not v for v in controls.values())
            or len(set(controls.values())) != 5
        ):
            raise ValueError("independent eligible roster")
        if not context["obligations"] or any(v != "satisfied-fixture" for v in context["obligations"].values()):
            return result("PENDING", "ERR_EVIDENCE_MISSING"), state

        def signed(message, kind):
            if len(message) > 65536:
                raise ValueError("signed size")
            return verify_federation_sign1(message, context["log_authority"], kind, now, expected_key_purpose=KeyPurpose.TRANSPARENCY_LOG)

        anchor = signed(package[9], ObjectType.TransparencyCheckpoint)
        checkpoint = signed(package[5], ObjectType.TransparencyCheckpoint)
        inclusion = signed(package[6], ObjectType.InclusionProof)
        consistency = signed(package[7], ObjectType.ConsistencyProof)
        if anchor.digest != context["accepted_anchor"] or state.floor not in (anchor.digest, checkpoint.digest):
            raise ValueError("retained floor/anchor")
        if record[39] != {1: anchor.log_id, 2: anchor.digest, 3: anchor.tree_size, 4: None} or record[33] != anchor.scope.to_mapping():
            raise ValueError("exact prior anchor")
        if checkpoint.tree_size <= anchor.tree_size or inclusion._payload[36] < anchor.tree_size or inclusion._payload[40] != 13:
            raise ValueError("post-anchor exact-class inclusion")
        staleness = context["maximum_staleness"]
        if type(staleness) is not int or staleness < 0:
            raise ValueError("staleness")
        checkpoint.require_fresh(now, maximum_staleness=staleness)
        if (
            TransparencyVerifier(anchor).accept_checkpoint(checkpoint, now=now, consistency=consistency, maximum_staleness=staleness)
            != "ACCEPT"
        ):
            raise ValueError("forward consistency")
        inclusion.verify(checkpoint, canonical_leaf=package[3], now=now, maximum_staleness=staleness)
        required = context["required_witnesses"]
        if type(required) is not int or required not in (2, 3):
            raise ValueError("witness policy")
        if not 2 <= len(context["witness_authorities"]) <= 5:
            raise ValueError("configured signer bound")
        witness_keys = {a.kid: (a, organization) for a, organization in context["witness_authorities"]}
        if len(witness_keys) != len(context["witness_authorities"]):
            raise ValueError("ambiguous witness key")
        witnesses = []
        for message in package[8]:
            # Resolve only from independently supplied accepted configuration.
            if not message.startswith(b"\xd2"):
                raise ValueError("tagged witness required")
            cose = decode_deterministic(message[1:])
            protected = decode_deterministic(cose[0])
            authority, organization = witness_keys[protected[4]]
            witnesses.append(authenticate_witness_sign1(message, authority, organization, now))
        order = [(w.authority_identity, w.signer_kid) for w in witnesses]
        if order != sorted(set(order)):
            raise ValueError("canonical witness order")
        verify_witness_threshold(
            witnesses,
            checkpoint,
            required,
            now=now,
            replay_contexts=context["witness_replays"],
            configured_witnesses=context["configured_witnesses"],
        )
        event = value[8][2]
        if any(previous == event and bound != digest for previous, bound in state.requests):
            raise ValueError("event replay")
        if state.record is not None:
            previous = parse_record(state.record)
            previous_digest = hashlib.sha256(state.record).digest()
            if digest == previous_digest:
                if state.floor != checkpoint.digest:
                    raise ValueError("applied record floor rolled back")
                if (event, digest) not in state.requests:
                    remembered = replace(state, requests=state.requests + ((event, digest),))
                    return result("IDEMPOTENT", "NONE", record[36], True), remembered
                return result("IDEMPOTENT", "NONE", record[36]), state
            if previous[35] or record[32] != previous[32] or record[33] != previous[33]:
                raise ValueError("terminal/target identity")
            # This local slice supports ordinary same-generation updates only;
            # recovery/new-generation evidence is outside its authority.
            if record[4] != previous[4] or record[5] != previous[5] + 1 or record.get(8) != previous_digest:
                raise ValueError("record lineage")
        elif (record[4], record[5]) != (1, 1):
            raise ValueError("missing record floor")
        next_state = FixtureState(checkpoint.digest, package[3], state.retained_revocations | {digest}, state.requests + ((event, digest),))
        return result("ACCEPT", "NONE", record[36], True), next_state
    except (FederationValidationError, ValueError, TypeError, KeyError, IndexError):
        return result("REJECT", "ERR_AUTHORITY"), state


def make_fixture(
    *,
    count=3,
    required=2,
    enforcement=4,
    terminal=False,
    sequence=None,
    record_changes=None,
    previous_package=None,
    event_id=None,
    anchor_timestamp=None,
):
    """Existing public deterministic material only; generates no new keys."""
    case = normal.signed_case(count=count, enforcement=enforcement, terminal=terminal)
    record = decode_deterministic(bytes.fromhex(case["record_hex"]))
    now = case["validation_context"]["now"]
    log = b"L" * 32
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    authority = FederationAuthority(
        b"log-key", key.public_key(), log, KeyPurpose.TRANSPARENCY_LOG, KeyLifecycle.ACTIVE, 1, 1, 1700000000, 1900000000, False
    )
    anchor = {
        1: 6,
        2: 1,
        3: {1: 5, 2: log, 3: b"log-key", 4: log},
        4: 1,
        5: 1,
        32: log,
        33: record[33],
        34: 0,
        35: EMPTY_TREE_ROOT,
        36: now - 1 if anchor_timestamp is None else anchor_timestamp,
        37: b"log-key",
        38: None,
        39: None,
    }
    previous_raw = None
    if previous_package is not None:
        previous = decode_deterministic(previous_package)
        anchor = decode_deterministic(decode_deterministic(previous[5][1:])[2])
        previous_raw = previous[3]
        previous_record = decode_deterministic(previous_raw)
        if anchor[34] != 1:
            raise ValueError("fixture builder only covers one immediate successor")
        record[5], record[8] = previous_record[5] + 1, hashlib.sha256(previous_raw).digest()
    record[2] = 2
    record[39] = {1: log, 2: render.digest(anchor), 3: anchor[34], 4: None}
    record.update(record_changes or {})
    raw_record = encode_deterministic(record)
    tree_root = leaf_hash(raw_record) if previous_raw is None else node_hash(leaf_hash(previous_raw), leaf_hash(raw_record))
    checkpoint = {
        **anchor,
        5: anchor[5] + 1 if sequence is None else sequence,
        34: anchor[34] + 1,
        35: tree_root,
        36: now,
        38: render.digest(anchor),
    }
    inclusion = {
        1: 7,
        2: 1,
        32: log,
        33: record[33],
        34: render.digest(checkpoint),
        35: checkpoint[34],
        36: anchor[34],
        37: leaf_hash(raw_record),
        38: [] if previous_raw is None else [leaf_hash(previous_raw)],
        39: 1,
        40: 13,
    }
    consistency = {
        1: 8,
        2: 1,
        32: log,
        33: record[33],
        34: render.digest(anchor),
        35: render.digest(checkpoint),
        36: anchor[34],
        37: checkpoint[34],
        38: anchor[35],
        39: checkpoint[35],
        40: [] if previous_raw is None else [leaf_hash(raw_record)],
        41: 1,
    }
    validation = case["validation_context"]
    validation["agreed_profile_id"] = PROFILE
    envelope = decode_deterministic(bytes.fromhex(case["envelope_hex"]))
    envelope[2], envelope[4] = PROFILE, hashlib.sha256(raw_record).digest()
    envelope[6] = render.digest(record[33])
    envelope[7] = {1: record[4], 2: record[5], 3: record.get(8)}
    if event_id is not None:
        validation["expected_request_event_transition_id"] = event_id.hex()
        envelope[8][2] = event_id
        envelope[8][5] = render.digest({k: v for k, v in envelope[8].items() if k != 5})
    signature_context = oracle.expected_signature_context(envelope, normal.GROUP, oracle.capability_session_binding(validation))
    entries = [render.signer(normal.GROUP, 4, 12, i, signature_context)[0] for i in range(1, count + 1)]
    envelope[9][0][2] = sorted(entries, key=lambda e: (e[1], e[2], e[3], e[4]))
    messages, authorities, configured, replays = [], [], {}, {}
    for i in range(1, (3 if required == 2 else 5) + 1):
        identity, kid, organization = bytes([i]) * 32, bytes([i]), f"accepted-control-{i}"
        witness_key = Ed25519PrivateKey.from_private_bytes(bytes([i]) * 32)
        witness_authority = FederationAuthority(
            kid, witness_key.public_key(), identity, KeyPurpose.WITNESS, KeyLifecycle.ACTIVE, 1, 1, 1700000000, 1900000000, False
        )
        authorities.append((witness_authority, organization))
        configured[identity], replays[identity] = (organization, kid), bytes([i]) * 16
        statement = {
            1: 9,
            2: 1,
            32: identity,
            33: log,
            34: record[33],
            35: render.digest(checkpoint),
            36: checkpoint[34],
            37: checkpoint[35],
            38: now - 1,
            39: 1,
            40: replays[identity],
            41: kid,
            42: now + 100,
        }
        if i <= required:
            messages.append(sign1(encode_deterministic(statement), kid, witness_key))

    def signed(value):
        return sign1(encode_deterministic(value), b"log-key", key)

    package = {
        1: 1,
        2: PROFILE,
        3: raw_record,
        4: encode_deterministic(envelope),
        5: signed(checkpoint),
        6: signed(inclusion),
        7: signed(consistency),
        8: messages,
        9: signed(anchor),
    }
    context = {
        "profile": PROFILE,
        "validation": validation,
        "control_domains": case["governing_fixture"]["control_domains"],
        "obligations": case["governing_fixture"]["applicable_obligations"],
        "log_authority": authority,
        "witness_authorities": tuple(authorities),
        "configured_witnesses": configured,
        "witness_replays": replays,
        "required_witnesses": required,
        "maximum_staleness": 900,
        "accepted_anchor": render.digest(anchor),
    }
    return encode_deterministic(package), context, FixtureState(render.digest(anchor))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    cases = []
    for count in (3, 4, 5):
        for required in (2, 3):
            raw, context, state = make_fixture(count=count, required=required)
            result, accepted = verify_package(raw, context, state)
            assert result["decision"] == "ACCEPT"
            assert verify_package(raw, context, accepted)[0]["decision"] == "IDEMPOTENT"
            cases.append(
                {"normal_signers": count, "witnesses": required, "package_hex": raw.hex(), "sha256": hashlib.sha256(raw).hexdigest()}
            )
    text = (
        json.dumps({"runtime_enabled": False, "live_enabled": False, "scope": "local public fixture packages", "cases": cases}, indent=2)
        + "\n"
    )
    if args.check:
        if VECTORS.read_text(encoding="utf-8") != text:
            raise ValueError("retained package drift")
    else:
        VECTORS.parent.mkdir(parents=True, exist_ok=True)
        VECTORS.write_text(text, encoding="utf-8")
    print("6 retained v2 inclusion packages verified, forward and idempotent; runtime disabled")


if __name__ == "__main__":
    main()
