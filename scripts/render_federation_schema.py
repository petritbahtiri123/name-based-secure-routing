#!/usr/bin/env python3
"""Render the human schema table and specification-authored Task 2 literals.

This proposal tool is deliberately independent of the future Federation runtime.
It contains a tiny RFC 8949 deterministic encoder for literal fixtures only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs/protocol/registries/federation-v0.1-schema-proposal.json"
TABLE_PATH = ROOT / "docs/protocol/wp8-federation-v0.1-schema-allocation.md"
FIXTURE_PATH = ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json"
STATUS = "APPROVED DEVELOPMENT PROFILE PROPOSAL — REQUIRES HUMAN APPROVAL"
OBJECT_ORDER = (
    "OperatorRegistryRecord",
    "KeyAuthorizationRecord",
    "NameOwnershipRecord",
    "DelegationRecord",
    "FederationTrustBundle",
    "TransparencyCheckpoint",
    "InclusionProof",
    "ConsistencyProof",
    "WitnessStatement",
    "OperatorEndpointRecord",
    "FederationAuthorityProof",
    "FederationAuthorizationContext",
    "TypedRevocationRecord",
    "ConflictEvidence",
    "OperatorLifecycleRecord",
    "RecoveryTransitionRecord",
    "ConflictResolutionRecord",
    "AppealDecisionRecord",
)

COMMON = {
    "object_type": (1, "uint", "approved ObjectType value"),
    "object_version": (2, "uint", "exactly 1"),
    "issuer_id": (3, "AuthorityReference", "one closed reference"),
    "generation": (4, "uint", "1..2^64-1"),
    "sequence": (5, "uint", "1..2^64-1"),
    "not_before": (6, "uint", "0..253402300799"),
    "expires_at": (7, "uint", "0..253402300799 and greater than not_before"),
    "previous_digest": (8, "bstr", "exactly 32 bytes"),
    "effective_at": (9, "uint", "0..253402300799"),
    "extensions": (31, "map<uint,ExtensionEntry>", "0..16 entries; IDs 1000..65535"),
}


def field(
    name: str,
    key: int,
    wire_type: str,
    bounds: str,
    requiredness: str = "required",
    privacy: str = "public",
    *,
    genesis: str = "required",
    update: str = "required",
    traits: tuple[str, ...] = (),
    critical: bool = True,
) -> dict[str, Any]:
    trait_set = set(traits)
    return {
        "name": name,
        "key": key,
        "wire_type": wire_type,
        "bounds": bounds,
        "requiredness": requiredness,
        "genesis": genesis,
        "update": update,
        "critical": critical,
        "immutable_after_genesis": "immutable-after-genesis" in trait_set,
        "monotonic": "monotonic" in trait_set,
        "predecessor_linked": "predecessor-linked" in trait_set,
        "authority_defining": "authority-defining" in trait_set,
        "lifecycle_defining": "lifecycle-defining" in trait_set,
        "privacy_sensitive": "privacy-sensitive" in trait_set,
        "privacy": privacy,
    }


def common(name: str, **kwargs: Any) -> dict[str, Any]:
    key, wire_type, bounds = COMMON[name]
    return field(name, key, wire_type, bounds, **kwargs)


def lineage_rules(*, new_generation_evidence: str) -> dict[str, Any]:
    return {
        "genesis": {
            "allowed": True,
            "generation": 1,
            "sequence": 1,
            "previous_digest": "forbidden",
        },
        "same_generation_update": {
            "allowed": True,
            "generation": "unchanged",
            "sequence": "exactly previous sequence plus 1",
            "previous_digest": "required and equals immediately accepted canonical digest",
            "equal_version_equal_digest": "ACCEPT/no-mutation",
            "equal_version_different_digest": "QUARANTINE/ERR_EQUIVOCATION/no-mutation",
        },
        "new_generation": {
            "allowed": True,
            "generation": "exactly previous generation plus 1",
            "sequence": 1,
            "previous_digest": "required and equals prior terminal or transition-authorized state",
            "evidence": new_generation_evidence,
            "terminal_non_resurrection": True,
        },
    }


def no_lineage_rules(binding: str) -> dict[str, Any]:
    return {
        "genesis": {"allowed": False, "reason": "not a lineage object"},
        "same_generation_update": {"allowed": False, "reason": "immutable one-shot object"},
        "new_generation": {"allowed": False, "reason": binding},
    }


def obj(
    lifecycle_class: str,
    rationale: str,
    fields: list[dict[str, Any]],
    lifecycle_rules: dict[str, Any],
    signer_rule: dict[str, Any],
    forbidden_fields: list[str],
    *,
    maximum_canonical_payload_bytes: int = 32_768,
    allowed_state_transitions: dict[str, list[str]] | None = None,
    new_generation_change_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "lifecycle_class": lifecycle_class,
        "rationale": rationale,
        "fields": fields,
        "lifecycle_rules": lifecycle_rules,
        "signer_rule": signer_rule,
        "forbidden_fields": forbidden_fields,
        "unknown_base_field": "REJECT/ERR_UNSUPPORTED_CRITICAL",
        "maximum_canonical_payload_bytes": maximum_canonical_payload_bytes,
        "maximum_signed_object_bytes": 65_536,
        "allowed_state_transitions": allowed_state_transitions or {},
        "new_generation_change_fields": new_generation_change_fields or [],
    }


def signer(normal: str, purpose: str, threshold: str, *, recovery: bool = False) -> dict[str, Any]:
    return {
        "normal_authority": normal,
        "key_purpose": purpose,
        "threshold": threshold,
        "kid_binding": "protected-kid-resolves-exactly-one-authorized-key",
        "recovery_substitution": recovery,
        "invalid_cross_purpose": "reject-ERR_KEY_PURPOSE",
    }


def schema() -> dict[str, Any]:
    lineage = "stateful-lineage"
    snapshot = "snapshot-state-summary"
    evidence = "immutable-proof-evidence"
    decision = "decision-context"
    objects: dict[str, Any] = {}

    objects["OperatorRegistryRecord"] = obj(
        lineage,
        "Durable registry authority and lifecycle state changes over time.",
        [
            common("object_type", traits=("immutable-after-genesis",)),
            common("object_version", traits=("immutable-after-genesis",)),
            common("issuer_id", traits=("authority-defining",)),
            common("generation", traits=("monotonic", "lifecycle-defining")),
            common("sequence", traits=("monotonic",)),
            common("not_before"),
            common("expires_at"),
            common(
                "previous_digest",
                requiredness="contextually-required",
                genesis="forbidden",
                update="required",
                traits=("predecessor-linked",),
            ),
            common("extensions", requiredness="optional-non-critical", genesis="optional", update="optional", critical=False),
            field("operator_id", 32, "bstr", "exactly 32 bytes", traits=("immutable-after-genesis", "authority-defining")),
            field("identity_root", 33, "AuthorityReference", "one IDENTITY_ROOT reference", traits=("authority-defining",)),
            field(
                "organization_binding",
                34,
                "OrganizationBinding",
                "closed map; public or private-domain mode",
                privacy="scope-dependent",
                traits=("authority-defining", "privacy-sensitive"),
            ),
            field("federation_scope", 35, "DelegationScope", "one closed non-empty scope", traits=("authority-defining",)),
            field("lifecycle_state", 36, "uint", "approved OperatorLifecycle value", traits=("lifecycle-defining",)),
            field(
                "revocation_reference",
                37,
                "AuthorityTarget|null",
                "null means explicitly no accepted revocation; otherwise one target",
                traits=("lifecycle-defining",),
            ),
            field("transparency_reference", 38, "TransparencyReference", "one exact checkpoint reference", traits=("authority-defining",)),
            field(
                "recovery_stage",
                39,
                "uint",
                "approved RecoveryStage value",
                requiredness="contextually-required",
                genesis="required iff lifecycle_state=RECOVERY; forbidden otherwise",
                update="required iff lifecycle_state=RECOVERY; forbidden otherwise",
                traits=("lifecycle-defining",),
            ),
        ],
        lineage_rules(new_generation_evidence="accepted RecoveryTransitionRecord or dual-authorized transfer"),
        signer("DEVELOPMENT_REGISTRAR plus WITNESS", "REGISTRY_SIGNING plus WITNESS", "1-of-1 plus 2-of-3", recovery=True),
        ["operational_endpoint", "origin_endpoint", "private_infrastructure", "subscriber_data", "recovery_secret"],
        allowed_state_transitions={
            "APPLIED": ["VERIFICATION_PENDING", "REJECTED"],
            "VERIFICATION_PENDING": ["VERIFIED", "REJECTED"],
            "VERIFIED": ["PROVISIONAL", "ACTIVE", "REJECTED"],
            "PROVISIONAL": ["ACTIVE", "SUSPENDED", "QUARANTINED", "RECOVERY", "RETIRED", "TERMINALLY_REVOKED"],
            "ACTIVE": ["SUSPENDED", "QUARANTINED", "RECOVERY", "RETIRED", "TERMINALLY_REVOKED"],
            "SUSPENDED": ["ACTIVE", "QUARANTINED", "RECOVERY", "RETIRED", "TERMINALLY_REVOKED"],
            "QUARANTINED": ["RECOVERY", "RETIRED", "TERMINALLY_REVOKED"],
            "RECOVERY": ["ACTIVE", "RETIRED", "TERMINALLY_REVOKED"],
            "RETIRED": [],
            "TERMINALLY_REVOKED": [],
            "REJECTED": [],
        },
        new_generation_change_fields=["identity_root", "organization_binding", "federation_scope", "lifecycle_state"],
    )

    objects["KeyAuthorizationRecord"] = obj(
        lineage,
        "Purpose-bound key authority rotates and recovers through durable continuity.",
        [
            common("object_type", traits=("immutable-after-genesis",)),
            common("object_version", traits=("immutable-after-genesis",)),
            common("issuer_id", traits=("authority-defining",)),
            common("generation", traits=("monotonic", "lifecycle-defining")),
            common("sequence", traits=("monotonic",)),
            common("not_before"),
            common("expires_at"),
            common(
                "previous_digest",
                requiredness="contextually-required",
                genesis="forbidden",
                update="required",
                traits=("predecessor-linked",),
            ),
            common("extensions", requiredness="optional-non-critical", genesis="optional", update="optional", critical=False),
            field("operator_id", 32, "bstr", "exactly 32 bytes", traits=("immutable-after-genesis", "authority-defining")),
            field(
                "key_id",
                33,
                "bstr",
                "1..64 bytes; immutable within a generation; never reused after terminal state",
                traits=("authority-defining",),
            ),
            field(
                "public_key",
                34,
                "bstr",
                "exactly 32-byte Ed25519 public key; immutable within a generation",
                traits=("authority-defining",),
            ),
            field("key_purpose", 35, "uint", "one approved KeyPurpose value", traits=("immutable-after-genesis", "authority-defining")),
            field("key_lifecycle", 36, "uint", "one approved KeyLifecycle value", traits=("lifecycle-defining",)),
            field("authorizing_authority", 37, "AuthorityReference", "identity-root or recovery authority", traits=("authority-defining",)),
            field("revocation_state", 38, "bool", "false or true; absence forbidden", traits=("monotonic", "lifecycle-defining")),
            field(
                "revocation_reference",
                39,
                "AuthorityTarget|null",
                "required target when revocation_state=true; explicit null otherwise",
                requiredness="contextually-required",
                traits=("lifecycle-defining",),
            ),
            field(
                "recovery_transition_digest",
                40,
                "bstr",
                "exactly 32 bytes",
                requiredness="contextually-required",
                genesis="forbidden",
                update="required only for recovery generation",
                traits=("authority-defining", "predecessor-linked"),
            ),
        ],
        lineage_rules(
            new_generation_evidence="accepted RecoveryTransitionRecord binding operator, key purpose, scope, old and new generation"
        ),
        signer("OPERATOR_IDENTITY_ROOT", "IDENTITY_ROOT", "1-of-1", recovery=True),
        ["multiple_key_purposes", "private_key", "unbounded_scope", "textual_operator_id"],
        allowed_state_transitions={
            "NEXT": ["ACTIVE", "REVOKED"],
            "ACTIVE": ["RETIRING", "REVOKED"],
            "RETIRING": ["RETIRED", "REVOKED"],
            "RETIRED": [],
            "REVOKED": [],
        },
        new_generation_change_fields=["key_id", "public_key", "key_lifecycle", "authorizing_authority"],
    )

    def standard_lineage(
        name: str,
        rationale: str,
        specifics: list[dict[str, Any]],
        signer_rule: dict[str, Any],
        evidence_rule: str,
        forbidden: list[str],
    ) -> None:
        objects[name] = obj(
            lineage,
            rationale,
            [
                common("object_type", traits=("immutable-after-genesis",)),
                common("object_version", traits=("immutable-after-genesis",)),
                common("issuer_id", traits=("authority-defining",)),
                common("generation", traits=("monotonic",)),
                common("sequence", traits=("monotonic",)),
                common("not_before"),
                common("expires_at"),
                common(
                    "previous_digest",
                    requiredness="contextually-required",
                    genesis="forbidden",
                    update="required",
                    traits=("predecessor-linked",),
                ),
                common("extensions", requiredness="optional-non-critical", genesis="optional", update="optional", critical=False),
                *specifics,
            ],
            lineage_rules(new_generation_evidence=evidence_rule),
            signer_rule,
            forbidden,
        )

    standard_lineage(
        "NameOwnershipRecord",
        "Durable ownership authority supports transfer and recovery.",
        [
            field("name_scope", 32, "tstr", "1..255 UTF-8 bytes; lowercase canonical name"),
            field(
                "owner_reference",
                33,
                "AuthorityReference",
                "one public or privacy-safe owner reference",
                privacy="scope-dependent",
                traits=("authority-defining", "privacy-sensitive"),
            ),
            field("service_id", 34, "bstr", "exactly 32 bytes", traits=("authority-defining",)),
            field(
                "bootstrap_evidence_digest",
                35,
                "bstr|null",
                "null or exact 32 bytes",
                requiredness="optional-critical",
                genesis="optional",
                update="optional",
            ),
            field("transfer_state", 36, "uint", "one OwnershipTransferState value", traits=("lifecycle-defining",)),
            field("revocation_reference", 37, "AuthorityTarget|null", "explicit null or one target"),
        ],
        signer("NAME_OWNER", "NAME_OWNERSHIP", "1-of-1", recovery=True),
        "accepted transfer or RecoveryTransitionRecord",
        ["origin_endpoint", "cdn_endpoint", "runtime_route_state"],
    )
    standard_lineage(
        "DelegationRecord",
        "Mutable scoped authority must retain ancestry and narrowing continuity.",
        [
            field("delegator", 32, "AuthorityReference", "one scoped authority", traits=("authority-defining",)),
            field("delegatee", 33, "AuthorityReference", "one scoped authority", traits=("authority-defining",)),
            field("delegation_scope", 34, "DelegationScope", "one closed non-empty scope", traits=("authority-defining",)),
            field(
                "parent_digest",
                35,
                "bstr",
                "exactly 32 bytes",
                requiredness="contextually-required",
                genesis="forbidden for ownership-root delegation; required for child",
                traits=("predecessor-linked", "authority-defining"),
            ),
            field("policy_reference", 36, "bstr|null", "null or exact 32-byte policy digest"),
            field("revocation_reference", 37, "AuthorityTarget|null", "explicit null or one target"),
        ],
        signer("NAME_OWNER or DELEGATE", "DELEGATION", "1-of-1 with scope", recovery=True),
        "accepted RecoveryTransitionRecord; ordinary generation change cannot widen scope",
        ["implicit_wildcard", "unbounded_depth", "origin_endpoint"],
    )
    standard_lineage(
        "FederationTrustBundle",
        "Trust roots, logs, witnesses, and thresholds are durable mutable trust state.",
        [
            field("bundle_scope", 32, "DelegationScope", "one closed non-empty scope", traits=("authority-defining",)),
            field("roots", 33, "array<AuthorityReference>", "1..32 sorted unique references", traits=("authority-defining",)),
            field("purpose_keys", 34, "array<AuthorityReference>", "1..256 sorted unique references", traits=("authority-defining",)),
            field("logs", 35, "array<AuthorityReference>", "1..32 sorted unique references"),
            field("witnesses", 36, "array<AuthorityReference>", "0..32 sorted unique references"),
            field("thresholds", 37, "ThresholdSet", "closed map; every numerator 1..denominator"),
            field("profiles", 38, "array<uint>", "1..64 sorted unique approved versions"),
            field("revocation_sources", 39, "array<AuthorityReference>", "1..64 sorted unique references"),
            field("max_staleness", 40, "uint", "0..900 seconds"),
            field("policy_reference", 41, "bstr|null", "null or exact 32-byte policy digest"),
        ],
        signer("FEDERATION_AUTHORITY plus WITNESS", "TRUST_BUNDLE plus WITNESS", "3-of-5 plus 2-of-3", recovery=True),
        "4-of-5 governance plus 3-of-5 witnesses or accepted scoped recovery transition",
        ["private_key", "subscriber_identity", "origin_endpoint", "session_state"],
    )
    standard_lineage(
        "OperatorEndpointRecord",
        "Federation-facing endpoint publication rotates while preserving operator continuity.",
        [
            field("operator_id", 32, "bstr", "exactly 32 bytes", traits=("authority-defining",)),
            field("endpoint_id", 33, "bstr", "1..64 bytes", traits=("immutable-after-genesis",)),
            field("locator", 34, "tstr", "1..255 UTF-8 bytes; canonical federation locator"),
            field("role", 35, "uint", "one EndpointRole value"),
            field("region", 36, "tstr|null", "null or 1..32 lowercase ASCII bytes"),
            field("transport_profile", 37, "uint", "one TransportProfile value"),
            field("port", 38, "uint", "1..65535"),
            field("priority", 39, "uint", "0..65535"),
            field("transport_key_digest", 40, "bstr", "exactly 32 bytes"),
            field("lifecycle_state", 41, "uint", "one EndpointLifecycle value", traits=("lifecycle-defining",)),
            field("revocation_reference", 42, "AuthorityTarget|null", "explicit null or one target"),
        ],
        signer("OPERATOR_ENDPOINT or DELEGATE", "ENDPOINT_DISCOVERY", "1-of-1 with scope", recovery=True),
        "accepted RecoveryTransitionRecord binding endpoint scope",
        ["origin_endpoint", "private_connector", "subscriber_address"],
    )
    standard_lineage(
        "TypedRevocationRecord",
        "Revocation authority is durable, monotonic, and must preserve replacement history.",
        [
            field("target", 32, "AuthorityTarget", "one exact target", traits=("authority-defining",)),
            field("scope", 33, "DelegationScope", "one non-empty target-contained scope", traits=("authority-defining",)),
            field("reason", 34, "uint", "approved ReasonCode value"),
            field("terminal", 35, "bool", "false or true", traits=("monotonic", "lifecycle-defining")),
            field("enforcement_mode", 36, "uint", "approved EnforcementMode value", traits=("authority-defining",)),
            field(
                "revocation_authority_mode",
                37,
                "uint",
                "one RevocationAuthorityMode value",
                traits=("authority-defining",),
            ),
            field(
                "replacement_reference",
                38,
                "AuthorityTarget|null",
                "null or one exact replacement",
                requiredness="optional-critical",
                genesis="optional",
                update="optional",
            ),
            field("transparency_reference", 39, "TransparencyReference", "one exact checkpoint reference"),
        ],
        signer("selected revocation authority alternative", "REVOCATION", "1-of-1, 3-of-5, or deny-only 2-of-5", recovery=False),
        "higher generation only for separately authorized replacement; terminal target never resurrects",
        ["expires_at when terminal=true", "authority_expansion", "unselected_signer_alternative"],
    )
    standard_lineage(
        "OperatorLifecycleRecord",
        "Registry lifecycle authority is durable and gates all operator authority.",
        [
            field("operator_id", 32, "bstr", "exactly 32 bytes", traits=("authority-defining",)),
            field("lifecycle_state", 33, "uint", "approved OperatorLifecycle value", traits=("lifecycle-defining",)),
            field(
                "recovery_stage",
                34,
                "uint",
                "approved RecoveryStage value",
                requiredness="contextually-required",
                genesis="required only when lifecycle_state=RECOVERY; forbidden otherwise",
                update="required only when lifecycle_state=RECOVERY; forbidden otherwise",
                traits=("lifecycle-defining",),
            ),
            field("affected_scope", 35, "DelegationScope", "one closed non-empty scope"),
            field("reason", 36, "uint", "approved ReasonCode value"),
            field(
                "reentry_evidence",
                37,
                "array<bstr>",
                "0..16 sorted unique 32-byte digests",
                requiredness="contextually-required",
                genesis="required for RECOVERY_VERIFIED or REENTRY_RESTRICTED",
                update="required for RECOVERY_VERIFIED or REENTRY_RESTRICTED",
            ),
            field("transparency_reference", 38, "TransparencyReference", "one exact checkpoint reference"),
        ],
        signer("DEVELOPMENT_REGISTRAR", "REGISTRY_SIGNING", "1-of-1", recovery=True),
        "accepted RecoveryTransitionRecord plus registry and witness approval",
        ["noncanonical_lifecycle_alias", "recovery_stage_outside_RECOVERY", "origin_endpoint"],
    )

    objects["TransparencyCheckpoint"] = obj(
        snapshot,
        "A signed tree snapshot uses log generation and checkpoint sequence; continuity is tree consistency, not object predecessor lineage.",
        [
            common("object_type", traits=("immutable-after-genesis",)),
            common("object_version", traits=("immutable-after-genesis",)),
            common("issuer_id", traits=("authority-defining",)),
            common("generation", traits=("monotonic",)),
            common("sequence", traits=("monotonic",)),
            common("extensions", requiredness="optional-non-critical", genesis="optional", update="optional", critical=False),
            field("log_id", 32, "bstr", "exactly 32 bytes"),
            field("scope", 33, "DelegationScope", "one closed partition scope"),
            field("tree_size", 34, "uint", "0..2^64-1", traits=("monotonic",)),
            field("merkle_root", 35, "bstr", "exactly 32 bytes"),
            field("timestamp", 36, "uint", "0..253402300799"),
            field("signing_key_id", 37, "bstr", "1..64 bytes"),
            field(
                "previous_checkpoint_digest",
                38,
                "bstr|null",
                "null for size 0; exact 32 bytes otherwise",
                requiredness="contextually-required",
            ),
            field("witness_policy_digest", 39, "bstr|null", "null or exact 32 bytes", requiredness="optional-critical"),
        ],
        {
            "genesis": {"allowed": True, "generation": 1, "sequence": 1, "tree_size": 0, "previous_checkpoint_digest": "null"},
            "same_generation_update": {
                "allowed": False,
                "reason": "each checkpoint is a new immutable snapshot; next checkpoint has higher sequence and a consistency proof",
            },
            "new_generation": {
                "allowed": True,
                "generation": "exactly prior generation plus 1",
                "sequence": 1,
                "evidence": "log recovery/governance transition and last checkpoint continuity or explicit break",
            },
        },
        signer("TRANSPARENCY_LOG", "TRANSPARENCY_LOG", "1-of-1"),
        ["underlying_record", "private_opening_key"],
    )

    def immutable_object(
        name: str, rationale: str, fields: list[dict[str, Any]], signer_rule: dict[str, Any], forbidden: list[str]
    ) -> None:
        objects[name] = obj(
            evidence,
            rationale,
            [
                common("object_type"),
                common("object_version"),
                common("extensions", requiredness="optional-non-critical", genesis="optional", update="optional", critical=False),
                *fields,
            ],
            no_lineage_rules("new evidence/state creates a new object digest"),
            signer_rule,
            forbidden,
        )

    immutable_object(
        "InclusionProof",
        "One-shot Merkle evidence derives freshness and continuity from its checkpoint.",
        [
            field("log_id", 32, "bstr", "exactly 32 bytes"),
            field("scope", 33, "DelegationScope", "one closed partition scope"),
            field("checkpoint_digest", 34, "bstr", "exactly 32 bytes"),
            field("tree_size", 35, "uint", "1..2^64-1"),
            field("leaf_index", 36, "uint", "0..tree_size-1"),
            field("leaf_digest", 37, "bstr", "exactly 32 bytes"),
            field("proof_path", 38, "array<bstr>", "0..64 ordered 32-byte digests"),
            field("hash_profile", 39, "uint", "one HashProfile value"),
            field("object_class", 40, "uint|null", "null or approved ObjectType"),
        ],
        signer("TRANSPARENCY_LOG", "TRANSPARENCY_LOG", "checkpoint signature authorizes proof"),
        ["generation", "sequence", "previous_digest"],
    )
    immutable_object(
        "ConsistencyProof",
        "One-shot consistency evidence derives continuity from its two checkpoints.",
        [
            field("log_id", 32, "bstr", "exactly 32 bytes"),
            field("scope", 33, "DelegationScope", "one closed partition scope"),
            field("old_checkpoint_digest", 34, "bstr", "exactly 32 bytes"),
            field("new_checkpoint_digest", 35, "bstr", "exactly 32 bytes"),
            field("old_tree_size", 36, "uint", "0..new_tree_size"),
            field("new_tree_size", 37, "uint", "old_tree_size..2^64-1"),
            field("old_root", 38, "bstr", "exactly 32 bytes"),
            field("new_root", 39, "bstr", "exactly 32 bytes"),
            field("proof_path", 40, "array<bstr>", "0..64 ordered 32-byte digests"),
            field("hash_profile", 41, "uint", "one HashProfile value"),
        ],
        signer("TRANSPARENCY_LOG", "TRANSPARENCY_LOG", "both checkpoint signatures authorize proof"),
        ["generation", "sequence", "previous_digest"],
    )
    immutable_object(
        "WitnessStatement",
        "A replay-bound signed observation is never updated in place.",
        [
            field("witness_id", 32, "bstr", "exactly 32 bytes"),
            field("log_id", 33, "bstr", "exactly 32 bytes"),
            field("scope", 34, "DelegationScope", "one closed partition scope"),
            field("checkpoint_digest", 35, "bstr", "exactly 32 bytes"),
            field("tree_size", 36, "uint", "0..2^64-1"),
            field("merkle_root", 37, "bstr", "exactly 32 bytes"),
            field("observed_at", 38, "uint", "0..253402300799"),
            field("verification_result", 39, "uint", "one WitnessVerificationResult value"),
            field("replay_context", 40, "bstr", "16..64 bytes"),
            field("signing_key_id", 41, "bstr", "1..64 bytes"),
            field("valid_until", 42, "uint", "observed_at..253402300799"),
        ],
        signer("WITNESS", "WITNESS", "1-of-1"),
        ["generation", "sequence", "previous_digest"],
    )
    immutable_object(
        "FederationAuthorityProof",
        "A derived authority proof is replaced by a new digest whenever dependency state changes.",
        [
            field("proof_id", 32, "bstr", "exactly 16 bytes"),
            field("authority_root_digest", 33, "bstr", "exactly 32 bytes"),
            field("chain_digests", 34, "array<bstr>", "1..16 sorted unique 32-byte digests"),
            field("service_id", 35, "bstr", "exactly 32 bytes"),
            field("scope", 36, "DelegationScope", "one closed non-empty scope"),
            field("source_operator_id", 37, "bstr|null", "null for unilateral; exact 32 bytes for bilateral"),
            field("destination_operator_id", 38, "bstr", "exactly 32 bytes", requiredness="contextually-required"),
            field("trust_bundle_digest", 39, "bstr", "exactly 32 bytes"),
            field("checkpoint_digest", 40, "bstr", "exactly 32 bytes"),
            field("revocation_commitment", 41, "bstr", "exactly 32 bytes"),
            field("valid_until", 42, "uint", "0..253402300799"),
        ],
        signer("SOURCE_OPERATOR or DESTINATION_OPERATOR", "FEDERATION_AUTHORIZATION", "role-specific 1-of-1"),
        ["generation", "sequence", "previous_digest", "hidden_broken_ancestor"],
    )
    immutable_object(
        "ConflictEvidence",
        "Evidence is append-only; additions create a new evidence object under the conflict ID.",
        [
            field("conflict_id", 32, "bstr", "exactly 16 bytes"),
            field("evidence_id", 33, "bstr", "exactly 16 bytes"),
            field("conflict_class", 34, "uint", "one ConflictClass value"),
            field("scope", 35, "DelegationScope", "one closed affected scope"),
            field("object_class", 36, "uint", "approved ObjectType"),
            field("conflicting_digests", 37, "array<bstr>", "2..16 sorted unique 32-byte digests"),
            field("claimed_versions", 38, "array<VersionTuple>", "1..16 sorted unique tuples"),
            field("checkpoint_digests", 39, "array<bstr>", "0..16 sorted unique 32-byte digests"),
            field("provenance_digests", 40, "array<bstr>", "1..32 sorted unique 32-byte digests"),
            field("first_observed_at", 41, "uint", "0..253402300799"),
            field("quarantine_recommended", 42, "bool", "false or true"),
            field("privacy_class", 43, "uint", "one PrivacyClass value", privacy="scope-dependent", traits=("privacy-sensitive",)),
        ],
        signer("SOURCE_OPERATOR or DESTINATION_OPERATOR", "GOVERNANCE", "one 1-of-1 set"),
        ["generation", "sequence", "previous_digest", "unbounded_prose_claim"],
    )

    def decision_object(
        name: str, rationale: str, fields: list[dict[str, Any]], signer_rule: dict[str, Any], continuation: str, forbidden: list[str]
    ) -> None:
        objects[name] = obj(
            decision,
            rationale,
            [
                common("object_type"),
                common("object_version"),
                common("issuer_id", traits=("authority-defining",)),
                common("effective_at"),
                common("extensions", requiredness="optional-non-critical", genesis="optional", update="optional", critical=False),
                *fields,
            ],
            no_lineage_rules(continuation),
            signer_rule,
            forbidden,
        )

    decision_object(
        "FederationAuthorizationContext",
        "Immutable bilateral authorization is replaced whenever any dependency or policy changes.",
        [
            field("context_id", 32, "bstr", "exactly 16 bytes"),
            field("source_operator_id", 33, "bstr", "exactly 32 bytes"),
            field("destination_operator_id", 34, "bstr", "exactly 32 bytes"),
            field("service_id", 35, "bstr", "exactly 32 bytes"),
            field("authority_proof_digest", 36, "bstr", "exactly 32 bytes"),
            field("trust_bundle_digest", 37, "bstr", "exactly 32 bytes"),
            field("checkpoint_digest", 38, "bstr", "exactly 32 bytes"),
            field("policy_digest", 39, "bstr", "exactly 32 bytes"),
            field("scope", 40, "DelegationScope", "one closed allowed scope"),
            field("valid_until", 41, "uint", "effective_at..253402300799"),
            field("affected_generation", 42, "uint", "1..2^64-1"),
            field("affected_sequence", 43, "uint", "1..2^64-1"),
            field("dependencies", 44, "FederationDependencySet", "1..256 sorted unique dependencies"),
            field("dependency_set_digest", 45, "bstr", "exactly 32 bytes"),
            field("route_context_digest", 46, "bstr", "exactly 32 bytes"),
        ],
        signer("SOURCE_OPERATOR plus DESTINATION_OPERATOR", "FEDERATION_AUTHORIZATION", "both 1-of-1"),
        "new authorization is a separate context ID and digest",
        ["previous_digest", "implicit_port", "implicit_protocol", "origin_endpoint"],
    )
    decision_object(
        "RecoveryTransitionRecord",
        "A one-shot recovery authorization binds old/new generations and cannot represent ordinary rotation.",
        [
            field("transition_id", 32, "bstr", "exactly 16 bytes"),
            field("operator_id", 33, "bstr", "exactly 32 bytes"),
            field("affected_targets", 34, "array<AuthorityTarget>", "1..64 sorted unique targets"),
            field("old_generation", 35, "uint", "1..2^64-2"),
            field("new_generation", 36, "uint", "exactly old_generation plus 1"),
            field("revoked_targets", 37, "array<AuthorityTarget>", "1..64 sorted unique targets"),
            field("replacement_targets", 38, "array<AuthorityTarget>", "1..64 sorted unique targets"),
            field("continuity_digest", 39, "bstr|null", "exact 32 bytes or null only with explicit_break=true"),
            field("explicit_break", 40, "bool", "false or true"),
            field("scope", 41, "DelegationScope", "restore-or-narrow affected scope"),
            field("approval_signatures", 42, "array<SignatureReference>", "5..7 canonically sorted references"),
            field("transparency_reference", 43, "TransparencyReference", "one exact checkpoint reference"),
            field("recovery_stage", 44, "uint", "RECOVERY_PENDING, RECOVERY_VERIFIED, or REENTRY_RESTRICTED"),
            field("activation_restrictions", 45, "DelegationScope", "one strict non-empty scope"),
        ],
        signer(
            "OPERATOR_RECOVERY plus DEVELOPMENT_REGISTRAR plus WITNESS",
            "RECOVERY plus REGISTRY_SIGNING plus WITNESS",
            "2-of-3 plus 1-of-1 plus 2-of-3",
        ),
        "a later recovery uses a new transition ID and strictly higher affected generation",
        ["ordinary_rotation", "authority_expansion", "compromised_signer"],
    )
    decision_object(
        "ConflictResolutionRecord",
        "A signed resolution is immutable; later process creates a separately identified decision.",
        [
            field("decision_id", 32, "bstr", "exactly 16 bytes"),
            field("conflict_id", 33, "bstr", "exactly 16 bytes"),
            field("evidence_set_digest", 34, "bstr", "exactly 32 bytes"),
            field("scope", 35, "DelegationScope", "one closed affected scope"),
            field("outcome", 36, "uint", "approved DecisionOutcome"),
            field("invalidated_targets", 37, "array<AuthorityTarget>", "0..64 sorted unique targets"),
            field("preserved_targets", 38, "array<AuthorityTarget>", "0..64 sorted unique targets"),
            field("affected_generation", 39, "uint", "1..2^64-1"),
            field("affected_sequence", 40, "uint", "1..2^64-1"),
            field("revocation_digests", 41, "array<bstr>", "0..64 sorted unique 32-byte digests"),
            field("recovery_requirement_digest", 42, "bstr|null", "null or exact 32 bytes"),
            field("appeal_deadline", 43, "uint", "effective_at..253402300799"),
            field("approvals", 44, "array<SignatureReference>", "7..10 canonically sorted references"),
            field(
                "previous_decision_digest",
                45,
                "bstr|null",
                "null or exact 32 bytes; only sequential review",
                requiredness="optional-critical",
            ),
            field("transparency_reference", 46, "TransparencyReference", "one exact checkpoint reference"),
        ],
        signer("CONFLICT_RESOLUTION plus WITNESS", "GOVERNANCE plus WITNESS", "4-of-5 plus 3-of-5"),
        "new resolution has a new decision ID; previous_decision_digest only for explicit sequential review",
        ["evidence_deletion", "silent_reactivation"],
    )
    decision_object(
        "AppealDecisionRecord",
        "An appeal result is immutable and cannot itself restore unsafe authority.",
        [
            field("decision_id", 32, "bstr", "exactly 16 bytes"),
            field("appeal_id", 33, "bstr", "exactly 16 bytes"),
            field("original_decision_digest", 34, "bstr", "exactly 32 bytes"),
            field("evidence_set_digest", 35, "bstr", "exactly 32 bytes"),
            field("appellant_standing", 36, "uint", "one AppellantStanding value"),
            field("scope", 37, "DelegationScope", "one closed affected scope"),
            field("grounds", 38, "uint", "one AppealGrounds value"),
            field("outcome", 39, "uint", "approved DecisionOutcome"),
            field("state_transitions", 40, "array<LifecycleTransition>", "1..16 ordered transitions"),
            field("invalidated_targets", 41, "array<AuthorityTarget>", "0..64 sorted unique targets"),
            field("preserved_targets", 42, "array<AuthorityTarget>", "0..64 sorted unique targets"),
            field("required_followup", 43, "array<AuthorityTarget>", "0..16 sorted unique targets"),
            field("approvals", 44, "array<SignatureReference>", "7..10 canonically sorted references"),
            field(
                "previous_decision_digest",
                45,
                "bstr|null",
                "null or exact 32 bytes; only sequential review",
                requiredness="optional-critical",
            ),
            field("transparency_reference", 46, "TransparencyReference", "one exact checkpoint reference"),
        ],
        signer("APPEAL plus WITNESS", "GOVERNANCE plus WITNESS", "4-of-5 plus 3-of-5"),
        "later review creates a new decision ID and optionally binds the prior decision",
        ["automatic_reactivation", "evidence_deletion", "generation", "sequence"],
    )

    recovery_allowed = {
        "OperatorRegistryRecord": (True, True, "2-of-3 operator recovery + 1-of-1 registry + 2-of-3 witnesses"),
        "KeyAuthorizationRecord": (True, True, "2-of-3 operator recovery + accepted registry verification"),
        "NameOwnershipRecord": (True, True, "2-of-3 recovery + ownership/registry verification + 2-of-3 witnesses"),
        "DelegationRecord": (True, True, "2-of-3 recovery + parent authority verification"),
        "FederationTrustBundle": (True, True, "4-of-5 governance + 3-of-5 witnesses"),
        "OperatorEndpointRecord": (True, True, "2-of-3 recovery + 1-of-1 registry + 2-of-3 witnesses"),
        "OperatorLifecycleRecord": (True, True, "2-of-3 recovery + 1-of-1 registry + 2-of-3 witnesses"),
    }
    recovery: dict[str, Any] = {}
    for name in objects:
        allowed, registry_required, threshold = recovery_allowed.get(name, (False, False, "not-applicable"))
        recovery[name] = {
            "allowed": allowed,
            "normal_signer": objects[name]["signer_rule"]["normal_authority"],
            "required_lifecycle": "RECOVERY" if allowed else None,
            "transition_binding_required": allowed,
            "strictly_higher_generation": allowed,
            "registry_approval_required": registry_required,
            "witness_threshold": threshold,
            "scope_change": "restore-or-narrow-only" if allowed else "not-applicable",
            "compromised_signer_forbidden": True,
        }

    common_fields = {name: {"key": key, "wire_type": wire_type, "bounds": bounds} for name, (key, wire_type, bounds) in COMMON.items()}
    return {
        "format_version": 1,
        "profile": "nbsr-federation-dev-v1",
        "status": STATUS,
        "proposal_authority": "new schema decisions authorized by the 2026-08-07 human request; not derived values from F1-F119",
        "runtime_implementation_authorized": False,
        "task2_ready_after_human_approval": True,
        "key_model": {
            "common": [1, 31],
            "object_specific": [32, 127],
            "reserved": [128, 999],
            "extension_ids": [1000, 65535],
            "unknown_base_key": "reject",
            "direct_extension_key": "reject",
        },
        "common_fields": common_fields,
        "scalar_types": {
            "operator_id": "bstr .size 32",
            "key_id": "bstr .size (1..64)",
            "digest": "bstr .size 32",
            "generation_sequence": "uint .within 1..2^64-1",
            "timestamp": "uint seconds .within 0..253402300799",
            "enum": "uint from the named approved registry",
            "canonical_name": "UTF-8 tstr, NFC, lowercase A-label form, 1..255 encoded bytes",
            "service_id": "bstr .size 32; SHA-256('NBSR-FEDERATION-SERVICE-ID-v1' || 0x00 || genesis_owner_operator_id:bstr32 || name_length:uint16be || canonical_name:utf8)",
            "request_event_object_id": "bstr .size 16; unique inside issuer domain; bytewise equality only",
        },
        "composite_types": composite_types(),
        "signature_threshold_rules": {
            "distinct_kid_per_set": True,
            "distinct_authority_identity_per_set": True,
            "signer_reuse_across_sets": "reject",
            "signed_payload_digest": "must-equal-object-payload-digest",
            "cose_binding": "cose_sign1_digest-must-identify-valid-COSE-Sign1-over-the-same-payload",
            "evaluation": "count-valid-distinct-authorities-not-array-items",
            "canonical_order": "authority_class,key_purpose,kid,cose_sign1_digest",
        },
        "local_enums": {
            "OrganizationBindingMode": {"PUBLIC_NAME": 1, "PRIVATE_DOMAIN_COMMITMENT": 2},
            "OwnershipTransferState": {"NONE": 0, "PENDING": 1, "COMPLETE": 2, "RECOVERY": 3},
            "EndpointRole": {"CONTROL": 1, "TRANSPARENCY": 2, "DISCOVERY": 3},
            "EndpointLifecycle": {"ACTIVE": 1, "RETIRING": 2, "RETIRED": 3, "REVOKED": 4},
            "TransportProfile": {"QUIC_TLS13": 1},
            "RevocationAuthorityMode": {"TARGET_CONTROLLER": 1, "NORMAL_THRESHOLD": 2, "EMERGENCY_DENY_ONLY": 3},
            "HashProfile": {"SHA256": 1},
            "WitnessVerificationResult": {"CONSISTENT": 1, "CONFLICT": 2},
            "PrivacyClass": {"PUBLIC": 1, "CONSORTIUM": 2, "PRIVATE": 3},
            "ConflictClass": {"EQUIVOCATION": 1, "OWNERSHIP": 2, "REGISTRY": 3, "RECOVERY": 4, "SCOPE": 5},
            "AppellantStanding": {"AFFECTED_OPERATOR": 1, "NAME_OWNER": 2, "REGISTRY": 3, "PUBLIC_INTEREST_REVIEWER": 4},
            "AppealGrounds": {
                "EVIDENCE_INTERPRETATION": 1,
                "PROCESS": 2,
                "CONFLICT_OF_INTEREST": 3,
                "PROPORTIONALITY": 4,
                "DECISION_ERROR": 5,
            },
        },
        "recovery_default": "reject-unless-object-entry-allows",
        "recovery_substitution": recovery,
        "objects": {name: objects[name] for name in OBJECT_ORDER},
    }


def composite_types() -> dict[str, Any]:
    base = {"closed": True, "duplicate_behavior": "reject", "unknown_field_behavior": "reject"}
    return {
        "DelegationScope": {
            **base,
            "wire_type": "map",
            "fields": {
                "1": "name_scope:tstr|null",
                "2": "service_id:bstr32|null",
                "3": "tenant_id:bstr(1..64)|null",
                "4": "source_operator_id:bstr32|null",
                "5": "destination_operator_id:bstr32|null",
                "6": "region:tstr(1..32)|null",
                "7": "port_ranges:array<[uint,uint]>(0..32)",
                "8": "protocols:array<uint>(1..16)",
                "9": "allowed_actions:array<uint>(1..32)",
                "10": "subdelegation_allowed:bool",
                "11": "remaining_depth:uint(0..8)",
            },
            "cardinality": "all 11 keys required; null means constrained dimension not applicable, never wildcard",
            "canonical_ordering": "map integer key order; arrays sorted lexicographically and duplicate-free; port ranges disjoint, ascending, and non-adjacent",
            "maximum_encoded_bytes": 2048,
            "intersection": "fieldwise intersection; null intersects only null; child must equal or narrow every dimension",
        },
        "AuthorityTarget": {
            **base,
            "wire_type": "map",
            "fields": {"1": "object_class:uint", "2": "identifier:bstr(1..64)", "3": "canonical_digest:bstr32|null"},
            "cardinality": "exactly three keys",
            "canonical_ordering": "integer key order",
            "maximum_encoded_bytes": 128,
        },
        "AuthorityReference": {
            **base,
            "wire_type": "map",
            "fields": {
                "1": "authority_class:uint",
                "2": "authority_id:bstr(1..64)",
                "3": "key_id:bstr(1..64)|null",
                "4": "operator_id:bstr32|null",
            },
            "cardinality": "exactly four keys",
            "canonical_ordering": "integer key order",
            "maximum_encoded_bytes": 256,
        },
        "TransparencyReference": {
            **base,
            "wire_type": "map",
            "fields": {
                "1": "log_id:bstr32",
                "2": "checkpoint_digest:bstr32",
                "3": "tree_size:uint",
                "4": "inclusion_proof_digest:bstr32|null",
            },
            "cardinality": "exactly four keys",
            "canonical_ordering": "integer key order",
            "maximum_encoded_bytes": 160,
        },
        "FederationDependencySet": {
            **base,
            "wire_type": "array",
            "item": "[object_class:uint, canonical_digest:bstr32]",
            "cardinality": "1..256",
            "canonical_ordering": "ascending object_class then bytewise digest; duplicate tuple rejected",
            "maximum_encoded_bytes": 9216,
            "digest": "SHA-256 over deterministic CBOR encoding of the complete array",
        },
        "ExtensionEntry": {
            **base,
            "wire_type": "map",
            "fields": {"1": "extension_version:uint(1..65535)", "2": "critical:bool", "3": "canonical_value:bstr(0..4096)"},
            "cardinality": "exactly three keys",
            "canonical_ordering": "outer extension IDs ascending; entry integer key order",
            "maximum_encoded_bytes": 4128,
            "preservation": "unknown non-critical canonical_value bytes preserved exactly; unknown critical rejected",
        },
        "SignatureReference": {
            **base,
            "wire_type": "map",
            "fields": {
                "1": "authority_class:uint",
                "2": "key_purpose:uint",
                "3": "kid:bstr(1..64)",
                "4": "cose_sign1_digest:bstr32",
                "5": "signed_payload_digest:bstr32",
            },
            "cardinality": "exactly five keys",
            "canonical_ordering": "authority_class, purpose, kid, COSE digest, payload digest; duplicates rejected",
            "maximum_encoded_bytes": 192,
        },
        "OrganizationBinding": {
            **base,
            "wire_type": "map",
            "fields": {
                "1": "mode:OrganizationBindingMode",
                "2": "public_name:tstr(1..255)|null",
                "3": "domain_commitment:bstr32|null",
            },
            "cardinality": "exactly one of public_name/domain_commitment non-null according to mode",
            "canonical_ordering": "integer key order",
            "maximum_encoded_bytes": 384,
        },
        "ThresholdSet": {
            **base,
            "wire_type": "map",
            "fields": {"1": "authority:[uint,uint]", "2": "witness:[uint,uint]", "3": "logs:[uint,uint]"},
            "cardinality": "exactly three keys",
            "canonical_ordering": "integer key order",
            "maximum_encoded_bytes": 64,
        },
        "VersionTuple": {
            **base,
            "wire_type": "array",
            "item": "[generation:uint, sequence:uint]",
            "cardinality": "exactly two items",
            "canonical_ordering": "generation then sequence",
            "maximum_encoded_bytes": 20,
        },
        "LifecycleTransition": {
            **base,
            "wire_type": "map",
            "fields": {"1": "target:AuthorityTarget", "2": "from_state:uint", "3": "to_state:uint", "4": "recovery_stage:uint|null"},
            "cardinality": "exactly four keys; recovery_stage non-null iff to_state=RECOVERY",
            "canonical_ordering": "integer key order",
            "maximum_encoded_bytes": 256,
        },
    }


def cbor(value: Any) -> bytes:
    if isinstance(value, bool):
        return b"\xf5" if value else b"\xf4"
    if value is None:
        return b"\xf6"
    if isinstance(value, int) and value >= 0:
        return head(0, value)
    if isinstance(value, bytes):
        return head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return head(3, len(raw)) + raw
    if isinstance(value, list):
        return head(4, len(value)) + b"".join(cbor(item) for item in value)
    if isinstance(value, dict):
        pairs = sorted(((cbor(key), cbor(item)) for key, item in value.items()), key=lambda pair: (len(pair[0]), pair[0]))
        return head(5, len(pairs)) + b"".join(key + item for key, item in pairs)
    raise TypeError(type(value))


def head(major: int, value: int) -> bytes:
    prefix = major << 5
    if value < 24:
        return bytes([prefix | value])
    if value <= 0xFF:
        return bytes([prefix | 24, value])
    if value <= 0xFFFF:
        return bytes([prefix | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([prefix | 26]) + value.to_bytes(4, "big")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes([prefix | 27]) + value.to_bytes(8, "big")
    raise ValueError(value)


def authority(authority_class: int, authority_id: bytes, kid: bytes | None, operator_id: bytes | None) -> dict[int, Any]:
    return {1: authority_class, 2: authority_id, 3: kid, 4: operator_id}


def scope(operator_id: bytes) -> dict[int, Any]:
    name = b"example.test"
    service_id = hashlib.sha256(b"NBSR-FEDERATION-SERVICE-ID-v1\x00" + operator_id + len(name).to_bytes(2, "big") + name).digest()
    return {
        1: "example.test",
        2: service_id,
        3: None,
        4: operator_id,
        5: operator_id,
        6: "eu",
        7: [[443, 443]],
        8: [1],
        9: [1],
        10: False,
        11: 0,
    }


def transparency() -> dict[int, Any]:
    return {1: b"L" * 32, 2: b"C" * 32, 3: 1, 4: b"P" * 32}


def fixtures() -> dict[str, Any]:
    operator = b"O" * 32
    registrar = authority(12, b"registrar", b"reg-kid", None)
    root = authority(1, operator, b"root-kid", operator)
    recovery = authority(2, operator, b"recovery-kid", operator)
    new_root = authority(1, operator, b"new-root-kid", operator)
    no_revoke = None
    op_genesis = {
        1: 1,
        2: 1,
        3: registrar,
        4: 1,
        5: 1,
        6: 1000,
        7: 2000,
        32: operator,
        33: root,
        34: {1: 1, 2: "Example Operator", 3: None},
        35: scope(operator),
        36: 1,
        37: no_revoke,
        38: transparency(),
    }
    op_genesis_digest = hashlib.sha256(cbor(op_genesis)).digest()
    op_update = {**op_genesis, 5: 2, 8: op_genesis_digest, 36: 2}
    op_update_digest = hashlib.sha256(cbor(op_update)).digest()
    op_active_predecessor = {**op_genesis, 5: 4, 8: b"H" * 32, 36: 5}
    op_active_digest = hashlib.sha256(cbor(op_active_predecessor)).digest()
    op_recovery = {**op_genesis, 4: 2, 5: 1, 8: op_active_digest, 33: new_root, 36: 8, 39: 1}
    key_genesis = {
        1: 2,
        2: 1,
        3: root,
        4: 1,
        5: 1,
        6: 1000,
        7: 2000,
        32: operator,
        33: b"operational-kid",
        34: b"K" * 32,
        35: 3,
        36: 2,
        37: root,
        38: False,
        39: None,
    }
    key_genesis_digest = hashlib.sha256(cbor(key_genesis)).digest()
    key_update = {**key_genesis, 5: 2, 8: key_genesis_digest, 36: 3}
    key_update_digest = hashlib.sha256(cbor(key_update)).digest()
    key_recovery = {
        **key_genesis,
        3: recovery,
        4: 2,
        5: 1,
        8: key_update_digest,
        33: b"recovered-kid",
        34: b"N" * 32,
        36: 1,
        37: recovery,
        40: b"R" * 32,
    }
    checkpoint_genesis = {
        1: 6,
        2: 1,
        3: authority(6, b"L" * 32, b"log-kid", None),
        4: 1,
        5: 1,
        32: b"L" * 32,
        33: scope(operator),
        34: 0,
        35: hashlib.sha256(b"").digest(),
        36: 0,
        37: b"log-kid",
        38: None,
        39: None,
    }
    old_checkpoint_digest = hashlib.sha256(cbor(checkpoint_genesis)).digest()
    new_checkpoint_digest = b"Q" * 32
    consistency_valid = {
        1: 8,
        2: 1,
        32: b"L" * 32,
        33: scope(operator),
        34: old_checkpoint_digest,
        35: new_checkpoint_digest,
        36: 0,
        37: 1,
        38: hashlib.sha256(b"").digest(),
        39: b"M" * 32,
        40: [],
        41: 1,
    }
    entries: list[tuple[str, str, dict[int, Any], str, str, bool, dict[str, Any]]] = [
        ("OperatorRegistryRecord", "valid-genesis", op_genesis, "ACCEPT", "NONE", True, {"signer": "registrar-plus-witnesses"}),
        (
            "OperatorRegistryRecord",
            "valid-same-generation-update",
            op_update,
            "ACCEPT",
            "NONE",
            True,
            {"signer": "registrar-plus-witnesses", "current_digest": op_genesis_digest.hex()},
        ),
        (
            "OperatorRegistryRecord",
            "valid-recovery-new-generation",
            op_recovery,
            "ACCEPT",
            "NONE",
            True,
            {
                "signer": "recovery-plus-registry-plus-witnesses",
                "recovery_transition": (b"R" * 32).hex(),
                "current_generation": 1,
                "current_sequence": 4,
                "current_lifecycle": "ACTIVE",
                "current_digest": op_active_digest.hex(),
            },
        ),
        (
            "OperatorRegistryRecord",
            "missing-required-operator-id",
            {k: v for k, v in op_genesis.items() if k != 32},
            "REJECT",
            "ERR_SCHEMA",
            False,
            {},
        ),
        ("OperatorRegistryRecord", "forbidden-genesis-predecessor", {**op_genesis, 8: b"A" * 32}, "REJECT", "ERR_SCHEMA", False, {}),
        ("OperatorRegistryRecord", "wrong-operator-id-length", {**op_genesis, 32: b"short"}, "REJECT", "ERR_IDENTITY", False, {}),
        (
            "OperatorRegistryRecord",
            "stale-sequence",
            op_update,
            "REJECT",
            "ERR_ROLLBACK",
            False,
            {"current_generation": 1, "current_sequence": 3},
        ),
        (
            "OperatorRegistryRecord",
            "equal-version-conflicting-digest",
            {**op_update, 36: 9},
            "QUARANTINE",
            "ERR_EQUIVOCATION",
            False,
            {"current_generation": 1, "current_sequence": 2, "current_digest": op_update_digest.hex()},
        ),
        ("OperatorRegistryRecord", "invalid-signer", op_genesis, "REJECT", "ERR_AUTHORITY", False, {"signer": "operator-root-only"}),
        (
            "OperatorRegistryRecord",
            "recovery-signer-without-transition",
            op_recovery,
            "REJECT",
            "ERR_RECOVERY_INVALID",
            False,
            {"recovery_transition": None},
        ),
        (
            "OperatorRegistryRecord",
            "unknown-critical-extension",
            {**op_genesis, 31: {1000: {1: 1, 2: True, 3: b"x"}}},
            "REJECT",
            "ERR_UNSUPPORTED_CRITICAL",
            False,
            {},
        ),
        (
            "OperatorRegistryRecord",
            "missing-recovery-stage",
            {k: v for k, v in op_recovery.items() if k != 39},
            "REJECT",
            "ERR_SCHEMA",
            False,
            {"recovery_transition": (b"R" * 32).hex()},
        ),
        (
            "OperatorRegistryRecord",
            "recovery-stage-outside-recovery",
            {**op_genesis, 39: 1},
            "REJECT",
            "ERR_SCHEMA",
            False,
            {},
        ),
        (
            "KeyAuthorizationRecord",
            "valid-root-authorized-genesis",
            key_genesis,
            "ACCEPT",
            "NONE",
            True,
            {"signer": "root", "protected_kid": "root-kid"},
        ),
        (
            "KeyAuthorizationRecord",
            "valid-rotation-update",
            key_update,
            "ACCEPT",
            "NONE",
            True,
            {
                "signer": "root",
                "protected_kid": "root-kid",
                "current_generation": 1,
                "current_sequence": 1,
                "current_digest": key_genesis_digest.hex(),
            },
        ),
        (
            "KeyAuthorizationRecord",
            "valid-recovery-authorized-new-generation",
            key_recovery,
            "ACCEPT",
            "NONE",
            True,
            {
                "signer": "recovery-threshold",
                "protected_kid": "recovery-kid",
                "recovery_transition": (b"R" * 32).hex(),
                "current_generation": 1,
                "current_sequence": 2,
                "current_digest": key_update_digest.hex(),
            },
        ),
        ("KeyAuthorizationRecord", "wrong-key-purpose", {**key_genesis, 35: 4}, "REJECT", "ERR_KEY_PURPOSE", False, {}),
        (
            "KeyAuthorizationRecord",
            "cross-purpose-signer",
            key_genesis,
            "REJECT",
            "ERR_KEY_PURPOSE",
            False,
            {"signer_purpose": "ENDPOINT_DISCOVERY"},
        ),
        ("KeyAuthorizationRecord", "bad-kid", key_genesis, "REJECT", "ERR_IDENTITY", False, {"protected_kid": "unknown-kid"}),
        ("KeyAuthorizationRecord", "expired", key_genesis, "REJECT", "ERR_FRESHNESS", False, {"validation_time": 2001}),
        (
            "KeyAuthorizationRecord",
            "predecessor-mismatch",
            {**key_update, 8: b"Z" * 32},
            "REJECT",
            "ERR_CONTINUITY",
            False,
            {"current_digest": key_genesis_digest.hex()},
        ),
        (
            "KeyAuthorizationRecord",
            "terminal-key-id-reuse",
            {**key_recovery, 33: b"terminal-kid"},
            "REJECT",
            "ERR_TERMINAL_STATE",
            False,
            {"terminal_key_ids": [b"terminal-kid".hex()]},
        ),
        ("KeyAuthorizationRecord", "compromised-signer", key_update, "REJECT", "ERR_KEY_LIFECYCLE", False, {"signer_lifecycle": "REVOKED"}),
        (
            "KeyAuthorizationRecord",
            "unknown-critical-extension",
            {**key_genesis, 31: {1000: {1: 1, 2: True, 3: b"x"}}},
            "REJECT",
            "ERR_UNSUPPORTED_CRITICAL",
            False,
            {},
        ),
        (
            "TransparencyCheckpoint",
            "valid-genesis-checkpoint",
            checkpoint_genesis,
            "ACCEPT",
            "NONE",
            True,
            {},
        ),
        (
            "TransparencyCheckpoint",
            "invalid-generation-reset-without-transition",
            {**checkpoint_genesis, 4: 2},
            "REJECT",
            "ERR_RECOVERY_INVALID",
            False,
            {"accepted_transition": None, "current_generation": 1},
        ),
        (
            "ConsistencyProof",
            "valid-checkpoint-continuity",
            consistency_valid,
            "ACCEPT",
            "NONE",
            False,
            {"expected_old_checkpoint_digest": old_checkpoint_digest.hex(), "expected_new_checkpoint_digest": new_checkpoint_digest.hex()},
        ),
        (
            "ConsistencyProof",
            "invalid-old-new-checkpoint-mismatch",
            {**consistency_valid, 34: b"Z" * 32},
            "REJECT",
            "ERR_CONTINUITY",
            False,
            {"expected_old_checkpoint_digest": old_checkpoint_digest.hex()},
        ),
    ]
    rendered = []
    for object_type, name, payload, outcome, reason, changed, context in entries:
        raw = cbor(payload)
        semantic_assertions: dict[str, Any] = {}
        if object_type == "OperatorRegistryRecord" and name == "valid-genesis":
            semantic_assertions["service_id"] = payload[35][2].hex()
        if object_type == "KeyAuthorizationRecord" and name == "valid-recovery-authorized-new-generation":
            semantic_assertions = {
                "key_id_changed_at_new_generation": payload[33] != key_update[33],
                "public_key_changed_at_new_generation": payload[34] != key_update[34],
                "key_lifecycle": "NEXT",
            }
        rendered.append(
            {
                "object_type": object_type,
                "name": name,
                "canonical_cbor_hex": raw.hex(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "expected_outcome": outcome,
                "reason": reason,
                "state_changed": changed,
                "validation_context": context,
                "semantic_assertions": semantic_assertions,
            }
        )
    return {
        "format_version": 1,
        "profile": "nbsr-federation-dev-v1",
        "status": STATUS,
        "generated_by_future_runtime": False,
        "encoder": "scripts/render_federation_schema.py tiny specification-only deterministic CBOR encoder",
        "fixtures": rendered,
    }


def markdown(data: dict[str, Any], package: dict[str, Any]) -> str:
    lines = [
        "# Federation v0.1 Schema Allocation Proposal",
        "",
        f"> **{STATUS}**",
        "",
        "This table is generated from the proposal registry. It does not authorize runtime implementation before human approval.",
        "",
        "## Common keys",
        "",
        "| Key | Field | Wire type | Bounds |",
        "|---:|---|---|---|",
    ]
    for name, spec in sorted(data["common_fields"].items(), key=lambda item: item[1]["key"]):
        lines.append(f"| {spec['key']} | `{name}` | `{spec['wire_type']}` | {spec['bounds']} |")
    lines += ["", "## Object allocations", ""]
    for name, spec in data["objects"].items():
        lines += [
            f"### {name}",
            "",
            f"Lifecycle: `{spec['lifecycle_class']}`. {spec['rationale']}",
            "",
            "| Key | Field | Type | Requiredness | Genesis | Update | Privacy |",
            "|---:|---|---|---|---|---|---|",
        ]
        for item in sorted(spec["fields"], key=lambda value: value["key"]):
            lines.append(
                f"| {item['key']} | `{item['name']}` | `{item['wire_type']}` | {item['requiredness']} | {item['genesis']} | {item['update']} | {item['privacy']} |"
            )
        lines.append("")
    lines += [
        "## Literal proposal fixture digests",
        "",
        "| Object | Fixture | SHA-256 | Expected | Reason | Mutation |",
        "|---|---|---|---|---|---|",
    ]
    for item in package["fixtures"]:
        lines.append(
            f"| {item['object_type']} | `{item['name']}` | `{item['sha256']}` | {item['expected_outcome']} | {item['reason']} | `{str(item['state_changed']).lower()}` |"
        )
    return "\n".join(lines) + "\n"


def encoded_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = schema()
    package = fixtures()
    outputs = {SCHEMA_PATH: encoded_json(data), FIXTURE_PATH: encoded_json(package), TABLE_PATH: markdown(data, package)}
    if args.check:
        stale = [
            str(path.relative_to(ROOT))
            for path, content in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print("stale federation schema outputs: " + ", ".join(stale))
            return 1
        print(f"federation schema proposal check passed: {len(data['objects'])} objects, {len(package['fixtures'])} proposal fixtures")
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"rendered federation schema proposal: {len(data['objects'])} objects, {len(package['fixtures'])} proposal fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
