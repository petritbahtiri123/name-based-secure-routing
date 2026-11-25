"""Generate literal coverage fixtures without keys, network or authority proofs."""

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "vectors/connector-source-coverage-draft1/vectors.json"


def baseline():
    case = {
        "id": "complete",
        "expected": "OFFLINE_COVERAGE_VALID",
        "supplied_upper_time": 1004,
        "supplied_unavailable": [],
        "supplied_unverified": [],
        "view": {},
        "retained": {},
    }
    for number in range(1, 7):
        d = f"C{number}"
        case["view"][d] = {
            "source": d + "-source",
            "contract": d + "-contract-v1",
            "epoch": 1,
            "revision": 2,
            "commitment": d + "-cut-2",
            "covered_through": 1000,
            "records": [d + "-denial", d + "-future"],
            "denials": [d + "-denial"],
            "future": [d + "-future"],
        }
        case["retained"][d] = {"epoch": 1, "revision": 2, "commitment": d + "-cut-2", "denials": [d + "-denial"]}
    return case


def build():
    cases = [baseline()]
    advanced = baseline()
    advanced["id"] = "all_empty_intervals"
    for domain, entry in advanced["view"].items():
        entry.update(revision=3, commitment=domain + "-cut-3", covered_through=1001)
    cases.append(advanced)
    for number in range(1, 7):
        d = f"C{number}"
        for kind, expected in (
            ("missing", "domains"),
            ("omitted_record", "coverage"),
            ("empty_response", "coverage"),
            ("wrong_source", "binding"),
            ("wrong_contract", "binding"),
            ("rollback", "rollback"),
            ("same_cut_conflict", "conflict"),
            ("stale", "freshness"),
            ("future_cut", "conflict"),
            ("bool_revision", "schema"),
            ("lost_denial", "denial_retention"),
            ("lost_future", "future_retention"),
            ("unverified_record", "record_verification"),
            ("source_outage", "unavailable"),
            ("empty_interval", "OFFLINE_COVERAGE_VALID"),
        ):
            c = copy.deepcopy(baseline())
            c["id"], c["expected"] = f"{d}-{kind}", expected
            e = c["view"][d]
            if kind == "missing":
                del c["view"][d]
            elif kind == "omitted_record":
                e["records"].pop()
            elif kind == "empty_response":
                e["records"] = []
            elif kind == "wrong_source":
                e["source"] = "other-source"
            elif kind == "wrong_contract":
                e["contract"] = "unapproved-v2"
            elif kind == "rollback":
                e["revision"] = 1
            elif kind == "same_cut_conflict":
                e["commitment"] = "fork"
            elif kind == "stale":
                # Other domains advance to their known empty-interval cut.
                for other, entry in c["view"].items():
                    if other != d:
                        entry.update(revision=3, commitment=other + "-cut-3", covered_through=1001)
                c["supplied_upper_time"] = 1006
            elif kind == "future_cut":
                e["covered_through"] = 1005
            elif kind == "bool_revision":
                e["revision"] = True
            elif kind == "lost_denial":
                e["denials"] = []
            elif kind == "lost_future":
                e["future"] = []
            elif kind == "unverified_record":
                c["supplied_unverified"] = [d]
            elif kind == "source_outage":
                c["supplied_unavailable"] = [d]
            elif kind == "empty_interval":
                e.update(revision=3, commitment=d + "-cut-3", covered_through=1001)
            cases.append(c)
    return {
        "profile": "connector-source-coverage-draft1",
        "runtime_authorized": False,
        "live_trust_authorized": False,
        "scope": "Supplied journals, symbolic cut commitments and inner-verifier outcomes only; no cryptographic coverage or runtime lifecycle.",
        "cases": cases,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build(), indent=2) + "\n").encode("utf-8")
    if args.check:
        if VECTORS.read_bytes() != raw:
            raise SystemExit("coverage vectors differ")
        print("coverage vectors byte-identical")
    else:
        VECTORS.parent.mkdir(exist_ok=True)
        VECTORS.write_bytes(raw)
