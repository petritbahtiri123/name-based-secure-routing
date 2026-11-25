"""Six-domain coverage contract fixtures, not authenticated authority."""

import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_literal_coverage_vectors_and_reproduction():
    from scripts.generate_connector_source_coverage_vectors import build
    from scripts.verify_connector_source_coverage_vectors import check

    assert check() == (8, 84)
    assert (json.dumps(build(), indent=2) + "\n").encode() == (ROOT / "vectors/connector-source-coverage-draft1/vectors.json").read_bytes()


@pytest.mark.parametrize("domain", [f"C{i}" for i in range(1, 7)])
def test_omission_rejected_without_mutating_retained_state(domain):
    from scripts.generate_connector_source_coverage_vectors import baseline
    from scripts.verify_connector_source_coverage_vectors import outcome

    case = baseline()
    case["view"][domain]["records"].pop()
    retained = copy.deepcopy(case["retained"])
    assert outcome(case) == "coverage"
    assert case["retained"] == retained


def test_every_domain_has_independent_negative_and_positive_cases():
    from scripts.generate_connector_source_coverage_vectors import build

    data = build()
    assert data["runtime_authorized"] is data["live_trust_authorized"] is False
    ids = {c["id"] for c in data["cases"]}
    assert len(ids) == len(data["cases"])
    for domain in [f"C{i}" for i in range(1, 7)]:
        assert {
            f"{domain}-{kind}"
            for kind in (
                "missing",
                "omitted_record",
                "empty_response",
                "wrong_source",
                "wrong_contract",
                "rollback",
                "same_cut_conflict",
                "stale",
                "future_cut",
                "bool_revision",
                "lost_denial",
                "lost_future",
                "unverified_record",
                "source_outage",
                "empty_interval",
            )
        } <= ids


def test_expected_label_is_not_a_verifier_input():
    from scripts.generate_connector_source_coverage_vectors import baseline
    from scripts.verify_connector_source_coverage_vectors import outcome

    case = baseline()
    case["expected"] = "coverage"
    assert outcome(case) == "OFFLINE_COVERAGE_VALID"
    case["view"]["C4"]["records"] = []
    case["expected"] = "OFFLINE_COVERAGE_VALID"
    assert outcome(case) == "coverage"


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ("bool_floor", "schema"),
        ("extra_domain", "domains"),
        ("cross_domain_record", "coverage"),
        ("duplicate_record", "coverage"),
        ("unknown_epoch", "rollback"),
        ("unknown_cut", "unknown_cut"),
        ("missing_field", "schema"),
        ("restart_lost_denial", "retained"),
    ],
)
def test_contract_boundary_rejections(mutation, expected):
    from scripts.generate_connector_source_coverage_vectors import baseline
    from scripts.verify_connector_source_coverage_vectors import outcome

    c = baseline()
    e = c["view"]["C4"]
    if mutation == "bool_floor":
        c["retained"]["C4"]["epoch"] = True
    elif mutation == "extra_domain":
        c["view"]["C7"] = copy.deepcopy(e)
    elif mutation == "cross_domain_record":
        e["records"][0] = "C3-denial"
    elif mutation == "duplicate_record":
        e["records"].append(e["records"][0])
    elif mutation == "unknown_epoch":
        e["epoch"] = 2
    elif mutation == "unknown_cut":
        e["revision"] = 4
    elif mutation == "missing_field":
        del e["source"]
    elif mutation == "restart_lost_denial":
        c["retained"]["C4"]["denials"] = []
    before = copy.deepcopy(c)
    assert outcome(c) == expected
    assert c == before
