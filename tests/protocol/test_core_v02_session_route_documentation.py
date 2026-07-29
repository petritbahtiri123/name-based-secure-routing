from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "docs" / "protocol" / "core-v0.2-session-route-schema-proposal.md"
STREAM_PROPOSAL = ROOT / "docs" / "protocol" / "core-v0.2-stream-binding-schema-proposal.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"

TABLE_HEADER = "| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |"
EXPECTED_FIELDS = {
    "CLIENT_HELLO body": {
        0: "body_version",
        1: "source_operator_id",
        2: "source_edge_id",
        3: "destination_operator_id",
        4: "destination_edge_id",
        5: "client_nonce",
        6: "client_session_public_key",
        7: "sent_at",
    },
    "EDGE_HELLO body": {
        0: "body_version",
        1: "source_edge_id",
        2: "destination_edge_id",
        3: "client_nonce",
        4: "edge_nonce",
        5: "client_session_key_thumbprint",
        6: "accepted_at",
    },
    "ROUTE_OPEN body": {
        0: "body_version",
        1: "channel_id",
        2: "route_grant",
        3: "edge_nonce",
        4: "requested_transport",
        5: "requested_port",
        6: "opened_at",
        7: "proof_signature",
    },
    "ROUTE_ACCEPT body": {
        0: "body_version",
        1: "channel_id",
        2: "route_id",
        3: "route_grant_digest",
        4: "accepted_at",
    },
    "ROUTE_REJECT body": {
        0: "body_version",
        1: "channel_id",
        2: "route_id",
        3: "route_grant_digest",
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


def test_session_route_proposal_has_complete_unique_approved_mappings() -> None:
    assert "**Status:** approved on 2026-07-29; frozen as a Core v0.2 candidate" in PROPOSAL.read_text(encoding="utf-8")

    for schema_name, expected_fields in EXPECTED_FIELDS.items():
        rows = _schema_rows(schema_name)
        keys = [int(row[0]) for row in rows]
        fields = {int(row[0]): row[1].strip("`") for row in rows}

        assert len(keys) == len(set(keys)), schema_name
        assert fields == expected_fields, schema_name
        assert all(len(row) == 7 for row in rows), schema_name
        assert all(row[2] == "required" for row in rows), schema_name
        assert all(all(cell and cell != "TBD" for cell in row[3:]) for row in rows)


def test_hello_binds_session_identity_key_and_freshness() -> None:
    text = _normalized()

    for rule in (
        "mutual TLS 1.3",
        "certificate SAN",
        "source-chosen unpredictable 16-byte `session_id`",
        "raw 32-byte RFC 8032 Ed25519 public key",
        "SHA-256",
        "client nonce",
        "edge nonce",
        "bounded clock-skew policy",
        "same authenticated QUIC Transport Session",
        "no 0-RTT",
    ):
        assert rule.casefold() in text.casefold()


def test_route_open_freezes_exact_proof_of_possession_transcript() -> None:
    text = _normalized()

    for rule in (
        "`NBSR-ROUTE-OPEN-v2`",
        "deterministic CBOR array",
        "`session_id`",
        "`request_id`",
        "`channel_id`",
        "`route_id`",
        "`service_id`",
        "`destination_edge_id`",
        "`edge_nonce`",
        "`requested_transport`",
        "`requested_port`",
        "`route_grant_digest`",
        "Ed25519",
        "client_session_key_thumbprint",
    ):
        assert rule.casefold() in text.casefold()


def test_route_admission_is_independent_fail_closed_and_origin_private() -> None:
    text = _normalized()

    for rule in (
        "caller-supplied authorized issuer trust context",
        "source and destination admission are independent",
        "most specific frozen ProtocolError",
        "origin endpoint",
        "must not appear",
        "no application stream",
        "NBSR_E_PROFILE_UNSUPPORTED",
        "unknown numeric key",
        "NBSR_E_REPLAY",
    ):
        assert rule.casefold() in text.casefold()


def test_proposal_preserves_core_v01_and_records_remaining_vector_gate() -> None:
    text = _normalized()

    for rule in (
        "17 message codes remain unchanged",
        "19 error codes remain unchanged",
        "six D6 schemas remain unchanged",
        "state registries and transitions remain unchanged",
        "no new critical extension",
        "no new COSE wrapper",
        "protocol version 2",
        "cross-language deterministic vectors",
        "blocks WP3 runtime",
    ):
        assert rule.casefold() in text.casefold()


def test_stream_proposal_approval_and_next_gate_are_recorded() -> None:
    stream = _normalized(STREAM_PROPOSAL)
    decisions = _normalized(V36_DECISIONS)
    roadmap = _normalized(ROADMAP)

    assert "**Status:** approved on 2026-07-29" in stream
    assert "Core v0.2 session and route schema proposal prepared" in decisions
    assert "was approved as a frozen candidate" in decisions
    assert "D8 approved" in decisions
    assert "pending human byte and checksum review" in roadmap
    assert "runtime remains blocked" in roadmap


def test_changed_document_local_links_resolve() -> None:
    for path in (PROPOSAL, STREAM_PROPOSAL, V36_DECISIONS, ROADMAP):
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            assert (path.parent / target).resolve().exists(), (path, raw_target)
