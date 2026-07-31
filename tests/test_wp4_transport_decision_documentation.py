from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "protocol" / "wp4-reusable-multi-service-transport-decision.md"
STATUS = ROOT / "docs" / "protocol" / "status.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_wp4_decision_freezes_session_reuse_and_channel_admission() -> None:
    text = _normalized(DECISION)

    for rule in (
        "(source_edge_id, destination_edge_id, trust_profile_id, ALPN, protocol_version)",
        "single-use",
        "fresh RouteGrant",
        "16-byte `channel_id`",
        "only Service Channel wire identifier",
        "session is draining",
        "expired",
        "over capacity",
        "different authenticated protocol version",
        "reauthentication policy",
        "requested service policy",
    ):
        assert rule.casefold() in text.casefold()


def test_wp4_decision_freezes_exporter_context_and_exact_bounds() -> None:
    text = _normalized(DECISION)

    for rule in (
        "EXPORTER-NBSR-Service-Channel-v2",
        "NBSR-SERVICE-CHANNEL-CONTEXT-v2",
        "session_id",
        "source_edge_id",
        "destination_edge_id",
        "channel_id",
        "route_id",
        "route_grant_digest",
        "service_id",
        "transport",
        "port",
        "policy_hash",
        "client_nonce",
        "edge_nonce",
        "32 active channels per session",
        "eight active channels for one service",
        "64 concurrent reliable streams per channel",
        "1 MiB",
        "8 MiB",
        "1024 events",
        "4096",
        "30 seconds",
    ):
        assert rule.casefold() in text.casefold()


def test_wp4_decision_retains_native_datagram_and_same_edge_limits() -> None:
    text = _normalized(DECISION)

    for rule in (
        "native QUIC DATAGRAM",
        "RFC 9221",
        "no HTTP/3",
        "no MASQUE",
        "no CONNECT-UDP",
        "same exact Source Edge and Destination Edge identities",
        "Cross-edge resumption and handover always fail closed and remain WP6",
        "0-RTT remains disabled",
        "Session drain stops new channels, streams, and datagrams",
        "Origin Endpoint replacement and origin drain are not WP4 behavior",
    ):
        assert rule.casefold() in text.casefold()


def test_wp4_decision_and_tracking_record_approved_in_progress_scope() -> None:
    decision = _normalized(DECISION)
    status = _normalized(STATUS)
    roadmap = _normalized(ROADMAP)

    for rule in (
        "Approved for implementation",
        "implementation is in progress",
        "does not select or connect an Origin Endpoint",
        "does not integrate NameRelay",
        "does not modify frozen Core v0.1 D1-D6",
        "does not claim production readiness",
    ):
        assert rule.casefold() in decision.casefold()

    assert "Reusable multi-service Transport Session with isolated Service Channels | Planned | WP4 implementation is approved and in progress" in status
    assert "WP4 implementation is approved and in progress" in roadmap
