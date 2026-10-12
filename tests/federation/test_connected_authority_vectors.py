from scripts.check_connected_authority_vectors import build


def test_connected_vectors_use_existing_verifier_and_no_runtime_authority():
    value = build()
    assert value["runtime_enabled"] is value["live_enabled"] is False
    assert {case["name"] for case in value["cases"]} >= {"deny", "terminate", "two-signers", "bad-signature"}
    assert sum(case["accepted"] for case in value["cases"]) >= 2


def test_connected_signed_schema_negatives_and_retained_anchor():
    cases = {case["name"]: case for case in build()["cases"]}
    for name in ("finite-terminal", "invalid-reason", "boolean-reason", "zero-validity", "timestamp-overflow"):
        assert cases[name]["python_decision"] == "REJECT"
        assert cases[name]["accepted"] is False
    assert cases["valid-terminal"]["accepted"] is True
    assert cases["old-retained-anchor"]["accepted"] is True


def test_fresh_event_pairs_are_idempotent_in_independent_oracle():
    pairs = build()["replays"]
    assert {pair["effect"] for pair in pairs} == {1, 4}
    assert all(pair["decision"] == "IDEMPOTENT" for pair in pairs)
