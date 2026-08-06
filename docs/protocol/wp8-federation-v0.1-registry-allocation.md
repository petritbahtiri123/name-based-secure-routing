# WP8 Federation v0.1 registry allocation amendment

**Task 0 status:** Proposed for human approval. These are normative Development Profile proposals, not permanently frozen Federation wire allocations. Task 1 may consume them only after approval.

The machine-readable authority is `registries/federation-v0.1-development.json`. This document is generated from it by `scripts/render_federation_registry.py`; tests require exact agreement. F105 supplies the semantic family requirement, while this amendment supplies the previously missing names, order, and values.

Federation messages occupy extension-local values 16384 through 16417. Frozen Core message values are 1 through 17. The namespaces are disjoint, and a Federation value is never decoded as a Core message. Reserved ranges are unavailable until a later reviewed allocation. Extension ID 1 scopes every Federation registry. This is a Development Profile allocation proposal; permanent reservation waits for schema and vector review.

Every registry is closed. Unknown, unallocated, or reserved values produce `REJECT/ERR_UNSUPPORTED_CRITICAL` with no state mutation. Core protocol versions, messages, and errors remain in their frozen Core namespaces; Core objects are schema-selected and have no numeric object registry. Federation extension-local values are never Core values.

## Extension Ids

<!-- registry:extension_ids -->
| Value | Name | Status |
|---:|---|---|
| 1 | `FEDERATION` | proposed Development Profile |

Reserved: `2..255`.

## Capability Ids

<!-- registry:capability_ids -->
| Value | Name | Status |
|---:|---|---|
| 1 | `FEDERATION_OBJECTS` | proposed Development Profile |
| 2 | `FEDERATION_AUTHORIZATION` | proposed Development Profile |
| 3 | `TRANSPARENCY_PROOFS` | proposed Development Profile |
| 4 | `STATIC_TRUST_COMPATIBILITY` | proposed Development Profile |
| 5 | `FEDERATION_CONTEXT_BINDING` | proposed Development Profile |

Reserved: `6..255`.

## Object Types

<!-- registry:object_types -->
| Value | Name | Status |
|---:|---|---|
| 1 | `OperatorRegistryRecord` | proposed Development Profile |
| 2 | `KeyAuthorizationRecord` | proposed Development Profile |
| 3 | `NameOwnershipRecord` | proposed Development Profile |
| 4 | `DelegationRecord` | proposed Development Profile |
| 5 | `FederationTrustBundle` | proposed Development Profile |
| 6 | `TransparencyCheckpoint` | proposed Development Profile |
| 7 | `InclusionProof` | proposed Development Profile |
| 8 | `ConsistencyProof` | proposed Development Profile |
| 9 | `WitnessStatement` | proposed Development Profile |
| 10 | `OperatorEndpointRecord` | proposed Development Profile |
| 11 | `FederationAuthorityProof` | proposed Development Profile |
| 12 | `FederationAuthorizationContext` | proposed Development Profile |
| 13 | `TypedRevocationRecord` | proposed Development Profile |
| 14 | `ConflictEvidence` | proposed Development Profile |
| 15 | `OperatorLifecycleRecord` | proposed Development Profile |
| 16 | `RecoveryTransitionRecord` | proposed Development Profile |
| 17 | `ConflictResolutionRecord` | proposed Development Profile |
| 18 | `AppealDecisionRecord` | proposed Development Profile |

Reserved: `19..255`.

## Message Types

<!-- registry:message_types -->
| Value | Name | Status |
|---:|---|---|
| 16384 | `OPERATOR_RECORD_SUBMIT` | proposed Development Profile |
| 16385 | `OPERATOR_RECORD_RESULT` | proposed Development Profile |
| 16386 | `KEY_AUTHORIZATION_SUBMIT` | proposed Development Profile |
| 16387 | `KEY_AUTHORIZATION_RESULT` | proposed Development Profile |
| 16388 | `NAME_OWNERSHIP_SUBMIT` | proposed Development Profile |
| 16389 | `NAME_OWNERSHIP_RESULT` | proposed Development Profile |
| 16390 | `DELEGATION_SUBMIT` | proposed Development Profile |
| 16391 | `DELEGATION_RESULT` | proposed Development Profile |
| 16392 | `TRUST_BUNDLE_REQUEST` | proposed Development Profile |
| 16393 | `TRUST_BUNDLE_RESULT` | proposed Development Profile |
| 16394 | `CHECKPOINT_REQUEST` | proposed Development Profile |
| 16395 | `CHECKPOINT_RESULT` | proposed Development Profile |
| 16396 | `INCLUSION_PROOF_REQUEST` | proposed Development Profile |
| 16397 | `INCLUSION_PROOF_RESULT` | proposed Development Profile |
| 16398 | `CONSISTENCY_PROOF_REQUEST` | proposed Development Profile |
| 16399 | `CONSISTENCY_PROOF_RESULT` | proposed Development Profile |
| 16400 | `WITNESS_STATEMENT_SUBMIT` | proposed Development Profile |
| 16401 | `WITNESS_STATEMENT_RESULT` | proposed Development Profile |
| 16402 | `ENDPOINT_REQUEST` | proposed Development Profile |
| 16403 | `ENDPOINT_RESULT` | proposed Development Profile |
| 16404 | `AUTHORITY_PROOF_SUBMIT` | proposed Development Profile |
| 16405 | `AUTHORITY_PROOF_RESULT` | proposed Development Profile |
| 16406 | `AUTHORIZATION_REQUEST` | proposed Development Profile |
| 16407 | `AUTHORIZATION_RESULT` | proposed Development Profile |
| 16408 | `REVOCATION_SUBMIT` | proposed Development Profile |
| 16409 | `REVOCATION_RESULT` | proposed Development Profile |
| 16410 | `LIFECYCLE_SUBMIT` | proposed Development Profile |
| 16411 | `LIFECYCLE_RESULT` | proposed Development Profile |
| 16412 | `RECOVERY_SUBMIT` | proposed Development Profile |
| 16413 | `RECOVERY_RESULT` | proposed Development Profile |
| 16414 | `CONFLICT_SUBMIT` | proposed Development Profile |
| 16415 | `CONFLICT_RESULT` | proposed Development Profile |
| 16416 | `APPEAL_SUBMIT` | proposed Development Profile |
| 16417 | `APPEAL_RESULT` | proposed Development Profile |

Reserved: `16418..16639`.

## Reason Codes

<!-- registry:reason_codes -->
| Value | Name | Status |
|---:|---|---|
| 0 | `NONE` | proposed Development Profile |
| 1 | `ERR_RESOURCE_LIMIT` | proposed Development Profile |
| 2 | `ERR_PARSE` | proposed Development Profile |
| 3 | `ERR_NON_CANONICAL` | proposed Development Profile |
| 4 | `ERR_UNSUPPORTED_CRITICAL` | proposed Development Profile |
| 5 | `ERR_CRYPTO_PROFILE` | proposed Development Profile |
| 6 | `ERR_SIGNATURE_INVALID` | proposed Development Profile |
| 7 | `ERR_IDENTITY` | proposed Development Profile |
| 8 | `ERR_KEY_PURPOSE` | proposed Development Profile |
| 9 | `ERR_KEY_LIFECYCLE` | proposed Development Profile |
| 10 | `ERR_SCHEMA` | proposed Development Profile |
| 11 | `ERR_VERSION` | proposed Development Profile |
| 12 | `ERR_AUTHORITY` | proposed Development Profile |
| 13 | `ERR_SCOPE` | proposed Development Profile |
| 14 | `ERR_POLICY_EXPANSION` | proposed Development Profile |
| 15 | `ERR_ROLLBACK` | proposed Development Profile |
| 16 | `ERR_REPLAY` | proposed Development Profile |
| 17 | `ERR_EQUIVOCATION` | proposed Development Profile |
| 18 | `ERR_CONTINUITY` | proposed Development Profile |
| 19 | `ERR_REVOKED` | proposed Development Profile |
| 20 | `ERR_TERMINAL_STATE` | proposed Development Profile |
| 21 | `ERR_TRANSPARENCY` | proposed Development Profile |
| 22 | `ERR_CHECKPOINT` | proposed Development Profile |
| 23 | `ERR_SPLIT_VIEW` | proposed Development Profile |
| 24 | `ERR_WITNESS_THRESHOLD` | proposed Development Profile |
| 25 | `ERR_FRESHNESS` | proposed Development Profile |
| 26 | `ERR_EVIDENCE_MISSING` | proposed Development Profile |
| 27 | `ERR_OUTAGE_POLICY` | proposed Development Profile |
| 28 | `ERR_DOWNGRADE` | proposed Development Profile |
| 29 | `ERR_LOCAL_POLICY` | proposed Development Profile |
| 30 | `ERR_RECOVERY_INVALID` | proposed Development Profile |
| 31 | `ERR_INTERNAL` | proposed Development Profile |

Reserved: `32..255`.

## Key Purposes

<!-- registry:key_purposes -->
| Value | Name | Status |
|---:|---|---|
| 1 | `IDENTITY_ROOT` | proposed Development Profile |
| 2 | `RECOVERY` | proposed Development Profile |
| 3 | `REGISTRY_SIGNING` | proposed Development Profile |
| 4 | `KEY_AUTHORIZATION` | proposed Development Profile |
| 5 | `NAME_OWNERSHIP` | proposed Development Profile |
| 6 | `DELEGATION` | proposed Development Profile |
| 7 | `TRUST_BUNDLE` | proposed Development Profile |
| 8 | `TRANSPARENCY_LOG` | proposed Development Profile |
| 9 | `WITNESS` | proposed Development Profile |
| 10 | `ENDPOINT_DISCOVERY` | proposed Development Profile |
| 11 | `FEDERATION_AUTHORIZATION` | proposed Development Profile |
| 12 | `REVOCATION` | proposed Development Profile |
| 13 | `GOVERNANCE` | proposed Development Profile |
| 14 | `FEDERATION_TRANSPORT` | proposed Development Profile |

Reserved: `15..255`.

## Key Lifecycles

<!-- registry:key_lifecycles -->
| Value | Name | Status |
|---:|---|---|
| 1 | `NEXT` | proposed Development Profile |
| 2 | `ACTIVE` | proposed Development Profile |
| 3 | `RETIRING` | proposed Development Profile |
| 4 | `RETIRED` | proposed Development Profile |
| 5 | `REVOKED` | proposed Development Profile |

Reserved: `6..255`.

## Operator Lifecycles

<!-- registry:operator_lifecycles -->
| Value | Name | Status |
|---:|---|---|
| 1 | `APPLIED` | proposed Development Profile |
| 2 | `VERIFIED` | proposed Development Profile |
| 3 | `ACTIVE` | proposed Development Profile |
| 4 | `RESTRICTED` | proposed Development Profile |
| 5 | `QUARANTINED` | proposed Development Profile |
| 6 | `SUSPENDED` | proposed Development Profile |
| 7 | `RECOVERY_PENDING` | proposed Development Profile |
| 8 | `REENTRY_PENDING` | proposed Development Profile |
| 9 | `RETIRED` | proposed Development Profile |
| 10 | `TERMINALLY_REVOKED` | proposed Development Profile |

Reserved: `11..255`.

## Recovery Stages

<!-- registry:recovery_stages -->
| Value | Name | Status |
|---:|---|---|
| 1 | `REQUESTED` | proposed Development Profile |
| 2 | `EVIDENCE_VERIFIED` | proposed Development Profile |
| 3 | `APPROVED` | proposed Development Profile |
| 4 | `ACTIVATED` | proposed Development Profile |
| 5 | `REENTRY_MONITORING` | proposed Development Profile |
| 6 | `COMPLETE` | proposed Development Profile |
| 7 | `REJECTED` | proposed Development Profile |

Reserved: `8..255`.

## Result Types

<!-- registry:result_types -->
| Value | Name | Status |
|---:|---|---|
| 1 | `VALIDATION` | proposed Development Profile |
| 2 | `PUBLICATION` | proposed Development Profile |
| 3 | `QUERY` | proposed Development Profile |
| 4 | `AUTHORIZATION` | proposed Development Profile |
| 5 | `LIFECYCLE` | proposed Development Profile |
| 6 | `RECOVERY` | proposed Development Profile |
| 7 | `CONFLICT` | proposed Development Profile |
| 8 | `APPEAL` | proposed Development Profile |

Reserved: `9..255`.

## Decision Outcomes

<!-- registry:decision_outcomes -->
| Value | Name | Status |
|---:|---|---|
| 1 | `ACCEPT` | proposed Development Profile |
| 2 | `REJECT` | proposed Development Profile |
| 3 | `PENDING` | proposed Development Profile |
| 4 | `RESTRICTED` | proposed Development Profile |
| 5 | `QUARANTINE` | proposed Development Profile |

Reserved: `6..255`.

## Enforcement Modes

<!-- registry:enforcement_modes -->
| Value | Name | Status |
|---:|---|---|
| 0 | `NONE` | proposed Development Profile |
| 1 | `DENY_NEW_USE` | proposed Development Profile |
| 2 | `REAUTHENTICATE` | proposed Development Profile |
| 3 | `DRAIN` | proposed Development Profile |
| 4 | `TERMINATE_ACTIVE_USE` | proposed Development Profile |

Reserved: `5..255`.

## Authority Classes

<!-- registry:authority_classes -->
| Value | Name | Status |
|---:|---|---|
| 1 | `OPERATOR_IDENTITY_ROOT` | proposed Development Profile |
| 2 | `OPERATOR_RECOVERY` | proposed Development Profile |
| 3 | `DEVELOPMENT_REGISTRAR` | proposed Development Profile |
| 4 | `FEDERATION_AUTHORITY` | proposed Development Profile |
| 5 | `TRANSPARENCY_LOG` | proposed Development Profile |
| 6 | `WITNESS` | proposed Development Profile |
| 7 | `NAME_OWNER` | proposed Development Profile |
| 8 | `DELEGATE` | proposed Development Profile |
| 9 | `SOURCE_OPERATOR` | proposed Development Profile |
| 10 | `DESTINATION_OPERATOR` | proposed Development Profile |
| 11 | `CONFLICT_RESOLUTION` | proposed Development Profile |
| 12 | `APPEAL` | proposed Development Profile |
| 13 | `OPERATOR_ENDPOINT` | proposed Development Profile |
| 14 | `TARGET_CONTROLLER` | proposed Development Profile |

Reserved: `15..255`.

## Approval and claim boundary

Human approval promotes these entries from proposed values to approved Development Profile values. It does not create permanently frozen wire allocations. That later gate requires closed schemas, literal vectors, cross-verifier agreement, and a separate decision. Production-profile values remain deferred. Task 0 implements no federation runtime and supplies no live federation, governance, interoperability, privacy, or production evidence.
