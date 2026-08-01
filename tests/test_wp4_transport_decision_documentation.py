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


def test_wp4_decision_binds_exporter_construction_and_resource_limits() -> None:
    text = _normalized(DECISION)
    decision = DECISION.read_text(encoding="utf-8")

    expected_context = """
    [
      "NBSR-SERVICE-CHANNEL-CONTEXT-v2",
      2,
      session_id,
      source_edge_id,
      destination_edge_id,
      channel_id,
      route_id,
      route_grant_digest,
      service_id,
      transport,
      port,
      policy_hash,
      client_nonce,
      edge_nonce
    ]
    """
    assert "The exporter context is the SHA-256 of the deterministic CBOR encoding of:" in decision
    assert " ".join(expected_context.split()) in text
    assert "expected 32-byte exporter result" in decision

    for resource_limit in (
        "| Active channels per Transport Session | 32 |",
        "| Active channels per service per session | 8 |",
        "| Concurrent reliable streams per channel | 64 |",
        "| Peer-initiated bidirectional streams per Transport Session | 2049 (1 control plus 2048 application streams) |",
        "| Buffered bytes per reliable stream | 1 MiB |",
        "| Buffered reliable bytes per channel | 8 MiB |",
        "| Audit queue | 1024 events in one queue shared across channels within a Transport Session |",
        "| Replay/tombstone entries per session | 4096 |",
        "| Channel drain maximum | 30 seconds |",
        "| Same-edge resume window | 30 seconds and never beyond grant/session expiry |",
    ):
        assert resource_limit in decision


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


def test_wp4_decision_and_tracking_record_completed_lab_scope() -> None:
    decision = _normalized(DECISION)
    status = _normalized(STATUS)
    roadmap = _normalized(ROADMAP)

    for rule in (
        "Complete at the approved origin-free reusable multi-service same-edge loopback lab scope",
        "no OriginSet selection",
        "Origin Endpoint connection",
        "NameRelay integration",
        "production readiness",
        "frozen Core v0.1",
        "A RouteGrant is single-use per Service Channel admission",
        "The existing 16-byte `channel_id` is the only Service Channel wire identifier in `ROUTE_*`, `STREAM_*`, exporter context, audit records, quota state, drain state, resume state, and UDP framing.",
    ):
        assert rule.casefold() in decision.casefold()

    assert "Reusable multi-service Transport Session with isolated Service Channels | Implemented" in status
    assert "WP4 reusable multi-service transport is complete" in roadmap
