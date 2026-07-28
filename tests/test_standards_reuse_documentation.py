from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REUSE_MATRIX = DOCS / "protocol" / "standards-reuse-matrix.md"
MINIMAL_SURFACE = DOCS / "protocol" / "minimal-nbsr-protocol-surface.md"
TRANSPORT_PROFILE = DOCS / "architecture" / "nbsr-transport-profile.md"
LEGACY_PROFILE = DOCS / "architecture" / "legacy-compatibility-profile.md"
SYNTHETIC_PROFILE = DOCS / "architecture" / "synthetic-address-profile.md"
RESOURCE_PROFILE = DOCS / "protocol" / "resource-timeout-profile.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _matrix_rows() -> list[list[str]]:
    lines = REUSE_MATRIX.read_text(encoding="utf-8").splitlines()
    rows: list[list[str]] = []
    for line in lines:
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def test_reuse_package_documents_exist() -> None:
    required = (
        REUSE_MATRIX,
        MINIMAL_SURFACE,
        TRANSPORT_PROFILE,
        LEGACY_PROFILE,
        SYNTHETIC_PROFILE,
        RESOURCE_PROFILE,
    )

    assert [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()] == []


def test_reuse_matrix_has_complete_classification_and_planning_columns() -> None:
    rows = _matrix_rows()
    assert rows[0] == [
        "Problem area",
        "Existing standard/mechanism",
        "What is reused",
        "NBSR profile/constraint",
        "New NBSR semantic",
        "Wire impact",
        "Human approval required",
        "Planned work package",
    ]

    body = rows[1:]
    assert len(body) >= 20
    classification_text = REUSE_MATRIX.read_text(encoding="utf-8")
    for classification in (
        "REUSE EXISTING STANDARD",
        "NBSR PROFILE OR CONSTRAINT",
        "NEW NBSR PROTOCOL SEMANTIC",
    ):
        assert classification in classification_text

    mechanisms = " ".join(row[1] for row in body)
    for required in ("QUIC v1", "TLS 1.3", "DNS", "MASQUE"):
        assert required.casefold() in mechanisms.casefold()


def test_minimal_surface_excludes_reused_transport_and_cryptography() -> None:
    text = _normalized(MINIMAL_SURFACE)
    assert "NBSR does not define congestion control" in text
    assert "NBSR does not define TLS cryptography" in text
    assert "name -> Synthetic IP mapping" in text
    assert "session reuse with service-isolated authorization" in text
    assert "OriginSet authority and publication" in text


def test_transport_profile_separates_quic_continuity_from_nbsr_authorization() -> None:
    text = _normalized(TRANSPORT_PROFILE)
    for invariant in (
        "QUIC v1",
        "TLS 1.3",
        "ALPN",
        "mutual edge authentication",
        "one bidirectional control stream",
        "one application stream per proxied TCP flow",
        "no 0-RTT for route-changing control messages",
        "NAT rebinding",
        "service binding",
        "grant binding",
        "gateway binding",
        "expiry",
        "revocation",
        "replay",
        "policy binding",
    ):
        assert invariant.casefold() in text.casefold()


def test_legacy_profile_keeps_dns_reachability_separate_from_authorization() -> None:
    text = _normalized(LEGACY_PROFILE)
    for mechanism in ("A", "AAAA", "CNAME", "SVCB", "HTTPS", "DNSSEC", "Web PKI", "Derived OriginSet"):
        assert mechanism.casefold() in text.casefold()
    assert "DNS TTL is not Route Grant expiry" in text
    assert "origin IP is never returned to the client" in text
    assert "direct fallback to an origin endpoint is forbidden" in text


def test_synthetic_profile_rejects_universal_cgn_safety_claim() -> None:
    text = _normalized(SYNTHETIC_PROFILE)
    assert "100.64.0.0/10 is not universally safe" in text
    assert "collision detection" in text.casefold()
    assert "configurable" in text.casefold()
    assert "universal production prefix remains unresolved" in text.casefold()


def test_resource_profile_separates_dns_origin_grant_channel_and_transport_time() -> None:
    text = _normalized(RESOURCE_PROFILE)
    for lifetime in (
        "DNS TTL",
        "OriginSet validity",
        "Route Grant expiry",
        "Transport Session lifetime",
        "Service Channel lifetime",
        "Application Stream lifetime",
    ):
        assert lifetime.casefold() in text.casefold()
    assert "DNS TTL does not authorize a route" in text


def test_frozen_core_registry_and_schema_guard_remains_explicit() -> None:
    text = _normalized(REUSE_MATRIX)
    assert "17 message codes" in text
    assert "19 error codes" in text
    assert "six frozen Core v0.1 wire schemas" in text
    assert "No frozen registry or schema change" in text
