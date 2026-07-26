from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VISION = DOCS / "architecture" / "NBSR_Protocol_Vision_v2.pdf"
VISION_SHA256 = "746cbe07012dd646de71537470ed9ef55a85222509f065d5dda4668557e56806"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _local_markdown_targets(path: Path) -> list[Path]:
    targets: list[Path] = []
    for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        targets.append((path.parent / target).resolve())
    return targets


def test_required_security_and_vision_documents_exist():
    required = (
        ROOT / "README.md",
        DOCS / "architecture.md",
        DOCS / "architecture" / "terminology.md",
        DOCS / "architecture" / "protocol-state-machine.md",
        DOCS / "vision-v2-conformance.md",
        DOCS / "threat-model.md",
        DOCS / "security-model.md",
        DOCS / "security-hardening-report.md",
        ROOT / "artifacts" / "capability-validation-report.md",
        VISION,
    )

    assert [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()] == []


def test_authoritative_vision_pdf_is_the_supplied_binary():
    assert hashlib.sha256(VISION.read_bytes()).hexdigest() == VISION_SHA256
    history_copy = DOCS / "history" / "NBSR_Protocol_Vision_v2.pdf"
    assert hashlib.sha256(history_copy.read_bytes()).hexdigest() == VISION_SHA256


def test_north_star_and_document_precedence_are_explicit():
    north_star = "NBSR turns a name into a secure route, not an IP address."
    for path in (
        ROOT / "README.md",
        DOCS / "architecture.md",
        DOCS / "architecture" / "terminology.md",
    ):
        assert north_star in path.read_text(encoding="utf-8")

    vision_v3 = (
        DOCS
        / "architecture"
        / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md"
    ).read_text(encoding="utf-8")
    assert "Authoritative architecture direction" in vision_v3
    assert "Name/Resolution Plane" in vision_v3
    assert "Secure Route/Tunnel Plane" in vision_v3

    conformance = " ".join(
        (DOCS / "vision-v2-conformance.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "historical Vision V2 baseline" in conformance
    assert "not V3 implementation evidence" in conformance
    assert "does not claim native NBSR conformance" in conformance


def test_readme_separates_v3_direction_from_current_implementation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())

    assert "NBSR Name Node resolves every configured name" in readme
    assert "Name/Resolution Plane" in readme
    assert "Secure Route/Tunnel Plane" in readme
    assert "not Protocol Core v0.1" in normalized
    assert "not a production system" in normalized
    assert "docs/protocol/status.md" in readme


def test_wp0_sources_are_preserved():
    assert (
        DOCS
        / "architecture"
        / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md"
    ).is_file()
    assert (
        DOCS
        / "architecture"
        / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.pdf"
    ).is_file()
    assert (DOCS / "history" / "NBSR_Protocol_Vision_v2.pdf").is_file()
    assert (
        DOCS / "research" / "Name-Based-Secure-Routing-feasibility-study.pdf"
    ).is_file()


def test_protocol_status_defines_required_vocabulary():
    status = (DOCS / "protocol" / "status.md").read_text(encoding="utf-8")
    for word in ("Implemented", "Partial", "Planned", "Normative"):
        assert f"| {word} |" in status
    assert "does not imply Core v0.1 conformance" in status


def test_active_overviews_point_to_v3_authority():
    v3_link = (
        "architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md"
    )
    for path in (
        DOCS / "architecture.md",
        DOCS / "security-model.md",
        DOCS / "threat-model.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "Protocol Vision V3" in content
        assert v3_link in content


def test_v2_evidence_is_labeled_as_a_historical_baseline():
    for path in (
        DOCS / "vision-v2-conformance.md",
        DOCS / "security-hardening-report.md",
    ):
        content = " ".join(path.read_text(encoding="utf-8").split())
        assert "historical Vision V2 baseline" in content
        assert "not V3 implementation evidence" in content


def test_wp0_local_document_links_resolve():
    paths = (
        ROOT / "README.md",
        DOCS / "architecture" / "README.md",
        DOCS / "history" / "README.md",
        DOCS / "research" / "README.md",
        DOCS / "protocol" / "status.md",
    )
    missing = [
        str(target.relative_to(ROOT))
        for path in paths
        for target in _local_markdown_targets(path)
        if not target.exists()
    ]
    assert missing == []


def test_state_machine_covers_required_design_states_and_marks_future_work():
    state_machine = (DOCS / "architecture" / "protocol-state-machine.md").read_text(encoding="utf-8").casefold()

    for state in (
        "discovery",
        "secure handshake",
        "registered-name resolution",
        "route creation",
        "stream establishment",
        "lease renewal",
        "revocation",
        "migration and resumption",
        "closure",
        "failure and downgrade",
    ):
        assert state in state_machine
    assert "design/documentation only" in state_machine
    assert "no plaintext fallback" in state_machine


def test_capability_report_uses_only_the_required_status_vocabulary():
    report = (ROOT / "artifacts" / "capability-validation-report.md").read_text(encoding="utf-8")
    statuses = (
        "Confirmed functional",
        "Partially functional",
        "Implemented but not live-verified",
        "Design/documentation only",
        "Not implemented",
        "Blocked/unverified",
    )

    for status in statuses:
        assert status in report
    for section in (
        "Executive verdict",
        "Component and trust-boundary inventory",
        "Allowed communication matrix",
        "Capability validation",
        "Vision v2 conformance summary",
        "Test evidence",
        "Remaining attack paths",
        "Production blockers",
        "Prioritized next roadmap",
    ):
        assert section in report
