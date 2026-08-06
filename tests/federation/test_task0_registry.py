import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/protocol/registries/federation-v0.1-development.json"
AMENDMENT = ROOT / "docs/protocol/wp8-federation-v0.1-registry-allocation.md"


EXPECTED_MESSAGES = [
    "OPERATOR_RECORD_SUBMIT",
    "OPERATOR_RECORD_RESULT",
    "KEY_AUTHORIZATION_SUBMIT",
    "KEY_AUTHORIZATION_RESULT",
    "NAME_OWNERSHIP_SUBMIT",
    "NAME_OWNERSHIP_RESULT",
    "DELEGATION_SUBMIT",
    "DELEGATION_RESULT",
    "TRUST_BUNDLE_REQUEST",
    "TRUST_BUNDLE_RESULT",
    "CHECKPOINT_REQUEST",
    "CHECKPOINT_RESULT",
    "INCLUSION_PROOF_REQUEST",
    "INCLUSION_PROOF_RESULT",
    "CONSISTENCY_PROOF_REQUEST",
    "CONSISTENCY_PROOF_RESULT",
    "WITNESS_STATEMENT_SUBMIT",
    "WITNESS_STATEMENT_RESULT",
    "ENDPOINT_REQUEST",
    "ENDPOINT_RESULT",
    "AUTHORITY_PROOF_SUBMIT",
    "AUTHORITY_PROOF_RESULT",
    "AUTHORIZATION_REQUEST",
    "AUTHORIZATION_RESULT",
    "REVOCATION_SUBMIT",
    "REVOCATION_RESULT",
    "LIFECYCLE_SUBMIT",
    "LIFECYCLE_RESULT",
    "RECOVERY_SUBMIT",
    "RECOVERY_RESULT",
    "CONFLICT_SUBMIT",
    "CONFLICT_RESULT",
    "APPEAL_SUBMIT",
    "APPEAL_RESULT",
]

EXPECTED_OBJECTS = [
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
]


def _load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_task0_allocates_all_message_and_object_values_literally() -> None:
    source = _load()
    assert [entry["name"] for entry in source["registries"]["message_types"]] == EXPECTED_MESSAGES
    assert [entry["value"] for entry in source["registries"]["message_types"]] == list(range(0x4000, 0x4022))
    assert [entry["name"] for entry in source["registries"]["object_types"]] == EXPECTED_OBJECTS
    assert [entry["value"] for entry in source["registries"]["object_types"]] == list(range(1, 19))


def test_task0_allocates_every_required_closed_registry() -> None:
    source = _load()
    required = {
        "extension_ids",
        "capability_ids",
        "object_types",
        "message_types",
        "reason_codes",
        "key_purposes",
        "key_lifecycles",
        "operator_lifecycles",
        "recovery_stages",
        "result_types",
        "decision_outcomes",
        "enforcement_modes",
        "authority_classes",
    }
    assert set(source["registries"]) == required
    for name, entries in source["registries"].items():
        assert entries, name
        values = [entry["value"] for entry in entries]
        assert len(values) == len(set(values)), name
        assert all(entry["status"] == "proposed-development-profile" for entry in entries)


def test_task0_registry_namespaces_and_reservations_are_explicit() -> None:
    source = _load()
    assert source["status"] == "proposed-for-human-approval"
    assert source["wire_freeze"] is False
    assert source["core_collision_proof"]["core_message_values"] == list(range(1, 18))
    assert source["reserved_ranges"]["message_types"] == [[0x4022, 0x40FF]]
    assert source["reserved_ranges"]["object_types"] == [[19, 255]]
    assert source["reserved_ranges"]["reason_codes"] == [[32, 255]]


def test_registry_amendment_tables_exactly_match_machine_source() -> None:
    source = _load()
    document = AMENDMENT.read_text(encoding="utf-8")
    for registry, entries in source["registries"].items():
        assert f"<!-- registry:{registry} -->" in document
        for entry in entries:
            assert f"| {entry['value']} | `{entry['name']}` |" in document


def test_every_registry_is_closed_and_unknown_values_fail_before_mutation() -> None:
    source = _load()
    assert source["unknown_value_policy"] == {
        "outcome": "REJECT",
        "reason": "ERR_UNSUPPORTED_CRITICAL",
        "state_changed": False,
        "applies_to": sorted(source["registries"]),
    }


def test_signer_recovery_and_privacy_opening_authority_is_exact() -> None:
    source = _load()
    assert source["signer_authority_matrix"]["KeyAuthorizationRecord"] == {
        "signer_sets": [
            {"authority": "OPERATOR_IDENTITY_ROOT", "purpose": "IDENTITY_ROOT", "threshold": [1, 1]},
            {"authority": "OPERATOR_RECOVERY", "purpose": "RECOVERY", "threshold": [2, 3]},
        ],
        "combination": "one-set-satisfies",
    }
    assert source["root_replacement"] == {
        "operator_recovery": [2, 3],
        "development_registry": [1, 1],
        "independent_witnesses": [2, 3],
        "all_sets_required": True,
        "compromised_or_terminal_root_may_sign": False,
        "missing_continuity": "lineage-breaking-recovery-only",
    }
    assert source["privacy_opening"] == {
        "authority": "CONFLICT_RESOLUTION",
        "purpose": "GOVERNANCE",
        "threshold": [4, 5],
        "witness_threshold": [3, 5],
        "binds": ["commitment", "object_digest", "request_id", "recipient_operator_id", "expires_at"],
        "single_use": True,
        "failure_outcome": "REJECT",
        "failure_reason": "ERR_AUTHORITY",
        "audit_required": True,
    }


def test_core_collision_proof_covers_every_frozen_registry_namespace() -> None:
    proof = _load()["core_collision_proof"]
    assert proof["core_registries"] == {
        "protocol_versions": {"CORE_0_1": 1, "CORE_0_2": 2},
        "message_types": {"minimum": 1, "maximum": 17},
        "error_codes": {"minimum": 1, "maximum": 19},
        "object_types": "Core objects are selected by closed schema/context, not a numeric object registry",
    }
    assert proof["rule"] == "extension-local-values-are-never-core-values"


def test_revocation_authority_alternatives_are_unambiguous() -> None:
    matrix = _load()["signer_authority_matrix"]["TypedRevocationRecord"]
    assert matrix == {
        "alternatives": [
            {
                "name": "target-controller",
                "signer_sets": [{"authority": "TARGET_CONTROLLER", "purpose": "REVOCATION", "threshold": [1, 1]}],
                "constraints": ["same-target-scope"],
            },
            {
                "name": "normal-threshold",
                "signer_sets": [{"authority": "FEDERATION_AUTHORITY", "purpose": "REVOCATION", "threshold": [3, 5]}],
                "constraints": [],
            },
            {
                "name": "emergency-deny-only",
                "signer_sets": [{"authority": "FEDERATION_AUTHORITY", "purpose": "REVOCATION", "threshold": [2, 5]}],
                "constraints": ["deny-only", "cannot-add-or-expand-trust", "maximum-300-seconds"],
            },
        ],
        "combination": "exactly-one-alternative",
        "selection": {
            "mode_field": "revocation_authority_mode",
            "mode_is_signed": True,
            "validate_only_selected_alternative": True,
            "unknown_mode": "REJECT/ERR_UNSUPPORTED_CRITICAL",
        },
    }


def test_schema_requiredness_is_a_named_blocking_decision() -> None:
    source = _load()
    assert source["deferred_decisions"]["WP8-SCHEMA-REQUIREDNESS-01"] == {
        "status": "blocking",
        "blocks": ["Task 2", "Task 3", "Task 4", "Task 5", "Task 6"],
        "required_deliverable": "object-by-object genesis/update requiredness matrix and literal schema vectors",
        "task1_registry_modules_allowed": True,
        "object_codec_or_validator_allowed": False,
    }
