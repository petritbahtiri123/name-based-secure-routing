"""Offline ACP provider seam model; no keys, transport, filesystem or permits.

All authorization, persistence and clock verdicts are injected test inputs.
This models proposed transaction outcomes, not real atomicity or cryptography.
"""

import argparse
import copy
import json
from pathlib import Path

VECTORS = Path(__file__).resolve().parents[1] / "vectors/acp-provider-contract-draft1/vectors.json"


def step(state, event):
    """Return a new symbolic state; never mutate caller-owned inputs."""
    s = copy.deepcopy(state)
    op = event.get("op")
    if op == "begin":
        if set(event) != {"op", "subject", "request", "entitled"}:
            return "schema", s
        binding = [event["subject"], event["request"]]
        if not all(type(x) is str and x for x in binding):
            return "schema", s
        if s["phase"] == "uncertain":
            return "blocked", s
        if event["entitled"] is not True:
            return "unauthorized", s
        if s["phase"] != "pristine":
            if binding != s["binding"]:
                return "conflict", s
            return ("replay" if s["phase"] == "committed" else "pending"), s
        # A reserved credential is an opaque fixture, not a generated identity.
        s.update(phase="pending", binding=binding, credential="credential-a")
        return "reserved", s
    if op == "commit":
        if set(event) != {"op", "confirmed"} or type(event["confirmed"]) is not bool:
            return "schema", s
        if s["phase"] != "pending":
            return "blocked", s
        s["phase"] = "committed" if event["confirmed"] else "uncertain"
        return ("committed" if event["confirmed"] else "uncertain"), s
    if op == "reconcile":
        if set(event) != {"op", "binding", "credential", "authenticated", "committed"}:
            return "schema", s
        if (
            s["phase"] != "uncertain"
            or event["authenticated"] is not True
            or event["committed"] is not True
            or event["binding"] != s["binding"]
            or event["credential"] != s["credential"]
        ):
            return "blocked", s
        # No reset-to-pristine path: missing/negative evidence cannot release a reservation.
        s["phase"] = "committed"
        return "reconciled", s
    if op == "publish":
        if s["phase"] in ("pending", "uncertain"):
            return "publication_blocked", s
        flags = {"inner_verified", "stored", "clock_valid", "signer_authorized", "policy_narrows"}
        if set(event) != flags | {"op", "verified_snapshot", "current_snapshot", "now", "expiry", "role"}:
            return "schema", s
        if not all(event[k] is True for k in flags):
            return "publication_blocked", s
        # Exact snapshot includes context, revision, digest and policy version.
        expected = ["context-a", 7, "digest-a", "policy-a"]
        for key in ("verified_snapshot", "current_snapshot"):
            value = event[key]
            if type(value) is not list or len(value) != 4 or type(value[1]) is not int or value != expected:
                return "snapshot_changed", s
        if type(event["now"]) is not int or type(event["expiry"]) is not int:
            return "schema", s
        if not 0 <= event["now"] < event["expiry"] <= 253402300799:
            return "expired", s
        if event["role"] != "client-acp-result":
            return "role_mismatch", s
        return "OFFLINE_PUBLICATION_VALID", s
    return "schema", s


def check():
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert data["profile"] == "acp-provider-contract-draft1"
    assert data["runtime_authorized"] is False and data["live_trust_authorized"] is False
    seen = set()
    counts = {"positive": 0, "negative": 0}
    for case in data["cases"]:
        assert case["id"] not in seen
        seen.add(case["id"])
        state = {"phase": "pristine", "binding": None, "credential": None}
        outcomes = []
        for event in case["events"]:
            before = copy.deepcopy(state)
            result, after = step(state, event)
            assert state == before
            outcomes.append(result)
            state = after
        assert outcomes == case["expected"], (case["id"], outcomes)
        assert state == case["final"], (case["id"], state)
        counts[case["kind"]] += 1
    return counts["positive"], counts["negative"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    good, bad = check()
    print(f"{good} positive, {bad} negative; OFFLINE PROVIDER CONTRACT ONLY")
