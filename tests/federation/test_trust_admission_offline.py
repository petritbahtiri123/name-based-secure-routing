import pytest
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from scripts import trust_admission_offline as admission


def test_composed_positive_and_idempotence():
    fixture = admission.build_fixture()
    state, context, candidate, proof = admission.inputs(fixture)
    result, updated = admission.admit(state, candidate, proof, context)
    assert result["crypto_decision"] == "ACCEPT"
    assert result["semantic_decision"] == "ACCEPT"
    assert result["fixture_state_changed"] is True
    assert updated.current.canonical_bytes() == candidate
    assert state.current.canonical_bytes() != candidate
    result, repeated = admission.admit(updated, candidate, proof, context)
    assert result["semantic_decision"] == "IDEMPOTENT"
    assert repeated.current.digest == updated.current.digest
    assert result["fixture_state_changed"] is False


@pytest.mark.parametrize(
    "case", ["payload", "scope", "lineage", "policy", "quorum", "signer", "expiry", "replay", "obligation", "lifecycle", "generation"]
)
def test_rejection_preserves_state(case):
    state, context, candidate, proof = admission.inputs(admission.build_fixture())
    envelope = decode_deterministic(proof)
    if case == "payload":
        value = decode_deterministic(candidate)
        value[40] -= 1
        candidate = encode_deterministic(value)
    elif case == "scope":
        envelope[6] = b"x" * 32
    elif case == "lineage":
        envelope[7][3] = b"x" * 32
    elif case == "policy":
        envelope[5][3] = "high-risk-global-root-v1"
    elif case == "quorum":
        envelope[9][0][2].pop()
    elif case == "signer":
        context["validation"]["accepted_authority_registry"][0]["revoked"] = True
    elif case == "expiry":
        context["validation"]["now"] += 10000
    elif case == "replay":
        context["validation"]["expected_request_event_transition_id"] = "ab" * 16
    elif case == "obligation":
        context["obligations"].pop("transparency")
    elif case == "lifecycle":
        context["lifecycles"] = {}
    elif case == "generation":
        value = decode_deterministic(candidate)
        value[4] += 1
        candidate = encode_deterministic(value)
    result, after = admission.admit(state, candidate, encode_deterministic(envelope), context)
    assert result["semantic_decision"] in {"REJECT", "PENDING"}
    assert result["fixture_state_changed"] is False
    assert after is state


def test_authenticated_conflict_retained_without_replacing_current():
    state, context, candidate, proof = admission.inputs(admission.build_fixture())
    _, accepted = admission.admit(state, candidate, proof, context)
    value = decode_deterministic(candidate)
    value[40] -= 1
    conflict = encode_deterministic(value)
    conflict_proof, _ = admission.sign_candidate(conflict)
    result, after = admission.admit(accepted, conflict, conflict_proof, context)
    assert result["crypto_decision"] == "ACCEPT"
    assert result["semantic_decision"] == "QUARANTINE"
    assert after.current.digest == accepted.current.digest
    assert len(after.conflicts) == 2
    assert accepted.conflicts == ()


def test_retained_fixture_matches_builder():
    assert admission.load_fixture() == admission.build_fixture()


def test_missing_obligation_snapshot_is_pending():
    state, context, candidate, proof = admission.inputs(admission.build_fixture())
    del context["obligations"]
    result, after = admission.admit(state, candidate, proof, context)
    assert result["semantic_decision"] == "PENDING"
    assert after is state


@pytest.mark.parametrize("proof", [b"", b"\xff", b"\xa1", b"\x00", b"x" * 65537], ids=["empty", "break", "truncated", "scalar", "oversize"])
def test_malformed_proof_does_not_escape_or_mutate(proof):
    state, context, candidate, _ = admission.inputs(admission.build_fixture())
    result, after = admission.admit(state, candidate, proof, context)
    assert result["semantic_decision"] == "REJECT"
    assert after is state


@pytest.mark.parametrize("case", ["inactive_governance", "trust_change", "rollback", "noncanonical", "missing_selection", "session"])
def test_additional_boundaries(case):
    state, context, candidate, proof = admission.inputs(admission.build_fixture())
    if case == "inactive_governance":
        del context["lifecycles"][b"c4-k5"]  # Unsigned eligible member also checked.
    elif case == "trust_change":
        value = decode_deterministic(candidate)
        value[41] = b"q" * 32
        candidate = encode_deterministic(value)
        proof, _ = admission.sign_candidate(candidate)
    elif case == "rollback":
        _, state = admission.admit(state, candidate, proof, context)
        candidate = bytes.fromhex(admission.build_fixture()["artifacts"]["current"]["hex"])
        proof, _ = admission.sign_candidate(candidate)
    elif case == "noncanonical":
        candidate += b"\x00"
    elif case == "missing_selection":
        context["selection"] = "runtime"
    elif case == "session":
        context["validation"]["authenticated_session_transcript_digest"] = "11" * 32
    result, after = admission.admit(state, candidate, proof, context)
    assert result["semantic_decision"] == "REJECT"
    assert after is state
