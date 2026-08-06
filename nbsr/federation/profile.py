from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


class CoreBaselineError(ValueError):
    """Raised when the frozen Core v0.2 baseline inventory differs."""


@dataclass(frozen=True, slots=True)
class FederationProfile:
    required_core_version: ClassVar[int] = 2
    core_baseline_commit: ClassVar[str] = "b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914"
    core_v02_manifest_sha256: ClassVar[str] = "d4cc06347be4ce7d4f118c004130a1ac7ab9a7d5fda6de3354fbb26bf72a3eeb"
    core_v02_baseline_lock_sha256: ClassVar[str] = "21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef"
    extension_id: ClassVar[int] = 1
    extension_version: ClassVar[int] = 1
    name: ClassVar[str] = "nbsr-federation-dev-v1"
    static_profile: ClassVar[str] = "nbsr-static-trust-v1"
    cose_tag: ClassVar[int] = 18
    cose_algorithm: ClassVar[int] = -8
    cose_kid_min_bytes: ClassVar[int] = 1
    cose_kid_max_bytes: ClassVar[int] = 64
    external_aad: ClassVar[bytes] = b""
    signature_algorithm: ClassVar[str] = "Ed25519"
    hash_algorithm: ClassVar[str] = "SHA-256"
    operator_id_domain: ClassVar[bytes] = b"NBSR-FEDERATION-OPERATOR-ID-v1"
    operator_id_separator: ClassVar[bytes] = b"\x00"
    operator_id_algorithm_discriminator: ClassVar[int] = 1
    operator_id_genesis_key_bytes: ClassVar[int] = 32
    operator_id_bytes: ClassVar[int] = 32
    operator_id_text_hrp: ClassVar[str] = "nbsr"
    operator_id_text_length: ClassVar[int] = 63
    merkle_leaf_domain_separator: ClassVar[bytes] = b"\x00"
    merkle_node_domain_separator: ClassVar[bytes] = b"\x01"
    empty_tree_root: ClassVar[bytes] = bytes.fromhex("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    genesis_checkpoint_tree_size: ClassVar[int] = 0
    genesis_checkpoint_generation: ClassVar[int] = 1
    genesis_checkpoint_sequence: ClassVar[int] = 1
    genesis_checkpoint_predecessor: ClassVar[None] = None
    deterministic_vector_genesis_timestamp: ClassVar[int] = 0
    privacy_commitment_algorithm: ClassVar[str] = "HMAC-SHA-256"
    privacy_commitment_key_bytes: ClassVar[int] = 32
    privacy_commitment_domain: ClassVar[bytes] = b"NBSR-FEDERATION-PRIVACY-COMMITMENT-v1"
    privacy_commitment_separator: ClassVar[bytes] = b"\x00"
    privacy_commitment_has_public_salt: ClassVar[bool] = False
    privacy_commitment_key_single_use: ClassVar[bool] = True

    unsigned_counter_max: ClassVar[int] = 18_446_744_073_709_551_615
    timestamp_max: ClassVar[int] = 253_402_300_799
    max_object_bytes: ClassVar[int] = 65_536
    max_cbor_depth: ClassVar[int] = 16
    max_array_items: ClassVar[int] = 256
    max_map_pairs: ClassVar[int] = 128
    max_text_bytes: ClassVar[int] = 4_096
    max_byte_string_bytes: ClassVar[int] = 32_768
    digest_bytes: ClassVar[int] = 32
    ed25519_public_key_bytes: ClassVar[int] = 32
    ed25519_signature_bytes: ClassVar[int] = 64
    max_delegation_depth: ClassVar[int] = 8
    max_chain_objects: ClassVar[int] = 16
    max_graph_nodes: ClassVar[int] = 256
    max_graph_depth: ClassVar[int] = 16
    max_merkle_path: ClassVar[int] = 64
    max_bundle_keys: ClassVar[int] = 256
    max_bundle_authorities: ClassVar[int] = 32
    max_bundle_logs: ClassVar[int] = 32
    max_bundle_witnesses: ClassVar[int] = 32
    max_bundle_profiles: ClassVar[int] = 64
    max_bundle_revocation_sources: ClassVar[int] = 64
    max_vector_artifacts: ClassVar[int] = 4_096
    max_vector_scenarios: ClassVar[int] = 1_024
    max_scenario_steps: ClassVar[int] = 256

    clock_skew_seconds: ClassVar[int] = 300
    operational_key_lifetime_seconds: ClassVar[int] = 2_592_000
    key_overlap_min_seconds: ClassVar[int] = 3_600
    key_overlap_max_seconds: ClassVar[int] = 86_400
    checkpoint_interval_seconds: ClassVar[int] = 60
    emergency_checkpoint_deadline_seconds: ClassVar[int] = 30
    trust_freshness_seconds: ClassVar[int] = 300
    degraded_staleness_seconds: ClassVar[int] = 900
    cache_lifetime_seconds: ClassVar[int] = 300
    replay_retention_min_seconds: ClassVar[int] = 86_400
    terminal_tombstones_expire: ClassVar[bool] = False
    missing_evidence_timeout_seconds: ClassVar[int] = 30
    quarantine_reevaluation_seconds: ClassVar[int] = 300
    drain_ceiling_seconds: ClassVar[int] = 30
    static_recovery_warning_seconds: ClassVar[int] = 900
    static_recovery_expiry_seconds: ClassVar[int] = 3_600
    static_recovery_timer_auto_reset: ClassVar[bool] = False

    public_authority_threshold: ClassVar[tuple[int, int]] = (3, 5)
    public_witness_threshold: ClassVar[tuple[int, int]] = (2, 3)
    high_risk_authority_threshold: ClassVar[tuple[int, int]] = (4, 5)
    high_risk_witness_threshold: ClassVar[tuple[int, int]] = (3, 5)
    emergency_deny_threshold: ClassVar[tuple[int, int]] = (2, 5)
    registration_registrar_threshold: ClassVar[tuple[int, int]] = (1, 1)
    registration_witness_threshold: ClassVar[tuple[int, int]] = (2, 3)
    recovery_operator_threshold: ClassVar[tuple[int, int]] = (2, 3)
    recovery_registry_threshold: ClassVar[tuple[int, int]] = (1, 1)
    recovery_witness_threshold: ClassVar[tuple[int, int]] = (2, 3)
    private_lab_threshold: ClassVar[tuple[int, int]] = (1, 1)


def _files_for_scope(root: Path, scope: str) -> set[str]:
    path = root / scope
    if path.is_file():
        return {scope}
    if not path.is_dir():
        return set()
    return {item.relative_to(root).as_posix() for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts}


def assert_core_baseline(root: Path) -> None:
    root = root.resolve()
    lock_path = root / "docs/protocol/registries/core-v0.2-baseline-lock.json"
    try:
        lock_bytes = lock_path.read_bytes()
    except OSError as exc:
        raise CoreBaselineError("missing Core v0.2 baseline lock") from exc
    if hashlib.sha256(lock_bytes).hexdigest() != FederationProfile.core_v02_baseline_lock_sha256:
        raise CoreBaselineError("modified Core v0.2 baseline lock")

    try:
        lock = json.loads(lock_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreBaselineError("invalid Core v0.2 baseline lock") from exc
    if lock.get("baseline_commit") != FederationProfile.core_baseline_commit:
        raise CoreBaselineError("modified Core v0.2 baseline commit")
    artifacts = lock.get("artifacts")
    scopes = lock.get("scopes")
    if not isinstance(artifacts, dict) or not isinstance(scopes, list) or len(artifacts) != 110:
        raise CoreBaselineError("invalid Core v0.2 baseline inventory")

    expected_paths = set(artifacts)
    actual_paths = set().union(*(_files_for_scope(root, scope) for scope in scopes))
    missing = expected_paths - actual_paths
    if missing:
        raise CoreBaselineError(f"missing Core v0.2 baseline artifact: {min(missing)}")
    unlisted = actual_paths - expected_paths
    if unlisted:
        raise CoreBaselineError(f"unlisted Core v0.2 baseline artifact: {min(unlisted)}")

    for relative, expected in artifacts.items():
        payload = (root / relative).read_bytes()
        if len(payload) != expected["length"] or hashlib.sha256(payload).hexdigest() != expected["sha256"]:
            raise CoreBaselineError(f"modified Core v0.2 baseline artifact: {relative}")
