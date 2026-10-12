"""Composition of existing verifiers under explicit public test configuration."""

from copy import deepcopy
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import FederationAuthority, KeyLifecycle, KeyPurpose
from nbsr.federation.transparency import EMPTY_TREE_ROOT, leaf_hash
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1
from scripts import render_federation_threshold_container as render
from scripts import verify_federation_threshold_container_fixtures as oracle
from scripts.normal_revocation_conformance import GROUP, check_case, signed_case
from scripts.normal_revocation_witness_conformance import WitnessFixtureInputs, check_witness_bound_case


def bound_fixture(*, required=2, sequence=2, predecessor=None, checkpoint_age=0, enforcement=4):
    case = signed_case(enforcement=enforcement)
    payload = decode_deterministic(bytes.fromhex(case["record_hex"]))
    now = case["validation_context"]["now"]
    log = b"L" * 32
    # Exact existing public test materials from test_transparency.py and
    # test_witness_thresholds.py; no private-key generation or provisioning.
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    log_authority = FederationAuthority(
        b"log-key",
        private.public_key(),
        log,
        KeyPurpose.TRANSPARENCY_LOG,
        KeyLifecycle.ACTIVE,
        1,
        1,
        1700000000,
        1900000000,
        False,
    )
    old = {
        1: 6,
        2: 1,
        3: {1: 5, 2: log, 3: b"log-key", 4: log},
        4: 1,
        5: 1,
        32: log,
        33: payload[33],
        34: 0,
        35: EMPTY_TREE_ROOT,
        36: now - 1,
        37: b"log-key",
        38: None,
        39: None,
    }
    checkpoint = {
        **old,
        5: sequence,
        34: 1,
        35: leaf_hash(b"retained fixture log entry"),
        36: now - checkpoint_age,
        38: render.digest(old) if predecessor is None else predecessor,
    }
    proof = {
        1: 8,
        2: 1,
        32: log,
        33: payload[33],
        34: render.digest(old),
        35: render.digest(checkpoint),
        36: 0,
        37: 1,
        38: EMPTY_TREE_ROOT,
        39: checkpoint[35],
        40: [],
        41: 1,
    }
    payload[39] = {1: log, 2: render.digest(checkpoint), 3: 1, 4: None}
    case["record_hex"] = encode_deterministic(payload).hex()
    value = decode_deterministic(bytes.fromhex(case["envelope_hex"]))
    value[4] = render.digest(payload)
    context = oracle.expected_signature_context(value, GROUP, oracle.capability_session_binding(case["validation_context"]))
    entries = [render.signer(GROUP, 4, 12, i, context)[0] for i in range(1, 4)]
    value[9][0][2] = sorted(entries, key=lambda item: (item[1], item[2], item[3], item[4]))
    case["envelope_hex"] = encode_deterministic(value).hex()
    configured, contexts, messages = {}, {}, []
    for i in range(1, (3 if required == 2 else 5) + 1):
        identity, kid = bytes([i]) * 32, bytes([i])
        key = Ed25519PrivateKey.from_private_bytes(bytes([i]) * 32)
        organization = f"accepted-control-{i}"
        authority = FederationAuthority(
            kid, key.public_key(), identity, KeyPurpose.WITNESS, KeyLifecycle.ACTIVE, 1, 1, 1700000000, 1900000000, False
        )
        statement = {
            1: 9,
            2: 1,
            32: identity,
            33: log,
            34: payload[33],
            35: render.digest(checkpoint),
            36: 1,
            37: checkpoint[35],
            38: now - 1,
            39: 1,
            40: bytes([i]) * 16,
            41: kid,
            42: now + 100,
        }
        configured[identity] = (organization, kid)
        contexts[identity] = statement[40]
        if i <= required:
            messages.append((sign1(encode_deterministic(statement), kid, key), authority, organization))
    return case, WitnessFixtureInputs(
        sign1(encode_deterministic(checkpoint), b"log-key", private),
        log_authority,
        tuple(messages),
        configured,
        contexts,
        required,
        900,
        sign1(encode_deterministic(old), b"log-key", private),
        sign1(encode_deterministic(proof), b"log-key", private),
    )


def test_missing_witness_evidence_cannot_be_replaced_by_fixture_status():
    case = signed_case()
    assert check_case(case)["decision"] == "ACCEPT"
    assert check_witness_bound_case(case, None)["decision"] == "PENDING"


@pytest.mark.parametrize("required", [2, 3])
@pytest.mark.parametrize("enforcement", range(5))
def test_existing_signed_witness_and_checkpoint_verifiers_compose_without_authority(required, enforcement):
    case, evidence = bound_fixture(required=required, enforcement=enforcement)
    before = deepcopy(case)
    result = check_witness_bound_case(case, evidence)
    assert result == {
        "decision": "ACCEPT",
        "reason": "NONE",
        "typed_enforcement": enforcement,
        "runtime_authority": False,
        "mutation": False,
    }
    assert case == before


@pytest.mark.parametrize(
    "change",
    [
        lambda e: replace(e, checkpoint_message=e.checkpoint_message[:-1] + bytes([e.checkpoint_message[-1] ^ 1])),
        lambda e: replace(e, log_authority=replace(e.log_authority, purpose=KeyPurpose.WITNESS)),
        lambda e: replace(e, log_authority=replace(e.log_authority, revoked=True)),
        lambda e: replace(e, consistency_message=None),
        lambda e: replace(e, consistency_message=e.consistency_message[:-1] + bytes([e.consistency_message[-1] ^ 1])),
        lambda e: replace(e, previous_checkpoint_message=None),
        lambda e: replace(e, witness_messages=e.witness_messages[:1]),
        lambda e: replace(e, witness_messages=(e.witness_messages[0], e.witness_messages[0])),
        lambda e: replace(e, replay_contexts={**e.replay_contexts, b"\x01" * 32: b"X" * 16}),
        lambda e: replace(e, configured_witnesses={}),
        lambda e: replace(e, required=2.0),
        lambda e: replace(e, maximum_staleness=-1),
    ],
    ids=[
        "bad-log-signature",
        "wrong-log-purpose",
        "revoked-log",
        "missing-consistency",
        "bad-consistency-signature",
        "missing-prior-floor",
        "insufficient-witnesses",
        "duplicate-witness",
        "witness-replay",
        "unconfigured-witnesses",
        "noninteger-threshold",
        "invalid-staleness",
    ],
)
def test_invalid_signed_evidence_or_context_rejects(change):
    case, evidence = bound_fixture()
    assert check_witness_bound_case(case, change(evidence))["decision"] == "REJECT"


@pytest.mark.parametrize(
    "options",
    [
        {"sequence": 3},
        {"predecessor": b"X" * 32},
        {"checkpoint_age": 901},
    ],
    ids=["sequence-gap", "wrong-predecessor", "stale-checkpoint"],
)
def test_correctly_signed_invalid_checkpoint_cannot_satisfy_obligation(options):
    case, evidence = bound_fixture(**options)
    assert check_witness_bound_case(case, evidence)["decision"] == "REJECT"


def test_stale_idempotent_checkpoint_does_not_bypass_freshness():
    case, evidence = bound_fixture(checkpoint_age=901)
    evidence = replace(evidence, previous_checkpoint_message=evidence.checkpoint_message, consistency_message=None)
    assert check_witness_bound_case(case, evidence)["decision"] == "REJECT"


@pytest.mark.parametrize("kind", ["bad-signature", "wrong-purpose", "common-control"])
def test_witness_signature_purpose_and_accepted_control_identity(kind):
    case, evidence = bound_fixture()
    messages = list(evidence.witness_messages)
    message, authority, organization = messages[1]
    configured = dict(evidence.configured_witnesses)
    if kind == "bad-signature":
        message = message[:-1] + bytes([message[-1] ^ 1])
    elif kind == "wrong-purpose":
        authority = replace(authority, purpose=KeyPurpose.REVOCATION)
    else:
        organization = messages[0][2]
        configured[authority.operator_id] = (organization, authority.kid)
    messages[1] = message, authority, organization
    assert (
        check_witness_bound_case(case, replace(evidence, witness_messages=tuple(messages), configured_witnesses=configured))["decision"]
        == "REJECT"
    )


def test_signed_checkpoint_does_not_satisfy_unrelated_record_reference_or_other_obligations():
    case, evidence = bound_fixture()
    assert check_witness_bound_case(signed_case(), evidence)["decision"] == "REJECT"
    case["governing_fixture"]["applicable_obligations"]["other-required-policy"] = "missing"
    assert check_witness_bound_case(case, evidence)["decision"] == "PENDING"
