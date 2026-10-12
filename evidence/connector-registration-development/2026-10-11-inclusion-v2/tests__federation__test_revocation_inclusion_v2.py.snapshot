import hashlib
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import FederationValidationError, KeyPurpose
from nbsr.federation.revocation import TypedRevocationRecord
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1
from scripts import normal_revocation_conformance as normal
from scripts import verify_federation_threshold_container_fixtures as oracle
from scripts.revocation_inclusion_v2 import make_fixture, verify_package


def mutate_package(raw, change):
    package = decode_deterministic(raw)
    change(package)
    return encode_deterministic(package)


def resign_log(package, field, change):
    cose = decode_deterministic(package[field][1:])
    payload = decode_deterministic(cose[2])
    change(payload)
    package[field] = sign1(encode_deterministic(payload), b"log-key", Ed25519PrivateKey.from_private_bytes(bytes(range(32))))


def test_forward_and_idempotent_reuse_preserve_exact_record():
    raw, context, initial = make_fixture()
    result, accepted = verify_package(raw, context, initial)
    assert result["decision"] == "ACCEPT"
    assert result["runtime_authority"] is False
    assert accepted != initial
    result, repeated = verify_package(raw, context, accepted)
    assert result["decision"] == "IDEMPOTENT"
    assert repeated is accepted


@pytest.mark.parametrize("count", [3, 4, 5])
@pytest.mark.parametrize("required", [2, 3])
@pytest.mark.parametrize("enforcement", range(5))
def test_exact_typed_enforcement_and_both_witness_policies(count, required, enforcement):
    raw, context, state = make_fixture(count=count, required=required, enforcement=enforcement)
    result, accepted = verify_package(raw, context, state)
    assert result["decision"] == "ACCEPT"
    assert result["typed_enforcement"] == enforcement
    record = decode_deterministic(raw)[3]
    assert accepted.record == record
    assert accepted.retained_revocations == frozenset({hashlib.sha256(record).digest()})


@pytest.mark.parametrize("field", [4, 5, 6, 7, 9])
def test_bad_signatures_or_threshold_encoding_reject_before_mutation(field):
    raw, context, state = make_fixture()
    bad = mutate_package(raw, lambda p: p.update({field: p[field][:-1] + bytes([p[field][-1] ^ 1])}))
    result, unchanged = verify_package(bad, context, state)
    assert result["decision"] == "REJECT"
    assert unchanged is state


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update({1: True}),
        lambda p: p.update({1: 2}),
        lambda p: p.update({2: "nbsr-federation-dev-v1"}),
        lambda p: p.update({10: None}),
        lambda p: p.update({3: p[3] + b"\x00"}),
        lambda p: p.update({8: p[8][:1]}),
        lambda p: p.update({8: p[8][::-1]}),
        lambda p: p.update({8: [p[8][0], p[8][0]]}),
        lambda p: resign_log(p, 6, lambda x: x.update({37: b"X" * 32})),
        lambda p: resign_log(p, 6, lambda x: x.update({34: b"X" * 32})),
        lambda p: resign_log(p, 6, lambda x: x.update({40: None})),
        lambda p: resign_log(p, 6, lambda x: x.update({40: 5})),
        lambda p: resign_log(p, 6, lambda x: x.update({38: [b"X" * 32]})),
        lambda p: resign_log(p, 7, lambda x: x.update({34: b"X" * 32})),
        lambda p: resign_log(p, 5, lambda x: x.update({38: b"X" * 32})),
        lambda p: resign_log(p, 9, lambda x: x.update({36: x[36] - 1})),
    ],
    ids=[
        "bool-version",
        "version",
        "profile",
        "unknown-field",
        "noncanonical-record",
        "insufficient-witnesses",
        "witness-order",
        "duplicate-witness",
        "wrong-leaf",
        "wrong-proof-checkpoint",
        "null-object-class",
        "wrong-object-class",
        "wrong-path",
        "wrong-consistency-anchor",
        "wrong-checkpoint-anchor",
        "different-signed-anchor",
    ],
)
def test_structural_and_correctly_signed_binding_failures(change):
    raw, context, state = make_fixture()
    result, unchanged = verify_package(mutate_package(raw, change), context, state)
    assert result["decision"] == "REJECT"
    assert unchanged is state


@pytest.mark.parametrize(
    "changes",
    [
        {2: 1},
        {2: True},
        {37: 1},
        {37: 3},
        {36: True},
        {39: {1: b"L" * 32, 2: b"X" * 32, 3: 0, 4: None}},
        {39: {1: b"L" * 32, 2: b"X" * 32, 3: 0, 4: b"P" * 32}},
        {5: 2, 8: b"P" * 32},
    ],
)
def test_even_fully_resigned_wrong_record_semantics_reject(changes):
    raw, context, state = make_fixture(record_changes=changes)
    result, unchanged = verify_package(raw, context, state)
    assert result["decision"] == "REJECT"
    assert unchanged is state


def test_default_historical_verifiers_reject_new_profile_and_record_version():
    raw, context, _ = make_fixture()
    package = decode_deterministic(raw)
    profile = normal.load_profile(normal.SELECTION)
    assert oracle.verify_literal(package[4], context["validation"], profile) == ("REJECT", "ERR_VERSION", False)
    with pytest.raises(FederationValidationError, match="version"):
        TypedRevocationRecord.from_bytes(package[3])
    assert oracle.verify_literal(package[4], context["validation"], profile, expected_profile_id="unknown")[0] == "REJECT"


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.update(profile="nbsr-federation-dev-v1"),
        lambda c: c.update(accepted_anchor=b"X" * 32),
        lambda c: c["validation"].update(authenticated_session_transcript_digest="aa" * 32),
        lambda c: c["validation"].update(expected_request_event_transition_id="aa" * 16),
        lambda c: c["validation"].update(agreed_profile_id="nbsr-federation-dev-v1"),
        lambda c: c["witness_replays"].update({b"\x01" * 32: b"X" * 16}),
        lambda c: c.update(required_witnesses=2.0),
        lambda c: c.update(log_authority=replace(c["log_authority"], purpose=KeyPurpose.WITNESS)),
        lambda c: c.update(log_authority=replace(c["log_authority"], revoked=True)),
        lambda c: c.update(control_domains={k: "shared" for k in c["control_domains"]}),
    ],
    ids=[
        "selection",
        "accepted-anchor",
        "session-replay",
        "event-replay",
        "negotiated-profile",
        "witness-replay",
        "threshold-type",
        "log-purpose",
        "revoked-log",
        "common-control-roster",
    ],
)
def test_independent_context_not_selected_by_package(change):
    raw, context, state = make_fixture()
    change(context)
    result, unchanged = verify_package(raw, context, state)
    assert result["decision"] == "REJECT"
    assert unchanged is state


def test_stale_floor_and_expiry_never_undo_retained_terminal_denial():
    raw, context, initial = make_fixture(terminal=True)
    _, applied = verify_package(raw, context, initial)
    later = replace(applied, floor=b"F" * 32)
    result, unchanged = verify_package(raw, context, later)
    assert result["decision"] == "REJECT" and unchanged is later
    assert unchanged.retained_revocations == applied.retained_revocations
    context["validation"]["now"] += 901
    result, unchanged = verify_package(raw, context, applied)
    assert result["decision"] == "REJECT" and unchanged is applied
    assert unchanged.retained_revocations


def test_retained_record_with_rolled_back_floor_cannot_claim_idempotent_success():
    raw, context, initial = make_fixture()
    _, applied = verify_package(raw, context, initial)
    rollback = replace(applied, floor=initial.floor)
    result, unchanged = verify_package(raw, context, rollback)
    assert result["decision"] == "REJECT"
    assert unchanged is rollback and unchanged.retained_revocations


def test_equivocation_or_replayed_event_cannot_replace_record():
    raw, context, initial = make_fixture()
    _, applied = verify_package(raw, context, initial)
    different, other_context, _ = make_fixture(enforcement=1)
    # Place floor at this independent candidate's anchor to reach event/lineage
    # checks; retained record/replay/denial information must still be respected.
    candidate_floor = replace(applied, floor=initial.floor)
    result, unchanged = verify_package(different, other_context, candidate_floor)
    assert result["decision"] == "REJECT" and unchanged is candidate_floor


def test_new_event_on_identical_record_is_retained_without_reapplying_revocation():
    raw, context, initial = make_fixture()
    _, applied = verify_package(raw, context, initial)
    reused, replay_context, _ = make_fixture(event_id=b"E" * 16)
    result, remembered = verify_package(reused, replay_context, applied)
    assert result["decision"] == "IDEMPOTENT"
    assert remembered.retained_revocations == applied.retained_revocations
    successor, successor_context, _ = make_fixture(previous_package=raw, event_id=b"E" * 16)
    # The successor is otherwise valid under an unused event ID.
    assert verify_package(successor, successor_context, applied)[0]["decision"] == "ACCEPT"
    result, unchanged = verify_package(successor, successor_context, remembered)
    assert result["decision"] == "REJECT"
    assert unchanged is remembered


def test_oversized_or_missing_package_and_pending_obligations_do_not_mutate():
    raw, context, state = make_fixture()
    for candidate in (b"x" * 65537, b"", None):
        result, unchanged = verify_package(candidate, context, state)
        assert result["decision"] == "REJECT" and unchanged is state
    context["obligations"]["other-required"] = "missing"
    result, unchanged = verify_package(raw, context, state)
    assert result["decision"] == "PENDING" and unchanged is state
