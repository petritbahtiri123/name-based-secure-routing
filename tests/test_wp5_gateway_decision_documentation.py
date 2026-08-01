from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "protocol" / "wp5-linux-gateway-packaging-decision.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def test_wp5_decision_freezes_linux_fail_closed_planning_boundary() -> None:
    content = DECISION.read_text(encoding="utf-8")

    for required in (
        "Linux/OpenWrt-first",
        "nftables",
        "policy routing",
        "terminal reject",
        "declarative operations only",
        "ownership journal",
        "reverse application order",
        "Name/Resolution",
        "Secure Route/Tunnel",
        "simulated policy-conformance",
    ):
        assert required in content


def test_wp5_decision_preserves_protocol_and_live_platform_non_claims() -> None:
    content = DECISION.read_text(encoding="utf-8")

    for required in (
        "no new wire values",
        "no frozen Core v0.1 change",
        "no OriginSet selection",
        "no Origin Endpoint connection or forwarding",
        "no NameRelay integration",
        "no production readiness",
        "no live nftables/TPROXY installation",
        "no clean no-agent client demonstration",
        "no operational rollback claim",
    ):
        assert required in content


def test_roadmap_marks_wp5_complete_without_live_claim() -> None:
    content = ROADMAP.read_text(encoding="utf-8")

    assert "WP5 deterministic Linux/OpenWrt gateway planning is complete" in content
    assert "interception and no-agent evidence remain separately gated" in content
    assert "WP6 is not authorized by this closure" in content
