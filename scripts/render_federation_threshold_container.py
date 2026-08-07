from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json"
FIXTURE_PATH = ROOT / "vectors/federation-v0.1-threshold-container/literal-fixtures.json"
TABLE_PATH = ROOT / "docs/protocol/wp8-federation-v0.1-threshold-container-allocation.md"
DOMAIN = "NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1"
BINDING_DOMAIN = "NBSR-FEDERATION-CAPABILITY-SESSION-BINDING-v1"
SESSION_TRANSCRIPT_DIGEST = hashlib.sha256(b"authenticated-federation-session-transcript-v1").digest()
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


def digest(value: object) -> bytes:
    return hashlib.sha256(encode_deterministic(value)).digest()


def capability_session_binding() -> bytes:
    return digest({1: BINDING_DOMAIN, 2: 2, 3: 1, 4: "nbsr-federation-dev-v1", 5: [6], 6: SESSION_TRANSCRIPT_DIGEST})


def authority_id(authority_class: int, index: int) -> bytes:
    return hashlib.sha256(b"authority\x00" + bytes([authority_class, index])).digest()


def policy(name: str, source: dict[str, Any], scope_digest: bytes) -> dict[int, Any]:
    requirements = []
    for group in source["groups"]:
        authority_class = CLASS[group["class"]]
        purpose = PURPOSE[group["purpose"]]
        requirements.append(
            {
                1: group["id"],
                2: group["required"],
                3: group["eligible"],
                4: [authority_class],
                5: [[authority_class, group["required"]]],
                6: sorted(authority_id(authority_class, index) for index in range(1, group["eligible"] + 1)),
                7: min(group["required"], source["minimum_organizations"]),
                8: [purpose],
                9: source["deny_only"],
                10: scope_digest,
            }
        )
    descriptor: dict[int, Any] = {
        1: 1,
        2: None,
        3: name,
        4: source["deny_only"],
        5: requirements,
        6: sorted(OBJECT[item] for item in source["allowed_object_classes"]),
        7: sorted(MESSAGE[item] for item in source["allowed_message_types"]),
        9: sorted(source["allowed_authority_effects"]),
    }
    descriptor[2] = digest(descriptor)
    return descriptor


def signer(
    group_id: str, authority_class: int, purpose: int, index: int, context_base: dict[int, Any], *, organization: bytes | None = None
) -> tuple[dict[int, Any], dict[str, Any]]:
    seed = hashlib.sha256(f"threshold-fixture-key-{authority_class}-{index}".encode()).digest()
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    authority_id_value = authority_id(authority_class, index)
    kid = f"c{authority_class}-k{index}".encode()
    org = organization if organization is not None else hashlib.sha256(b"organization\x00" + bytes([authority_class, index])).digest()[:16]
    signature_context = dict(context_base)
    signature_context[7] = group_id
    payload = encode_deterministic(signature_context)
    protected = encode_deterministic({1: -8, 4: kid})
    signature = private.sign(encode_deterministic(["Signature1", protected, b"", payload]))
    cose = b"\xd2" + encode_deterministic([protected, {}, payload, signature])
    entry = {1: authority_class, 2: authority_id_value, 3: purpose, 4: kid, 5: org, 6: context_base[5], 7: cose}
    authority = {
        "authority_id": authority_id_value.hex(),
        "authority_class": authority_class,
        "key_purpose": purpose,
        "kid": kid.hex(),
        "organization_id": org.hex(),
        "public_key": public.hex(),
        "not_before": 1_700_000_000,
        "expires_at": 1_900_000_000,
        "revoked": False,
    }
    return entry, authority


def envelope(
    profile: dict[str, Any],
    policy_name: str,
    counts: list[int],
    *,
    object_type: int = 5,
    message_type: int = 16396,
    generation: int = 7,
    sequence: int = 3,
    scope_digest: bytes | None = None,
    request_id: bytes | None = None,
    same_org: bool = False,
    authority_effect: str | None = None,
    policy_mutator: Any = None,
    reverse_collector_order: bool = False,
) -> tuple[dict[int, Any], dict[str, Any]]:
    scope_digest = scope_digest or hashlib.sha256(b"scope/global-trust").digest()
    request_id = request_id or hashlib.sha256(b"request/global-trust/update/7/3").digest()[:16]
    payload_digest = hashlib.sha256(b"canonical-federation-target-payload-v1").digest()
    selected = profile["named_policies"][policy_name]
    descriptor = policy(policy_name, selected, scope_digest)
    if policy_mutator is not None:
        policy_mutator(descriptor)
        descriptor[2] = None
        descriptor[2] = digest(descriptor)
    lineage = {1: generation, 2: sequence, 3: hashlib.sha256(b"lineage/global-trust/7").digest()}
    effect = authority_effect or selected["allowed_authority_effects"][0]
    auth_without_digest = {1: message_type, 2: request_id, 3: 1_750_000_000, 4: 1_750_003_600, 6: 1, 7: effect}
    authorization = dict(auth_without_digest)
    authorization[5] = digest(auth_without_digest)
    context = {
        1: DOMAIN,
        2: 1,
        3: "nbsr-federation-dev-v1",
        4: object_type,
        5: payload_digest,
        6: descriptor[2],
        7: "",
        8: scope_digest,
        9: lineage,
        10: authorization,
        11: 6,
        12: capability_session_binding(),
    }
    groups = []
    authorities = []
    for requirement, count in zip(descriptor[5], counts, strict=True):
        entries = []
        common_org = hashlib.sha256(b"same-organization").digest()[:16] if same_org else None
        for index in range(1, count + 1):
            entry, authority = signer(requirement[1], requirement[4][0], requirement[8][0], index, context, organization=common_org)
            authority["eligible_policy_groups"] = [f"{policy_name}:{requirement[1]}"]
            entries.append(entry)
            authorities.append(authority)
        for index in range(count + 1, requirement[3] + 1):
            _, authority = signer(requirement[1], requirement[4][0], requirement[8][0], index, context, organization=common_org)
            authority["eligible_policy_groups"] = [f"{policy_name}:{requirement[1]}"]
            authorities.append(authority)
        if reverse_collector_order:
            entries.reverse()
        entries.sort(key=lambda item: (item[1], item[2], item[3], item[4]))
        groups.append({1: requirement[1], 2: entries})
    value = {
        1: 1,
        2: "nbsr-federation-dev-v1",
        3: object_type,
        4: payload_digest,
        5: descriptor,
        6: scope_digest,
        7: lineage,
        8: authorization,
        9: groups,
    }
    validation = {
        "capability_agreement_authenticated": True,
        "selected_core_version": 2,
        "agreed_federation_version": 1,
        "agreed_profile_id": "nbsr-federation-dev-v1",
        "authenticated_session_transcript_digest": SESSION_TRANSCRIPT_DIGEST.hex(),
        "now": 1_750_000_100,
        "accepted_authority_registry": authorities,
        "negotiated_capabilities": ["THRESHOLD_EVIDENCE"],
        "authenticated_capabilities": ["THRESHOLD_EVIDENCE"],
        "expected_request_event_transition_id": request_id.hex(),
    }
    return value, validation


def fixture(
    name: str, value: dict[int, Any], validation: dict[str, Any], decision: str, reason: str, *, note: str | None = None
) -> dict[str, Any]:
    raw = encode_deterministic(value)
    result = {
        "name": name,
        "canonical_cbor_hex": raw.hex(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "expected_decision": decision,
        "expected_reason": reason,
        "expected_mutation": False,
        "validation_context": validation,
    }
    if note:
        result["note"] = note
    return result


def build_fixtures(profile: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    specs = [
        ("valid-registrar-1-of-1", "registrar-v1", [1], 1, 16418),
        ("valid-witness-2-of-3", "ordinary-witness-v1", [2], 9, 16404),
        ("valid-global-trust-3-of-5", "global-trust-v1", [3], 5, 16396),
        ("valid-high-risk-trust-4-of-5", "high-risk-global-root-v1", [4], 5, 16396),
        ("valid-recovery-plus-registry-plus-witness", "operator-recovery-v1", [2, 1, 2], 16, 16417),
        ("valid-over-threshold", "ordinary-witness-v1", [3], 9, 16404),
        ("valid-high-risk-witness-3-of-5", "high-risk-witness-v1", [3], 9, 16404),
        ("valid-deny-only-emergency-2-of-5", "deny-only-emergency-v1", [2], 13, 16407),
        ("valid-conflict-plus-witness", "conflict-decision-v1", [2, 2], 17, 16438),
        ("valid-appeal-plus-witness", "appeal-decision-v1", [2, 2], 18, 16441),
    ]
    valid: dict[str, tuple[dict[int, Any], dict[str, Any]]] = {}
    for name, policy_name, counts, object_type, message_type in specs:
        value, validation = envelope(profile, policy_name, counts, object_type=object_type, message_type=message_type)
        valid[name] = (value, validation)
        items.append(fixture(name, value, validation, "ACCEPT", "NONE"))
    value, validation = envelope(profile, "ordinary-witness-v1", [2], object_type=9, message_type=16404, reverse_collector_order=True)
    normalized = fixture(
        "valid-input-order-normalizes",
        value,
        validation,
        "ACCEPT",
        "NONE",
        note="collectors presented reverse signer order; canonicalizer emitted the same bytes as valid-witness-2-of-3",
    )
    normalized["collector_input_order"] = "reverse-canonical-signer-order"
    items.append(normalized)

    zero, zero_context = envelope(profile, "ordinary-witness-v1", [0], object_type=9, message_type=16404)
    items.append(fixture("pending-zero-signatures", zero, zero_context, "PENDING", "ERR_EVIDENCE_MISSING"))

    def add(name: str, base: str, mutate: Any, reason: str, decision: str = "REJECT") -> None:
        value, validation = deepcopy(valid[base])
        mutate(value, validation)
        items.append(fixture(name, value, validation, decision, reason))

    add("invalid-insufficient-threshold", "valid-witness-2-of-3", lambda v, c: v[9][0][2].pop(), "ERR_WITNESS_THRESHOLD", "PENDING")
    add("invalid-duplicate-signer", "valid-witness-2-of-3", lambda v, c: v[9][0][2].append(deepcopy(v[9][0][2][0])), "ERR_AUTHORITY")
    same, same_context = envelope(profile, "ordinary-witness-v1", [2], object_type=9, message_type=16404, same_org=True)
    items.append(fixture("invalid-same-organization-twice", same, same_context, "REJECT", "ERR_WITNESS_THRESHOLD"))
    add("invalid-wrong-authority-class", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(1, 4), "ERR_AUTHORITY")
    add("invalid-wrong-purpose", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(3, 13), "ERR_KEY_PURPOSE")
    add("invalid-bad-kid", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(4, b"unknown-kid"), "ERR_IDENTITY")
    add(
        "invalid-revoked-signer",
        "valid-witness-2-of-3",
        lambda v, c: c["accepted_authority_registry"][0].__setitem__("revoked", True),
        "ERR_REVOKED",
    )
    add(
        "invalid-expired-signer",
        "valid-witness-2-of-3",
        lambda v, c: c["accepted_authority_registry"][0].__setitem__("expires_at", 1_700_000_001),
        "ERR_FRESHNESS",
    )
    add(
        "invalid-wrong-payload-digest",
        "valid-witness-2-of-3",
        lambda v, c: v.__setitem__(4, hashlib.sha256(b"wrong").digest()),
        "ERR_SIGNATURE_INVALID",
    )
    add(
        "invalid-mixed-payload-digests",
        "valid-witness-2-of-3",
        lambda v, c: v[9][0][2][0].__setitem__(6, hashlib.sha256(b"mixed").digest()),
        "ERR_SIGNATURE_INVALID",
    )
    add("invalid-wrong-generation", "valid-witness-2-of-3", lambda v, c: v[7].__setitem__(1, 8), "ERR_REPLAY")
    add("invalid-wrong-scope", "valid-witness-2-of-3", lambda v, c: v.__setitem__(6, hashlib.sha256(b"wrong-scope").digest()), "ERR_SCOPE")
    add("invalid-wrong-action", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(1, 16418), "ERR_REPLAY")
    add(
        "invalid-signature",
        "valid-witness-2-of-3",
        lambda v, c: v[9][0][2][0].__setitem__(7, v[9][0][2][0][7][:-1] + bytes([v[9][0][2][0][7][-1] ^ 1])),
        "ERR_SIGNATURE_INVALID",
    )
    add(
        "invalid-unsupported-critical-extension",
        "valid-witness-2-of-3",
        lambda v, c: v.__setitem__(10, [{1: 65535, 2: True, 3: b""}]),
        "ERR_UNSUPPORTED_CRITICAL",
    )
    excessive, excessive_context = envelope(profile, "ordinary-witness-v1", [5], object_type=9, message_type=16404)
    extra, extra_authority = signer(
        "witness",
        6,
        9,
        6,
        {
            1: DOMAIN,
            2: 1,
            3: excessive[2],
            4: excessive[3],
            5: excessive[4],
            6: excessive[5][2],
            7: "",
            8: excessive[6],
            9: excessive[7],
            10: excessive[8],
        },
    )
    excessive[9][0][2].append(extra)
    extra_authority["eligible_policy_groups"] = ["ordinary-witness-v1:witness"]
    excessive_context["accepted_authority_registry"].append(extra_authority)
    items.append(fixture("invalid-excessive-signer-count", excessive, excessive_context, "REJECT", "ERR_RESOURCE_LIMIT"))
    add("invalid-malformed-signer-entry", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].pop(7), "ERR_SCHEMA")
    add(
        "invalid-replay-authorization-context",
        "valid-witness-2-of-3",
        lambda v, c: c.__setitem__("expected_request_event_transition_id", bytes(16).hex()),
        "ERR_REPLAY",
    )
    add("invalid-unsupported-container-version", "valid-witness-2-of-3", lambda v, c: v.__setitem__(1, 2), "ERR_VERSION")
    add("invalid-wrong-group-order", "valid-recovery-plus-registry-plus-witness", lambda v, c: v[9].reverse(), "ERR_AUTHORITY")
    add(
        "invalid-cross-group-signer-reuse",
        "valid-recovery-plus-registry-plus-witness",
        lambda v, c: v[9][1][2].__setitem__(0, deepcopy(v[9][0][2][0])),
        "ERR_AUTHORITY",
    )
    ineligible, ineligible_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0][6].pop(0),
    )
    items.append(fixture("invalid-ineligible-authority-id", ineligible, ineligible_context, "REJECT", "ERR_AUTHORITY"))
    class_count, class_count_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0].__setitem__(5, [[4, 1]]),
    )
    items.append(fixture("invalid-required-class-count", class_count, class_count_context, "REJECT", "ERR_AUTHORITY"))
    group_scope, group_scope_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0].__setitem__(10, hashlib.sha256(b"wrong-group-scope").digest()),
    )
    items.append(fixture("invalid-group-scope-digest", group_scope, group_scope_context, "REJECT", "ERR_SCOPE"))
    add("invalid-authorization-window", "valid-witness-2-of-3", lambda v, c: c.__setitem__("now", 1_800_000_000), "ERR_FRESHNESS")
    deny_add, deny_add_context = envelope(
        profile, "deny-only-emergency-v1", [2], object_type=13, message_type=16407, authority_effect="grant"
    )
    items.append(fixture("invalid-deny-only-add-action", deny_add, deny_add_context, "REJECT", "ERR_POLICY_EXPANSION"))
    add(
        "invalid-excessive-group-count",
        "valid-recovery-plus-registry-plus-witness",
        lambda v, c: v[9].extend([{1: "x", 2: []}, {1: "y", 2: []}]),
        "ERR_RESOURCE_LIMIT",
    )
    total, total_context = deepcopy(valid["valid-recovery-plus-registry-plus-witness"])
    while sum(len(group[2]) for group in total[9]) <= 16:
        total[9][0][2].append(deepcopy(total[9][0][2][0]))
    items.append(fixture("invalid-excessive-total-signers", total, total_context, "REJECT", "ERR_RESOURCE_LIMIT"))
    nested_value: Any = b"leaf"
    for _ in range(10):
        nested_value = [nested_value]
    add("invalid-excessive-nested-depth", "valid-witness-2-of-3", lambda v, c: v.__setitem__(10, nested_value), "ERR_RESOURCE_LIMIT")
    policy_object, policy_object_context = envelope(profile, "registrar-v1", [1], object_type=5, message_type=16418)
    items.append(fixture("invalid-policy-object-substitution", policy_object, policy_object_context, "REJECT", "ERR_AUTHORITY"))
    policy_message, policy_message_context = envelope(profile, "registrar-v1", [1], object_type=1, message_type=16396)
    items.append(fixture("invalid-policy-message-substitution", policy_message, policy_message_context, "REJECT", "ERR_REPLAY"))
    add(
        "invalid-missing-required-capability",
        "valid-witness-2-of-3",
        lambda v, c: (c.__setitem__("negotiated_capabilities", []), c.__setitem__("authenticated_capabilities", [])),
        "ERR_UNSUPPORTED_CRITICAL",
    )
    add(
        "invalid-federation-objects-only",
        "valid-witness-2-of-3",
        lambda v, c: (
            c.__setitem__("negotiated_capabilities", ["FEDERATION_OBJECTS"]),
            c.__setitem__("authenticated_capabilities", ["FEDERATION_OBJECTS"]),
        ),
        "ERR_UNSUPPORTED_CRITICAL",
    )
    add(
        "invalid-pre-capability-agreement",
        "valid-witness-2-of-3",
        lambda v, c: c.__setitem__("capability_agreement_authenticated", False),
        "ERR_DOWNGRADE",
    )
    add(
        "invalid-wrong-agreed-profile",
        "valid-witness-2-of-3",
        lambda v, c: c.__setitem__("agreed_profile_id", "nbsr-federation-other-v1"),
        "ERR_VERSION",
    )
    add(
        "invalid-wrong-agreed-federation-version",
        "valid-witness-2-of-3",
        lambda v, c: c.__setitem__("agreed_federation_version", 2),
        "ERR_VERSION",
    )
    add(
        "invalid-wrong-selected-core-version", "valid-witness-2-of-3", lambda v, c: c.__setitem__("selected_core_version", 1), "ERR_VERSION"
    )
    add("invalid-capability-stripping", "valid-witness-2-of-3", lambda v, c: c.__setitem__("negotiated_capabilities", []), "ERR_DOWNGRADE")
    add(
        "invalid-cross-session-replay",
        "valid-witness-2-of-3",
        lambda v, c: c.__setitem__(
            "authenticated_session_transcript_digest", hashlib.sha256(b"different-authenticated-session").hexdigest()
        ),
        "ERR_REPLAY",
    )
    add(
        "invalid-malformed-capability-collection",
        "valid-witness-2-of-3",
        lambda v, c: (
            c.__setitem__("negotiated_capabilities", "THRESHOLD_EVIDENCE"),
            c.__setitem__("authenticated_capabilities", "THRESHOLD_EVIDENCE"),
        ),
        "ERR_SCHEMA",
    )
    add(
        "invalid-single-sign1-downgrade", "valid-witness-2-of-3", lambda v, c: c.__setitem__("single_sign1_fallback", True), "ERR_DOWNGRADE"
    )
    add(
        "invalid-replay-without-threshold-capability",
        "valid-witness-2-of-3",
        lambda v, c: (c.__setitem__("negotiated_capabilities", []), c.__setitem__("authenticated_capabilities", [])),
        "ERR_UNSUPPORTED_CRITICAL",
    )

    def wrong_signature_capability(value: dict[int, Any], _: dict[str, Any]) -> None:
        cose = decode_deterministic(value[9][0][2][0][7][1:])
        signed_context = decode_deterministic(cose[2])
        signed_context[11] = 1
        cose[2] = encode_deterministic(signed_context)
        value[9][0][2][0][7] = b"\xd2" + encode_deterministic(cose)

    add("invalid-signature-context-capability", "valid-witness-2-of-3", wrong_signature_capability, "ERR_DOWNGRADE")
    eligible, eligible_context = envelope(profile, "ordinary-witness-v1", [4], object_type=9, message_type=16404)
    items.append(fixture("invalid-eligible-count-exceeded", eligible, eligible_context, "REJECT", "ERR_AUTHORITY"))
    add("invalid-malformed-extension", "valid-witness-2-of-3", lambda v, c: v.__setitem__(10, [1]), "ERR_SCHEMA")
    add("invalid-oversize-authority-id", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(2, b"a" * 65), "ERR_RESOURCE_LIMIT")
    add(
        "invalid-oversize-organization-id",
        "valid-witness-2-of-3",
        lambda v, c: v[9][0][2][0].__setitem__(5, b"o" * 65),
        "ERR_RESOURCE_LIMIT",
    )
    add("invalid-oversize-kid", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(4, b"k" * 65), "ERR_RESOURCE_LIMIT")
    weakened_class, weakened_class_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0].__setitem__(5, []),
    )
    items.append(fixture("invalid-weakened-class-count", weakened_class, weakened_class_context, "REJECT", "ERR_AUTHORITY"))
    weakened_org, weakened_org_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        same_org=True,
        policy_mutator=lambda p: p[5][0].__setitem__(7, 1),
    )
    items.append(fixture("invalid-weakened-organization-diversity", weakened_org, weakened_org_context, "REJECT", "ERR_AUTHORITY"))
    selected_set, selected_set_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0][6].__setitem__(2, hashlib.sha256(b"attacker-selected-authority").digest()),
    )
    items.append(fixture("invalid-self-selected-eligible-set", selected_set, selected_set_context, "REJECT", "ERR_AUTHORITY"))
    add(
        "invalid-noncanonical-cose-sign1",
        "valid-witness-2-of-3",
        lambda v, c: v[9][0][2][0].__setitem__(7, v[9][0][2][0][7] + b"\x00"),
        "ERR_NON_CANONICAL",
    )
    unknown_policy, unknown_policy_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p.__setitem__(99, 1),
    )
    items.append(fixture("invalid-unknown-policy-key", unknown_policy, unknown_policy_context, "REJECT", "ERR_SCHEMA"))
    unknown_group, unknown_group_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0].__setitem__(99, 1),
    )
    items.append(fixture("invalid-unknown-group-requirement-key", unknown_group, unknown_group_context, "REJECT", "ERR_SCHEMA"))
    add("invalid-unknown-lineage-key", "valid-witness-2-of-3", lambda v, c: v[7].__setitem__(99, 1), "ERR_SCHEMA")
    add("invalid-unknown-authorization-key", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(99, 1), "ERR_SCHEMA")
    malformed_policy_ext, malformed_policy_ext_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p.__setitem__(8, [1]),
    )
    items.append(fixture("invalid-malformed-policy-extension", malformed_policy_ext, malformed_policy_ext_context, "REJECT", "ERR_SCHEMA"))
    malformed_group_ext, malformed_group_ext_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0].__setitem__(11, [1]),
    )
    items.append(fixture("invalid-malformed-group-extension", malformed_group_ext, malformed_group_ext_context, "REJECT", "ERR_SCHEMA"))
    add("invalid-malformed-authorization-context", "valid-witness-2-of-3", lambda v, c: v.__setitem__(8, []), "ERR_SCHEMA")
    add("invalid-lineage-field-types", "valid-witness-2-of-3", lambda v, c: v[7].__setitem__(1, "seven"), "ERR_SCHEMA")
    add("invalid-short-request-id", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(2, b"short"), "ERR_SCHEMA")
    add("invalid-authorization-time-type", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(3, True), "ERR_SCHEMA")
    add("invalid-authorization-window-order", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(3, v[8][4] + 1), "ERR_SCHEMA")
    add("invalid-extension-version", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(6, 2), "ERR_SCHEMA")
    add("invalid-boolean-container-version", "valid-witness-2-of-3", lambda v, c: v.__setitem__(1, True), "ERR_VERSION")
    boolean_policy, boolean_policy_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p.__setitem__(1, True),
    )
    items.append(fixture("invalid-boolean-policy-version", boolean_policy, boolean_policy_context, "REJECT", "ERR_SCHEMA"))

    def nondict_signature_context(value: dict[int, Any], _: dict[str, Any]) -> None:
        body = decode_deterministic(value[9][0][2][0][7][1:])
        body[2] = encode_deterministic([])
        value[9][0][2][0][7] = b"\xd2" + encode_deterministic(body)

    add("invalid-nondict-signature-context", "valid-witness-2-of-3", nondict_signature_context, "ERR_SCHEMA")
    multiple_keys, multiple_keys_context = deepcopy(valid["valid-witness-2-of-3"])
    extra_key = deepcopy(multiple_keys_context["accepted_authority_registry"][0])
    extra_key["kid"] = b"second-key-for-same-authority".hex()
    extra_key["public_key"] = hashlib.sha256(b"second-public-key-for-same-authority").hexdigest()
    multiple_keys_context["accepted_authority_registry"].append(extra_key)
    items.append(fixture("valid-multiple-keys-one-authority-identity", multiple_keys, multiple_keys_context, "ACCEPT", "NONE"))
    add("invalid-negative-not-before", "valid-witness-2-of-3", lambda v, c: v[8].__setitem__(3, -1), "ERR_SCHEMA")
    add("invalid-boolean-object-class", "valid-registrar-1-of-1", lambda v, c: v.__setitem__(3, True), "ERR_SCHEMA")
    boolean_required, boolean_required_context = envelope(
        profile,
        "registrar-v1",
        [1],
        object_type=1,
        message_type=16418,
        policy_mutator=lambda p: p[5][0].__setitem__(2, True),
    )
    items.append(fixture("invalid-boolean-required-count", boolean_required, boolean_required_context, "REJECT", "ERR_SCHEMA"))
    boolean_eligible, boolean_eligible_context = envelope(
        profile,
        "registrar-v1",
        [1],
        object_type=1,
        message_type=16418,
        policy_mutator=lambda p: p[5][0].__setitem__(3, True),
    )
    items.append(fixture("invalid-boolean-eligible-count", boolean_eligible, boolean_eligible_context, "REJECT", "ERR_SCHEMA"))
    boolean_org, boolean_org_context = envelope(
        profile,
        "registrar-v1",
        [1],
        object_type=1,
        message_type=16418,
        policy_mutator=lambda p: p[5][0].__setitem__(7, True),
    )
    items.append(fixture("invalid-boolean-minimum-organizations", boolean_org, boolean_org_context, "REJECT", "ERR_SCHEMA"))
    mixed_eligible, mixed_eligible_context = envelope(
        profile,
        "ordinary-witness-v1",
        [2],
        object_type=9,
        message_type=16404,
        policy_mutator=lambda p: p[5][0][6].__setitem__(2, 7),
    )
    items.append(fixture("invalid-mixed-eligible-id-types", mixed_eligible, mixed_eligible_context, "REJECT", "ERR_SCHEMA"))
    add("invalid-empty-authority-id", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(2, b""), "ERR_SCHEMA")
    add("invalid-empty-kid", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(4, b""), "ERR_SCHEMA")
    add("invalid-empty-organization-id", "valid-witness-2-of-3", lambda v, c: v[9][0][2][0].__setitem__(5, b""), "ERR_SCHEMA")
    return {
        "format_version": 1,
        "status": "proposed-requires-human-approval",
        "decision_id": "WP8-THRESHOLD-CONTAINER-01",
        "fixtures": items,
    }


def render_table(profile: dict[str, Any], package: dict[str, Any]) -> str:
    lines = [
        "# Federation v0.1 Threshold Container Allocation",
        "",
        "> **PROPOSED — REQUIRES HUMAN APPROVAL**",
        "",
        "Generated from `registries/federation-v0.1-threshold-container-proposal.json`.",
        "",
        "## Container fields",
        "",
        "| Key | Type and rule |",
        "|---:|---|",
    ]
    lines.extend(f"| {key} | `{value}` |" for key, value in profile["container_fields"].items())
    lines += ["", "## Literal fixture digests", "", "| Fixture | SHA-256 | Decision | Reason | Mutation |", "|---|---|---|---|---|"]
    lines.extend(
        f"| `{item['name']}` | `{item['sha256']}` | {item['expected_decision']} | `{item['expected_reason']}` | false |"
        for item in package["fixtures"]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    package = build_fixtures(profile)
    fixtures_text = json.dumps(package, indent=2, sort_keys=True) + "\n"
    table_text = render_table(profile, package)
    if args.check:
        if not FIXTURE_PATH.exists() or FIXTURE_PATH.read_text(encoding="utf-8") != fixtures_text:
            raise SystemExit("threshold fixture package is stale")
        if not TABLE_PATH.exists() or TABLE_PATH.read_text(encoding="utf-8") != table_text:
            raise SystemExit("threshold allocation table is stale")
        print(f"threshold container render check passed: {len(package['fixtures'])} literal fixtures")
        return 0
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(fixtures_text, encoding="utf-8", newline="\n")
    TABLE_PATH.write_text(table_text, encoding="utf-8", newline="\n")
    print(f"rendered threshold container proposal: {len(package['fixtures'])} literal fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
