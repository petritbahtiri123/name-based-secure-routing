from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WP2A = ROOT / "docs" / "protocol" / "wp2a-name-node-core.md"
STATUS = ROOT / "docs" / "protocol" / "status.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def test_wp2a_document_freezes_security_boundary_without_wire_drift() -> None:
    text = WP2A.read_text(encoding="utf-8")
    for required in (
        "Synthetic IP for every successful resolution",
        "origin endpoints remain internal",
        "invalid NBSR state never downgrades to legacy",
        "DNS TTL is not RouteIntent or RouteGrant lifetime",
        "17 message codes remain unchanged",
        "19 error codes remain unchanged",
        "D1-D7 remain unchanged",
        "WP3 remains gated",
    ):
        assert required in text


def test_wp2a_document_records_exact_implemented_and_non_claimed_boundaries() -> None:
    text = WP2A.read_text(encoding="utf-8")

    for implemented in (
        "SignedServiceRegistry",
        "ResolutionContextStore",
        "NameNodeDnsAdapter",
        "NameNodeLabServer",
        "BoundedNameNodeMetrics",
        "loopback-only UDP and TCP DNS",
    ):
        assert implemented in text

    for non_claim in (
        "no real recursive DNS",
        "no production DNSSEC or Web PKI validation",
        "no signed NBSR-native OriginSet publication",
        "no runtime relay or tunnel integration",
        "no HA or federation",
        "not production ready",
    ):
        assert non_claim in text


def test_status_marks_only_wp2a_lab_scope_implemented() -> None:
    status = STATUS.read_text(encoding="utf-8")

    assert "| WP2A Name Node core | Implemented |" in status
    assert "| Real recursive DNS, production DNSSEC, and Web PKI validation | Planned |" in status
    assert "| Signed NBSR-native OriginSet publication | Planned |" in status
    assert "| Multi-zone HA and shared security state | Planned |" in status
    assert "| Signed ownership, delegation, transparency, and global federation | Planned |" in status
    assert "WP3 is complete at its documented origin-free" in status
    assert "- production readiness;" in status


def test_roadmap_records_wp2a_completion_without_advancing_wp3() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert "**WP2A status:** Implemented at bounded loopback lab scope." in roadmap
    assert "WP3 is complete at its documented origin-free" in roadmap
    assert "No Core v0.1 registry, schema, state, transition, extension, or COSE wrapper changed." in roadmap
