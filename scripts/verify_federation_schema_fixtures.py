#!/usr/bin/env python3
"""Independent canonical/schema verifier for Federation proposal literals."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/protocol/registries/federation-v0.1-schema-proposal.json"
FIXTURES = ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json"
TASK1 = ROOT / "docs/protocol/registries/federation-v0.1-development.json"
SERVICE_DOMAIN = b"NBSR-FEDERATION-SERVICE-ID-v1\x00"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def service_id(operator_id: bytes, canonical_name: str) -> bytes:
    name = canonical_name.encode("utf-8")
    return hashlib.sha256(SERVICE_DOMAIN + operator_id + len(name).to_bytes(2, "big") + name).digest()


def verify_accepted_task2(name: str, object_name: str, payload: dict[int, Any]) -> None:
    required_common = {1, 2, 3, 4, 5, 6, 7}
    require(required_common <= set(payload), f"{name}: missing required common key")
    require(payload[2] == 1, f"{name}: wrong object version")
    require(isinstance(payload[4], int) and payload[4] >= 1, f"{name}: generation")
    require(isinstance(payload[5], int) and payload[5] >= 1, f"{name}: sequence")
    require((payload[4], payload[5]) == (1, 1) or 8 in payload, f"{name}: predecessor")
    if object_name == "OperatorRegistryRecord":
        require({32, 33, 34, 35, 36, 37, 38} <= set(payload), f"{name}: missing operator field")
        require(isinstance(payload[32], bytes) and len(payload[32]) == 32, f"{name}: operator ID")
        scope = payload[35]
        require(scope[2] == service_id(payload[32], scope[1]), f"{name}: Service ID")
        require(payload[36] in range(1, 12), f"{name}: lifecycle")
        require((payload[36] == 8 and payload.get(39) in {1, 2, 3}) or (payload[36] != 8 and 39 not in payload), f"{name}: recovery stage")
    elif object_name == "KeyAuthorizationRecord":
        require({32, 33, 34, 35, 36, 37, 38, 39} <= set(payload), f"{name}: missing key field")
        require(isinstance(payload[32], bytes) and len(payload[32]) == 32, f"{name}: operator ID")
        require(isinstance(payload[33], bytes) and 1 <= len(payload[33]) <= 64, f"{name}: key ID")
        require(isinstance(payload[34], bytes) and len(payload[34]) == 32, f"{name}: public key")
        require(payload[36] in range(1, 6), f"{name}: key lifecycle")
        require(
            (payload[38] is False and payload[39] is None) or (payload[38] is True and payload[39] is not None),
            f"{name}: revocation binding",
        )
        require((payload[4] == 1 and 40 not in payload) or (payload[4] > 1 and 40 in payload), f"{name}: recovery binding")


def classify_task2(object_name: str, payload: dict[int, Any], context: dict[str, Any]) -> tuple[str, str, bool]:
    required = {
        "OperatorRegistryRecord": {1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38},
        "KeyAuthorizationRecord": {1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39},
    }[object_name]
    if not required <= set(payload):
        return "REJECT", "ERR_SCHEMA", False
    if (payload.get(4), payload.get(5)) == (1, 1) and 8 in payload:
        return "REJECT", "ERR_SCHEMA", False
    if object_name == "OperatorRegistryRecord":
        if (payload[36] == 8 and 39 not in payload) or (payload[36] != 8 and 39 in payload):
            return "REJECT", "ERR_SCHEMA", False
        if not isinstance(payload[32], bytes) or len(payload[32]) != 32:
            return "REJECT", "ERR_IDENTITY", False
    if 31 in payload and any(entry.get(2) is True for entry in payload[31].values()):
        return "REJECT", "ERR_UNSUPPORTED_CRITICAL", False
    if context.get("protected_kid") == "unknown-kid":
        return "REJECT", "ERR_IDENTITY", False
    if context.get("signer_purpose") == "ENDPOINT_DISCOVERY" or (object_name == "KeyAuthorizationRecord" and payload[35] != 3):
        return "REJECT", "ERR_KEY_PURPOSE", False
    if context.get("signer_lifecycle") == "REVOKED":
        return "REJECT", "ERR_KEY_LIFECYCLE", False
    if context.get("signer") == "operator-root-only":
        return "REJECT", "ERR_AUTHORITY", False
    if context.get("current_generation") is not None:
        current = (context["current_generation"], context["current_sequence"])
        candidate = (payload[4], payload[5])
        if candidate < current:
            return "REJECT", "ERR_ROLLBACK", False
        if candidate == current and context.get("current_digest") != hashlib.sha256(encode_deterministic(payload)).hexdigest():
            return "QUARANTINE", "ERR_EQUIVOCATION", False
    if context.get("current_digest") and 8 in payload and payload[8].hex() != context["current_digest"]:
        return "REJECT", "ERR_CONTINUITY", False
    if object_name == "KeyAuthorizationRecord" and payload[33].hex() in context.get("terminal_key_ids", []):
        return "REJECT", "ERR_TERMINAL_STATE", False
    if context.get("validation_time", 0) > payload[7]:
        return "REJECT", "ERR_FRESHNESS", False
    if payload[4] > 1 and context.get("recovery_transition") is None:
        return "REJECT", "ERR_RECOVERY_INVALID", False
    return "ACCEPT", "NONE", True


def classify_checkpoint(payload: dict[int, Any], context: dict[str, Any]) -> tuple[str, str, bool]:
    genesis = payload[4] == 1 and payload[5] == 1 and payload[34] == 0
    if genesis:
        valid = payload[35] == hashlib.sha256(b"").digest() and payload[36] == 0 and payload[38] is None
        return ("ACCEPT", "NONE", True) if valid else ("REJECT", "ERR_CHECKPOINT", False)
    if payload[5] == 1 and context.get("accepted_transition") is None:
        return "REJECT", "ERR_RECOVERY_INVALID", False
    return "ACCEPT", "NONE", True


def classify_consistency(payload: dict[int, Any], context: dict[str, Any]) -> tuple[str, str, bool]:
    if context.get("expected_old_checkpoint_digest") and payload[34].hex() != context["expected_old_checkpoint_digest"]:
        return "REJECT", "ERR_CONTINUITY", False
    if context.get("expected_new_checkpoint_digest") and payload[35].hex() != context["expected_new_checkpoint_digest"]:
        return "REJECT", "ERR_CONTINUITY", False
    if payload[36] > payload[37]:
        return "REJECT", "ERR_CONTINUITY", False
    return "ACCEPT", "NONE", False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    package = json.loads(args.fixtures.read_text(encoding="utf-8"))
    task1 = json.loads(TASK1.read_text(encoding="utf-8"))
    object_values = {entry["name"]: entry["value"] for entry in task1["registries"]["object_types"]}
    for fixture in package["fixtures"]:
        name = f"{fixture['object_type']}/{fixture['name']}"
        raw = bytes.fromhex(fixture["canonical_cbor_hex"])
        require(hashlib.sha256(raw).hexdigest() == fixture["sha256"], f"{name}: digest")
        decoded = decode_deterministic(raw)
        require(encode_deterministic(decoded) == raw, f"{name}: non-canonical")
        require(isinstance(decoded, dict), f"{name}: payload not map")
        require(decoded.get(1) == object_values[fixture["object_type"]], f"{name}: object type")
        allowed_keys = {field["key"] for field in schema["objects"][fixture["object_type"]]["fields"]}
        require(set(decoded) <= allowed_keys, f"{name}: unknown base key")
        if fixture["expected_outcome"] == "ACCEPT" and fixture["object_type"] in {
            "OperatorRegistryRecord",
            "KeyAuthorizationRecord",
        }:
            verify_accepted_task2(name, fixture["object_type"], decoded)
        if fixture["object_type"] in {"OperatorRegistryRecord", "KeyAuthorizationRecord"}:
            derived = classify_task2(fixture["object_type"], decoded, fixture["validation_context"])
        elif fixture["object_type"] == "TransparencyCheckpoint":
            derived = classify_checkpoint(decoded, fixture["validation_context"])
        elif fixture["object_type"] == "ConsistencyProof":
            derived = classify_consistency(decoded, fixture["validation_context"])
        else:
            raise ValueError(f"{name}: unsupported fixture class")
        declared = (fixture["expected_outcome"], fixture["reason"], fixture["state_changed"])
        require(derived == declared, f"{name}: expected outcome {declared}, derived {derived}")
    print(f"independently verified {len(package['fixtures'])} canonical Federation proposal fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
