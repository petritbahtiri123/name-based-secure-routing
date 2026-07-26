from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIRE_SCHEMA = ROOT / "docs" / "protocol" / "core-v0.1-wire-schema.md"
DECISIONS = ROOT / "docs" / "protocol" / "wp1-decisions.md"
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-07-26-wp1-protocol-data-model.md"

EXPECTED_FIELDS = {
    "ServiceRecord": {
        0: "record_version",
        1: "canonical_name",
        2: "sequence",
        3: "owner_key_id",
        4: "service_id",
        5: "destination_operator_id",
        6: "destination_edge_set",
        7: "origin_connector_id",
        8: "transports",
        9: "ports",
        10: "route_profiles",
        11: "publication_mode",
        12: "not_before",
        13: "not_after",
        14: "revocation_ref",
    },
    "RouteIntent": {
        0: "intent_version",
        1: "resolution_context_digest",
        2: "canonical_name",
        3: "service_id",
        4: "source_operator_id",
        5: "source_edge_id",
        6: "destination_operator_id",
        7: "destination_edge_set",
        8: "allowed_transports",
        9: "allowed_ports",
        10: "created_at",
        11: "expires_at",
        12: "record_sequence",
        13: "policy_hash",
        14: "route_id",
        15: "lease_id",
    },
    "RouteGrant": {
        0: "grant_version",
        1: "route_id",
        2: "name_digest",
        3: "service_id",
        4: "source_operator_id",
        5: "source_edge_id",
        6: "destination_operator_id",
        7: "destination_edge_set",
        8: "allowed_transports",
        9: "allowed_ports",
        10: "client_session_key_thumbprint",
        11: "not_before",
        12: "expires_at",
        13: "lease_id",
        14: "record_sequence",
        15: "policy_hash",
        16: "unique_nonce",
    },
    "Revocation": {
        0: "revocation_version",
        1: "revocation_id",
        2: "issuer_key_id",
        3: "generation",
        4: "target_type",
        5: "target_id",
        6: "mode",
        7: "not_before",
        8: "expires_at",
        9: "record_sequence",
        10: "reason_code",
    },
    "ProtocolError": {
        0: "error_version",
        1: "error_code",
        2: "request_id",
        3: "retryable",
        4: "retry_after_seconds",
    },
    "ControlEnvelope": {
        0: "protocol_version",
        1: "message_type",
        2: "request_id",
        3: "session_id",
        4: "monotonic_sequence",
        5: "body",
        6: "critical_extension_keys",
    },
}

TABLE_HEADER = "| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |"


def _schema_rows(schema_name: str) -> list[list[str]]:
    text = WIRE_SCHEMA.read_text(encoding="utf-8")
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


def test_all_six_wire_schema_tables_freeze_complete_unique_numeric_mappings() -> None:
    for schema_name, expected_fields in EXPECTED_FIELDS.items():
        rows = _schema_rows(schema_name)
        numeric_keys = [int(row[0]) for row in rows]
        actual_fields = {int(row[0]): row[1].strip("`") for row in rows}

        assert len(numeric_keys) == len(set(numeric_keys)), schema_name
        assert actual_fields == expected_fields, schema_name


def test_every_wire_field_has_presence_type_bounds_and_semantic_validation() -> None:
    for schema_name in EXPECTED_FIELDS:
        rows = _schema_rows(schema_name)

        assert all(len(row) == 7 for row in rows), schema_name
        assert all(row[2] in {"required", "optional"} for row in rows), schema_name
        assert all(all(cell and cell != "TBD" for cell in row[3:]) for row in rows), schema_name


def test_d6_and_task4_use_the_wire_schema_as_the_only_mapping_source() -> None:
    decisions = DECISIONS.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "## D6 - Core v0.1 wire schema freeze" in decisions
    assert "docs/protocol/core-v0.1-wire-schema.md" in decisions
    assert "docs/protocol/core-v0.1-wire-schema.md" in plan
    assert "use the field order from" not in plan.lower()
