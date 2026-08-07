from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from scripts.verify_federation_threshold_container_fixtures import verify_literal


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json"
FIXTURES = ROOT / "vectors/federation-v0.1-threshold-container/literal-fixtures.json"
RENDERER = ROOT / "scripts/render_federation_threshold_container.py"
VERIFIER = ROOT / "scripts/verify_federation_threshold_container_fixtures.py"


def _profile() -> dict[str, object]:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def _fixtures() -> dict[str, object]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_threshold_container_freezes_option_c_without_nineteenth_object() -> None:
    profile = _profile()
    assert profile["status"] == "proposed-requires-human-approval"
    assert profile["selected_model"] == "OPTION_C_NBSR_ENVELOPE_WITH_INDEPENDENT_COSE_SIGN1"
    assert profile["object_registry_impact"] == "none-evidence-container-not-authority-object"
    assert profile["container_id"] == "nbsr-federation-threshold-evidence-v1"
    assert profile["container_version"] == 1
    assert profile["required_capability"] == "FEDERATION_OBJECTS"


def test_threshold_schema_freezes_exact_keys_types_and_common_signature_input() -> None:
    profile = _profile()
    assert profile["container_fields"] == {
        "1": "container_version:uint=1",
        "2": "profile_id:tstr=nbsr-federation-dev-v1",
        "3": "target_object_class:uint:registered-object-type",
        "4": "payload_digest:bstr32:sha-256-canonical-target-payload",
        "5": "threshold_policy:ThresholdPolicy",
        "6": "authority_scope_digest:bstr32",
        "7": "lineage:LineageContext",
        "8": "authorization_context:AuthorizationContext",
        "9": "threshold_groups:[ThresholdGroup]",
        "10": "extensions:[ExtensionEntry]:optional",
    }
    assert profile["signer_entry_fields"] == {
        "1": "authority_class:uint:registered-authority-class",
        "2": "authority_id:bstr:1..64",
        "3": "key_purpose:uint:registered-key-purpose",
        "4": "kid:bstr:1..64",
        "5": "organization_id:bstr:1..64|null",
        "6": "signed_payload_digest:bstr32",
        "7": "cose_sign1:bstr:tagged-cose-sign1",
        "8": "extensions:[ExtensionEntry]:optional",
    }
    signature = profile["signature_input"]
    assert signature["cose_structure"] == "tagged-COSE_Sign1"
    assert signature["protected_headers"] == {"1": -8, "4": "entry.kid"}
    assert signature["unprotected_headers"] == {}
    assert signature["external_aad"] == "h''"
    assert signature["payload"] == "deterministic-CBOR-ThresholdSignatureContext"
    assert signature["domain"] == "NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1"


def test_policy_and_multi_group_rules_are_not_flattened() -> None:
    profile = _profile()
    policies = profile["named_policies"]
    assert policies["operator-recovery-v1"]["groups"] == [
        {"id": "recovery", "required": 2, "eligible": 3, "class": "OPERATOR_RECOVERY", "purpose": "RECOVERY"},
        {"id": "registry", "required": 1, "eligible": 1, "class": "DEVELOPMENT_REGISTRAR", "purpose": "REGISTRY_SIGNING"},
        {"id": "witness", "required": 2, "eligible": 3, "class": "WITNESS", "purpose": "WITNESS"},
    ]
    assert policies["ordinary-witness-v1"]["minimum_organizations"] == 2
    assert policies["high-risk-witness-v1"]["groups"][0]["required"] == 3
    assert policies["global-trust-v1"]["groups"][0]["required"] == 3
    assert policies["high-risk-global-root-v1"]["groups"][0]["required"] == 4
    assert policies["deny-only-emergency-v1"]["deny_only"] is True
    assert policies["deny-only-emergency-v1"]["groups"][0]["required"] == 2


def test_ordering_duplicates_partial_and_resource_limits_are_exact() -> None:
    profile = _profile()
    assert profile["signer_order"] == ["authority_class", "authority_id", "key_purpose", "kid"]
    assert profile["duplicate_rule"] == "reject-identical-ordering-tuple-or-authority-identity-within-group"
    assert profile["partial_collection"] == "pending-evidence-only-no-authority"
    assert profile["invalid_entry_rule"] == "reject-whole-container-even-if-remaining-signatures-satisfy-threshold"
    assert profile["activation_rule"] == "all-required-groups-valid"
    assert profile["resource_limits"] == {
        "max_threshold_groups": 4,
        "max_signatures_per_group": 5,
        "max_total_signer_entries": 16,
        "max_encoded_container_bytes": 65536,
        "max_authority_identity_bytes": 64,
        "max_organization_identity_bytes": 64,
        "max_kid_bytes": 64,
        "max_nested_depth": 8,
        "max_signature_verifications": 16,
    }


def test_literal_fixture_inventory_and_canonical_bytes() -> None:
    package = _fixtures()
    expected = {
        "valid-registrar-1-of-1",
        "valid-witness-2-of-3",
        "valid-global-trust-3-of-5",
        "valid-high-risk-trust-4-of-5",
        "valid-recovery-plus-registry-plus-witness",
        "valid-over-threshold",
        "valid-input-order-normalizes",
        "valid-high-risk-witness-3-of-5",
        "valid-deny-only-emergency-2-of-5",
        "valid-conflict-plus-witness",
        "valid-appeal-plus-witness",
        "pending-zero-signatures",
        "invalid-insufficient-threshold",
        "invalid-duplicate-signer",
        "invalid-same-organization-twice",
        "invalid-wrong-authority-class",
        "invalid-wrong-purpose",
        "invalid-bad-kid",
        "invalid-revoked-signer",
        "invalid-expired-signer",
        "invalid-wrong-payload-digest",
        "invalid-mixed-payload-digests",
        "invalid-wrong-generation",
        "invalid-wrong-scope",
        "invalid-wrong-action",
        "invalid-signature",
        "invalid-unsupported-critical-extension",
        "invalid-excessive-signer-count",
        "invalid-malformed-signer-entry",
        "invalid-replay-authorization-context",
        "invalid-unsupported-container-version",
        "invalid-wrong-group-order",
        "invalid-cross-group-signer-reuse",
        "invalid-ineligible-authority-id",
        "invalid-required-class-count",
        "invalid-group-scope-digest",
        "invalid-authorization-window",
        "invalid-deny-only-add-action",
        "invalid-excessive-group-count",
        "invalid-excessive-total-signers",
        "invalid-excessive-nested-depth",
        "invalid-policy-object-substitution",
        "invalid-policy-message-substitution",
        "invalid-missing-required-capability",
        "invalid-eligible-count-exceeded",
        "invalid-malformed-extension",
        "invalid-oversize-authority-id",
        "invalid-oversize-organization-id",
        "invalid-oversize-kid",
        "invalid-weakened-class-count",
        "invalid-weakened-organization-diversity",
        "invalid-self-selected-eligible-set",
        "invalid-noncanonical-cose-sign1",
        "invalid-unknown-policy-key",
        "invalid-unknown-group-requirement-key",
        "invalid-unknown-lineage-key",
        "invalid-unknown-authorization-key",
        "invalid-malformed-policy-extension",
        "invalid-malformed-group-extension",
        "invalid-malformed-authorization-context",
        "invalid-lineage-field-types",
        "invalid-short-request-id",
        "invalid-authorization-time-type",
        "invalid-authorization-window-order",
        "invalid-extension-version",
        "invalid-boolean-container-version",
        "invalid-boolean-policy-version",
        "invalid-nondict-signature-context",
        "valid-multiple-keys-one-authority-identity",
        "invalid-negative-not-before",
        "invalid-boolean-object-class",
        "invalid-boolean-required-count",
        "invalid-boolean-eligible-count",
        "invalid-boolean-minimum-organizations",
        "invalid-mixed-eligible-id-types",
        "invalid-empty-authority-id",
        "invalid-empty-kid",
        "invalid-empty-organization-id",
    }
    assert {fixture["name"] for fixture in package["fixtures"]} == expected
    for fixture in package["fixtures"]:
        raw = bytes.fromhex(fixture["canonical_cbor_hex"])
        assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
        assert encode_deterministic(decode_deterministic(raw)) == raw
        assert fixture["expected_decision"] in {"ACCEPT", "PENDING", "REJECT"}
        assert isinstance(fixture["expected_reason"], str)
        assert fixture["expected_mutation"] is False
        assert "accepted_authority_registry" in fixture["validation_context"]
        assert "authorities" not in fixture["validation_context"]


def test_resource_size_is_rejected_before_decode() -> None:
    observed = verify_literal(
        b"\x00" * 65_537,
        {},
        _profile(),
        decoder=lambda _: (_ for _ in ()).throw(AssertionError("decoder must not run")),
    )
    assert observed == ("REJECT", "ERR_RESOURCE_LIMIT", False)


def test_malformed_outer_cbor_fails_closed() -> None:
    for raw in (b"\xff", b"\x9f\xff"):
        assert verify_literal(raw, {}, _profile()) == ("REJECT", "ERR_PARSE", False)


def test_reverse_collector_order_has_identical_canonical_envelope() -> None:
    fixtures = {item["name"]: item for item in _fixtures()["fixtures"]}
    assert fixtures["valid-input-order-normalizes"]["canonical_cbor_hex"] == fixtures["valid-witness-2-of-3"]["canonical_cbor_hex"]
    assert fixtures["valid-input-order-normalizes"]["collector_input_order"] == "reverse-canonical-signer-order"


def test_policy_names_pin_object_message_effect_and_capability() -> None:
    profile = _profile()
    assert profile["named_policies"]["registrar-v1"] == {
        "deny_only": False,
        "minimum_organizations": 1,
        "allowed_object_classes": ["OperatorRegistryRecord"],
        "allowed_message_types": ["OPERATOR_REGISTRATION_REQUEST"],
        "allowed_authority_effects": ["grant"],
        "groups": [
            {
                "id": "registry",
                "required": 1,
                "eligible": 1,
                "class": "DEVELOPMENT_REGISTRAR",
                "purpose": "REGISTRY_SIGNING",
            }
        ],
    }
    assert profile["required_validation_context"] == [
        "negotiated_capabilities",
        "accepted_authority_registry",
        "expected_request_event_transition_id",
        "now",
    ]
    assert profile["authority_registry_invariant"] == "kid-and-public-key-resolve-to-exactly-one-authority-identity"


def test_independent_verifier_and_renderer_checks_pass() -> None:
    for script in (VERIFIER, RENDERER):
        completed = subprocess.run(
            [sys.executable, str(script), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
