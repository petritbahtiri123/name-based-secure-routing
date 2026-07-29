from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "docs" / "protocol" / "core-v0.2-version-negotiation-decision.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"
VECTOR_SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-07-29-core-v0.2-deterministic-vectors-design.md"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _normalized(path: Path = DECISION) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_d8_and_vector_design_record_human_approval() -> None:
    text = _normalized()
    vector_spec = _normalized(VECTOR_SPEC)

    assert "**Status:** approved on 2026-07-29" in DECISION.read_text(encoding="utf-8")
    assert "**Status:** approved on 2026-07-29" in VECTOR_SPEC.read_text(encoding="utf-8")
    assert "Runtime authorization:** none" in text
    assert "runtime authorization" in vector_spec.casefold()


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
    vector_spec = _normalized(VECTOR_SPEC)

    for rule in (
        "`NBSR_E_DOWNGRADE`",
        "unknown",
        "generic application failure",
        "does not allocate a QUIC application error code",
        "never interpreted as the nearest known version",
        "Origin Endpoints",
    ):
        assert rule.casefold() in text.casefold()
    assert "no Core v0.2 `ERROR` envelope" in vector_spec
    assert "generic transport close" in vector_spec


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


def test_v36_record_and_roadmap_record_fixture_approval_and_byte_review() -> None:
    decisions = _normalized(V36_DECISIONS)
    roadmap = _normalized(ROADMAP)

    assert "exact public fixtures were approved" in decisions
    assert "pending human byte and checksum review" in roadmap
    assert "runtime remains blocked" in roadmap


def test_v36_records_generated_package_pending_byte_approval() -> None:
    decisions = _normalized(V36_DECISIONS)
    roadmap = _normalized(ROADMAP)

    assert "generated package pending byte approval" in decisions.casefold()
    assert "human byte and checksum review" in roadmap.casefold()
    assert "cross-language interoperability is not yet proven" in decisions.casefold()


def test_changed_document_local_links_resolve() -> None:
    for path in (DECISION, V36_DECISIONS, ROADMAP, VECTOR_SPEC):
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            assert (path.parent / target).resolve().exists(), (path, raw_target)
