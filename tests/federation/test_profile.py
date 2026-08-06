from dataclasses import FrozenInstanceError

import pytest

from nbsr.federation.profile import FederationProfile


def test_development_profile_has_exact_approved_identity_and_crypto_constants() -> None:
    assert FederationProfile.required_core_version == 2
    assert FederationProfile.core_baseline_commit == "b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914"
    assert FederationProfile.core_v02_manifest_sha256 == "d4cc06347be4ce7d4f118c004130a1ac7ab9a7d5fda6de3354fbb26bf72a3eeb"
    assert FederationProfile.core_v02_baseline_lock_sha256 == "21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef"
    assert FederationProfile.extension_id == 1
    assert FederationProfile.extension_version == 1
    assert FederationProfile.name == "nbsr-federation-dev-v1"
    assert FederationProfile.static_profile == "nbsr-static-trust-v1"
    assert FederationProfile.cose_tag == 18
    assert FederationProfile.cose_algorithm == -8
    assert FederationProfile.cose_kid_min_bytes == 1
    assert FederationProfile.cose_kid_max_bytes == 64
    assert FederationProfile.external_aad == b""
    assert FederationProfile.signature_algorithm == "Ed25519"
    assert FederationProfile.hash_algorithm == "SHA-256"
    assert FederationProfile.operator_id_domain == b"NBSR-FEDERATION-OPERATOR-ID-v1"
    assert FederationProfile.operator_id_separator == b"\x00"
    assert FederationProfile.operator_id_algorithm_discriminator == 1
    assert FederationProfile.operator_id_genesis_key_bytes == 32
    assert FederationProfile.operator_id_bytes == 32
    assert FederationProfile.operator_id_text_hrp == "nbsr"
    assert FederationProfile.operator_id_text_length == 63
    assert FederationProfile.merkle_leaf_domain_separator == b"\x00"
    assert FederationProfile.merkle_node_domain_separator == b"\x01"
    assert FederationProfile.empty_tree_root == bytes.fromhex("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert FederationProfile.genesis_checkpoint_tree_size == 0
    assert FederationProfile.genesis_checkpoint_generation == 1
    assert FederationProfile.genesis_checkpoint_sequence == 1
    assert FederationProfile.genesis_checkpoint_predecessor is None
    assert FederationProfile.deterministic_vector_genesis_timestamp == 0
    assert FederationProfile.privacy_commitment_algorithm == "HMAC-SHA-256"
    assert FederationProfile.privacy_commitment_key_bytes == 32
    assert FederationProfile.privacy_commitment_domain == b"NBSR-FEDERATION-PRIVACY-COMMITMENT-v1"
    assert FederationProfile.privacy_commitment_separator == b"\x00"
    assert FederationProfile.privacy_commitment_has_public_salt is False
    assert FederationProfile.privacy_commitment_key_single_use is True


def test_development_profile_has_exact_approved_bounds() -> None:
    assert FederationProfile.unsigned_counter_max == 18_446_744_073_709_551_615
    assert FederationProfile.timestamp_max == 253_402_300_799
    assert FederationProfile.max_object_bytes == 65_536
    assert FederationProfile.max_cbor_depth == 16
    assert FederationProfile.max_array_items == 256
    assert FederationProfile.max_map_pairs == 128
    assert FederationProfile.max_text_bytes == 4_096
    assert FederationProfile.max_byte_string_bytes == 32_768
    assert FederationProfile.digest_bytes == 32
    assert FederationProfile.ed25519_public_key_bytes == 32
    assert FederationProfile.ed25519_signature_bytes == 64
    assert FederationProfile.max_delegation_depth == 8
    assert FederationProfile.max_chain_objects == 16
    assert FederationProfile.max_graph_nodes == 256
    assert FederationProfile.max_graph_depth == 16
    assert FederationProfile.max_merkle_path == 64
    assert FederationProfile.max_bundle_keys == 256
    assert FederationProfile.max_bundle_authorities == 32
    assert FederationProfile.max_bundle_logs == 32
    assert FederationProfile.max_bundle_witnesses == 32
    assert FederationProfile.max_bundle_profiles == 64
    assert FederationProfile.max_bundle_revocation_sources == 64
    assert FederationProfile.max_vector_artifacts == 4_096
    assert FederationProfile.max_vector_scenarios == 1_024
    assert FederationProfile.max_scenario_steps == 256


def test_development_profile_has_exact_approved_timing_and_thresholds() -> None:
    assert FederationProfile.clock_skew_seconds == 300
    assert FederationProfile.operational_key_lifetime_seconds == 2_592_000
    assert FederationProfile.key_overlap_min_seconds == 3_600
    assert FederationProfile.key_overlap_max_seconds == 86_400
    assert FederationProfile.checkpoint_interval_seconds == 60
    assert FederationProfile.emergency_checkpoint_deadline_seconds == 30
    assert FederationProfile.trust_freshness_seconds == 300
    assert FederationProfile.degraded_staleness_seconds == 900
    assert FederationProfile.cache_lifetime_seconds == 300
    assert FederationProfile.replay_retention_min_seconds == 86_400
    assert FederationProfile.terminal_tombstones_expire is False
    assert FederationProfile.missing_evidence_timeout_seconds == 30
    assert FederationProfile.quarantine_reevaluation_seconds == 300
    assert FederationProfile.drain_ceiling_seconds == 30
    assert FederationProfile.static_recovery_warning_seconds == 900
    assert FederationProfile.static_recovery_expiry_seconds == 3_600
    assert FederationProfile.static_recovery_timer_auto_reset is False
    assert FederationProfile.public_authority_threshold == (3, 5)
    assert FederationProfile.public_witness_threshold == (2, 3)
    assert FederationProfile.high_risk_authority_threshold == (4, 5)
    assert FederationProfile.high_risk_witness_threshold == (3, 5)
    assert FederationProfile.emergency_deny_threshold == (2, 5)
    assert FederationProfile.registration_registrar_threshold == (1, 1)
    assert FederationProfile.registration_witness_threshold == (2, 3)
    assert FederationProfile.recovery_operator_threshold == (2, 3)
    assert FederationProfile.recovery_registry_threshold == (1, 1)
    assert FederationProfile.recovery_witness_threshold == (2, 3)
    assert FederationProfile.private_lab_threshold == (1, 1)


def test_development_profile_is_immutable() -> None:
    profile = FederationProfile()
    with pytest.raises(FrozenInstanceError):
        profile.name = "changed"  # type: ignore[misc]
