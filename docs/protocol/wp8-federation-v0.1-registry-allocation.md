# WP8 Federation v0.1 registry allocation amendment

**Task 1 status:** Ratified Development Profile implementation authority. These are approved Development Profile allocations, not permanently frozen Federation wire allocations. `WP8-NORMATIVE-SOURCE-01: CLOSED`.

The machine-readable authority is `registries/federation-v0.1-development.json`. This document is generated from it by `scripts/render_federation_registry.py`; tests require exact agreement. F105 supplies the semantic family requirement, while this amendment supplies the previously missing names, order, and values.

Federation messages occupy extension-local values 16384 through 16441. Frozen Core message values are 1 through 17. The namespaces are disjoint, and a Federation value is never decoded as a Core message. Reserved ranges are unavailable until a later reviewed allocation. Extension ID 1 scopes every Federation registry. This is a Development Profile allocation proposal; permanent reservation waits for schema and vector review.

Every registry is closed. Unknown, unallocated, or reserved values produce `REJECT/ERR_UNSUPPORTED_CRITICAL` with no state mutation. Core protocol versions, messages, and errors remain in their frozen Core namespaces; Core objects are schema-selected and have no numeric object registry. Federation extension-local values are never Core values.

## Extension Ids

<!-- registry:extension_ids -->
| Value | Name | Status |
|---:|---|---|
| 1 | `FEDERATION` | approved Development Profile |

Reserved: `2..255`.

## Capability Ids

<!-- registry:capability_ids -->
| Value | Name | Status |
|---:|---|---|
| 1 | `FEDERATION_OBJECTS` | approved Development Profile |
| 2 | `FEDERATION_AUTHORIZATION` | approved Development Profile |
| 3 | `TRANSPARENCY_PROOFS` | approved Development Profile |
| 4 | `STATIC_TRUST_COMPATIBILITY` | approved Development Profile |
| 5 | `FEDERATION_CONTEXT_BINDING` | approved Development Profile |
| 6 | `THRESHOLD_EVIDENCE` | approved Development Profile |

Reserved: `7..255`.

## Object Types

<!-- registry:object_types -->
| Value | Name | Status |
|---:|---|---|
| 1 | `OperatorRegistryRecord` | approved Development Profile |
| 2 | `KeyAuthorizationRecord` | approved Development Profile |
| 3 | `NameOwnershipRecord` | approved Development Profile |
| 4 | `DelegationRecord` | approved Development Profile |
| 5 | `FederationTrustBundle` | approved Development Profile |
| 6 | `TransparencyCheckpoint` | approved Development Profile |
| 7 | `InclusionProof` | approved Development Profile |
| 8 | `ConsistencyProof` | approved Development Profile |
| 9 | `WitnessStatement` | approved Development Profile |
| 10 | `OperatorEndpointRecord` | approved Development Profile |
| 11 | `FederationAuthorityProof` | approved Development Profile |
| 12 | `FederationAuthorizationContext` | approved Development Profile |
| 13 | `TypedRevocationRecord` | approved Development Profile |
| 14 | `ConflictEvidence` | approved Development Profile |
| 15 | `OperatorLifecycleRecord` | approved Development Profile |
| 16 | `RecoveryTransitionRecord` | approved Development Profile |
| 17 | `ConflictResolutionRecord` | approved Development Profile |
| 18 | `AppealDecisionRecord` | approved Development Profile |

Reserved: `19..255`.

## Message Types

<!-- registry:message_types -->
The count is derived from the 58 semantic entries; no target count applies.

| Value | Name | Family | Class | Senders | Receivers | Allowed state | Replay context | State mutation | Idempotency | Object | Authority effect | Why | Status |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16384 | `FED_CAPABILITIES` | capability-agreement | offer | authenticated-federation-peer | authenticated-federation-peer | core-v2-selected-peer-authenticated | authenticated-session-transcript | federation-capability-state-only | same-replay-context-and-canonical-digest-same-result | none | none | Advertises compatible Federation extension/object/profile/capability/bound values after the selected authenticated Core context. | approved Development Profile |
| 16385 | `FED_CAPABILITIES_ACK` | capability-agreement | ack | authenticated-federation-peer | authenticated-federation-peer | core-v2-selected-peer-authenticated | authenticated-session-transcript | federation-capability-state-only | same-replay-context-and-canonical-digest-same-result | none | none | Confirms the exact compatible Federation selection and rejects unsupported critical semantics. | approved Development Profile |
| 16386 | `OPERATOR_RECORD_QUERY` | operator-discovery | query | source-operator, destination-operator | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | OperatorRegistryRecord | none | Requests one exact Operator Registry Record without enumeration. | approved Development Profile |
| 16387 | `OPERATOR_RECORD_RESPONSE` | operator-discovery | response | registry-service | source-operator, destination-operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | verified-cache-only | same-replay-context-and-canonical-digest-same-result | OperatorRegistryRecord | none-until-object-validation | Returns the exact record or privacy-safe absence proof for the bound query. | approved Development Profile |
| 16388 | `ENDPOINT_RECORD_QUERY` | endpoint-discovery | query | source-operator, destination-operator | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | OperatorEndpointRecord | none | Requests one exact Operator Endpoint Record after operator identity selection. | approved Development Profile |
| 16389 | `ENDPOINT_RECORD_RESPONSE` | endpoint-discovery | response | registry-service | source-operator, destination-operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | verified-cache-only | same-replay-context-and-canonical-digest-same-result | OperatorEndpointRecord | none-until-object-validation | Returns endpoint candidates cryptographically bound to the requested operator. | approved Development Profile |
| 16390 | `OWNERSHIP_AUTHORITY_QUERY` | authority-retrieval | query | source-operator, destination-operator | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | NameOwnershipRecord+DelegationRecord | none | Requests the bounded ownership and delegation chain for one service scope. | approved Development Profile |
| 16391 | `OWNERSHIP_AUTHORITY_RESPONSE` | authority-retrieval | response | registry-service | source-operator, destination-operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | verified-cache-only | same-replay-context-and-canonical-digest-same-result | NameOwnershipRecord+DelegationRecord | none-until-chain-validation | Returns a bounded ordered ownership/delegation chain without granting authority by delivery. | approved Development Profile |
| 16392 | `AUTHORITY_PROOF_QUERY` | authority-proof | query | source-operator, destination-operator | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | FederationAuthorityProof | none | Requests one compact Federation Authority Proof for a bound bilateral context. | approved Development Profile |
| 16393 | `AUTHORITY_PROOF_RESPONSE` | authority-proof | response | authenticated-federation-peer | source-operator, destination-operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | verified-cache-only | same-replay-context-and-canonical-digest-same-result | FederationAuthorityProof | none-until-proof-validation | Returns the requested compact proof bound to its exact dependencies. | approved Development Profile |
| 16394 | `TRUST_BUNDLE_REQUEST` | trust-bundle-sync | query | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | FederationTrustBundle | none | Requests a scoped bundle version or a newer compatible version. | approved Development Profile |
| 16395 | `TRUST_BUNDLE_RESPONSE` | trust-bundle-sync | response | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-bundle-only | same-replay-context-and-canonical-digest-same-result | FederationTrustBundle | none-until-bundle-validation | Returns the requested bundle and continuity evidence. | approved Development Profile |
| 16396 | `TRUST_BUNDLE_UPDATE` | trust-bundle-sync | update | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-bundle-only | same-replay-context-and-canonical-digest-same-result | FederationTrustBundle | none-until-bundle-validation | Pushes a newer candidate bundle with continuity and transparency evidence. | approved Development Profile |
| 16397 | `TRUST_BUNDLE_ACK` | trust-bundle-sync | ack | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | FederationTrustBundle | delivery-and-exact-processing-result-only | Acknowledges delivery and exact processing outcome without equating delivery with normative acceptance. | approved Development Profile |
| 16398 | `CHECKPOINT_QUERY` | transparency-sync | query | authenticated-federation-peer | transparency-log | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | TransparencyCheckpoint | none | Requests a checkpoint at or after a bound tree size. | approved Development Profile |
| 16399 | `CHECKPOINT_RESPONSE` | transparency-sync | response | transparency-log | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-checkpoint-only | same-replay-context-and-canonical-digest-same-result | TransparencyCheckpoint | none-until-checkpoint-validation | Returns the exact signed checkpoint for the query. | approved Development Profile |
| 16400 | `INCLUSION_PROOF_REQUEST` | transparency-sync | request | authenticated-federation-peer | transparency-log | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | InclusionProof | none | Requests inclusion of one exact object digest at one checkpoint. | approved Development Profile |
| 16401 | `INCLUSION_PROOF_RESPONSE` | transparency-sync | response | transparency-log | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-proof-only | same-replay-context-and-canonical-digest-same-result | InclusionProof | none-until-proof-validation | Returns the bounded proof for the exact object and checkpoint. | approved Development Profile |
| 16402 | `CONSISTENCY_PROOF_REQUEST` | transparency-sync | request | authenticated-federation-peer | transparency-log | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | ConsistencyProof | none | Requests consistency between two exact checkpoint sizes and roots. | approved Development Profile |
| 16403 | `CONSISTENCY_PROOF_RESPONSE` | transparency-sync | response | transparency-log | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-proof-only | same-replay-context-and-canonical-digest-same-result | ConsistencyProof | none-until-proof-validation | Returns the bounded proof connecting the requested checkpoints. | approved Development Profile |
| 16404 | `WITNESS_STATEMENT` | transparency-sync | statement | witness | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-witness-only | same-replay-context-and-canonical-digest-same-result | WitnessStatement | none-until-threshold-validation | Publishes a witness statement for one exact checkpoint and organization. | approved Development Profile |
| 16405 | `AUTHORIZATION_REQUEST` | bilateral-authorization | request | source-operator | destination-operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | pending-authorization-only | same-replay-context-and-canonical-digest-same-result | FederationAuthorityProof | none | Requests destination authorization after independent source validation has succeeded. | approved Development Profile |
| 16406 | `AUTHORIZATION_RESPONSE` | bilateral-authorization | response | destination-operator | source-operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | bilateral-authorization-result | same-replay-context-and-canonical-digest-same-result | FederationAuthorizationContext | only-after-independent-source-and-destination-validation | Returns the destination decision bound to the source-validated request without replacing source validation. | approved Development Profile |
| 16407 | `REVOCATION_PUSH` | revocation | push | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-revocation-only | same-replay-context-and-canonical-digest-same-result | TypedRevocationRecord | none-until-revocation-validation | Pushes a typed revocation for immediate validation and selective enforcement. | approved Development Profile |
| 16408 | `REVOCATION_ACK` | revocation | ack | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | TypedRevocationRecord | exact-processing-result-only | Acknowledges the exact accepted or rejected revocation digest, reason, enforcement, and state result. | approved Development Profile |
| 16409 | `REVOCATION_QUERY` | revocation | query | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | TypedRevocationRecord | none | Queries current revocation state for an exact target and generation. | approved Development Profile |
| 16410 | `REVOCATION_RESPONSE` | revocation | response | authenticated-federation-peer | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-revocation-only | same-replay-context-and-canonical-digest-same-result | TypedRevocationRecord | none-until-revocation-validation | Returns current typed revocation state or privacy-safe absence evidence. | approved Development Profile |
| 16411 | `CONFLICT_REPORT` | conflict | report | authenticated-federation-peer | conflict-resolution-authority | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | conflict-evidence-only | same-replay-context-and-canonical-digest-same-result | ConflictEvidence | none-by-report | Reports retained equivocation or split-view evidence without unilateral conviction authority. | approved Development Profile |
| 16412 | `CONFLICT_ACK` | conflict | ack | conflict-resolution-authority | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | ConflictEvidence | none-by-delivery | Acknowledges receipt and exact evidence digest without deciding the conflict. | approved Development Profile |
| 16413 | `OPERATOR_STATUS_QUERY` | operator-lifecycle | query | authenticated-federation-peer | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | none | same-replay-context-and-canonical-digest-same-result | OperatorLifecycleRecord | none | Queries exact current operator lifecycle generation and recovery stage. | approved Development Profile |
| 16414 | `OPERATOR_STATUS_RESPONSE` | operator-lifecycle | response | registry-service | authenticated-federation-peer | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-lifecycle-only | same-replay-context-and-canonical-digest-same-result | OperatorLifecycleRecord | none-until-lifecycle-validation | Returns the exact signed lifecycle record and dependencies. | approved Development Profile |
| 16415 | `QUARANTINE_NOTICE` | operator-lifecycle | notice | registry-service | authenticated-federation-peer | operator-lifecycle=QUARANTINED | authenticated-peer-sequence-and-message-digest | notice-log-only | same-replay-context-and-canonical-digest-same-result | OperatorLifecycleRecord | none-by-delivery | Notifies peers of quarantine evidence and required enforcement without creating authority by delivery. | approved Development Profile |
| 16416 | `RECOVERY_NOTICE` | operator-lifecycle | notice | registry-service | authenticated-federation-peer | operator-lifecycle=RECOVERY;recovery-stage=RECOVERY_PENDING-or-RECOVERY_VERIFIED | authenticated-peer-sequence-and-message-digest | notice-log-only | same-replay-context-and-canonical-digest-same-result | RecoveryTransitionRecord | none-by-delivery | Notifies peers of a candidate recovery transition without activating recovered authority. | approved Development Profile |
| 16417 | `REENTRY_EVIDENCE` | operator-lifecycle | evidence | authenticated-federation-peer | registry-service | operator-lifecycle=RECOVERY;recovery-stage=REENTRY_RESTRICTED | authenticated-peer-sequence-and-message-digest | candidate-reentry-evidence-only | same-replay-context-and-canonical-digest-same-result | RecoveryTransitionRecord | none-until-complete-gate-validation | Supplies synchronization, checkpoint, revocation, monitoring, and readiness evidence for staged re-entry. | approved Development Profile |
| 16418 | `OPERATOR_REGISTRATION_REQUEST` | operator-publication | request | operator-applicant | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | OperatorRegistryRecord | none-until-registration-validation | Requests genesis registration under registrar and witness authority. | approved Development Profile |
| 16419 | `OPERATOR_REGISTRATION_RESPONSE` | operator-publication | response | registry-service | operator-applicant | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | registry-result | same-replay-context-and-canonical-digest-same-result | OperatorRegistryRecord | accepted-state-only | Returns exact registration acceptance, rejection, or pending result. | approved Development Profile |
| 16420 | `OPERATOR_RECORD_UPDATE` | operator-publication | update | operator | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | OperatorRegistryRecord | none-until-update-validation | Presents a monotonic signed operator record update with continuity evidence. | approved Development Profile |
| 16421 | `OPERATOR_RECORD_UPDATE_ACK` | operator-publication | ack | registry-service | operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | OperatorRegistryRecord | exact-processing-result-only | Acknowledges the exact operator update digest and processing result. | approved Development Profile |
| 16422 | `KEY_AUTHORIZATION_PUBLISH` | key-publication | publish | operator-root-or-recovery | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | KeyAuthorizationRecord | none-until-object-validation | Publishes a genesis purpose-bound key authorization. | approved Development Profile |
| 16423 | `KEY_AUTHORIZATION_ACK` | key-publication | ack | registry-service | operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | KeyAuthorizationRecord | exact-processing-result-only | Acknowledges the exact genesis key authorization processing result. | approved Development Profile |
| 16424 | `KEY_AUTHORIZATION_UPDATE` | key-publication | update | operator-root-or-recovery | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | KeyAuthorizationRecord | none-until-object-validation | Publishes a monotonic key authorization rotation or lifecycle update. | approved Development Profile |
| 16425 | `KEY_AUTHORIZATION_UPDATE_ACK` | key-publication | ack | registry-service | operator | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | KeyAuthorizationRecord | exact-processing-result-only | Acknowledges the exact key update digest and processing result. | approved Development Profile |
| 16426 | `NAME_OWNERSHIP_PUBLISH` | ownership-publication | publish | name-owner | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | NameOwnershipRecord | none-until-object-validation | Publishes genesis name ownership under registry-rooted authority. | approved Development Profile |
| 16427 | `NAME_OWNERSHIP_ACK` | ownership-publication | ack | registry-service | name-owner | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | NameOwnershipRecord | exact-processing-result-only | Acknowledges exact ownership publication processing state. | approved Development Profile |
| 16428 | `NAME_OWNERSHIP_UPDATE` | ownership-publication | update | name-owner | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | NameOwnershipRecord | none-until-object-validation | Publishes a monotonic ownership update or dual-authorized transfer. | approved Development Profile |
| 16429 | `NAME_OWNERSHIP_UPDATE_ACK` | ownership-publication | ack | registry-service | name-owner | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | NameOwnershipRecord | exact-processing-result-only | Acknowledges exact ownership update or transfer processing state. | approved Development Profile |
| 16430 | `DELEGATION_PUBLISH` | delegation-publication | publish | name-owner, delegate | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | DelegationRecord | none-until-chain-validation | Publishes a genesis scope-narrowing delegation. | approved Development Profile |
| 16431 | `DELEGATION_ACK` | delegation-publication | ack | registry-service | name-owner, delegate | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | DelegationRecord | exact-processing-result-only | Acknowledges the exact delegation publication result. | approved Development Profile |
| 16432 | `DELEGATION_UPDATE` | delegation-publication | update | name-owner, delegate | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | DelegationRecord | none-until-chain-validation | Publishes a monotonic narrowing, expiry, or revocation-aware delegation update. | approved Development Profile |
| 16433 | `DELEGATION_UPDATE_ACK` | delegation-publication | ack | registry-service | name-owner, delegate | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | DelegationRecord | exact-processing-result-only | Acknowledges the exact delegation update result. | approved Development Profile |
| 16434 | `ENDPOINT_RECORD_PUBLISH` | endpoint-publication | publish | operator-endpoint-authority | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | OperatorEndpointRecord | none-until-object-validation | Publishes a genesis operator-bound endpoint record. | approved Development Profile |
| 16435 | `ENDPOINT_RECORD_ACK` | endpoint-publication | ack | registry-service | operator-endpoint-authority | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | OperatorEndpointRecord | exact-processing-result-only | Acknowledges exact endpoint publication processing state. | approved Development Profile |
| 16436 | `ENDPOINT_RECORD_UPDATE` | endpoint-publication | update | operator-endpoint-authority | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | OperatorEndpointRecord | none-until-object-validation | Publishes a monotonic endpoint binding or key update. | approved Development Profile |
| 16437 | `ENDPOINT_RECORD_UPDATE_ACK` | endpoint-publication | ack | registry-service | operator-endpoint-authority | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | OperatorEndpointRecord | exact-processing-result-only | Acknowledges exact endpoint update processing state. | approved Development Profile |
| 16438 | `CONFLICT_RESOLUTION_PUBLISH` | governance | publish | governance-authority | registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | ConflictResolutionRecord | none-until-governance-validation | Publishes threshold-authorized conflict resolution without erasing retained evidence. | approved Development Profile |
| 16439 | `CONFLICT_RESOLUTION_ACK` | governance | ack | registry-service | governance-authority | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | acknowledgement-log-only | same-replay-context-and-canonical-digest-same-result | ConflictResolutionRecord | exact-processing-result-only | Acknowledges exact conflict resolution processing state. | approved Development Profile |
| 16440 | `APPEAL_REQUEST` | governance | request | authorized-appellant | appeal-authority | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | appeal-case-only | same-replay-context-and-canonical-digest-same-result | AppealDecisionRecord | none | Requests appeal review separately from recovery and without reactivating authority. | approved Development Profile |
| 16441 | `APPEAL_RESPONSE` | governance | response | appeal-authority | authorized-appellant, registry-service | federation-capabilities-agreed | authenticated-peer-sequence-and-message-digest | candidate-object-only | same-replay-context-and-canonical-digest-same-result | AppealDecisionRecord | none-until-governance-validation | Returns a threshold-authorized appeal decision that cannot override terminal non-reactivation rules. | approved Development Profile |

Reserved: `16442..16639`.

## Reason Codes

<!-- registry:reason_codes -->
| Value | Name | Status |
|---:|---|---|
| 0 | `NONE` | approved Development Profile |
| 1 | `ERR_RESOURCE_LIMIT` | approved Development Profile |
| 2 | `ERR_PARSE` | approved Development Profile |
| 3 | `ERR_NON_CANONICAL` | approved Development Profile |
| 4 | `ERR_UNSUPPORTED_CRITICAL` | approved Development Profile |
| 5 | `ERR_CRYPTO_PROFILE` | approved Development Profile |
| 6 | `ERR_SIGNATURE_INVALID` | approved Development Profile |
| 7 | `ERR_IDENTITY` | approved Development Profile |
| 8 | `ERR_KEY_PURPOSE` | approved Development Profile |
| 9 | `ERR_KEY_LIFECYCLE` | approved Development Profile |
| 10 | `ERR_SCHEMA` | approved Development Profile |
| 11 | `ERR_VERSION` | approved Development Profile |
| 12 | `ERR_AUTHORITY` | approved Development Profile |
| 13 | `ERR_SCOPE` | approved Development Profile |
| 14 | `ERR_POLICY_EXPANSION` | approved Development Profile |
| 15 | `ERR_ROLLBACK` | approved Development Profile |
| 16 | `ERR_REPLAY` | approved Development Profile |
| 17 | `ERR_EQUIVOCATION` | approved Development Profile |
| 18 | `ERR_CONTINUITY` | approved Development Profile |
| 19 | `ERR_REVOKED` | approved Development Profile |
| 20 | `ERR_TERMINAL_STATE` | approved Development Profile |
| 21 | `ERR_TRANSPARENCY` | approved Development Profile |
| 22 | `ERR_CHECKPOINT` | approved Development Profile |
| 23 | `ERR_SPLIT_VIEW` | approved Development Profile |
| 24 | `ERR_WITNESS_THRESHOLD` | approved Development Profile |
| 25 | `ERR_FRESHNESS` | approved Development Profile |
| 26 | `ERR_EVIDENCE_MISSING` | approved Development Profile |
| 27 | `ERR_OUTAGE_POLICY` | approved Development Profile |
| 28 | `ERR_DOWNGRADE` | approved Development Profile |
| 29 | `ERR_LOCAL_POLICY` | approved Development Profile |
| 30 | `ERR_RECOVERY_INVALID` | approved Development Profile |
| 31 | `ERR_INTERNAL` | approved Development Profile |

Reserved: `32..255`.

## Key Purposes

<!-- registry:key_purposes -->
| Value | Name | Status |
|---:|---|---|
| 1 | `IDENTITY_ROOT` | approved Development Profile |
| 2 | `RECOVERY` | approved Development Profile |
| 3 | `REGISTRY_SIGNING` | approved Development Profile |
| 4 | `KEY_AUTHORIZATION` | approved Development Profile |
| 5 | `NAME_OWNERSHIP` | approved Development Profile |
| 6 | `DELEGATION` | approved Development Profile |
| 7 | `TRUST_BUNDLE` | approved Development Profile |
| 8 | `TRANSPARENCY_LOG` | approved Development Profile |
| 9 | `WITNESS` | approved Development Profile |
| 10 | `ENDPOINT_DISCOVERY` | approved Development Profile |
| 11 | `FEDERATION_AUTHORIZATION` | approved Development Profile |
| 12 | `REVOCATION` | approved Development Profile |
| 13 | `GOVERNANCE` | approved Development Profile |
| 14 | `FEDERATION_TRANSPORT` | approved Development Profile |

Reserved: `15..255`.

## Key Lifecycles

<!-- registry:key_lifecycles -->
| Value | Name | Status |
|---:|---|---|
| 1 | `NEXT` | approved Development Profile |
| 2 | `ACTIVE` | approved Development Profile |
| 3 | `RETIRING` | approved Development Profile |
| 4 | `RETIRED` | approved Development Profile |
| 5 | `REVOKED` | approved Development Profile |

Reserved: `6..255`.

## Operator Lifecycles

<!-- registry:operator_lifecycles -->
| Value | Name | Status |
|---:|---|---|
| 1 | `APPLIED` | approved Development Profile |
| 2 | `VERIFICATION_PENDING` | approved Development Profile |
| 3 | `VERIFIED` | approved Development Profile |
| 4 | `PROVISIONAL` | approved Development Profile |
| 5 | `ACTIVE` | approved Development Profile |
| 6 | `SUSPENDED` | approved Development Profile |
| 7 | `QUARANTINED` | approved Development Profile |
| 8 | `RECOVERY` | approved Development Profile |
| 9 | `RETIRED` | approved Development Profile |
| 10 | `TERMINALLY_REVOKED` | approved Development Profile |
| 11 | `REJECTED` | approved Development Profile |

Reserved: `12..255`.

## Recovery Stages

<!-- registry:recovery_stages -->
| Value | Name | Status |
|---:|---|---|
| 1 | `RECOVERY_PENDING` | approved Development Profile |
| 2 | `RECOVERY_VERIFIED` | approved Development Profile |
| 3 | `REENTRY_RESTRICTED` | approved Development Profile |

Reserved: `4..255`.

## Result Types

<!-- registry:result_types -->
| Value | Name | Status |
|---:|---|---|
| 1 | `VALIDATION` | approved Development Profile |
| 2 | `PUBLICATION` | approved Development Profile |
| 3 | `QUERY` | approved Development Profile |
| 4 | `AUTHORIZATION` | approved Development Profile |
| 5 | `LIFECYCLE` | approved Development Profile |
| 6 | `RECOVERY` | approved Development Profile |
| 7 | `CONFLICT` | approved Development Profile |
| 8 | `APPEAL` | approved Development Profile |

Reserved: `9..255`.

## Decision Outcomes

<!-- registry:decision_outcomes -->
| Value | Name | Status |
|---:|---|---|
| 1 | `ACCEPT` | approved Development Profile |
| 2 | `REJECT` | approved Development Profile |
| 3 | `PENDING` | approved Development Profile |
| 4 | `RESTRICTED` | approved Development Profile |
| 5 | `QUARANTINE` | approved Development Profile |

Reserved: `6..255`.

## Enforcement Modes

<!-- registry:enforcement_modes -->
| Value | Name | Status |
|---:|---|---|
| 0 | `NONE` | approved Development Profile |
| 1 | `DENY_NEW_USE` | approved Development Profile |
| 2 | `REAUTHENTICATE` | approved Development Profile |
| 3 | `DRAIN` | approved Development Profile |
| 4 | `TERMINATE_ACTIVE_USE` | approved Development Profile |

Reserved: `5..255`.

## Authority Classes

<!-- registry:authority_classes -->
| Value | Name | Status |
|---:|---|---|
| 1 | `OPERATOR_IDENTITY_ROOT` | approved Development Profile |
| 2 | `OPERATOR_RECOVERY` | approved Development Profile |
| 3 | `DEVELOPMENT_REGISTRAR` | approved Development Profile |
| 4 | `FEDERATION_AUTHORITY` | approved Development Profile |
| 5 | `TRANSPARENCY_LOG` | approved Development Profile |
| 6 | `WITNESS` | approved Development Profile |
| 7 | `NAME_OWNER` | approved Development Profile |
| 8 | `DELEGATE` | approved Development Profile |
| 9 | `SOURCE_OPERATOR` | approved Development Profile |
| 10 | `DESTINATION_OPERATOR` | approved Development Profile |
| 11 | `CONFLICT_RESOLUTION` | approved Development Profile |
| 12 | `APPEAL` | approved Development Profile |
| 13 | `OPERATOR_ENDPOINT` | approved Development Profile |
| 14 | `TARGET_CONTROLLER` | approved Development Profile |

Reserved: `15..255`.

## Contextual lifecycle rules

`recovery_stage` is required exactly when `operator_lifecycle=RECOVERY` and forbidden otherwise. The only wire stages are `RECOVERY_PENDING`, `RECOVERY_VERIFIED`, and `REENTRY_RESTRICTED`. Normal `ACTIVE` follows `REENTRY_RESTRICTED` only after peer synchronization, compatible checkpoints, current revocations, monitoring completion, and readiness approval.

The labels `REQUESTED`, `EVIDENCE_VERIFIED`, `APPROVED`, `ACTIVATED`, `REENTRY_MONITORING`, `COMPLETE`, and local `REJECTED` are non-wire implementation workflow labels only.

Lifecycle numbers are identifiers rather than transition ranks. Monotonicity applies to identity generation and record sequence. Allowed transitions are:

- `APPLIED` -> `VERIFICATION_PENDING`, `REJECTED`
- `VERIFICATION_PENDING` -> `VERIFIED`, `REJECTED`
- `VERIFIED` -> `PROVISIONAL`, `ACTIVE`, `REJECTED`
- `PROVISIONAL` -> `ACTIVE`, `SUSPENDED`, `QUARANTINED`, `RECOVERY`, `RETIRED`, `TERMINALLY_REVOKED`
- `ACTIVE` -> `SUSPENDED`, `QUARANTINED`, `RECOVERY`, `RETIRED`, `TERMINALLY_REVOKED`
- `SUSPENDED` -> `ACTIVE`, `QUARANTINED`, `RECOVERY`, `RETIRED`, `TERMINALLY_REVOKED`
- `QUARANTINED` -> `RECOVERY`, `RETIRED`, `TERMINALLY_REVOKED`
- `RECOVERY` -> `ACTIVE`, `RETIRED`, `TERMINALLY_REVOKED`
- `RETIRED` -> none
- `TERMINALLY_REVOKED` -> none
- `REJECTED` -> none

Recovery stages advance only `RECOVERY_PENDING -> RECOVERY_VERIFIED -> REENTRY_RESTRICTED -> ACTIVE`; skips and rollback reject `ERR_CONTINUITY` without mutation.

## Approval and claim boundary

Human approval has promoted these entries to approved Development Profile values. It does not create permanently frozen wire allocations. That later gate requires closed schemas, literal vectors, cross-verifier agreement, and a separate decision. Production-profile values remain deferred. Task 1 implements only profile constants, registry tables, and baseline enforcement; it supplies no live federation, governance, interoperability, privacy, or production evidence.
