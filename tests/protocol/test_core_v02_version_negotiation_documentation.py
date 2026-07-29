from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "docs" / "protocol" / "core-v0.2-version-negotiation-decision.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _normalized(path: Path = DECISION) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_d8_records_approved_direction_and_written_review_gate() -> None:
    text = _normalized()

    assert "design direction approved on 2026-07-29" in text
    assert "written D8 record pending review" in text
    assert "Runtime authorization:** none" in text


def test_d8_assigns_exact_future_version_without_widening_core_v01() -> None:
    text = _normalized()

    assert "| `CORE_0_2` | 2 |" in text
    assert "`CORE_0_1 = 1`" in text
    assert "does not widen the accepted value of the frozen Core v0.1 schema" in text
    assert "current production registry continues to contain only `CORE_0_1`" in text


def test_d8_keeps_one_alpn_and_rejects_in_band_negotiation() -> None:
    text = _normalized()

    for rule in (
        "exact ALPN `nbsr-quic-1`",
        "No `nbsr-quic-2` token",
        "There is no version-list field",
        "first NBSR control frame",
        "authenticated local/operator policy",
        "Legacy DNS",
    ):
        assert rule.casefold() in text.casefold()


def test_d8_locks_one_version_per_session_and_forbids_fallback() -> None:
    text = _normalized()

    for rule in (
        "every envelope on that QUIC Transport Session uses the same Core version",
        "reuse key includes `protocol_version`",
        "never retries as Core v0.1",
        "protocol does not perform that downgrade automatically",
        "QUIC path migration does not change the version",
        "resumption",
    ):
        assert rule.casefold() in text.casefold()


def test_d8_defines_safe_mismatch_and_unknown_version_failure() -> None:
    text = _normalized()

    for rule in (
        "`NBSR_E_DOWNGRADE`",
        "unknown",
        "generic application failure",
        "does not allocate a QUIC application error code",
        "never interpreted as the nearest known version",
        "Origin Endpoints",
    ):
        assert rule.casefold() in text.casefold()


def test_d8_preserves_frozen_registries_and_lists_conformance_cases() -> None:
    text = _normalized()

    for rule in (
        "17-message",
        "19-error",
        "six D6 object schemas",
        "state transition",
        "critical extension",
        "COSE wrapper",
        "Core v0.1 accepts only version 1",
        "Core v0.2 accepts only version 2",
        "mixed-version envelope",
        "automatic v0.1 attempt",
        "same exact ALPN `nbsr-quic-1`",
    ):
        assert rule.casefold() in text.casefold()


def test_v36_record_and_roadmap_point_to_written_d8_review() -> None:
    decisions = _normalized(V36_DECISIONS)
    roadmap = _normalized(ROADMAP)

    assert "D8 written record prepared" in decisions
    assert "written D8 record review" in decisions
    assert "written D8 version-selection record" in roadmap
    assert "runtime remains blocked" in roadmap


def test_changed_document_local_links_resolve() -> None:
    for path in (DECISION, V36_DECISIONS, ROADMAP):
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            assert (path.parent / target).resolve().exists(), (path, raw_target)
