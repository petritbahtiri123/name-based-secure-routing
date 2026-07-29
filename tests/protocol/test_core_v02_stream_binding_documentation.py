from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "docs" / "protocol" / "core-v0.2-stream-binding-schema-proposal.md"
WP3_DECISION = ROOT / "docs" / "protocol" / "wp3-single-service-transport-decision.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"

TABLE_HEADER = "| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |"
EXPECTED_FIELDS = {
    "STREAM_OPEN body": {
        0: "body_version",
        1: "quic_stream_id",
        2: "channel_id",
        3: "route_id",
        4: "route_grant_digest",
        5: "transport",
        6: "port",
    },
    "STREAM_ACCEPT body": {
        0: "body_version",
        1: "quic_stream_id",
        2: "channel_id",
        3: "route_id",
        4: "accepted_at",
    },
    "STREAM_REJECT body": {
        0: "body_version",
        1: "quic_stream_id",
        2: "channel_id",
        3: "route_id",
        4: "protocol_error",
    },
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _normalized(path: Path = PROPOSAL) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _schema_rows(schema_name: str) -> list[list[str]]:
    text = PROPOSAL.read_text(encoding="utf-8")
    section_start = text.index(f"## {schema_name}")
    section_end = text.find("\n## ", section_start + 1)
    section = text[section_start : section_end if section_end >= 0 else None]
    lines = section.splitlines()
    header_index = lines.index(TABLE_HEADER)
    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def test_stream_binding_proposal_is_complete_unique_and_review_gated() -> None:
    assert "**Status:** human approval required; not frozen" in PROPOSAL.read_text(encoding="utf-8")

    for schema_name, expected_fields in EXPECTED_FIELDS.items():
        rows = _schema_rows(schema_name)
        keys = [int(row[0]) for row in rows]
        actual_fields = {int(row[0]): row[1].strip("`") for row in rows}

        assert len(keys) == len(set(keys)), schema_name
        assert actual_fields == expected_fields, schema_name
        assert all(len(row) == 7 for row in rows), schema_name
        assert all(row[2] == "required" for row in rows), schema_name
        assert all(all(cell and cell != "TBD" for cell in row[3:]) for row in rows)


def test_stream_binding_is_transport_and_authorization_bound() -> None:
    text = _normalized()

    for rule in (
        "stream 0",
        "source-initiated bidirectional",
        "shortest-form QUIC variable-length integer",
        "65,536 bytes",
        "deterministic CBOR ControlEnvelope",
        "no application bytes",
        "matching `STREAM_ACCEPT`",
        "same authenticated Transport Session",
        "one `quic_stream_id`",
        "one `channel_id`",
        "one `route_id`",
        "RouteGrant",
        "expiry",
        "revocation",
        "policy",
        "no 0-RTT",
    ):
        assert rule.casefold() in text.casefold()


def test_stream_binding_preserves_replay_and_privacy_invariants() -> None:
    text = _normalized()

    for rule in (
        "`request_id` is unique",
        "`monotonic_sequence` strictly increases",
        "opened at most once",
        "origin endpoint",
        "must not appear",
        "client-visible",
        "NBSR_E_PROFILE_UNSUPPORTED",
        "unknown numeric key",
    ):
        assert rule.casefold() in text.casefold()


def test_stream_binding_records_unresolved_route_and_session_dependencies() -> None:
    text = _normalized()

    for rule in (
        "CLIENT_HELLO",
        "EDGE_HELLO",
        "ROUTE_OPEN",
        "ROUTE_ACCEPT",
        "ROUTE_REJECT",
        "separate human approval",
        "blocks WP3 runtime",
    ):
        assert rule.casefold() in text.casefold()


def test_stream_binding_does_not_change_frozen_core_v01() -> None:
    text = _normalized()

    for rule in (
        "17 message codes remain unchanged",
        "19 error codes remain unchanged",
        "six D6 schemas remain unchanged",
        "state registries and transitions remain unchanged",
        "no new critical extension",
        "no new COSE wrapper",
        "protocol version 2",
        "separate approval",
    ):
        assert rule.casefold() in text.casefold()


def test_decision_records_point_to_the_schema_approval_gate() -> None:
    wp3 = _normalized(WP3_DECISION)
    decisions = _normalized(V36_DECISIONS)
    roadmap = _normalized(ROADMAP)

    assert "Core v0.2 stream-binding schema proposal prepared" in wp3
    assert "stream-binding schema approval" in decisions
    assert "Core v0.2 stream-binding schema proposal prepared" in roadmap
    assert "runtime remains blocked" in roadmap


def test_changed_document_local_links_resolve() -> None:
    for path in (PROPOSAL, WP3_DECISION, V36_DECISIONS, ROADMAP):
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            assert (path.parent / target).resolve().exists(), (path, raw_target)
