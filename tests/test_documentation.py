from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VISION = DOCS / "architecture" / "NBSR_Protocol_Vision_v2.pdf"
VISION_SHA256 = "746cbe07012dd646de71537470ed9ef55a85222509f065d5dda4668557e56806"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
CORE_V01_WIRE = DOCS / "protocol" / "core-v0.1-wire.md"
CORE_V01_SCHEMA = DOCS / "protocol" / "core-v0.1-wire-schema.md"

STABLE_PROTOCOL_API = {
    "CborLimits",
    "ConnectorState",
    "ControlEnvelope",
    "DEFAULT_LIMITS",
    "ErrorCode",
    "InvalidTransition",
    "MessageType",
    "ProtocolError",
    "ProtocolVersion",
    "ProtocolViolation",
    "ResolutionState",
    "Revocation",
    "RevocationMode",
    "RevocationReason",
    "RevocationTargetType",
    "RouteGrant",
    "RouteIntent",
    "ServiceRecord",
    "StreamState",
    "TunnelState",
    "VerifiedSign1",
    "decode_deterministic",
    "decode_envelope",
    "decode_error",
    "decode_revocation",
    "decode_route_grant",
    "decode_route_intent",
    "decode_service_record",
    "encode_deterministic",
    "encode_model",
    "require_kid",
    "sign1",
    "transition",
    "verify_sign1",
}

MESSAGE_CODES = {
    "CLIENT_HELLO": 1,
    "EDGE_HELLO": 2,
    "ROUTE_OPEN": 3,
    "ROUTE_ACCEPT": 4,
    "ROUTE_REJECT": 5,
    "STREAM_OPEN": 6,
    "STREAM_ACCEPT": 7,
    "STREAM_REJECT": 8,
    "LEASE_RENEW": 9,
    "LEASE_RESULT": 10,
    "KEY_UPDATE_NOTICE": 11,
    "ROUTE_DRAIN": 12,
    "ROUTE_REVOKE": 13,
    "ROUTE_CLOSE": 14,
    "PING": 15,
    "PONG": 16,
    "ERROR": 17,
}

ERROR_CODES = {
    "NBSR_E_NAME_INVALID": 1,
    "NBSR_E_NAME_NOT_FOUND": 2,
    "NBSR_E_RECORD_UNTRUSTED": 3,
    "NBSR_E_RECORD_STALE": 4,
    "NBSR_E_RECORD_REVOKED": 5,
    "NBSR_E_CONTEXT_REQUIRED": 6,
    "NBSR_E_HANDLE_EXHAUSTED": 7,
    "NBSR_E_ROUTE_DENIED": 8,
    "NBSR_E_GRANT_INVALID": 9,
    "NBSR_E_GRANT_EXPIRED": 10,
    "NBSR_E_PROOF_INVALID": 11,
    "NBSR_E_REPLAY": 12,
    "NBSR_E_PROFILE_UNSUPPORTED": 13,
    "NBSR_E_DOWNGRADE": 14,
    "NBSR_E_EDGE_UNAVAILABLE": 15,
    "NBSR_E_ORIGIN_UNAVAILABLE": 16,
    "NBSR_E_REVOKED": 17,
    "NBSR_E_OVER_CAPACITY": 18,
    "NBSR_E_INTERNAL": 19,
}


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


def test_core_v01_wire_contract_is_complete_and_non_claiming() -> None:
    text = CORE_V01_WIRE.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    for heading in (
        "## Normative scope",
        "## Deterministic CBOR profile",
        "## Numeric registries",
        "## Common wire types and bounds",
        "## Object field schemas",
        "## COSE Sign1 profile",
        "## Extensions and unknown fields",
        "## Golden vectors",
        "## Privacy invariant",
        "## Versioning and incompatibility",
        "## Non-claims",
    ):
        assert heading in text

    assert "RFC 8949 Core Deterministic Encoding" in text
    assert "tests/vectors/core-v0.1/manifest.json" in text
    assert "python tools/generate_core_v01_vectors.py --check" in text
    assert "origin address" in normalized
    assert "MUST NOT" in text
    assert "does not integrate" in normalized
    assert "WP2" in text


def test_core_v01_wire_contract_contains_every_frozen_numeric_mapping() -> None:
    wire = CORE_V01_WIRE.read_text(encoding="utf-8")
    schema = CORE_V01_SCHEMA.read_text(encoding="utf-8")

    for name, code in MESSAGE_CODES.items():
        assert f"| {code} | `{name}` |" in wire
    for name, code in ERROR_CODES.items():
        assert f"| {code} | `{name}` |" in wire

    for schema_name in (
        "ServiceRecord",
        "RouteIntent",
        "RouteGrant",
        "Revocation",
        "ProtocolError",
        "ControlEnvelope",
    ):
        section_start = schema.index(f"## {schema_name}")
        section_end = schema.find("\n## ", section_start + 1)
        section = schema[section_start : section_end if section_end >= 0 else None]
        table_rows = [
            line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| Key ") and not line.startswith("|---")
        ]

        assert table_rows
        assert all(row in wire for row in table_rows), schema_name


def test_protocol_package_exports_only_stable_wp1_surface() -> None:
    protocol = importlib.import_module("nbsr.protocol")

    assert set(protocol.__all__) == STABLE_PROTOCOL_API
    assert all(getattr(protocol, name, None) is not None for name in STABLE_PROTOCOL_API)
    assert "SERVICE_RECORD_FIELDS" not in protocol.__all__
    assert "_StructuralScanner" not in protocol.__all__


def test_authoritative_vision_pdf_is_the_supplied_binary():
    assert hashlib.sha256(VISION.read_bytes()).hexdigest() == VISION_SHA256
    history_copy = DOCS / "history" / "NBSR_Protocol_Vision_v2.pdf"
    assert hashlib.sha256(history_copy.read_bytes()).hexdigest() == VISION_SHA256


def test_v36_north_star_and_document_precedence_are_explicit():
    north_star = "every successful"
    for path in (
        ROOT / "README.md",
        DOCS / "architecture.md",
        DOCS / "architecture" / "NBSR_Protocol_Vision_V3.6.md",
    ):
        content = path.read_text(encoding="utf-8").casefold()
        assert north_star in content
        assert "synthetic ip" in content

    vision_v36 = (DOCS / "architecture" / "NBSR_Protocol_Vision_V3.6.md").read_text(encoding="utf-8")
    assert "Current architectural source of truth" in vision_v36
    assert "Transport Session -> Route Context / Service Channel -> Application Stream" in vision_v36
    assert "OriginSet" in vision_v36

    conformance = " ".join((DOCS / "vision-v2-conformance.md").read_text(encoding="utf-8").split())
    assert "historical Vision V2 baseline" in conformance
    assert "not V3.6 implementation evidence" in conformance
    assert "does not claim native NBSR conformance" in conformance


def test_readme_separates_v3_direction_from_current_implementation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())

    assert "synthetic IP for every successfully resolved name" in normalized
    assert "Name/Resolution Plane" in readme
    assert "Secure Route/Tunnel Plane" in readme
    assert "not Protocol Core v0.1" in normalized
    assert "not a production system" in normalized
    assert "docs/protocol/status.md" in readme


def test_wp0_sources_are_preserved():
    assert (DOCS / "architecture" / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md").is_file()
    assert (DOCS / "architecture" / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.pdf").is_file()
    assert (DOCS / "history" / "NBSR_Protocol_Vision_v2.pdf").is_file()
    assert (DOCS / "research" / "Name-Based-Secure-Routing-feasibility-study.pdf").is_file()


def test_protocol_status_defines_required_vocabulary():
    status = (DOCS / "protocol" / "status.md").read_text(encoding="utf-8")
    for word in ("Implemented", "Partial", "Planned", "Normative"):
        assert f"| {word} |" in status
    assert "does not imply Core v0.1 conformance" in status


def test_active_overviews_point_to_v36_authority():
    v36_link = "architecture/NBSR_Protocol_Vision_V3.6.md"
    for path in (
        DOCS / "architecture.md",
        DOCS / "security-model.md",
        DOCS / "threat-model.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "NBSR Protocol Vision V3.6" in content
        assert v36_link in content


def test_v2_evidence_is_labeled_as_a_historical_baseline():
    for path in (
        DOCS / "vision-v2-conformance.md",
        DOCS / "security-hardening-report.md",
    ):
        content = " ".join(path.read_text(encoding="utf-8").split())
        assert "historical Vision V2 baseline" in content
        assert "not V3.6 implementation evidence" in content


def test_wp0_local_document_links_resolve():
    paths = (
        ROOT / "README.md",
        DOCS / "architecture" / "README.md",
        DOCS / "history" / "README.md",
        DOCS / "research" / "README.md",
        DOCS / "protocol" / "status.md",
        CORE_V01_WIRE,
    )
    missing = [str(target.relative_to(ROOT)) for path in paths for target in _local_markdown_targets(path) if not target.exists()]
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
