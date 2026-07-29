from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "protocol" / "wp3-single-service-transport-decision.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def _normalized() -> str:
    return " ".join(DECISION.read_text(encoding="utf-8").split())


def test_wp3_transport_decision_exists_and_remains_review_gated() -> None:
    text = _normalized()

    assert "Status: Human approval required" in text
    assert "Runtime authorization: None" in text
    assert "does not authorize WP3 implementation" in text


def test_wp3_reuses_quic_and_recommends_only_a_prototype_library() -> None:
    text = _normalized()

    for rule in (
        "QUIC v1",
        "TLS 1.3",
        "RFC 9000",
        "RFC 9001",
        "aioquic",
        "Python prototype",
        "Quinn",
        "production candidate",
        "custom QUIC implementation",
        "rejected",
    ):
        assert rule.casefold() in text.casefold()


def test_wp3_proposes_exact_transport_profile_without_freezing_it() -> None:
    text = _normalized()

    for rule in (
        "`nbsr-quic-1`",
        "proposed ALPN",
        "mutual TLS 1.3",
        "private lab CA",
        "certificate SAN",
        "no 0-RTT",
        "Source Edge",
        "Destination Edge",
    ):
        assert rule.casefold() in text.casefold()


def test_wp3_reuse_key_excludes_service_authorization() -> None:
    text = _normalized()

    assert "(source_edge_id, destination_edge_id, trust_profile_id, ALPN, protocol_version)" in text
    assert "Service Identity is not part of transport authentication" in text
    assert "RouteGrant is not reusable transport authority" in text


def test_wp3_identifies_stream_binding_wire_gap_without_allocating_values() -> None:
    text = _normalized()

    for rule in (
        "STREAM_OPEN",
        "STREAM_ACCEPT",
        "STREAM_REJECT",
        "no frozen message-body schema",
        "QUIC stream ID",
        "Service Channel",
        "RouteGrant",
        "Core v0.2",
        "new numeric body keys",
        "human approval",
    ):
        assert rule.casefold() in text.casefold()


def test_wp3_decision_preserves_every_frozen_core_surface() -> None:
    text = _normalized()

    for rule in (
        "17 message codes remain unchanged",
        "19 error codes remain unchanged",
        "six D6 schemas remain unchanged",
        "frozen state transitions remain unchanged",
        "no new critical extension",
        "no new COSE wrapper",
    ):
        assert rule.casefold() in text.casefold()


def test_v36_record_and_roadmap_point_to_wp3_transport_review() -> None:
    decisions = " ".join(V36_DECISIONS.read_text(encoding="utf-8").split())
    roadmap = " ".join(ROADMAP.read_text(encoding="utf-8").split())

    assert "WP3 single-service transport proposal prepared" in decisions
    assert "WP3 transport decision review" in decisions
    assert "Phase E decision package prepared; human approval pending" in roadmap
    assert "application-stream binding wire gap" in roadmap
