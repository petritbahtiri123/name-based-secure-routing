from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp4_status_records_reviewed_lab_completion_and_fresh_evidence() -> None:
    status = read("docs/protocol/status.md")
    required = (
        "WP4 is complete at its documented origin-free reusable multi-service same-edge loopback lab scope",
        "114 executable Rust tests and 16 doctests (130 total)",
        "332 focused WP4/frozen-protocol Python tests",
        "826 passed and 1 skipped",
        "107 files already formatted",
        "2 valid and 21 invalid/mutation cases",
        "0 Critical, 0 Important, and 0 Minor findings",
        "no OriginSet selection",
        "no Origin Endpoint connection or forwarding",
        "no NameRelay integration",
        "no production-readiness claim",
        "no cross-edge resume",
        "no 0-RTT",
        "no frozen Core v0.1",
        "Core v0.2 exporter subtree",
    )
    for text in required:
        assert text in status
    assert "Pre-documentation implementation baseline" in status
    assert "Post-documentation current validation" in status
    assert "335 focused" in status
    assert "829 passed and 1 skipped (830 collected)" in status
    assert "108 files already formatted" in status
    assert "Multiplexed streams | Implemented" in status


def test_wp4_decision_records_exact_completed_limits_and_review_chain() -> None:
    decision = read("docs/protocol/wp4-reusable-multi-service-transport-decision.md")
    required = (
        "**Status:** Complete",
        "2049 (1 control plus 2048 application streams)",
        "1 MiB",
        "8 MiB",
        "1235 bytes",
        "1200 bytes",
        "100 datagrams/second with burst 100",
        "1024 events",
        "60 minutes",
        "30 seconds",
        "same-edge",
        "fresh RouteGrant",
        "fresh nonces",
        "canonical CBOR",
        "single hash",
        "Final independent review: PASS",
        "0 Critical, 0 Important, and 0 Minor",
    )
    for text in required:
        assert text in decision
    assert "Pre-documentation implementation baseline" in decision
    assert "Post-documentation current validation" in decision
    assert "one queue shared across channels within a Transport Session" in decision


def test_wp4_roadmap_and_plan_mark_only_the_approved_task_complete() -> None:
    roadmap = read("docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md")
    plan = read("docs/superpowers/plans/2026-07-31-wp4-reusable-multi-service-transport.md")
    assert "WP4 reusable multi-service transport is complete" in roadmap
    assert "origin-free reusable multi-service same-edge loopback lab scope" in roadmap
    for step in range(1, 10):
        assert f"- [x] **Step {step}:" in plan
    assert "114 executable Rust tests plus 16 doctests" in plan
    assert "826 passed, 1 skipped" in plan
    assert "Pre-documentation implementation baseline" in plan
    assert "Post-documentation current validation" in plan
    assert "829 passed, 1 skipped (830 collected)" in plan
