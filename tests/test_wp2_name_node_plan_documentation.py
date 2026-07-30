from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "superpowers" / "specs" / "2026-07-30-wp2-name-node-core-design.md"
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-07-30-wp2-name-node-core.md"
STATUS = ROOT / "docs" / "protocol" / "status.md"


def test_wp2a_design_records_delegated_approval_and_smallest_safe_scope() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    normalized = " ".join(text.split()).casefold()

    for required in (
        "**status:** approved through explicit owner-delegated authorization",
        "isolated name node core with injected upstreams — approved",
        "full recursive resolver and udp/tcp service immediately — deferred",
        "extend the historical route registry and relay service — rejected",
        "every successful resolution",
        "synthetic ip",
        "invalid configured NBSR record",
        "never a signal to try legacy DNS",
        "d1–d7",
        "wp3",
    ):
        assert required.casefold() in normalized


def test_wp2a_plan_is_tdd_bounded_and_has_no_wire_registry_changes() -> None:
    text = PLAN.read_text(encoding="utf-8")
    normalized = " ".join(text.split()).casefold()

    for task in (
        "### Task 1: Add the signed local ServiceRecord registry",
        "### Task 2: Add bounded Resolution Context and RouteIntent state",
        "### Task 3: Implement the injected Name Node resolution core",
        "### Task 4: Connect the DNS-compatible response boundary",
        "### Task 5: Add privacy-safe events and bounded lab UDP/TCP DNS",
        "### Task 6: Freeze WP2A conformance and observed status",
    ):
        assert task in text

    for required in (
        "17 message codes",
        "19 error codes",
        "D1–D7",
        "Every successful configured-name resolution returns only a Synthetic IP",
        "invalid configured NBSR record fails closed and never downgrades to legacy",
        "Use TDD",
        "do not merge to `main`",
        "do not push without explicit instruction",
        "## Stop conditions",
    ):
        assert required.casefold() in normalized

    assert "TBD" not in text
    assert "TODO" not in text


def test_status_records_wp2a_as_implemented_without_advancing_wp3() -> None:
    text = " ".join(STATUS.read_text(encoding="utf-8").split()).casefold()

    for required in (
        "wp2a name node core | implemented",
        "signed registry, bounded resolution state, synthetic-only core",
        "real recursive dns, production dnssec, and web pki validation | planned",
        "wp3 runtime remains gated",
    ):
        assert required in text
