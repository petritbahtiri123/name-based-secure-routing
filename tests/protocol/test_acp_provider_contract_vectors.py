"""Offline provider seam traces. Supplied verdicts are not authority proofs."""

import copy
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "vectors/acp-provider-contract-draft1/vectors.json"


def test_literal_provider_traces():
    from scripts.verify_acp_provider_contract_vectors import check

    assert check() == (6, 22)


def test_rejects_leave_ownership_and_consumption_unchanged():
    from scripts.verify_acp_provider_contract_vectors import step

    state = {"phase": "uncertain", "binding": ["subject-a", "request-a"], "credential": "credential-a"}
    before = copy.deepcopy(state)
    result, after = step(state, {"op": "begin", "subject": "subject-b", "request": "request-b", "entitled": True})
    assert result == "blocked"
    assert after == before == state


@pytest.mark.parametrize("field", ["inner_verified", "stored", "clock_valid", "signer_authorized", "policy_narrows"])
def test_truthy_values_are_not_verifier_success(field):
    from scripts.verify_acp_provider_contract_vectors import step

    data = json.loads(PATH.read_text(encoding="utf-8"))
    event = copy.deepcopy(next(c for c in data["cases"] if c["id"] == "publish_valid")["events"][0])
    event[field] = 1
    assert step({"phase": "pristine", "binding": None, "credential": None}, event)[0] == "publication_blocked"


@pytest.mark.parametrize("change", ["credential", "negative_commit", "boolean_commit"])
def test_uncertain_reconciliation_never_resets_consumption(change):
    from scripts.verify_acp_provider_contract_vectors import step

    state = {"phase": "uncertain", "binding": ["subject-a", "request-a"], "credential": "credential-a"}
    event = {
        "op": "reconcile",
        "binding": ["subject-a", "request-a"],
        "credential": "credential-a",
        "authenticated": True,
        "committed": True,
    }
    if change == "credential":
        event["credential"] = "credential-b"
    elif change == "negative_commit":
        event["committed"] = False
    else:
        event["committed"] = 1
    result, after = step(state, event)
    assert result == "blocked"
    assert state == after


@pytest.mark.parametrize("phase", ["pending", "uncertain"])
def test_unsettled_enrollment_blocks_publication(phase):
    from scripts.verify_acp_provider_contract_vectors import step

    data = json.loads(PATH.read_text(encoding="utf-8"))
    event = next(c for c in data["cases"] if c["id"] == "publish_valid")["events"][0]
    state = {"phase": phase, "binding": ["subject-a", "request-a"], "credential": "credential-a"}
    result, after = step(state, event)
    assert result == "publication_blocked"
    assert state == after
