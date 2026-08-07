from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/protocol/registries/federation-v0.1-schema-proposal.json"
TABLE = ROOT / "docs/protocol/wp8-federation-v0.1-schema-allocation.md"
FIXTURES = ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json"
OBJECTS = (
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


def load_schema() -> dict[str, object]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_schema_proposal_covers_all_18_objects_without_runtime_authority() -> None:
    data = load_schema()
    assert data["status"] == "APPROVED DEVELOPMENT PROFILE PROPOSAL — REQUIRES HUMAN APPROVAL"
    assert data["runtime_implementation_authorized"] is False
    assert tuple(data["objects"]) == OBJECTS
    assert data["task2_ready_after_human_approval"] is True


def test_lifecycle_classes_are_complete_and_do_not_fake_proof_lineages() -> None:
    objects = load_schema()["objects"]
    expected = {
        "stateful-lineage": 8,
        "snapshot-state-summary": 1,
        "immutable-proof-evidence": 5,
        "decision-context": 4,
    }
    actual = {name: 0 for name in expected}
    for spec in objects.values():
        actual[spec["lifecycle_class"]] += 1
        rules = spec["lifecycle_rules"]
        assert set(rules) == {"genesis", "same_generation_update", "new_generation"}
    assert actual == expected
    for name in (
        "InclusionProof",
        "ConsistencyProof",
        "WitnessStatement",
        "FederationAuthorityProof",
        "ConflictEvidence",
    ):
        fields = {field["name"] for field in objects[name]["fields"]}
        assert not {"generation", "sequence", "previous_digest"} & fields


def test_every_field_has_unambiguous_requiredness_type_and_privacy() -> None:
    allowed_requiredness = {
        "required",
        "optional-critical",
        "optional-non-critical",
        "contextually-required",
        "contextually-forbidden",
    }
    allowed_privacy = {"public", "private", "scope-dependent"}
    for object_name, spec in load_schema()["objects"].items():
        assert spec["fields"], object_name
        keys: set[int] = set()
        for field in spec["fields"]:
            assert field["requiredness"] in allowed_requiredness
            assert field["wire_type"]
            assert field["bounds"]
            assert field["privacy"] in allowed_privacy
            assert isinstance(field["critical"], bool)
            for classification in (
                "immutable_after_genesis",
                "monotonic",
                "predecessor_linked",
                "authority_defining",
                "lifecycle_defining",
                "privacy_sensitive",
            ):
                assert isinstance(field[classification], bool)
            assert field["key"] not in keys
            keys.add(field["key"])


def test_key_namespaces_and_shared_field_semantics_are_closed() -> None:
    data = load_schema()
    assert data["key_model"] == {
        "common": [1, 31],
        "object_specific": [32, 127],
        "reserved": [128, 999],
        "extension_ids": [1000, 65535],
        "unknown_base_key": "reject",
        "direct_extension_key": "reject",
    }
    common = data["common_fields"]
    assert {entry["key"] for entry in common.values()} == set(range(1, 10)) | {31}
    for spec in data["objects"].values():
        for field in spec["fields"]:
            if field["key"] <= 31:
                assert common[field["name"]]["key"] == field["key"]
                assert common[field["name"]]["wire_type"] == field["wire_type"]
            else:
                assert 32 <= field["key"] <= 127


def test_composite_types_are_closed_bounded_and_canonically_ordered() -> None:
    composites = load_schema()["composite_types"]
    required = {
        "DelegationScope",
        "AuthorityTarget",
        "AuthorityReference",
        "TransparencyReference",
        "FederationDependencySet",
        "ExtensionEntry",
        "SignatureReference",
    }
    assert required <= set(composites)
    for name, composite in composites.items():
        assert composite["closed"] is True, name
        assert composite["duplicate_behavior"] == "reject", name
        assert composite["unknown_field_behavior"] == "reject", name
        assert composite["maximum_encoded_bytes"] > 0, name
        assert composite["canonical_ordering"], name


def test_recovery_substitution_is_explicit_and_fail_closed() -> None:
    data = load_schema()
    matrix = data["recovery_substitution"]
    assert set(matrix) == set(OBJECTS)
    assert data["recovery_default"] == "reject-unless-object-entry-allows"
    allowed = {name for name, rule in matrix.items() if rule["allowed"]}
    assert allowed == {
        "OperatorRegistryRecord",
        "KeyAuthorizationRecord",
        "NameOwnershipRecord",
        "DelegationRecord",
        "FederationTrustBundle",
        "OperatorEndpointRecord",
        "OperatorLifecycleRecord",
    }
    for name in allowed:
        rule = matrix[name]
        assert rule["required_lifecycle"] == "RECOVERY"
        assert rule["transition_binding_required"] is True
        assert rule["strictly_higher_generation"] is True
        assert rule["scope_change"] == "restore-or-narrow-only"
        assert rule["compromised_signer_forbidden"] is True


def test_task2_schemas_are_complete() -> None:
    objects = load_schema()["objects"]
    expected_fields = {
        "OperatorRegistryRecord": {
            "object_type",
            "object_version",
            "issuer_id",
            "generation",
            "sequence",
            "not_before",
            "expires_at",
            "previous_digest",
            "extensions",
            "operator_id",
            "identity_root",
            "organization_binding",
            "federation_scope",
            "lifecycle_state",
            "revocation_reference",
            "transparency_reference",
            "recovery_stage",
        },
        "KeyAuthorizationRecord": {
            "object_type",
            "object_version",
            "issuer_id",
            "generation",
            "sequence",
            "not_before",
            "expires_at",
            "previous_digest",
            "extensions",
            "operator_id",
            "key_id",
            "public_key",
            "key_purpose",
            "key_lifecycle",
            "authorizing_authority",
            "revocation_state",
            "revocation_reference",
            "recovery_transition_digest",
        },
    }
    for name, expected in expected_fields.items():
        spec = objects[name]
        assert {field["name"] for field in spec["fields"]} == expected
        assert spec["signer_rule"]["kid_binding"] == "protected-kid-resolves-exactly-one-authorized-key"
        assert spec["forbidden_fields"]
        assert spec["lifecycle_rules"]["genesis"]["allowed"] is True
        assert spec["maximum_canonical_payload_bytes"] <= 65_536
        assert spec["maximum_signed_object_bytes"] == 65_536
        assert spec["allowed_state_transitions"]


def test_service_id_and_recovery_fixture_match_selected_semantics() -> None:
    package = json.loads(FIXTURES.read_text(encoding="utf-8"))
    operator_genesis = next(item for item in package["fixtures"] if item["name"] == "valid-genesis")
    recovery = next(item for item in package["fixtures"] if item["name"] == "valid-recovery-authorized-new-generation")
    assert operator_genesis["semantic_assertions"]["service_id"] == ("5e7bc609762ba3451f4b46417fe1c46132e17ebb6d4a0a6ee295d4f815f0b1aa")
    assert recovery["semantic_assertions"] == {
        "key_id_changed_at_new_generation": True,
        "public_key_changed_at_new_generation": True,
        "key_lifecycle": "NEXT",
    }
    key_fields = {field["name"]: field for field in load_schema()["objects"]["KeyAuthorizationRecord"]["fields"]}
    assert key_fields["key_id"]["immutable_after_genesis"] is False
    assert key_fields["public_key"]["immutable_after_genesis"] is False
    assert {"key_id", "public_key"} <= set(load_schema()["objects"]["KeyAuthorizationRecord"]["new_generation_change_fields"])


def test_threshold_references_bind_distinct_signers_and_exact_payload() -> None:
    data = load_schema()
    signature = data["composite_types"]["SignatureReference"]
    assert signature["fields"] == {
        "1": "authority_class:uint",
        "2": "key_purpose:uint",
        "3": "kid:bstr(1..64)",
        "4": "cose_sign1_digest:bstr32",
        "5": "signed_payload_digest:bstr32",
    }
    threshold = data["signature_threshold_rules"]
    assert threshold["distinct_kid_per_set"] is True
    assert threshold["distinct_authority_identity_per_set"] is True
    assert threshold["signer_reuse_across_sets"] == "reject"
    assert threshold["signed_payload_digest"] == "must-equal-object-payload-digest"
    assert threshold["evaluation"] == "count-valid-distinct-authorities-not-array-items"


def test_checkpoint_and_consistency_literal_continuity_inventory() -> None:
    package = json.loads(FIXTURES.read_text(encoding="utf-8"))
    names = {(item["object_type"], item["name"]) for item in package["fixtures"]}
    assert {
        ("TransparencyCheckpoint", "valid-genesis-checkpoint"),
        ("TransparencyCheckpoint", "invalid-generation-reset-without-transition"),
        ("ConsistencyProof", "valid-checkpoint-continuity"),
        ("ConsistencyProof", "invalid-old-new-checkpoint-mismatch"),
    } <= names


def test_independent_literal_verifier_accepts_package() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_federation_schema_fixtures.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "independently verified" in result.stdout


def test_operator_registry_recovery_stage_is_contextual() -> None:
    fields = {field["name"]: field for field in load_schema()["objects"]["OperatorRegistryRecord"]["fields"]}
    recovery_stage = fields["recovery_stage"]
    assert recovery_stage["requiredness"] == "contextually-required"
    assert recovery_stage["genesis"] == "required iff lifecycle_state=RECOVERY; forbidden otherwise"
    assert recovery_stage["update"] == "required iff lifecycle_state=RECOVERY; forbidden otherwise"


def test_operator_registry_transitions_exactly_reuse_task1_authority() -> None:
    task1 = json.loads((ROOT / "docs/protocol/registries/federation-v0.1-development.json").read_text(encoding="utf-8"))
    proposed = load_schema()["objects"]["OperatorRegistryRecord"]
    assert proposed["allowed_state_transitions"] == task1["operator_lifecycle_semantics"]["allowed_transitions"]


def test_recovery_stage_negative_literal_inventory() -> None:
    package = json.loads(FIXTURES.read_text(encoding="utf-8"))
    names = {item["name"] for item in package["fixtures"] if item["object_type"] == "OperatorRegistryRecord"}
    assert {
        "missing-recovery-stage",
        "recovery-stage-outside-recovery",
    } <= names


def test_independent_verifier_rejects_relabeled_consistency_fixture(
    tmp_path: Path,
) -> None:
    package = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = next(item for item in package["fixtures"] if item["name"] == "valid-checkpoint-continuity")
    fixture["expected_outcome"] = "REJECT"
    fixture["reason"] = "ERR_CONTINUITY"
    tampered = tmp_path / "literal-fixtures.json"
    tampered.write_text(json.dumps(package), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_federation_schema_fixtures.py",
            "--fixtures",
            str(tampered),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "expected outcome" in result.stdout + result.stderr


def test_literal_task2_fixture_inventory_and_stored_bytes() -> None:
    package = json.loads(FIXTURES.read_text(encoding="utf-8"))
    approved_registry = json.loads((ROOT / "docs/protocol/registries/federation-v0.1-development.json").read_text(encoding="utf-8"))
    approved_reasons = {entry["name"] for entry in approved_registry["registries"]["reason_codes"]}
    expected = {"OperatorRegistryRecord": 13, "KeyAuthorizationRecord": 11}
    assert package["status"] == "APPROVED DEVELOPMENT PROFILE PROPOSAL — REQUIRES HUMAN APPROVAL"
    assert package["generated_by_future_runtime"] is False
    for object_name, count in expected.items():
        fixtures = [f for f in package["fixtures"] if f["object_type"] == object_name]
        assert len(fixtures) == count
        assert len({f["name"] for f in fixtures}) == count
        for fixture in fixtures:
            raw = bytes.fromhex(fixture["canonical_cbor_hex"])
            assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
            assert fixture["expected_outcome"] in {"ACCEPT", "REJECT", "QUARANTINE"}
            assert fixture["reason"] in approved_reasons
            assert isinstance(fixture["state_changed"], bool)


def test_machine_source_markdown_and_fixture_render_are_exact() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/render_federation_schema.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert TABLE.is_file()
