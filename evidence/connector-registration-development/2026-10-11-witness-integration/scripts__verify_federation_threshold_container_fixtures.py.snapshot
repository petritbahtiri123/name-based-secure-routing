from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json"
FIXTURE_PATH = ROOT / "vectors/federation-v0.1-threshold-container/literal-fixtures.json"
DOMAIN = "NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1"
BINDING_DOMAIN = "NBSR-FEDERATION-CAPABILITY-SESSION-BINDING-v1"
CLASS = {
    "OPERATOR_RECOVERY": 2,
    "DEVELOPMENT_REGISTRAR": 3,
    "FEDERATION_AUTHORITY": 4,
    "WITNESS": 6,
    "CONFLICT_RESOLUTION": 11,
    "APPEAL": 12,
}
PURPOSE = {"RECOVERY": 2, "REGISTRY_SIGNING": 3, "WITNESS": 9, "REVOCATION": 12, "GOVERNANCE": 13}
OBJECT = {
    "OperatorRegistryRecord": 1,
    "FederationTrustBundle": 5,
    "WitnessStatement": 9,
    "TypedRevocationRecord": 13,
    "RecoveryTransitionRecord": 16,
    "ConflictResolutionRecord": 17,
    "AppealDecisionRecord": 18,
}
MESSAGE = {
    "TRUST_BUNDLE_UPDATE": 16396,
    "WITNESS_STATEMENT": 16404,
    "REVOCATION_PUSH": 16407,
    "REENTRY_EVIDENCE": 16417,
    "OPERATOR_REGISTRATION_REQUEST": 16418,
    "CONFLICT_RESOLUTION_PUBLISH": 16438,
    "APPEAL_RESPONSE": 16441,
}


def result(decision: str, reason: str) -> tuple[str, str, bool]:
    return decision, reason, False


def policy_digest(policy: dict[int, Any]) -> bytes:
    candidate = dict(policy)
    candidate[2] = None
    return hashlib.sha256(encode_deterministic(candidate)).digest()


def nested_depth(value: object) -> int:
    if type(value) is dict:
        return 1 + max((max(nested_depth(key), nested_depth(item)) for key, item in value.items()), default=0)
    if type(value) is list:
        return 1 + max((nested_depth(item) for item in value), default=0)
    return 0


def capability_session_binding(validation: dict[str, Any]) -> bytes:
    transcript_digest = bytes.fromhex(validation["authenticated_session_transcript_digest"])
    value = {
        1: BINDING_DOMAIN,
        2: validation["selected_core_version"],
        3: validation["agreed_federation_version"],
        4: validation["agreed_profile_id"],
        5: [6],
        6: transcript_digest,
    }
    return hashlib.sha256(encode_deterministic(value)).digest()


def expected_signature_context(envelope: dict[int, Any], group_id: str, session_binding: bytes) -> dict[int, Any]:
    return {
        1: DOMAIN,
        2: envelope[1],
        3: envelope[2],
        4: envelope[3],
        5: envelope[4],
        6: envelope[5][2],
        7: group_id,
        8: envelope[6],
        9: envelope[7],
        10: envelope[8],
        11: 6,
        12: session_binding,
    }


def _extensions(value: object) -> str | None:
    if type(value) is not list or any(
        type(item) is not dict
        or set(item) != {1, 2, 3}
        or type(item[1]) is not int
        or type(item[2]) is not bool
        or type(item[3]) is not bytes
        for item in value
    ):
        return "ERR_SCHEMA"
    if any(item[2] for item in value):
        return "ERR_UNSUPPORTED_CRITICAL"
    return None


def _valid_hex(value: object, minimum: int, maximum: int) -> bool:
    if type(value) is not str:
        return False
    try:
        decoded = bytes.fromhex(value)
    except ValueError:
        return False
    return minimum <= len(decoded) <= maximum and decoded.hex() == value


def _valid_authority_row(row: object) -> bool:
    if type(row) is not dict or set(row) != {
        "authority_id",
        "authority_class",
        "key_purpose",
        "kid",
        "organization_id",
        "public_key",
        "not_before",
        "expires_at",
        "revoked",
        "eligible_policy_groups",
    }:
        return False
    return (
        _valid_hex(row["authority_id"], 1, 64)
        and _valid_hex(row["kid"], 1, 64)
        and _valid_hex(row["organization_id"], 1, 64)
        and _valid_hex(row["public_key"], 32, 32)
        and type(row["authority_class"]) is int
        and type(row["key_purpose"]) is int
        and type(row["not_before"]) is int
        and type(row["expires_at"]) is int
        and type(row["revoked"]) is bool
        and type(row["eligible_policy_groups"]) is list
        and all(type(item) is str and item for item in row["eligible_policy_groups"])
    )


def classify(raw: bytes, envelope: object, validation: dict[str, Any], profile: dict[str, Any]) -> tuple[str, str, bool]:
    limits = profile["resource_limits"]
    if type(envelope) is not dict:
        return result("REJECT", "ERR_SCHEMA")
    if not set(profile["required_validation_context"]) <= set(validation):
        return result("REJECT", "ERR_SCHEMA")
    if (
        type(validation.get("now")) is not int
        or type(validation.get("expected_request_event_transition_id")) is not str
        or type(validation.get("accepted_authority_registry")) is not list
        or any(not _valid_authority_row(item) for item in validation["accepted_authority_registry"])
    ):
        return result("REJECT", "ERR_SCHEMA")
    if validation.get("capability_agreement_authenticated") is not True:
        return result("REJECT", "ERR_DOWNGRADE")
    if validation.get("selected_core_version") != 2 or validation.get("agreed_federation_version") != 1:
        return result("REJECT", "ERR_VERSION")
    if validation.get("agreed_profile_id") != "nbsr-federation-dev-v1":
        return result("REJECT", "ERR_VERSION")
    negotiated = validation.get("negotiated_capabilities", [])
    authenticated = validation.get("authenticated_capabilities", [])
    if (
        type(negotiated) is not list
        or type(authenticated) is not list
        or any(type(item) is not str or not item for item in negotiated + authenticated)
        or negotiated != sorted(set(negotiated))
        or authenticated != sorted(set(authenticated))
    ):
        return result("REJECT", "ERR_SCHEMA")
    transcript_digest = validation.get("authenticated_session_transcript_digest")
    try:
        transcript_digest_bytes = bytes.fromhex(transcript_digest)
    except (TypeError, ValueError):
        return result("REJECT", "ERR_SCHEMA")
    if len(transcript_digest_bytes) != 32:
        return result("REJECT", "ERR_SCHEMA")
    session_binding = capability_session_binding(validation)
    if negotiated != authenticated:
        return result("REJECT", "ERR_DOWNGRADE")
    if validation.get("single_sign1_fallback") is True:
        return result("REJECT", "ERR_DOWNGRADE")
    if "THRESHOLD_EVIDENCE" not in negotiated:
        return result("REJECT", "ERR_UNSUPPORTED_CRITICAL")
    groups = envelope.get(9)
    if type(groups) is not list:
        return result("REJECT", "ERR_SCHEMA")
    signature_count = sum(len(group.get(2, [])) if type(group) is dict and type(group.get(2)) is list else 0 for group in groups)
    if (
        nested_depth(envelope) > limits["max_nested_depth"]
        or len(groups) > limits["max_threshold_groups"]
        or signature_count > limits["max_total_signer_entries"]
        or signature_count > limits["max_signature_verifications"]
        or any(
            type(group) is dict and type(group.get(2)) is list and len(group[2]) > limits["max_signatures_per_group"] for group in groups
        )
    ):
        return result("REJECT", "ERR_RESOURCE_LIMIT")
    extension_error = _extensions(envelope.get(10, []))
    if extension_error:
        return result("REJECT", extension_error)
    if set(envelope) - set(range(1, 11)) or not set(range(1, 10)) <= set(envelope):
        return result("REJECT", "ERR_SCHEMA")
    if type(envelope[1]) is not int or envelope[1] != 1 or envelope[2] != "nbsr-federation-dev-v1":
        return result("REJECT", "ERR_VERSION")
    if type(envelope[4]) is not bytes or len(envelope[4]) != 32 or type(envelope[6]) is not bytes or len(envelope[6]) != 32:
        return result("REJECT", "ERR_SCHEMA")
    if type(envelope[3]) is not int or envelope[3] < 0:
        return result("REJECT", "ERR_SCHEMA")
    policy = envelope[5]
    if type(policy) is not dict or type(policy.get(1)) is not int or policy.get(1) != 1 or policy.get(2) != policy_digest(policy):
        return result("REJECT", "ERR_SCHEMA")
    if set(policy) - {1, 2, 3, 4, 5, 6, 7, 8, 9} or not {1, 2, 3, 4, 5, 6, 7, 9} <= set(policy):
        return result("REJECT", "ERR_SCHEMA")
    if 8 in policy:
        extension_error = _extensions(policy[8])
        if extension_error:
            return result("REJECT", extension_error)
    requirements = policy.get(5)
    if type(requirements) is not list or len(requirements) != len(groups):
        return result("REJECT", "ERR_AUTHORITY")
    named = profile["named_policies"].get(policy.get(3))
    if named is None or policy.get(4) is not named["deny_only"]:
        return result("REJECT", "ERR_AUTHORITY")
    if (
        type(policy.get(6)) is not list
        or any(type(item) is not int for item in policy[6])
        or type(policy.get(7)) is not list
        or any(type(item) is not int for item in policy[7])
        or type(policy.get(9)) is not list
        or any(type(item) is not str for item in policy[9])
    ):
        return result("REJECT", "ERR_SCHEMA")
    if policy.get(6) != sorted(OBJECT[item] for item in named["allowed_object_classes"]):
        return result("REJECT", "ERR_AUTHORITY")
    if policy.get(7) != sorted(MESSAGE[item] for item in named["allowed_message_types"]):
        return result("REJECT", "ERR_AUTHORITY")
    if policy.get(9) != sorted(named["allowed_authority_effects"]):
        return result("REJECT", "ERR_AUTHORITY")
    lineage, authorization = envelope[7], envelope[8]
    if type(lineage) is not dict or set(lineage) != {1, 2, 3}:
        return result("REJECT", "ERR_SCHEMA")
    if type(authorization) is not dict or set(authorization) != {1, 2, 3, 4, 5, 6, 7}:
        return result("REJECT", "ERR_SCHEMA")
    if (
        any(value is not None and (type(value) is not int or value < 0) for value in (lineage[1], lineage[2]))
        or lineage[3] is not None
        and (type(lineage[3]) is not bytes or len(lineage[3]) != 32)
        or type(authorization[1]) is not int
        or type(authorization[2]) is not bytes
        or not 16 <= len(authorization[2]) <= 64
        or type(authorization[3]) is not int
        or authorization[3] < 0
        or type(authorization[4]) is not int
        or authorization[4] < 0
        or authorization[3] > authorization[4]
        or type(authorization[5]) is not bytes
        or len(authorization[5]) != 32
        or type(authorization[6]) is not int
        or authorization[6] != 1
        or type(authorization[7]) is not str
    ):
        return result("REJECT", "ERR_SCHEMA")
    if envelope[3] not in policy[6]:
        return result("REJECT", "ERR_AUTHORITY")
    if authorization.get(1) not in policy[7]:
        return result("REJECT", "ERR_REPLAY")
    if authorization.get(7) not in policy[9] or (policy[4] and authorization.get(7) != "deny"):
        return result("REJECT", "ERR_POLICY_EXPANSION")
    unsigned_authorization = {key: value for key, value in authorization.items() if key != 5}
    if authorization.get(5) != hashlib.sha256(encode_deterministic(unsigned_authorization)).digest():
        return result("REJECT", "ERR_REPLAY")
    if authorization.get(2, b"").hex() != validation["expected_request_event_transition_id"]:
        return result("REJECT", "ERR_REPLAY")
    if not authorization.get(3, -1) <= validation["now"] <= authorization.get(4, -1):
        return result("REJECT", "ERR_FRESHNESS")
    rows = validation["accepted_authority_registry"]
    if len({item["kid"] for item in rows}) != len(rows) or len({item["public_key"] for item in rows}) != len(rows):
        return result("REJECT", "ERR_IDENTITY")
    authorities = {(bytes.fromhex(item["authority_id"]), bytes.fromhex(item["kid"])): item for item in rows}
    seen_global: set[bytes] = set()
    for group_index, (requirement, group) in enumerate(zip(requirements, groups, strict=True)):
        named_group = named["groups"][group_index]
        expected_class, expected_purpose = CLASS[named_group["class"]], PURPOSE[named_group["purpose"]]
        if type(requirement) is not dict or set(requirement) - set(range(1, 12)) or not set(range(1, 11)) <= set(requirement):
            return result("REJECT", "ERR_SCHEMA")
        if 11 in requirement:
            extension_error = _extensions(requirement[11])
            if extension_error:
                return result("REJECT", extension_error)
        if any(type(requirement[key]) is not int or requirement[key] < 1 for key in (2, 3, 7)):
            return result("REJECT", "ERR_SCHEMA")
        expected_minimum_organizations = min(named_group["required"], named["minimum_organizations"])
        if (
            requirement.get(1) != named_group["id"]
            or requirement.get(2) != named_group["required"]
            or requirement.get(3) != named_group["eligible"]
            or requirement.get(4) != [expected_class]
            or requirement.get(8) != [expected_purpose]
            or requirement.get(9) is not named["deny_only"]
            or requirement.get(5) != [[expected_class, named_group["required"]]]
            or requirement.get(7) != expected_minimum_organizations
        ):
            return result("REJECT", "ERR_AUTHORITY")
        if requirement.get(10) != envelope[6]:
            return result("REJECT", "ERR_SCOPE")
        eligible = requirement.get(6)
        if type(eligible) is not list or any(type(item) is not bytes for item in eligible):
            return result("REJECT", "ERR_SCHEMA")
        if any(not 1 <= len(item) <= limits["max_authority_identity_bytes"] for item in eligible):
            return result("REJECT", "ERR_SCHEMA")
        registry_eligible = sorted(
            set(
                bytes.fromhex(item["authority_id"])
                for item in rows
                if f"{policy[3]}:{requirement[1]}" in item.get("eligible_policy_groups", [])
            )
        )
        if len(eligible) != requirement[3] or eligible != sorted(set(eligible)) or eligible != registry_eligible:
            return result("REJECT", "ERR_AUTHORITY")
        if type(group) is not dict or set(group) != {1, 2} or type(group[2]) is not list:
            return result("REJECT", "ERR_SCHEMA")
        if group[1] != requirement[1]:
            return result("REJECT", "ERR_AUTHORITY")
        entries, tuples, organizations = group[2], [], set()
        for entry in entries:
            if type(entry) is not dict or not set(range(1, 8)) <= set(entry) or set(entry) - set(range(1, 9)):
                return result("REJECT", "ERR_SCHEMA")
            if 8 in entry:
                extension_error = _extensions(entry[8])
                if extension_error:
                    return result("REJECT", extension_error)
            authority_id, kid = entry[2], entry[4]
            if not all(type(value) is bytes for value in (authority_id, kid, entry[6], entry[7])):
                return result("REJECT", "ERR_SCHEMA")
            if type(entry[1]) is not int or type(entry[3]) is not int:
                return result("REJECT", "ERR_SCHEMA")
            if not authority_id or not kid or entry[5] == b"":
                return result("REJECT", "ERR_SCHEMA")
            if (
                len(authority_id) > limits["max_authority_identity_bytes"]
                or len(kid) > limits["max_kid_bytes"]
                or entry[5] is not None
                and (type(entry[5]) is not bytes or len(entry[5]) > limits["max_organization_identity_bytes"])
            ):
                return result("REJECT", "ERR_RESOURCE_LIMIT")
            if authority_id not in eligible:
                return result("REJECT", "ERR_AUTHORITY")
            ordering = (entry[1], authority_id, entry[3], kid)
            tuples.append(ordering)
            if authority_id in seen_global:
                return result("REJECT", "ERR_AUTHORITY")
            seen_global.add(authority_id)
            authority = authorities.get((authority_id, kid))
            if authority is None:
                return result("REJECT", "ERR_IDENTITY")
            if entry[1] != authority["authority_class"] or entry[1] not in requirement[4]:
                return result("REJECT", "ERR_AUTHORITY")
            if entry[3] != authority["key_purpose"] or entry[3] not in requirement[8]:
                return result("REJECT", "ERR_KEY_PURPOSE")
            if authority["revoked"]:
                return result("REJECT", "ERR_REVOKED")
            if not authority["not_before"] <= validation["now"] <= authority["expires_at"]:
                return result("REJECT", "ERR_FRESHNESS")
            if entry[5] is None or entry[5].hex() != authority["organization_id"]:
                return result("REJECT", "ERR_AUTHORITY")
            organizations.add(entry[5])
            if entry[6] != envelope[4]:
                return result("REJECT", "ERR_SIGNATURE_INVALID")
            if not entry[7].startswith(b"\xd2"):
                return result("REJECT", "ERR_SCHEMA")
            try:
                cose = decode_deterministic(entry[7][1:])
            except Exception:
                return result("REJECT", "ERR_NON_CANONICAL")
            if type(cose) is not list or len(cose) != 4 or b"\xd2" + encode_deterministic(cose) != entry[7]:
                return result("REJECT", "ERR_NON_CANONICAL")
            try:
                protected_raw, unprotected, signed_payload, signature = cose
                protected = decode_deterministic(protected_raw)
                if protected != {1: -8, 4: kid} or unprotected != {}:
                    return result("REJECT", "ERR_CRYPTO_PROFILE")
                signed_context = decode_deterministic(signed_payload)
                if type(signed_context) is not dict:
                    return result("REJECT", "ERR_SCHEMA")
                expected = expected_signature_context(envelope, group[1], session_binding)
                if signed_context != expected:
                    if signed_context.get(11) != 6:
                        return result("REJECT", "ERR_DOWNGRADE")
                    if signed_context.get(12) != expected[12]:
                        return result("REJECT", "ERR_REPLAY")
                    if signed_context.get(5) != expected[5]:
                        return result("REJECT", "ERR_SIGNATURE_INVALID")
                    if signed_context.get(8) != expected[8]:
                        return result("REJECT", "ERR_SCOPE")
                    if signed_context.get(9) != expected[9] or signed_context.get(10) != expected[10]:
                        return result("REJECT", "ERR_REPLAY")
                    return result("REJECT", "ERR_SIGNATURE_INVALID")
                sig_structure = encode_deterministic(["Signature1", protected_raw, b"", signed_payload])
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority["public_key"])).verify(signature, sig_structure)
            except (InvalidSignature, ValueError, TypeError, KeyError, cbor2.CBORDecodeError):
                return result("REJECT", "ERR_SIGNATURE_INVALID")
        if tuples != sorted(tuples) or len(set(tuples)) != len(tuples) or len(entries) > requirement[3]:
            return result("REJECT", "ERR_AUTHORITY")
        if len(entries) < requirement[2]:
            return result("PENDING", "ERR_EVIDENCE_MISSING" if signature_count == 0 else "ERR_WITNESS_THRESHOLD")
        class_counts = {authority_class: sum(entry[1] == authority_class for entry in entries) for authority_class, _ in requirement[5]}
        if any(class_counts[authority_class] < count for authority_class, count in requirement[5]):
            return result("REJECT", "ERR_AUTHORITY")
        if len(organizations) < requirement[7]:
            return result("REJECT", "ERR_WITNESS_THRESHOLD")
    return result("ACCEPT", "NONE")


def verify_literal(
    raw: bytes, validation: dict[str, Any], profile: dict[str, Any], *, decoder: Any = decode_deterministic
) -> tuple[str, str, bool]:
    if len(raw) > profile["resource_limits"]["max_encoded_container_bytes"]:
        return result("REJECT", "ERR_RESOURCE_LIMIT")
    try:
        envelope = decoder(raw)
    except Exception:
        return result("REJECT", "ERR_PARSE")
    if encode_deterministic(envelope) != raw:
        return result("REJECT", "ERR_NON_CANONICAL")
    return classify(raw, envelope, validation, profile)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify the frozen package")
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_PATH)
    args = parser.parse_args()
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    package = json.loads(args.fixtures.read_text(encoding="utf-8"))
    for item in package["fixtures"]:
        raw = bytes.fromhex(item["canonical_cbor_hex"])
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError(f"{item['name']}: SHA-256 mismatch")
        observed = verify_literal(raw, item["validation_context"], profile)
        expected = (item["expected_decision"], item["expected_reason"], item["expected_mutation"])
        if observed != expected:
            raise ValueError(f"{item['name']}: expected {expected}, observed {observed}")
    print(f"independently verified {len(package['fixtures'])} threshold container literals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
