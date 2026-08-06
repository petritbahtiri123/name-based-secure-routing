import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/protocol/registries/federation-v0.1-development.json"
AMENDMENT = ROOT / "docs/protocol/wp8-federation-v0.1-registry-allocation.md"


EXPECTED_MESSAGES = [
    "FED_CAPABILITIES",
    "FED_CAPABILITIES_ACK",
    "OPERATOR_RECORD_QUERY",
    "OPERATOR_RECORD_RESPONSE",
    "ENDPOINT_RECORD_QUERY",
    "ENDPOINT_RECORD_RESPONSE",
    "OWNERSHIP_AUTHORITY_QUERY",
    "OWNERSHIP_AUTHORITY_RESPONSE",
    "AUTHORITY_PROOF_QUERY",
    "AUTHORITY_PROOF_RESPONSE",
    "TRUST_BUNDLE_REQUEST",
    "TRUST_BUNDLE_RESPONSE",
    "TRUST_BUNDLE_UPDATE",
    "TRUST_BUNDLE_ACK",
    "CHECKPOINT_QUERY",
    "CHECKPOINT_RESPONSE",
    "INCLUSION_PROOF_REQUEST",
    "INCLUSION_PROOF_RESPONSE",
    "CONSISTENCY_PROOF_REQUEST",
    "CONSISTENCY_PROOF_RESPONSE",
    "WITNESS_STATEMENT",
    "AUTHORIZATION_REQUEST",
    "AUTHORIZATION_RESPONSE",
    "REVOCATION_PUSH",
    "REVOCATION_ACK",
    "REVOCATION_QUERY",
    "REVOCATION_RESPONSE",
    "CONFLICT_REPORT",
    "CONFLICT_ACK",
    "OPERATOR_STATUS_QUERY",
    "OPERATOR_STATUS_RESPONSE",
    "QUARANTINE_NOTICE",
    "RECOVERY_NOTICE",
    "REENTRY_EVIDENCE",
    "OPERATOR_REGISTRATION_REQUEST",
    "OPERATOR_REGISTRATION_RESPONSE",
    "OPERATOR_RECORD_UPDATE",
    "OPERATOR_RECORD_UPDATE_ACK",
    "KEY_AUTHORIZATION_PUBLISH",
    "KEY_AUTHORIZATION_ACK",
    "KEY_AUTHORIZATION_UPDATE",
    "KEY_AUTHORIZATION_UPDATE_ACK",
    "NAME_OWNERSHIP_PUBLISH",
    "NAME_OWNERSHIP_ACK",
    "NAME_OWNERSHIP_UPDATE",
    "NAME_OWNERSHIP_UPDATE_ACK",
    "DELEGATION_PUBLISH",
    "DELEGATION_ACK",
    "DELEGATION_UPDATE",
    "DELEGATION_UPDATE_ACK",
    "ENDPOINT_RECORD_PUBLISH",
    "ENDPOINT_RECORD_ACK",
    "ENDPOINT_RECORD_UPDATE",
    "ENDPOINT_RECORD_UPDATE_ACK",
    "CONFLICT_RESOLUTION_PUBLISH",
    "CONFLICT_RESOLUTION_ACK",
    "APPEAL_REQUEST",
    "APPEAL_RESPONSE",
]

EXPECTED_OPERATOR_LIFECYCLES = [
    "APPLIED",
    "VERIFICATION_PENDING",
    "VERIFIED",
    "PROVISIONAL",
    "ACTIVE",
    "SUSPENDED",
    "QUARANTINED",
    "RECOVERY",
    "RETIRED",
    "TERMINALLY_REVOKED",
    "REJECTED",
]

EXPECTED_RECOVERY_STAGES = [
    "RECOVERY_PENDING",
    "RECOVERY_VERIFIED",
    "REENTRY_RESTRICTED",
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
    assert [entry["value"] for entry in source["registries"]["message_types"]] == list(range(0x4000, 0x4000 + len(EXPECTED_MESSAGES)))
    assert [entry["name"] for entry in source["registries"]["object_types"]] == EXPECTED_OBJECTS
    assert [entry["value"] for entry in source["registries"]["object_types"]] == list(range(1, 19))


def test_operator_lifecycle_is_the_exact_approved_top_level_model() -> None:
    entries = _load()["registries"]["operator_lifecycles"]
    assert [entry["name"] for entry in entries] == EXPECTED_OPERATOR_LIFECYCLES
    assert [entry["value"] for entry in entries] == list(range(1, 12))
    assert not {"RESTRICTED", "RECOVERY_PENDING", "REENTRY_PENDING"} & {entry["name"] for entry in entries}


def test_recovery_stages_are_canonical_and_contextually_required() -> None:
    source = _load()
    entries = source["registries"]["recovery_stages"]
    assert [entry["name"] for entry in entries] == EXPECTED_RECOVERY_STAGES
    assert [entry["value"] for entry in entries] == [1, 2, 3]
    assert source["contextual_rules"]["recovery_stage"] == {
        "required_when": {"operator_lifecycle": "RECOVERY"},
        "forbidden_otherwise": True,
        "normal_active_transition_from": "REENTRY_RESTRICTED",
        "active_gate_requires": [
            "peer_synchronization",
            "compatible_checkpoints",
            "current_revocations",
            "monitoring_complete",
            "readiness_approved",
        ],
    }
    workflow = source["local_workflow_states"]["recovery"]
    assert workflow["wire_registry"] is False
    assert workflow["states"] == [
        "REQUESTED",
        "EVIDENCE_VERIFIED",
        "APPROVED",
        "ACTIVATED",
        "REENTRY_MONITORING",
        "COMPLETE",
        "REJECTED",
    ]
    assert not set(workflow["states"]) & {entry["name"] for entry in entries}


def test_lifecycle_authority_and_monotonic_semantics_are_explicit() -> None:
    rules = _load()["operator_lifecycle_semantics"]
    assert rules["REJECTED"]["authority"] == "none"
    assert rules["PROVISIONAL"]["authority"] == "bounded-pilot-only"
    assert rules["RECOVERY"]["requires_recovery_stage"] is True
    assert rules["monotonic"] is True
    assert rules["monotonic_dimension"] == "identity-generation-and-record-sequence"
    assert rules["lifecycle_values_are_ranked"] is False
    assert rules["unknown_or_invalid_transition"] == "REJECT/ERR_CONTINUITY/no-mutation"
    assert rules["same_state_update"] == "allowed-only-with-higher-sequence-and-valid-continuity"
    assert rules["allowed_transitions"] == {
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
    }
    assert rules["recovery_stage_transitions"] == {
        "entry_stage": "RECOVERY_PENDING",
        "RECOVERY_PENDING": ["RECOVERY_VERIFIED"],
        "RECOVERY_VERIFIED": ["REENTRY_RESTRICTED"],
        "REENTRY_RESTRICTED": ["ACTIVE"],
        "skip_or_rollback": "REJECT/ERR_CONTINUITY/no-mutation",
    }


def test_message_registry_is_semantic_not_count_driven() -> None:
    source = _load()
    assert source["message_registry_policy"]["allocation_basis"] == "semantic-requirements"
    assert source["message_registry_policy"]["target_count"] is None
    assert source["message_registry_policy"]["derived_count"] == len(EXPECTED_MESSAGES)
    assert len(EXPECTED_MESSAGES) != 34


def test_every_message_has_complete_behavioral_metadata() -> None:
    source = _load()
    messages = source["registries"]["message_types"]
    semantics = source["message_semantics"]
    assert set(semantics) == {entry["name"] for entry in messages}
    required = {
        "family",
        "why",
        "senders",
        "receivers",
        "class",
        "replay_context",
        "state_mutation",
        "idempotency",
        "allowed_protocol_state",
        "object_type",
        "authority_effect",
    }
    for name, metadata in semantics.items():
        assert set(metadata) == required, name
        assert metadata["senders"] and metadata["receivers"]


def test_capability_agreement_is_post_core_and_cannot_negotiate_core_versions() -> None:
    semantics = _load()["message_semantics"]
    for name in ("FED_CAPABILITIES", "FED_CAPABILITIES_ACK"):
        message = semantics[name]
        assert message["allowed_protocol_state"] == "core-v2-selected-peer-authenticated"
        assert message["replay_context"] == "authenticated-session-transcript"
        assert "core_versions" not in message
        assert "Core version" not in message["why"]
        assert message["state_mutation"] == "federation-capability-state-only"


def test_distinct_ack_push_query_notice_and_update_semantics_remain_distinct() -> None:
    semantics = _load()["message_semantics"]
    assert {semantics[name]["class"] for name in ("REVOCATION_PUSH", "REVOCATION_ACK", "REVOCATION_QUERY", "REVOCATION_RESPONSE")} == {
        "push",
        "ack",
        "query",
        "response",
    }
    assert semantics["TRUST_BUNDLE_UPDATE"]["class"] == "update"
    assert semantics["TRUST_BUNDLE_ACK"]["class"] == "ack"
    for notice in ("QUARANTINE_NOTICE", "RECOVERY_NOTICE"):
        assert semantics[notice]["class"] == "notice"
        assert semantics[notice]["authority_effect"] == "none-by-delivery"
    assert semantics["TRUST_BUNDLE_ACK"]["authority_effect"] == "delivery-and-exact-processing-result-only"


def test_lifecycle_messages_have_exact_contextual_state_gates() -> None:
    semantics = _load()["message_semantics"]
    assert semantics["QUARANTINE_NOTICE"]["allowed_protocol_state"] == ("operator-lifecycle=QUARANTINED")
    assert semantics["RECOVERY_NOTICE"]["allowed_protocol_state"] == (
        "operator-lifecycle=RECOVERY;recovery-stage=RECOVERY_PENDING-or-RECOVERY_VERIFIED"
    )
    assert semantics["REENTRY_EVIDENCE"]["allowed_protocol_state"] == ("operator-lifecycle=RECOVERY;recovery-stage=REENTRY_RESTRICTED")


def test_message_allocations_remain_extension_local_and_core_disjoint() -> None:
    source = _load()
    values = [entry["value"] for entry in source["registries"]["message_types"]]
    assert min(values) == 0x4000
    assert not set(values) & set(source["core_collision_proof"]["core_message_values"])
    assert source["core_collision_proof"]["federation_message_range"] == [min(values), max(values)]


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
    message_values = [entry["value"] for entry in source["registries"]["message_types"]]
    assert source["reserved_ranges"]["message_types"] == [[max(message_values) + 1, 0x40FF]]
    assert source["reserved_ranges"]["object_types"] == [[19, 255]]
    assert source["reserved_ranges"]["reason_codes"] == [[32, 255]]


def test_registry_amendment_tables_exactly_match_machine_source() -> None:
    source = _load()
    document = AMENDMENT.read_text(encoding="utf-8")
    for registry, entries in source["registries"].items():
        assert f"<!-- registry:{registry} -->" in document
        for entry in entries:
            assert f"| {entry['value']} | `{entry['name']}` |" in document


def test_registry_renderer_check_mode_detects_drift() -> None:
    original = AMENDMENT.read_text(encoding="utf-8")
    try:
        AMENDMENT.write_text(original + "drift\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "scripts/render_federation_registry.py", "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr == "registry-render-drift\n"
    finally:
        AMENDMENT.write_text(original, encoding="utf-8")


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


def test_historical_source_closes_task1_source_blocker() -> None:
    source = _load()
    assert source["deferred_decisions"]["WP8-NORMATIVE-SOURCE-01"] == {
        "status": "closed",
        "resolution": "exact-digest-pinned-historical-source-checked-in",
        "source_manifest": "docs/protocol/registries/wp8-planning-sources.json",
        "current_decision_index_complete_source": False,
        "clean_room_source_input_allowed": True,
        "clean_room_implementation_allowed": False,
        "implementation_blocked_by": "WP8-SCHEMA-REQUIREDNESS-01-and-later-task-gates",
        "task1_after_human_approval": True,
    }
