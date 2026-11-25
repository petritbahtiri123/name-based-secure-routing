"""Six-domain supplied-oracle fixtures; no signatures, runtime trust or permits.

Journal, cut commitments, record-verifier verdicts and restart floors are TEST
inputs. Equality with this oracle is not proof that a real source is complete.
The JSON format is a fixture format, not a proposed authority wire encoding.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "vectors/connector-source-coverage-draft1/vectors.json"
DOMAINS = tuple(f"C{i}" for i in range(1, 7))
VALID = "OFFLINE_COVERAGE_VALID"


class Rejected(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Rejected(reason)


def exact(value, keys):
    need(type(value) is dict and set(value) == set(keys), "schema")


def evaluate(case):
    # These selectors inject unavailable source / failed inner verification.
    # They are not flags accepted from a publisher or authenticated evidence.
    unavailable = case["supplied_unavailable"]
    unverified = case["supplied_unverified"]
    need(type(unavailable) is list and set(unavailable) <= set(DOMAINS), "schema")
    need(type(unverified) is list and set(unverified) <= set(DOMAINS), "schema")
    view, retained = case["view"], case["retained"]
    need(type(view) is dict and set(view) == set(DOMAINS), "domains")
    exact(retained, DOMAINS)
    now = case["supplied_upper_time"]
    need(type(now) is int and 0 <= now <= 253402300799, "schema")
    for domain in DOMAINS:
        entry = view[domain]
        exact(entry, ("source", "contract", "epoch", "revision", "commitment", "covered_through", "records", "denials", "future"))
        floor = retained[domain]
        exact(floor, ("epoch", "revision", "commitment", "denials"))
        need(type(floor["epoch"]) is int and type(floor["revision"]) is int, "schema")
        # Retained state is a known read-only test snapshot, never loaded from disk.
        need(floor == {"epoch": 1, "revision": 2, "commitment": domain + "-cut-2", "denials": [domain + "-denial"]}, "retained")
        need(domain not in unavailable, "unavailable")
        need(entry["source"] == domain + "-source" and entry["contract"] == domain + "-contract-v1", "binding")
        need(all(type(entry[k]) is int for k in ("epoch", "revision", "covered_through")), "schema")
        need(entry["epoch"] == 1 and entry["revision"] >= floor["revision"], "rollback")
        # Only two independently supplied cuts exist. Revision 3 attests an empty
        # interval after revision 2; changing a timestamp alone is not a new cut.
        revision = entry["revision"]
        need(revision in (2, 3), "unknown_cut")
        need(entry["commitment"] == f"{domain}-cut-{revision}", "conflict")
        cut = 1000 if revision == 2 else 1001
        need(entry["covered_through"] == cut, "conflict")
        need(cut <= now <= cut + 5, "freshness")
        need(entry["records"] == [domain + "-denial", domain + "-future"], "coverage")
        need(domain not in unverified, "record_verification")
        need(entry["denials"] == floor["denials"], "denial_retention")
        need(entry["future"] == [domain + "-future"], "future_retention")
    return VALID


def outcome(case):
    try:
        return evaluate(case)
    except Rejected as exc:
        return str(exc)
    except (KeyError, TypeError):
        return "schema"


def check():
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    need(
        data["profile"] == "connector-source-coverage-draft1"
        and data["runtime_authorized"] is False
        and data["live_trust_authorized"] is False,
        "manifest",
    )
    ids = set()
    good = 0
    for case in data["cases"]:
        need(case["id"] not in ids, "duplicate case")
        ids.add(case["id"])
        actual = outcome(case)
        need(actual == case["expected"], f"{case['id']}: expected {case['expected']}, got {actual}")
        good += actual == VALID
    return good, len(ids) - good


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    good, bad = check()
    print(f"{good} positive, {bad} negative; OFFLINE SUPPLIED ORACLES ONLY")
