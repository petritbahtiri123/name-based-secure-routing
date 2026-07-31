from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "protocol" / "status.md"
DECISION = ROOT / "docs" / "protocol" / "wp3-single-service-transport-decision.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def test_wp3_docs_record_only_the_verified_single_service_boundary() -> None:
    text = " ".join(
        (STATUS.read_text(encoding="utf-8") + DECISION.read_text(encoding="utf-8") + ROADMAP.read_text(encoding="utf-8")).split()
    ).casefold()

    for required in (
        "one service channel and one tcp application stream",
        "origin endpoint remains internal and is not connected",
        "core v0.2 failure never retries as core v0.1",
        "multi-service transport session reuse remains wp4",
        "namerelay remains unchanged",
        "no production readiness claim",
        "decoded routeopen",
        "caller-trusted signed routegrant",
        "real loopback quic application-stream lifecycle",
        "4 kib",
        "payload before stream_accept is reset without delivery",
    ):
        assert required in text


def test_wp3_docs_preserve_excluded_runtime_capabilities() -> None:
    status = " ".join(STATUS.read_text(encoding="utf-8").split()).casefold()

    for excluded in (
        "no originset selection",
        "no origin connection",
        "no relay integration",
        "no multi-service reuse",
        "no production-readiness claim",
    ):
        assert excluded in status
