from enum import IntEnum
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import nbsr.federation as federation
from nbsr.federation.registry import (
    AuthorityClass,
    CapabilityId,
    DecisionOutcome,
    EnforcementMode,
    ExtensionId,
    KeyLifecycle,
    KeyPurpose,
    MessageType,
    ObjectType,
    OperatorLifecycle,
    ReasonCode,
    RecoveryStage,
    ResultType,
    CONTEXTUAL_RULES,
    CORE_COLLISION_PROOF,
    LOCAL_WORKFLOW_STATES,
    MESSAGE_REGISTRY_POLICY,
    MESSAGE_SEMANTICS,
    OPERATOR_LIFECYCLE_SEMANTICS,
    PRIVACY_OPENING,
    REGISTRY_SOURCE_SHA256,
    RESERVED_RANGES,
    ROOT_REPLACEMENT,
    SIGNER_AUTHORITY_MATRIX,
    UNKNOWN_VALUE_POLICY,
)
from nbsr.protocol.registry import MessageType as CoreMessageType


ROOT = Path(__file__).resolve().parents[2]


EXPECTED_REGISTRIES = {
    ExtensionId: (("FEDERATION", 1),),
    CapabilityId: (
        ("FEDERATION_OBJECTS", 1),
        ("FEDERATION_AUTHORIZATION", 2),
        ("TRANSPARENCY_PROOFS", 3),
        ("STATIC_TRUST_COMPATIBILITY", 4),
        ("FEDERATION_CONTEXT_BINDING", 5),
        ("THRESHOLD_EVIDENCE", 6),
    ),
    ObjectType: (
        ("OperatorRegistryRecord", 1),
        ("KeyAuthorizationRecord", 2),
        ("NameOwnershipRecord", 3),
        ("DelegationRecord", 4),
        ("FederationTrustBundle", 5),
        ("TransparencyCheckpoint", 6),
        ("InclusionProof", 7),
        ("ConsistencyProof", 8),
        ("WitnessStatement", 9),
        ("OperatorEndpointRecord", 10),
        ("FederationAuthorityProof", 11),
        ("FederationAuthorizationContext", 12),
        ("TypedRevocationRecord", 13),
        ("ConflictEvidence", 14),
        ("OperatorLifecycleRecord", 15),
        ("RecoveryTransitionRecord", 16),
        ("ConflictResolutionRecord", 17),
        ("AppealDecisionRecord", 18),
    ),
    MessageType: (
        ("FED_CAPABILITIES", 16_384),
        ("FED_CAPABILITIES_ACK", 16_385),
        ("OPERATOR_RECORD_QUERY", 16_386),
        ("OPERATOR_RECORD_RESPONSE", 16_387),
        ("ENDPOINT_RECORD_QUERY", 16_388),
        ("ENDPOINT_RECORD_RESPONSE", 16_389),
        ("OWNERSHIP_AUTHORITY_QUERY", 16_390),
        ("OWNERSHIP_AUTHORITY_RESPONSE", 16_391),
        ("AUTHORITY_PROOF_QUERY", 16_392),
        ("AUTHORITY_PROOF_RESPONSE", 16_393),
        ("TRUST_BUNDLE_REQUEST", 16_394),
        ("TRUST_BUNDLE_RESPONSE", 16_395),
        ("TRUST_BUNDLE_UPDATE", 16_396),
        ("TRUST_BUNDLE_ACK", 16_397),
        ("CHECKPOINT_QUERY", 16_398),
        ("CHECKPOINT_RESPONSE", 16_399),
        ("INCLUSION_PROOF_REQUEST", 16_400),
        ("INCLUSION_PROOF_RESPONSE", 16_401),
        ("CONSISTENCY_PROOF_REQUEST", 16_402),
        ("CONSISTENCY_PROOF_RESPONSE", 16_403),
        ("WITNESS_STATEMENT", 16_404),
        ("AUTHORIZATION_REQUEST", 16_405),
        ("AUTHORIZATION_RESPONSE", 16_406),
        ("REVOCATION_PUSH", 16_407),
        ("REVOCATION_ACK", 16_408),
        ("REVOCATION_QUERY", 16_409),
        ("REVOCATION_RESPONSE", 16_410),
        ("CONFLICT_REPORT", 16_411),
        ("CONFLICT_ACK", 16_412),
        ("OPERATOR_STATUS_QUERY", 16_413),
        ("OPERATOR_STATUS_RESPONSE", 16_414),
        ("QUARANTINE_NOTICE", 16_415),
        ("RECOVERY_NOTICE", 16_416),
        ("REENTRY_EVIDENCE", 16_417),
        ("OPERATOR_REGISTRATION_REQUEST", 16_418),
        ("OPERATOR_REGISTRATION_RESPONSE", 16_419),
        ("OPERATOR_RECORD_UPDATE", 16_420),
        ("OPERATOR_RECORD_UPDATE_ACK", 16_421),
        ("KEY_AUTHORIZATION_PUBLISH", 16_422),
        ("KEY_AUTHORIZATION_ACK", 16_423),
        ("KEY_AUTHORIZATION_UPDATE", 16_424),
        ("KEY_AUTHORIZATION_UPDATE_ACK", 16_425),
        ("NAME_OWNERSHIP_PUBLISH", 16_426),
        ("NAME_OWNERSHIP_ACK", 16_427),
        ("NAME_OWNERSHIP_UPDATE", 16_428),
        ("NAME_OWNERSHIP_UPDATE_ACK", 16_429),
        ("DELEGATION_PUBLISH", 16_430),
        ("DELEGATION_ACK", 16_431),
        ("DELEGATION_UPDATE", 16_432),
        ("DELEGATION_UPDATE_ACK", 16_433),
        ("ENDPOINT_RECORD_PUBLISH", 16_434),
        ("ENDPOINT_RECORD_ACK", 16_435),
        ("ENDPOINT_RECORD_UPDATE", 16_436),
        ("ENDPOINT_RECORD_UPDATE_ACK", 16_437),
        ("CONFLICT_RESOLUTION_PUBLISH", 16_438),
        ("CONFLICT_RESOLUTION_ACK", 16_439),
        ("APPEAL_REQUEST", 16_440),
        ("APPEAL_RESPONSE", 16_441),
    ),
    ReasonCode: (
        ("NONE", 0),
        ("ERR_RESOURCE_LIMIT", 1),
        ("ERR_PARSE", 2),
        ("ERR_NON_CANONICAL", 3),
        ("ERR_UNSUPPORTED_CRITICAL", 4),
        ("ERR_CRYPTO_PROFILE", 5),
        ("ERR_SIGNATURE_INVALID", 6),
        ("ERR_IDENTITY", 7),
        ("ERR_KEY_PURPOSE", 8),
        ("ERR_KEY_LIFECYCLE", 9),
        ("ERR_SCHEMA", 10),
        ("ERR_VERSION", 11),
        ("ERR_AUTHORITY", 12),
        ("ERR_SCOPE", 13),
        ("ERR_POLICY_EXPANSION", 14),
        ("ERR_ROLLBACK", 15),
        ("ERR_REPLAY", 16),
        ("ERR_EQUIVOCATION", 17),
        ("ERR_CONTINUITY", 18),
        ("ERR_REVOKED", 19),
        ("ERR_TERMINAL_STATE", 20),
        ("ERR_TRANSPARENCY", 21),
        ("ERR_CHECKPOINT", 22),
        ("ERR_SPLIT_VIEW", 23),
        ("ERR_WITNESS_THRESHOLD", 24),
        ("ERR_FRESHNESS", 25),
        ("ERR_EVIDENCE_MISSING", 26),
        ("ERR_OUTAGE_POLICY", 27),
        ("ERR_DOWNGRADE", 28),
        ("ERR_LOCAL_POLICY", 29),
        ("ERR_RECOVERY_INVALID", 30),
        ("ERR_INTERNAL", 31),
    ),
    KeyPurpose: (
        ("IDENTITY_ROOT", 1),
        ("RECOVERY", 2),
        ("REGISTRY_SIGNING", 3),
        ("KEY_AUTHORIZATION", 4),
        ("NAME_OWNERSHIP", 5),
        ("DELEGATION", 6),
        ("TRUST_BUNDLE", 7),
        ("TRANSPARENCY_LOG", 8),
        ("WITNESS", 9),
        ("ENDPOINT_DISCOVERY", 10),
        ("FEDERATION_AUTHORIZATION", 11),
        ("REVOCATION", 12),
        ("GOVERNANCE", 13),
        ("FEDERATION_TRANSPORT", 14),
        ("ACP_RESULT_SIGNING", 15),
    ),
    KeyLifecycle: (("NEXT", 1), ("ACTIVE", 2), ("RETIRING", 3), ("RETIRED", 4), ("REVOKED", 5)),
    OperatorLifecycle: (
        ("APPLIED", 1),
        ("VERIFICATION_PENDING", 2),
        ("VERIFIED", 3),
        ("PROVISIONAL", 4),
        ("ACTIVE", 5),
        ("SUSPENDED", 6),
        ("QUARANTINED", 7),
        ("RECOVERY", 8),
        ("RETIRED", 9),
        ("TERMINALLY_REVOKED", 10),
        ("REJECTED", 11),
    ),
    RecoveryStage: (("RECOVERY_PENDING", 1), ("RECOVERY_VERIFIED", 2), ("REENTRY_RESTRICTED", 3)),
    ResultType: (
        ("VALIDATION", 1),
        ("PUBLICATION", 2),
        ("QUERY", 3),
        ("AUTHORIZATION", 4),
        ("LIFECYCLE", 5),
        ("RECOVERY", 6),
        ("CONFLICT", 7),
        ("APPEAL", 8),
    ),
    DecisionOutcome: (("ACCEPT", 1), ("REJECT", 2), ("PENDING", 3), ("RESTRICTED", 4), ("QUARANTINE", 5)),
    EnforcementMode: (("NONE", 0), ("DENY_NEW_USE", 1), ("REAUTHENTICATE", 2), ("DRAIN", 3), ("TERMINATE_ACTIVE_USE", 4)),
    AuthorityClass: (
        ("OPERATOR_IDENTITY_ROOT", 1),
        ("OPERATOR_RECOVERY", 2),
        ("DEVELOPMENT_REGISTRAR", 3),
        ("FEDERATION_AUTHORITY", 4),
        ("TRANSPARENCY_LOG", 5),
        ("WITNESS", 6),
        ("NAME_OWNER", 7),
        ("DELEGATE", 8),
        ("SOURCE_OPERATOR", 9),
        ("DESTINATION_OPERATOR", 10),
        ("CONFLICT_RESOLUTION", 11),
        ("APPEAL", 12),
        ("OPERATOR_ENDPOINT", 13),
        ("TARGET_CONTROLLER", 14),
    ),
}


@pytest.mark.parametrize(("enum_type", "expected"), EXPECTED_REGISTRIES.items())
def test_registry_has_exact_approved_literal_order_and_values(enum_type: type[IntEnum], expected: tuple[tuple[str, int], ...]) -> None:
    assert tuple((item.name, item.value) for item in enum_type) == expected


def test_registries_are_closed_for_unknown_and_reserved_values() -> None:
    for enum_type, expected in EXPECTED_REGISTRIES.items():
        used = {value for _, value in expected}
        unknown = max(used) + 1
        while unknown in used:
            unknown += 1
        with pytest.raises(ValueError):
            enum_type(unknown)


def test_threshold_evidence_capability_is_new_and_collision_free() -> None:
    assert CapabilityId.THRESHOLD_EVIDENCE == 6
    assert tuple(item.value for item in CapabilityId) == (1, 2, 3, 4, 5, 6)
    assert len({item.value for item in CapabilityId}) == len(CapabilityId)


def test_key_purpose_includes_acp_result_signing_only_once() -> None:
    assert KeyPurpose.ACP_RESULT_SIGNING == 15
    assert tuple(item.value for item in KeyPurpose) == tuple(dict.fromkeys(item.value for item in KeyPurpose))


def test_federation_message_namespace_is_disjoint_from_frozen_core() -> None:
    assert not {item.value for item in MessageType} & {item.value for item in CoreMessageType}
    assert min(item.value for item in MessageType) == 0x4000
    assert len(MessageType) == 58


def test_obsolete_lifecycle_and_recovery_values_are_not_allocated() -> None:
    assert not {"RESTRICTED", "RECOVERY_PENDING", "REENTRY_PENDING"} & OperatorLifecycle.__members__.keys()
    assert tuple(RecoveryStage.__members__) == ("RECOVERY_PENDING", "RECOVERY_VERIFIED", "REENTRY_RESTRICTED")


def test_machine_registry_is_ratified_without_claiming_wire_freeze() -> None:
    source_path = ROOT / "docs/protocol/registries/federation-v0.1-development.json"
    payload = source_path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == REGISTRY_SOURCE_SHA256
    attributes = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", source_path.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert attributes == [
        "docs/protocol/registries/federation-v0.1-development.json: text: set",
        "docs/protocol/registries/federation-v0.1-development.json: eol: lf",
    ]
    source = json.loads(payload)
    assert source["status"] == "approved-development-profile"
    assert source["wire_freeze"] is False
    assert source["allocation_policy"] == (
        "All listed values are approved Development Profile allocations. "
        "None is a permanent Federation wire allocation until schemas and vectors are reviewed."
    )
    for entries in source["registries"].values():
        assert {entry["status"] for entry in entries} == {"approved-development-profile"}


def test_canonical_registry_metadata_is_complete_and_source_pinned() -> None:
    assert REGISTRY_SOURCE_SHA256 == "ed48559f233e8e78e90cf99c178f08a4e5f5b3892e37b3dc0d191ebd8b89e70c"
    assert len(MESSAGE_SEMANTICS) == 58
    assert len(SIGNER_AUTHORITY_MATRIX) == 18
    assert set(RESERVED_RANGES) == {
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
    assert MESSAGE_REGISTRY_POLICY == {
        "allocation_basis": "semantic-requirements",
        "target_count": None,
        "derived_count": 58,
        "namespace": "federation-extension-local",
    }


def test_canonical_message_and_authority_metadata_has_exact_approved_behavior() -> None:
    assert MESSAGE_SEMANTICS["FED_CAPABILITIES"] == {
        "family": "capability-agreement",
        "why": "Advertises compatible Federation extension/object/profile/capability/bound values after the selected authenticated Core context.",
        "senders": ("authenticated-federation-peer",),
        "receivers": ("authenticated-federation-peer",),
        "class": "offer",
        "replay_context": "authenticated-session-transcript",
        "state_mutation": "federation-capability-state-only",
        "idempotency": "same-replay-context-and-canonical-digest-same-result",
        "allowed_protocol_state": "core-v2-selected-peer-authenticated",
        "object_type": None,
        "authority_effect": "none",
    }
    assert SIGNER_AUTHORITY_MATRIX["OperatorRegistryRecord"] == {
        "signer_sets": (
            {"authority": "DEVELOPMENT_REGISTRAR", "purpose": "REGISTRY_SIGNING", "threshold": (1, 1)},
            {"authority": "WITNESS", "purpose": "WITNESS", "threshold": (2, 3)},
        ),
        "combination": "all-sets-required",
    }
    assert ROOT_REPLACEMENT == {
        "operator_recovery": (2, 3),
        "development_registry": (1, 1),
        "independent_witnesses": (2, 3),
        "all_sets_required": True,
        "compromised_or_terminal_root_may_sign": False,
        "missing_continuity": "lineage-breaking-recovery-only",
    }
    assert PRIVACY_OPENING["threshold"] == (4, 5)
    assert PRIVACY_OPENING["witness_threshold"] == (3, 5)
    assert PRIVACY_OPENING["single_use"] is True


def test_canonical_policy_tables_are_fail_closed_and_immutable() -> None:
    assert UNKNOWN_VALUE_POLICY["outcome"] == "REJECT"
    assert UNKNOWN_VALUE_POLICY["reason"] == "ERR_UNSUPPORTED_CRITICAL"
    assert UNKNOWN_VALUE_POLICY["state_changed"] is False
    assert CONTEXTUAL_RULES["recovery_stage"]["forbidden_otherwise"] is True
    assert LOCAL_WORKFLOW_STATES["recovery"]["wire_registry"] is False
    assert OPERATOR_LIFECYCLE_SEMANTICS["lifecycle_values_are_ranked"] is False
    assert CORE_COLLISION_PROOF["federation_message_range"] == (16_384, 16_441)
    with pytest.raises(TypeError):
        MESSAGE_SEMANTICS["FED_CAPABILITIES"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        MESSAGE_SEMANTICS["FED_CAPABILITIES"]["class"] = "changed"  # type: ignore[index]


def test_package_exports_all_canonical_registry_tables() -> None:
    for name in (
        "CONTEXTUAL_RULES",
        "CORE_COLLISION_PROOF",
        "LOCAL_WORKFLOW_STATES",
        "MESSAGE_REGISTRY_POLICY",
        "MESSAGE_SEMANTICS",
        "OPERATOR_LIFECYCLE_SEMANTICS",
        "PRIVACY_OPENING",
        "RESERVED_RANGES",
        "ROOT_REPLACEMENT",
        "SIGNER_AUTHORITY_MATRIX",
        "UNKNOWN_VALUE_POLICY",
    ):
        assert hasattr(federation, name), name


def test_federation_package_import_is_self_contained_without_repository_docs(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "nbsr", tmp_path / "nbsr")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", "from nbsr.federation import MESSAGE_SEMANTICS; print(len(MESSAGE_SEMANTICS))"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "58"
