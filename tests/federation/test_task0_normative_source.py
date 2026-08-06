from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt"
MANIFEST_PATH = ROOT / "docs/protocol/registries/wp8-planning-sources.json"
EXPECTED_LENGTH = 318_890
EXPECTED_SHA256 = "6058485d07d9c827c0cb62dad325fb389b213e35801c0799414bb6338d89848e"
AUTHORITY_DOCS = {
    "profile": ROOT / "docs/protocol/federation-v0.1-development-profile.md",
    "direction": ROOT / "docs/protocol/wp8-federation-v0.1-direction.md",
    "decisions": ROOT / "docs/protocol/wp8-federation-v0.1-decisions.md",
    "design": ROOT / "docs/superpowers/specs/2026-08-06-wp8-federation-v0.1-design.md",
    "plan": ROOT / "docs/superpowers/plans/2026-08-06-wp8-federation-v0.1.md",
    "status": ROOT / "docs/protocol/status.md",
    "roadmap": ROOT / "docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md",
}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_historical_source_has_exact_approved_bytes_and_provenance() -> None:
    payload = SOURCE_PATH.read_bytes()
    assert len(payload) == EXPECTED_LENGTH
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_SHA256

    manifest = _manifest()
    assert manifest == {
        "format_version": 1,
        "sources": [
            {
                "path": "docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt",
                "title": "NBSR WP8 Federation Decisions and Design Questions",
                "byte_length": EXPECTED_LENGTH,
                "sha256": EXPECTED_SHA256,
                "source_date": "2026-08-05",
                "provenance": "project-owner-supplied-original-plain-text-source",
                "status": "historical-normative-input-immutable-after-approval",
                "decision_scope": "complete-detailed-F1-F119-and-V1-V6-record",
                "representation": "original-UTF-8-BOM-and-CRLF-bytes-preserved",
                "matches_previously_recorded_sha256": True,
            }
        ],
    }


def test_historical_source_is_exempt_from_git_text_normalization() -> None:
    relative = SOURCE_PATH.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "check-attr", "text", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"{relative}: text: unset"


def test_authority_documents_reference_source_and_closed_blocker() -> None:
    repository_path = "docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt"
    for name in ("profile", "direction", "decisions"):
        assert repository_path in _normalized(AUTHORITY_DOCS[name])
    for path in AUTHORITY_DOCS.values():
        text = _normalized(path)
        assert "WP8-NORMATIVE-SOURCE-01: CLOSED" in text

    decisions = _normalized(AUTHORITY_DOCS["decisions"]).casefold()
    assert "canonical condensed index" in decisions
    assert "not a complete replacement" in decisions


def test_direction_defines_all_three_authority_layers_and_scoped_precedence() -> None:
    direction = _normalized(AUTHORITY_DOCS["direction"])
    for heading in (
        "Historical detailed decision authority",
        "Condensed decision index",
        "Current implementation-profile authority",
    ):
        assert heading in direction
    assert "only for the exact values or ambiguities they expressly freeze or correct" in direction
    assert "cannot silently override" in direction
    assert "external decision record is incorporated by digest" not in direction.casefold()


def test_clean_room_inputs_include_source_without_external_dependencies() -> None:
    plan = _normalized(AUTHORITY_DOCS["plan"])
    source_path = "docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt"
    assert source_path in plan
    assert "permitted clean-room input" in plan.casefold()

    prerequisites = "\n".join(_normalized(path) for path in AUTHORITY_DOCS.values())
    lowered = prerequisites.casefold()
    assert "c:\\users\\" not in lowered
    assert "codex conversation" not in lowered
    assert "chatgpt conversation" not in lowered
    assert "unavailable google doc" not in lowered
    assert "depends on a google doc" not in lowered


def test_task1_is_authorized_only_after_approval_and_schema_gate_stays_scoped() -> None:
    plan = _normalized(AUTHORITY_DOCS["plan"])
    assert "Task 1 may begin after human approval" in plan
    assert "Development Profile constants" in plan
    assert "registry enums/tables" in plan
    assert "baseline immutability enforcement" in plan
    assert "MUST NOT implement object codecs or validators" in plan
    assert "WP8-SCHEMA-REQUIREDNESS-01" in plan
    assert "blocks Tasks 2-6" in plan


def test_registry_renderer_never_generates_or_modifies_historical_source() -> None:
    before = SOURCE_PATH.read_bytes()
    renderer = (ROOT / "scripts/render_federation_registry.py").read_text(encoding="utf-8")
    assert str(SOURCE_PATH.relative_to(ROOT)).replace("\\", "/") not in renderer
    subprocess.run(
        [sys.executable, "scripts/render_federation_registry.py", "--check"],
        cwd=ROOT,
        check=True,
    )
    assert SOURCE_PATH.read_bytes() == before
