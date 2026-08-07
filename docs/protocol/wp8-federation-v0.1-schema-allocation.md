# Federation v0.1 Schema Allocation Proposal

> **APPROVED DEVELOPMENT PROFILE PROPOSAL — REQUIRES HUMAN APPROVAL**

This table is generated from the proposal registry. It does not authorize runtime implementation before human approval.

## Common keys

| Key | Field | Wire type | Bounds |
|---:|---|---|---|
| 1 | `object_type` | `uint` | approved ObjectType value |
| 2 | `object_version` | `uint` | exactly 1 |
| 3 | `issuer_id` | `AuthorityReference` | one closed reference |
| 4 | `generation` | `uint` | 1..2^64-1 |
| 5 | `sequence` | `uint` | 1..2^64-1 |
| 6 | `not_before` | `uint` | 0..253402300799 |
| 7 | `expires_at` | `uint` | 0..253402300799 and greater than not_before |
| 8 | `previous_digest` | `bstr` | exactly 32 bytes |
| 9 | `effective_at` | `uint` | 0..253402300799 |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | 0..16 entries; IDs 1000..65535 |

## Object allocations

### OperatorRegistryRecord

Lifecycle: `stateful-lineage`. Durable registry authority and lifecycle state changes over time.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `operator_id` | `bstr` | required | required | required | public |
| 33 | `identity_root` | `AuthorityReference` | required | required | required | public |
| 34 | `organization_binding` | `OrganizationBinding` | required | required | required | scope-dependent |
| 35 | `federation_scope` | `DelegationScope` | required | required | required | public |
| 36 | `lifecycle_state` | `uint` | required | required | required | public |
| 37 | `revocation_reference` | `AuthorityTarget|null` | required | required | required | public |
| 38 | `transparency_reference` | `TransparencyReference` | required | required | required | public |
| 39 | `recovery_stage` | `uint` | contextually-required | required iff lifecycle_state=RECOVERY; forbidden otherwise | required iff lifecycle_state=RECOVERY; forbidden otherwise | public |

### KeyAuthorizationRecord

Lifecycle: `stateful-lineage`. Purpose-bound key authority rotates and recovers through durable continuity.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `operator_id` | `bstr` | required | required | required | public |
| 33 | `key_id` | `bstr` | required | required | required | public |
| 34 | `public_key` | `bstr` | required | required | required | public |
| 35 | `key_purpose` | `uint` | required | required | required | public |
| 36 | `key_lifecycle` | `uint` | required | required | required | public |
| 37 | `authorizing_authority` | `AuthorityReference` | required | required | required | public |
| 38 | `revocation_state` | `bool` | required | required | required | public |
| 39 | `revocation_reference` | `AuthorityTarget|null` | contextually-required | required | required | public |
| 40 | `recovery_transition_digest` | `bstr` | contextually-required | forbidden | required only for recovery generation | public |

### NameOwnershipRecord

Lifecycle: `stateful-lineage`. Durable ownership authority supports transfer and recovery.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `name_scope` | `tstr` | required | required | required | public |
| 33 | `owner_reference` | `AuthorityReference` | required | required | required | scope-dependent |
| 34 | `service_id` | `bstr` | required | required | required | public |
| 35 | `bootstrap_evidence_digest` | `bstr|null` | optional-critical | optional | optional | public |
| 36 | `transfer_state` | `uint` | required | required | required | public |
| 37 | `revocation_reference` | `AuthorityTarget|null` | required | required | required | public |

### DelegationRecord

Lifecycle: `stateful-lineage`. Mutable scoped authority must retain ancestry and narrowing continuity.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `delegator` | `AuthorityReference` | required | required | required | public |
| 33 | `delegatee` | `AuthorityReference` | required | required | required | public |
| 34 | `delegation_scope` | `DelegationScope` | required | required | required | public |
| 35 | `parent_digest` | `bstr` | contextually-required | forbidden for ownership-root delegation; required for child | required | public |
| 36 | `policy_reference` | `bstr|null` | required | required | required | public |
| 37 | `revocation_reference` | `AuthorityTarget|null` | required | required | required | public |

### FederationTrustBundle

Lifecycle: `stateful-lineage`. Trust roots, logs, witnesses, and thresholds are durable mutable trust state.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `bundle_scope` | `DelegationScope` | required | required | required | public |
| 33 | `roots` | `array<AuthorityReference>` | required | required | required | public |
| 34 | `purpose_keys` | `array<AuthorityReference>` | required | required | required | public |
| 35 | `logs` | `array<AuthorityReference>` | required | required | required | public |
| 36 | `witnesses` | `array<AuthorityReference>` | required | required | required | public |
| 37 | `thresholds` | `ThresholdSet` | required | required | required | public |
| 38 | `profiles` | `array<uint>` | required | required | required | public |
| 39 | `revocation_sources` | `array<AuthorityReference>` | required | required | required | public |
| 40 | `max_staleness` | `uint` | required | required | required | public |
| 41 | `policy_reference` | `bstr|null` | required | required | required | public |

### TransparencyCheckpoint

Lifecycle: `snapshot-state-summary`. A signed tree snapshot uses log generation and checkpoint sequence; continuity is tree consistency, not object predecessor lineage.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `log_id` | `bstr` | required | required | required | public |
| 33 | `scope` | `DelegationScope` | required | required | required | public |
| 34 | `tree_size` | `uint` | required | required | required | public |
| 35 | `merkle_root` | `bstr` | required | required | required | public |
| 36 | `timestamp` | `uint` | required | required | required | public |
| 37 | `signing_key_id` | `bstr` | required | required | required | public |
| 38 | `previous_checkpoint_digest` | `bstr|null` | contextually-required | required | required | public |
| 39 | `witness_policy_digest` | `bstr|null` | optional-critical | required | required | public |

### InclusionProof

Lifecycle: `immutable-proof-evidence`. One-shot Merkle evidence derives freshness and continuity from its checkpoint.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `log_id` | `bstr` | required | required | required | public |
| 33 | `scope` | `DelegationScope` | required | required | required | public |
| 34 | `checkpoint_digest` | `bstr` | required | required | required | public |
| 35 | `tree_size` | `uint` | required | required | required | public |
| 36 | `leaf_index` | `uint` | required | required | required | public |
| 37 | `leaf_digest` | `bstr` | required | required | required | public |
| 38 | `proof_path` | `array<bstr>` | required | required | required | public |
| 39 | `hash_profile` | `uint` | required | required | required | public |
| 40 | `object_class` | `uint|null` | required | required | required | public |

### ConsistencyProof

Lifecycle: `immutable-proof-evidence`. One-shot consistency evidence derives continuity from its two checkpoints.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `log_id` | `bstr` | required | required | required | public |
| 33 | `scope` | `DelegationScope` | required | required | required | public |
| 34 | `old_checkpoint_digest` | `bstr` | required | required | required | public |
| 35 | `new_checkpoint_digest` | `bstr` | required | required | required | public |
| 36 | `old_tree_size` | `uint` | required | required | required | public |
| 37 | `new_tree_size` | `uint` | required | required | required | public |
| 38 | `old_root` | `bstr` | required | required | required | public |
| 39 | `new_root` | `bstr` | required | required | required | public |
| 40 | `proof_path` | `array<bstr>` | required | required | required | public |
| 41 | `hash_profile` | `uint` | required | required | required | public |

### WitnessStatement

Lifecycle: `immutable-proof-evidence`. A replay-bound signed observation is never updated in place.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `witness_id` | `bstr` | required | required | required | public |
| 33 | `log_id` | `bstr` | required | required | required | public |
| 34 | `scope` | `DelegationScope` | required | required | required | public |
| 35 | `checkpoint_digest` | `bstr` | required | required | required | public |
| 36 | `tree_size` | `uint` | required | required | required | public |
| 37 | `merkle_root` | `bstr` | required | required | required | public |
| 38 | `observed_at` | `uint` | required | required | required | public |
| 39 | `verification_result` | `uint` | required | required | required | public |
| 40 | `replay_context` | `bstr` | required | required | required | public |
| 41 | `signing_key_id` | `bstr` | required | required | required | public |
| 42 | `valid_until` | `uint` | required | required | required | public |

### OperatorEndpointRecord

Lifecycle: `stateful-lineage`. Federation-facing endpoint publication rotates while preserving operator continuity.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `operator_id` | `bstr` | required | required | required | public |
| 33 | `endpoint_id` | `bstr` | required | required | required | public |
| 34 | `locator` | `tstr` | required | required | required | public |
| 35 | `role` | `uint` | required | required | required | public |
| 36 | `region` | `tstr|null` | required | required | required | public |
| 37 | `transport_profile` | `uint` | required | required | required | public |
| 38 | `port` | `uint` | required | required | required | public |
| 39 | `priority` | `uint` | required | required | required | public |
| 40 | `transport_key_digest` | `bstr` | required | required | required | public |
| 41 | `lifecycle_state` | `uint` | required | required | required | public |
| 42 | `revocation_reference` | `AuthorityTarget|null` | required | required | required | public |

### FederationAuthorityProof

Lifecycle: `immutable-proof-evidence`. A derived authority proof is replaced by a new digest whenever dependency state changes.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `proof_id` | `bstr` | required | required | required | public |
| 33 | `authority_root_digest` | `bstr` | required | required | required | public |
| 34 | `chain_digests` | `array<bstr>` | required | required | required | public |
| 35 | `service_id` | `bstr` | required | required | required | public |
| 36 | `scope` | `DelegationScope` | required | required | required | public |
| 37 | `source_operator_id` | `bstr|null` | required | required | required | public |
| 38 | `destination_operator_id` | `bstr` | contextually-required | required | required | public |
| 39 | `trust_bundle_digest` | `bstr` | required | required | required | public |
| 40 | `checkpoint_digest` | `bstr` | required | required | required | public |
| 41 | `revocation_commitment` | `bstr` | required | required | required | public |
| 42 | `valid_until` | `uint` | required | required | required | public |

### FederationAuthorizationContext

Lifecycle: `decision-context`. Immutable bilateral authorization is replaced whenever any dependency or policy changes.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 9 | `effective_at` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `context_id` | `bstr` | required | required | required | public |
| 33 | `source_operator_id` | `bstr` | required | required | required | public |
| 34 | `destination_operator_id` | `bstr` | required | required | required | public |
| 35 | `service_id` | `bstr` | required | required | required | public |
| 36 | `authority_proof_digest` | `bstr` | required | required | required | public |
| 37 | `trust_bundle_digest` | `bstr` | required | required | required | public |
| 38 | `checkpoint_digest` | `bstr` | required | required | required | public |
| 39 | `policy_digest` | `bstr` | required | required | required | public |
| 40 | `scope` | `DelegationScope` | required | required | required | public |
| 41 | `valid_until` | `uint` | required | required | required | public |
| 42 | `affected_generation` | `uint` | required | required | required | public |
| 43 | `affected_sequence` | `uint` | required | required | required | public |
| 44 | `dependencies` | `FederationDependencySet` | required | required | required | public |
| 45 | `dependency_set_digest` | `bstr` | required | required | required | public |
| 46 | `route_context_digest` | `bstr` | required | required | required | public |

### TypedRevocationRecord

Lifecycle: `stateful-lineage`. Revocation authority is durable, monotonic, and must preserve replacement history.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `target` | `AuthorityTarget` | required | required | required | public |
| 33 | `scope` | `DelegationScope` | required | required | required | public |
| 34 | `reason` | `uint` | required | required | required | public |
| 35 | `terminal` | `bool` | required | required | required | public |
| 36 | `enforcement_mode` | `uint` | required | required | required | public |
| 37 | `revocation_authority_mode` | `uint` | required | required | required | public |
| 38 | `replacement_reference` | `AuthorityTarget|null` | optional-critical | optional | optional | public |
| 39 | `transparency_reference` | `TransparencyReference` | required | required | required | public |

### ConflictEvidence

Lifecycle: `immutable-proof-evidence`. Evidence is append-only; additions create a new evidence object under the conflict ID.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `conflict_id` | `bstr` | required | required | required | public |
| 33 | `evidence_id` | `bstr` | required | required | required | public |
| 34 | `conflict_class` | `uint` | required | required | required | public |
| 35 | `scope` | `DelegationScope` | required | required | required | public |
| 36 | `object_class` | `uint` | required | required | required | public |
| 37 | `conflicting_digests` | `array<bstr>` | required | required | required | public |
| 38 | `claimed_versions` | `array<VersionTuple>` | required | required | required | public |
| 39 | `checkpoint_digests` | `array<bstr>` | required | required | required | public |
| 40 | `provenance_digests` | `array<bstr>` | required | required | required | public |
| 41 | `first_observed_at` | `uint` | required | required | required | public |
| 42 | `quarantine_recommended` | `bool` | required | required | required | public |
| 43 | `privacy_class` | `uint` | required | required | required | scope-dependent |

### OperatorLifecycleRecord

Lifecycle: `stateful-lineage`. Registry lifecycle authority is durable and gates all operator authority.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 4 | `generation` | `uint` | required | required | required | public |
| 5 | `sequence` | `uint` | required | required | required | public |
| 6 | `not_before` | `uint` | required | required | required | public |
| 7 | `expires_at` | `uint` | required | required | required | public |
| 8 | `previous_digest` | `bstr` | contextually-required | forbidden | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `operator_id` | `bstr` | required | required | required | public |
| 33 | `lifecycle_state` | `uint` | required | required | required | public |
| 34 | `recovery_stage` | `uint` | contextually-required | required only when lifecycle_state=RECOVERY; forbidden otherwise | required only when lifecycle_state=RECOVERY; forbidden otherwise | public |
| 35 | `affected_scope` | `DelegationScope` | required | required | required | public |
| 36 | `reason` | `uint` | required | required | required | public |
| 37 | `reentry_evidence` | `array<bstr>` | contextually-required | required for RECOVERY_VERIFIED or REENTRY_RESTRICTED | required for RECOVERY_VERIFIED or REENTRY_RESTRICTED | public |
| 38 | `transparency_reference` | `TransparencyReference` | required | required | required | public |

### RecoveryTransitionRecord

Lifecycle: `decision-context`. A one-shot recovery authorization binds old/new generations and cannot represent ordinary rotation.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 9 | `effective_at` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `transition_id` | `bstr` | required | required | required | public |
| 33 | `operator_id` | `bstr` | required | required | required | public |
| 34 | `affected_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 35 | `old_generation` | `uint` | required | required | required | public |
| 36 | `new_generation` | `uint` | required | required | required | public |
| 37 | `revoked_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 38 | `replacement_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 39 | `continuity_digest` | `bstr|null` | required | required | required | public |
| 40 | `explicit_break` | `bool` | required | required | required | public |
| 41 | `scope` | `DelegationScope` | required | required | required | public |
| 42 | `approval_signatures` | `array<SignatureReference>` | required | required | required | public |
| 43 | `transparency_reference` | `TransparencyReference` | required | required | required | public |
| 44 | `recovery_stage` | `uint` | required | required | required | public |
| 45 | `activation_restrictions` | `DelegationScope` | required | required | required | public |

### ConflictResolutionRecord

Lifecycle: `decision-context`. A signed resolution is immutable; later process creates a separately identified decision.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 9 | `effective_at` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `decision_id` | `bstr` | required | required | required | public |
| 33 | `conflict_id` | `bstr` | required | required | required | public |
| 34 | `evidence_set_digest` | `bstr` | required | required | required | public |
| 35 | `scope` | `DelegationScope` | required | required | required | public |
| 36 | `outcome` | `uint` | required | required | required | public |
| 37 | `invalidated_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 38 | `preserved_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 39 | `affected_generation` | `uint` | required | required | required | public |
| 40 | `affected_sequence` | `uint` | required | required | required | public |
| 41 | `revocation_digests` | `array<bstr>` | required | required | required | public |
| 42 | `recovery_requirement_digest` | `bstr|null` | required | required | required | public |
| 43 | `appeal_deadline` | `uint` | required | required | required | public |
| 44 | `approvals` | `array<SignatureReference>` | required | required | required | public |
| 45 | `previous_decision_digest` | `bstr|null` | optional-critical | required | required | public |
| 46 | `transparency_reference` | `TransparencyReference` | required | required | required | public |

### AppealDecisionRecord

Lifecycle: `decision-context`. An appeal result is immutable and cannot itself restore unsafe authority.

| Key | Field | Type | Requiredness | Genesis | Update | Privacy |
|---:|---|---|---|---|---|---|
| 1 | `object_type` | `uint` | required | required | required | public |
| 2 | `object_version` | `uint` | required | required | required | public |
| 3 | `issuer_id` | `AuthorityReference` | required | required | required | public |
| 9 | `effective_at` | `uint` | required | required | required | public |
| 31 | `extensions` | `map<uint,ExtensionEntry>` | optional-non-critical | optional | optional | public |
| 32 | `decision_id` | `bstr` | required | required | required | public |
| 33 | `appeal_id` | `bstr` | required | required | required | public |
| 34 | `original_decision_digest` | `bstr` | required | required | required | public |
| 35 | `evidence_set_digest` | `bstr` | required | required | required | public |
| 36 | `appellant_standing` | `uint` | required | required | required | public |
| 37 | `scope` | `DelegationScope` | required | required | required | public |
| 38 | `grounds` | `uint` | required | required | required | public |
| 39 | `outcome` | `uint` | required | required | required | public |
| 40 | `state_transitions` | `array<LifecycleTransition>` | required | required | required | public |
| 41 | `invalidated_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 42 | `preserved_targets` | `array<AuthorityTarget>` | required | required | required | public |
| 43 | `required_followup` | `array<AuthorityTarget>` | required | required | required | public |
| 44 | `approvals` | `array<SignatureReference>` | required | required | required | public |
| 45 | `previous_decision_digest` | `bstr|null` | optional-critical | required | required | public |
| 46 | `transparency_reference` | `TransparencyReference` | required | required | required | public |

## Literal proposal fixture digests

| Object | Fixture | SHA-256 | Expected | Reason | Mutation |
|---|---|---|---|---|---|
| OperatorRegistryRecord | `valid-genesis` | `f9cd917c8e556bd9f6c90c8ca98b6d8ffd8ec16642f68d989f51b40292450961` | ACCEPT | NONE | `true` |
| OperatorRegistryRecord | `valid-same-generation-update` | `8b38eb8419e0704d7e88b55f78f10f34b17cc16b32ff474d51138b4b06cd30ea` | ACCEPT | NONE | `true` |
| OperatorRegistryRecord | `valid-recovery-new-generation` | `d1ed0e24725a18c67bcd7f164176862d13b5fa3fc19d721af23d494c4f7d1997` | ACCEPT | NONE | `true` |
| OperatorRegistryRecord | `missing-required-operator-id` | `afa745a9d95c8b44604ef2bae5cf575b8b266690f361f8bc00c3e13d31ba368d` | REJECT | ERR_SCHEMA | `false` |
| OperatorRegistryRecord | `forbidden-genesis-predecessor` | `f181ffaf5e1cb9173ceba2048a93a98a9de86a3156c099428701cf4f2a91bcd3` | REJECT | ERR_SCHEMA | `false` |
| OperatorRegistryRecord | `wrong-operator-id-length` | `d1d1327cc96705aa20dc7baa301e90fe44989ac43c8fa6464f9ca1d5e97b3862` | REJECT | ERR_IDENTITY | `false` |
| OperatorRegistryRecord | `stale-sequence` | `8b38eb8419e0704d7e88b55f78f10f34b17cc16b32ff474d51138b4b06cd30ea` | REJECT | ERR_ROLLBACK | `false` |
| OperatorRegistryRecord | `equal-version-conflicting-digest` | `3306db9a22428f74b53b416d0755fbabff230008351b19a80a72a6018a341a31` | QUARANTINE | ERR_EQUIVOCATION | `false` |
| OperatorRegistryRecord | `invalid-signer` | `f9cd917c8e556bd9f6c90c8ca98b6d8ffd8ec16642f68d989f51b40292450961` | REJECT | ERR_AUTHORITY | `false` |
| OperatorRegistryRecord | `recovery-signer-without-transition` | `d1ed0e24725a18c67bcd7f164176862d13b5fa3fc19d721af23d494c4f7d1997` | REJECT | ERR_RECOVERY_INVALID | `false` |
| OperatorRegistryRecord | `unknown-critical-extension` | `9f104fddf79f74cad98441cefe1ee6d437eb501cf218e1d69c23a30d9fe02704` | REJECT | ERR_UNSUPPORTED_CRITICAL | `false` |
| OperatorRegistryRecord | `missing-recovery-stage` | `5f466210e1c37cb52c3ddcef2fc5ea98614bf62d3232c40a365abdcbeada51aa` | REJECT | ERR_SCHEMA | `false` |
| OperatorRegistryRecord | `recovery-stage-outside-recovery` | `a39eea9229dd37558aed447743f9ae1274f92ce6c9f8448067d2e40a4a5fe7fb` | REJECT | ERR_SCHEMA | `false` |
| KeyAuthorizationRecord | `valid-root-authorized-genesis` | `714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed` | ACCEPT | NONE | `true` |
| KeyAuthorizationRecord | `valid-rotation-update` | `06b273ec47d7d8176b3980ebbd151c96b5656d9e6334ed51ed10e94afab4b33c` | ACCEPT | NONE | `true` |
| KeyAuthorizationRecord | `valid-recovery-authorized-new-generation` | `fbfd3782e7668c7673a59960acab82ba293c842756b2021b16b19aec9cdaa091` | ACCEPT | NONE | `true` |
| KeyAuthorizationRecord | `wrong-key-purpose` | `21479c7a110466542881976947ab65ee64983ee49ae47c53e5a165390bb046ec` | REJECT | ERR_KEY_PURPOSE | `false` |
| KeyAuthorizationRecord | `cross-purpose-signer` | `714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed` | REJECT | ERR_KEY_PURPOSE | `false` |
| KeyAuthorizationRecord | `bad-kid` | `714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed` | REJECT | ERR_IDENTITY | `false` |
| KeyAuthorizationRecord | `expired` | `714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed` | REJECT | ERR_FRESHNESS | `false` |
| KeyAuthorizationRecord | `predecessor-mismatch` | `6ee6bda9e7ec21c6ab40c8c0172eb59207c10e1b3cef1cdc10e323c560aca8eb` | REJECT | ERR_CONTINUITY | `false` |
| KeyAuthorizationRecord | `terminal-key-id-reuse` | `1d394c74b3ea42c7e0029b1ec4dd33885daf58e1d20bedca02b76a8798c2c7c7` | REJECT | ERR_TERMINAL_STATE | `false` |
| KeyAuthorizationRecord | `compromised-signer` | `06b273ec47d7d8176b3980ebbd151c96b5656d9e6334ed51ed10e94afab4b33c` | REJECT | ERR_KEY_LIFECYCLE | `false` |
| KeyAuthorizationRecord | `unknown-critical-extension` | `afc5ab8f8722caaf6b36bf1892079040a70b1a0a0a0e19318b14216b3e0e47ad` | REJECT | ERR_UNSUPPORTED_CRITICAL | `false` |
| TransparencyCheckpoint | `valid-genesis-checkpoint` | `8eec20858d9326a899dccda190bc726504873a8e87171727a2709b2fe18a56e5` | ACCEPT | NONE | `true` |
| TransparencyCheckpoint | `invalid-generation-reset-without-transition` | `798dafa7a80277358e96cf012866947877e2267e391356808d542789b895511e` | REJECT | ERR_RECOVERY_INVALID | `false` |
| ConsistencyProof | `valid-checkpoint-continuity` | `596c9e120a9a283c0c90cbab731ef60342244a30e59c0f4e9427926cbdcdd79e` | ACCEPT | NONE | `false` |
| ConsistencyProof | `invalid-old-new-checkpoint-mismatch` | `7a5a8de6f13f462038e1a5f0c4cb637e87c129f764bebedc976db11cb094d22d` | REJECT | ERR_CONTINUITY | `false` |
