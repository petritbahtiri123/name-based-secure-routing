"""Local amendment conformance; never produces runtime authority."""

import json
from copy import deepcopy

import pytest

from scripts.normal_revocation_conformance import AMENDMENT, VECTORS, build_vectors, check_case, load_profile


def test_explicit_amendment_and_all_literal_expectations():
    profile = load_profile("normal-revocation-conformance-v1")
    assert profile["named_policies"]["normal-revocation-v1"]["groups"] == [
        {"id": "normal-revocation", "required": 3, "eligible": 5, "class": "FEDERATION_AUTHORITY", "purpose": "REVOCATION"}
    ]


@pytest.mark.parametrize("case", build_vectors(), ids=lambda case: case["name"])
def test_literal_expectation(case):
    before = deepcopy(case)
    assert check_case(case) == case["expected"]
    assert case == before


def test_retained_vectors_and_runtime_flags():
    retained = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert retained["cases"] == build_vectors()
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    assert amendment["runtime_enabled"] is amendment["live_enabled"] is False


@pytest.mark.parametrize("selection", [None, "", "global-trust-v1", "deny-only-emergency-v1"])
def test_no_implicit_selection_or_substitution(selection):
    with pytest.raises(ValueError, match="explicit"):
        load_profile(selection)
