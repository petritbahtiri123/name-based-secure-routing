from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "relative",
    [
        "docs/protocol/federation-v0.1-wire.md",
        "docs/protocol/wp8-federation-v0.1-decision.md",
        "docs/internet-drafts/draft-nbsr-federation-00.md",
        "docs/protocol/wp8-task10-packet-capture.md",
    ],
)
def test_task10_public_document_exists(relative: str) -> None:
    assert (ROOT / relative).is_file(), relative


def test_public_draft_has_required_normative_sections_and_nonclaims() -> None:
    text = (ROOT / "docs/internet-drafts/draft-nbsr-federation-00.md").read_text(encoding="utf-8")
    for heading in (
        "## Terminology",
        "## Architecture",
        "## Operator ID",
        "## Ownership and delegation",
        "## Trust bundles and transparency",
        "## Key purposes and lifecycle",
        "## Rollback, equivocation, and split view",
        "## Deterministic encoding",
        "## Transport and F75 route establishment",
        "## Error behavior",
        "## Privacy considerations",
        "## Operational and security considerations",
        "## Conformance requirements",
        "## Extension and versioning rules",
        "## Implementation evidence",
        "## Future work and non-claims",
    ):
        assert heading in text
    for claim in (
        "not an IETF standard",
        "not production readiness",
        "not Internet-scale deployment",
        "not vendor or ISP adoption",
    ):
        assert claim in text


def test_evidence_tiers_are_explicit_and_honest() -> None:
    text = (ROOT / "docs/protocol/wp8-federation-v0.1-decision.md").read_text(encoding="utf-8")
    assert "live two-operator federation integration: PROVEN" in text
    assert "independent federation semantic verification: PROVEN" in text
    assert "independent route/stream wire interoperability: NOT YET PROVEN" in text
    assert "WP8 evidence closure: BLOCKED" in text
    assert "84c7c026b45acd98550c3487adfa3ce60cbc62c591a16aae7046ce9cd6b1c798" in text
    assert "Npcap 1.88" in text
    assert "udp port 45975 and host 127.0.0.1" in text
    assert "python scripts/verify_wp8_conformance.py" in text


def test_current_status_has_no_stale_task10_planned_claim() -> None:
    text = (ROOT / "docs/protocol/status.md").read_text(encoding="utf-8")
    assert "| Public conformance suite and Internet-Draft | Planned |" not in text
    assert "| Public conformance suite and Internet-Draft | Implemented |" in text
