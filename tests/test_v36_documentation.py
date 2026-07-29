from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ARCH = DOCS / "architecture"
PROTOCOL = DOCS / "protocol"

VISION = ARCH / "NBSR_Protocol_Vision_V3.6.md"
DECISIONS = PROTOCOL / "v3.6-decisions.md"
TERMINOLOGY = PROTOCOL / "terminology.md"
SESSION_MODEL = ARCH / "session-channel-model.md"
ORIGIN_MODEL = ARCH / "origin-publication-migration.md"
STATE_MACHINES = ARCH / "protocol-state-machine.md"
THREAT_MODEL = DOCS / "threat-model.md"
ROADMAP = DOCS / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"
ANTI_DRIFT = PROTOCOL / "v3.6-anti-drift-checklist.md"
OLD_VISION = ARCH / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _section(path: Path, heading: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(heading)
    next_heading = re.search(r"\n#{1,2} ", text[start + len(heading) :])
    if next_heading is None:
        return text[start:]
    return text[start : start + len(heading) + next_heading.start()]


def test_v36_document_set_exists() -> None:
    required = (
        VISION,
        DECISIONS,
        TERMINOLOGY,
        SESSION_MODEL,
        ORIGIN_MODEL,
        STATE_MACHINES,
        THREAT_MODEL,
        ROADMAP,
        ANTI_DRIFT,
    )

    assert [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()] == []


def test_current_pointers_adopt_v36_and_preserve_v3_history() -> None:
    pointers = (
        ROOT / "README.md",
        DOCS / "architecture.md",
        ARCH / "README.md",
        PROTOCOL / "status.md",
        DOCS / "security-model.md",
        THREAT_MODEL,
    )

    for path in pointers:
        text = path.read_text(encoding="utf-8")
        assert "NBSR Protocol Vision V3.6" in text, path
        assert "NBSR_Protocol_Vision_V3.6.md" in text, path

    old_vision = _normalized(OLD_VISION)
    assert "Superseded on 2026-07-28" in old_vision
    assert "NBSR_Protocol_Vision_V3.6.md" in old_vision
    assert OLD_VISION.is_file()


def test_v36_freezes_universal_synthetic_resolution_and_flow() -> None:
    vision = _normalized(VISION)
    required = (
        "every successful name resolution returns a scoped synthetic IP",
        "origin IP is never returned to the client",
        "direct client fallback to an origin endpoint is forbidden",
        "Service Identity != Origin Endpoint",
        "Synthetic IP != Origin Endpoint",
        "Application requests a name",
        "Name Node returns the synthetic IP",
        "application connects to the synthetic IP",
        "Transport Session is reused or created",
        "Service Channel is independently authorized",
        "Application Stream is opened",
        "validated Origin Endpoint",
    )

    for statement in required:
        assert statement.casefold() in vision.casefold()


def test_v36_glossary_has_all_canonical_terms_and_invariants() -> None:
    text = TERMINOLOGY.read_text(encoding="utf-8")
    terms = (
        "Service Name",
        "Service Identity",
        "Synthetic IP",
        "Origin Endpoint",
        "OriginSet",
        "Source Edge",
        "Destination Edge",
        "Transport Session",
        "Route Context",
        "Service Channel",
        "Application Stream",
        "Route Grant",
        "Publication Mode",
        "Migration",
        "Resumption",
        "Handover",
        "Drain",
    )

    for term in terms:
        assert f"| {term} |" in text
    assert text.count("| MUST ") >= len(terms)


def test_decision_record_separates_approved_direction_from_pending_wire_work() -> None:
    approved = _section(DECISIONS, "## Approved V3.6 architecture")
    pending = _section(DECISIONS, "## Pending human decisions")
    compatibility = _section(DECISIONS, "## Compatibility-impact matrix")

    for concept in (
        "resolver-first",
        "session reuse, service isolation",
        "LEGACY_DNS",
        "HYBRID",
        "NBSR_NATIVE",
        "application-protocol boundary",
    ):
        assert concept.casefold() in approved.casefold()

    for gate in (
        "exact wire representation of OriginSet",
        "exact OriginSet wrapper schema",
        "`kid` binding",
        "message codes for origin update",
        "service-channel wire representation",
        "cryptographic channel derivation",
        "transport-session scope and reuse key",
        "route grant reuse versus one grant per channel",
        "migration and resume message types",
        "gateway handover authority",
        "origin health-check trust model",
        "graceful-drain maximum lifetime",
    ):
        assert gate.casefold() in pending.casefold()

    assert "OriginSet" in compatibility
    assert "Core v0.2 candidate" in compatibility

    for addition in (
        "Service Channel model",
        "multi-service Transport Session",
        "cryptographic channel separation",
        "OriginSet",
        "origin update message",
        "migration/resumption messages",
        "gateway handover",
        "state-machine transitions",
        "registry entries",
        "critical or non-critical extensions",
    ):
        assert addition.casefold() in compatibility.casefold()

    for classification in (
        "editorial clarification",
        "internal implementation model",
        "backward-compatible extension",
        "Core v0.2",
        "incompatible change",
    ):
        assert classification.casefold() in compatibility.casefold()

    decisions = _normalized(DECISIONS)
    assert "D1-D6 remain approved and unchanged" in decisions
    assert "17 message codes" in decisions
    assert "19 error codes" in decisions


def test_phase_d_is_approved_without_ungating_transport_runtime() -> None:
    roadmap = _normalized(ROADMAP)

    assert "Phase D implementation approved and complete" in roadmap
    assert "bounded last-known-good" in roadmap
    assert "NameRelay integration remains gated" in roadmap
    assert "WP3 runtime remains separately gated" in roadmap


def test_session_model_enforces_reuse_with_service_isolation() -> None:
    text = _normalized(SESSION_MODEL)

    assert ("Transport Session -> Route Context / Service Channel -> Application Stream") in text
    for invariant in (
        "independently authorized",
        "name-bound",
        "service-bound",
        "independently revocable",
        "independent quotas",
        "audit attribution",
        "failure containment",
        "cryptographic or transcript-bound",
    ):
        assert invariant.casefold() in text.casefold()
    assert "universal VPN-like authorization context" in text
    assert "full edge-to-edge cryptographic handshake for every hostname" in text


def test_origin_model_defines_modes_precedence_update_and_drain() -> None:
    text = _normalized(ORIGIN_MODEL)

    assert "LEGACY_DNS -> HYBRID -> NBSR_NATIVE" in text
    for rule in (
        "DNS TTL is not an authorization lease",
        "valid signed NBSR-native OriginSet",
        "delegated Destination Edge or connector metadata",
        "constrained legacy DNS discovery",
        "otherwise fail closed",
        "receive candidate update",
        "authenticate issuer",
        "validate and health-check new endpoints",
        "new channels",
        "gracefully drain existing streams",
        "blind delete-and-replace is forbidden",
    ):
        assert rule.casefold() in text.casefold()

    for field in (
        "service identifier",
        "service-record generation",
        "origin generation",
        "monotonic sequence",
        "endpoint set",
        "priorities",
        "weights",
        "transport and port",
        "region or locality",
        "publication mode",
        "validity interval",
        "issuer identity",
        "rollback protection",
        "authenticated wrapper",
    ):
        assert field.casefold() in text.casefold()


def test_state_machine_document_preserves_frozen_registry_and_proposes_lifecycles() -> None:
    text = _normalized(STATE_MACHINES)

    assert "frozen Core v0.1 state registries remain unchanged" in text
    for lifecycle in (
        "Transport Session lifecycle",
        "Service Channel lifecycle",
        "Origin publication lifecycle",
        "Migration and resumption lifecycle",
        "Graceful origin drain lifecycle",
    ):
        assert lifecycle.casefold() in text.casefold()
    assert "documentation-only proposal" in text
    assert "human approval" in text


def test_v36_threat_model_covers_new_cross_service_origin_and_mobility_threats() -> None:
    text = _normalized(THREAT_MODEL)
    threats = (
        "malicious or compromised legacy DNS",
        "stale origin update",
        "rollback or resurrection of an old OriginSet",
        "same-sequence different-content equivocation",
        "compromised destination edge",
        "cross-service authorization confusion",
        "channel key/context confusion",
        "transport-session compromise blast radius",
        "malicious session migration",
        "replayed resume proof",
        "unauthorized gateway handover",
        "origin leak through logs, errors, telemetry, or fallback",
        "origin churn denial of service",
        "poisoned health checks",
        "service-channel starvation or noisy-neighbor behavior",
        "split-brain origin publication",
        "route continuation after service revocation",
    )

    for threat in threats:
        assert threat.casefold() in text.casefold()


def test_v36_roadmap_reconciles_wp2_through_wp6_and_phases_a_through_i() -> None:
    text = ROADMAP.read_text(encoding="utf-8")

    for work_package in ("WP2", "WP3", "WP4", "WP5", "WP6"):
        assert f"## {work_package}" in text

    for phase in "ABCDEFGHI":
        section = _section(text_path := ROADMAP, f"### Phase {phase}")
        for field in (
            "**Prerequisites:**",
            "**Expected files:**",
            "**Tests:**",
            "**Human approval gate:**",
            "**Abort criteria:**",
        ):
            assert field in section, (phase, field, text_path)

    assert "Do not implement runtime behavior from this plan without approval" in text


def test_v36_anti_drift_checklist_contains_all_required_guardrails() -> None:
    text = _normalized(ANTI_DRIFT)
    guardrails = (
        "synthetic IP always",
        "origin hidden",
        "no direct fallback",
        "service identity independent of IP",
        "session reuse does not imply authorization reuse",
        "each Service Channel independently authorized",
        "legacy DNS is compatibility reachability only",
        "NBSR-native origin publication has precedence",
        "stale or rollback origin updates rejected",
        "frozen Core v0.1 registries",
        "application authentication remains outside NBSR",
        "no runtime implementation before required gates pass",
    )

    for guardrail in guardrails:
        assert guardrail.casefold() in text.casefold()
