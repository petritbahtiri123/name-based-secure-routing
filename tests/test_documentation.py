from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VISION = DOCS / "architecture" / "NBSR_Protocol_Vision_v2.pdf"
VISION_SHA256 = "746cbe07012dd646de71537470ed9ef55a85222509f065d5dda4668557e56806"


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


def test_north_star_and_document_precedence_are_explicit():
    north_star = "NBSR turns a name into a secure route, not an IP address."
    for path in (
        ROOT / "README.md",
        DOCS / "architecture.md",
        DOCS / "architecture" / "terminology.md",
    ):
        assert north_star in path.read_text(encoding="utf-8")

    conformance = (DOCS / "vision-v2-conformance.md").read_text(encoding="utf-8")
    assert "authoritative direction document" in conformance
    assert "supporting research" in conformance
    assert "was not supplied" in conformance
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
