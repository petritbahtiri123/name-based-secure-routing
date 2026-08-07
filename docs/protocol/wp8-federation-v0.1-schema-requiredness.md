# WP8 Federation v0.1 Schema Decision Supplement

> **APPROVED DEVELOPMENT PROFILE PROPOSAL — REQUIRES HUMAN APPROVAL**

**Decision:** `WP8-SCHEMA-REQUIREDNESS-01`
**Baseline:** `4c8c9ef9963e5cf2e0f9037a9d35b6555bb27776`
**Runtime authority:** none; Task 2 remains prohibited until this proposal is
human-approved.

This supplement selects new Development Profile schema decisions where
F1–F119 intentionally stopped short. Those selections are proposals, not
facts derived from the historical source. The complete field-level authority
is the machine registry
`registries/federation-v0.1-schema-proposal.json`; the generated exact table is
`wp8-federation-v0.1-schema-allocation.md`.

## Lifecycle classification

| Class | Objects | Rationale |
|---|---|---|
| Stateful lineage | OperatorRegistryRecord, KeyAuthorizationRecord, NameOwnershipRecord, DelegationRecord, FederationTrustBundle, OperatorEndpointRecord, TypedRevocationRecord, OperatorLifecycleRecord | Each is durable mutable authority or trust state. Genesis is generation 1/sequence 1 with no predecessor. Same-generation updates increment sequence by exactly one and bind the immediately accepted digest. A new generation starts at sequence 1 and requires the object-specific recovery, transfer, replacement, or governance evidence. |
| Snapshot/state summary | TransparencyCheckpoint | A checkpoint is an immutable tree snapshot. It carries log generation and checkpoint sequence, but continuity is established by checkpoint references and consistency proofs rather than mutation of an earlier checkpoint object. |
| Immutable proof/evidence | InclusionProof, ConsistencyProof, WitnessStatement, FederationAuthorityProof, ConflictEvidence | These are one-shot evidence. They have no object-local generation, sequence, genesis, update, or predecessor. New observations or dependency state create new bytes and a new digest. |
| Decision/context | FederationAuthorizationContext, RecoveryTransitionRecord, ConflictResolutionRecord, AppealDecisionRecord | These are immutable signed decisions or contexts. They bind affected generations/sequences where relevant but do not acquire a synthetic object-local lineage. A later decision is separate; `previous_decision_digest` is permitted only for an explicit sequential review process. |

Equal lineage version plus equal digest is idempotent `ACCEPT` with no
mutation. Equal version plus a different digest is
`QUARANTINE/ERR_EQUIVOCATION` with no authority mutation. Lower versions are
`REJECT/ERR_ROLLBACK`. Terminal identities and key IDs never resurrect or
become reusable.

## Wire types and identifiers

- Operator IDs are exactly 32-byte CBOR `bstr` values. A textual Operator ID
  appears only in an explicitly named presentation field; none exists in the
  base objects in this proposal.
- key IDs are `bstr` values of 1 through 64 bytes; digests and Service IDs are
  exactly 32-byte `bstr` values.
- request, event, proof, transition, conflict, appeal, and decision IDs are
  exactly 16-byte `bstr` values and are unique within the issuer domain.
- generations, sequences, timestamps, and enums are unsigned integers.
  Timestamps are UTC seconds in `0..253402300799`. Enums must be allocated in
  the named approved Task 1 registry or the object-local proposal table.
- canonical names are NFC UTF-8, lowercase A-label form, and at most 255
  encoded bytes. Free-form maps are forbidden.
- Service ID is exactly
  `SHA-256("NBSR-FEDERATION-SERVICE-ID-v1" || 0x00 ||
  genesis_owner_operator_id || uint16be(name_utf8_length) || canonical_name)`.
  The owner is the genesis owner, so later transfer does not change the ID.
  The canonical name is the exact NFC lowercase A-label UTF-8 form.

Every composite is closed and bounded. Its numeric members, cardinality,
ordering, duplicate rule, unknown-field rule, and maximum encoded size are in
the machine registry. In particular:

- `DelegationScope` contains all eleven keys. `null` means that a dimension is
  inapplicable, never unrestricted. Port ranges are ascending, disjoint, and
  non-adjacent; lists are sorted and duplicate-free. Intersection is fieldwise
  and a child must equal or narrow every dimension.
- `AuthorityTarget` is exactly object class, bounded identifier, and optional
  canonical digest.
- `FederationDependencySet` is a sorted unique array of
  `[object_class, canonical_digest]`; its digest is SHA-256 over the complete
  deterministic CBOR array.
- authority, transparency, signature, threshold, organization, version, and
  lifecycle-transition structures use only their registered numeric keys.

Every object entry also freezes `maximum_canonical_payload_bytes`; every
complete signed object remains bounded by 65,536 bytes. Task 2 payloads are
bounded to 32,768 bytes. Exceeding either bound is
`REJECT/ERR_RESOURCE_LIMIT` before signature or state processing.

Thresholds count valid distinct authority identities, not array entries. Each
`SignatureReference` binds authority class, purpose, protected `kid`, the
digest of the complete COSE Sign1, and the exact signed payload digest. Every
reference must bind the current object's canonical payload. A `kid` and
authority identity may appear only once in a signer set and may not be reused
across required sets. Sorting, cardinality, or duplicate COSE bytes alone can
never satisfy a threshold.

## CBOR key model and extensions

The proposed base range is `1..127`. Keys `1..31` are common only where name,
type, bounds, and semantics are identical. Keys `32..127` are object-specific.
Keys `128..999` are reserved and reject. Registered extension IDs are
`1000..65535`; they never appear directly as base keys.

| Key | Common field |
|---:|---|
| 1 | object_type |
| 2 | object_version |
| 3 | issuer_id |
| 4 | generation |
| 5 | sequence |
| 6 | not_before |
| 7 | expires_at |
| 8 | previous_digest |
| 9 | effective_at |
| 31 | extensions |

`extensions` is the only optional extension container. It is a canonical map
from registered extension ID to a closed `ExtensionEntry` containing keys 1
`extension_version`, 2 `critical`, and 3 `canonical_value`. The value is an
opaque canonical CBOR byte string of at most 4,096 bytes. At most 16 entries
are permitted. Unknown critical entries reject. Unknown non-critical entries
may be ignored only when they cannot affect authority and must be preserved
byte-for-byte. Unknown direct base keys always reject.

## Recovery substitution

Recovery substitution is deny-by-default. It is proposed only for:

- OperatorRegistryRecord;
- KeyAuthorizationRecord;
- NameOwnershipRecord;
- DelegationRecord;
- FederationTrustBundle;
- OperatorEndpointRecord; and
- OperatorLifecycleRecord.

Every allowed substitution requires canonical `RECOVERY`, an accepted
`RecoveryTransitionRecord` binding the exact object class and scope, the
object-specific recovery/registry/witness thresholds, a generation exactly
one higher than the accepted lineage, and restore-or-narrow scope. A
compromised, retired, superseded, or terminal signer cannot authorize its own
recovery. Trust expansion requires a separate ownership or governance
authorization. All other object classes reject a recovery signer.

## Task 2 closed schemas

### OperatorRegistryRecord

Keys 1–8 and 31 use the common meanings. Object keys are: 32 `operator_id`,
33 `identity_root`, 34 `organization_binding`, 35 `federation_scope`, 36
`lifecycle_state`, 37 `revocation_reference`, and 38
`transparency_reference`, and 39 `recovery_stage`. All except predecessor,
extensions, and the contextual recovery stage are required.
Predecessor is forbidden at genesis and required thereafter. Revocation uses
an explicit `null` for no accepted revocation; absence is invalid.

The operator ID is immutable. Organization binding is exactly public-name or
private-domain commitment mode. Scope changes during ordinary updates must
maintain or narrow authority; expansion requires separately validated
registry/governance authorization. Normal signing requires the Development
Profile registrar 1-of-1 plus witnesses 2-of-3 using registry-signing and
witness purposes. The protected COSE `kid` for each signature must resolve to
exactly one authorized live key, authority class, purpose, operator, validity,
generation, and sequence. Operational endpoints, origins, private
infrastructure, subscriber data, and recovery secrets are forbidden.

Operator lifecycle transitions exactly reuse Task 1's frozen
`operator_lifecycle_semantics.allowed_transitions` table. APPLIED and
VERIFICATION_PENDING advance or reject; VERIFIED advances to PROVISIONAL or
ACTIVE or rejects; PROVISIONAL and ACTIVE may suspend, quarantine, recover,
retire, or terminally revoke as listed; SUSPENDED may additionally return to
ACTIVE; QUARANTINED may enter RECOVERY; RECOVERY may return to ACTIVE only
after the re-entry gate, or retire/terminally revoke. RETIRED,
TERMINALLY_REVOKED, and REJECTED have no successors.
`recovery_stage` is required exactly for RECOVERY and forbidden otherwise.

### KeyAuthorizationRecord

Keys 1–8 and 31 use the common meanings. Object keys are: 32 `operator_id`,
33 `key_id`, 34 `public_key`, 35 `key_purpose`, 36 `key_lifecycle`, 37
`authorizing_authority`, 38 `revocation_state`, 39 `revocation_reference`, and
40 `recovery_transition_digest`.

One record authorizes exactly one Ed25519 public key for one approved purpose.
Operator ID and purpose are immutable across generations. Key ID and public
key are immutable within one generation but must change for recovery of an
affected key at a new generation. A normal genesis or lifecycle update is
signed 1-of-1 by the live identity root with the
`IDENTITY_ROOT` purpose. Recovery uses 2-of-3 live recovery keys, an accepted
transition digest, registry verification, and a strictly higher generation.
The protected `kid` must resolve uniquely to the selected signer and purpose.
Cross-purpose, ambiguous, expired, compromised, retired, superseded, or
revoked signers reject. A terminal key ID is permanently non-reusable.
Revocation state is always explicit; its reference is non-null exactly when
revoked. Recovery transition digest is forbidden for ordinary genesis/update
and required for recovery generation.

Key lifecycle transitions are closed: NEXT may become ACTIVE or REVOKED;
ACTIVE may become RETIRING or REVOKED; RETIRING may become RETIRED or REVOKED;
RETIRED and REVOKED are terminal. Recovery creates a new generation in NEXT;
it does not reactivate the old key material or key ID.

## Literal fixture package

`vectors/federation-v0.1-schema-proposal/literal-fixtures.json` contains 28
specification-authored payloads: thirteen OperatorRegistryRecord cases,
including both recovery-stage boundaries, eleven KeyAuthorizationRecord cases, plus valid/invalid
checkpoint-generation and consistency-proof continuity cases. Each records exact
deterministic CBOR hex, SHA-256, expected outcome, reason, mutation flag, and
external validation context. The tiny encoder in
`scripts/render_federation_schema.py` implements only unsigned integers,
byte/text strings, arrays, maps, booleans, and null. It imports no future
Federation codec and sorts map keys by RFC 8949 deterministic encoded-key
order. The proposal renderer's `--check` mode recomputes every artifact.

`scripts/verify_federation_schema_fixtures.py` is a separate verifier. It uses
the frozen Core deterministic decoder/encoder rather than the proposal
renderer, independently checks canonical bytes and digests, checks object
types and closed key sets, and validates accepted Task 2 required fields,
Service ID derivation, predecessor/recovery context, lengths, lifecycle, and
revocation binding.

These payload bytes are object payloads, not complete COSE envelopes. Signer,
protected-`kid`, current-state, compromise, and terminal-reuse facts are
literal validation context because Task 2 COSE wrapping is not yet authorized.

## Approval and closure

The proposal removes the requiredness, key-allocation, signer-substitution,
and literal-byte choices that previously forced Task 2 to invent semantics.
Before human approval, `WP8-SCHEMA-REQUIREDNESS-01` remains
`PROPOSED-CLOSURE/PENDING-HUMAN-APPROVAL`, and Task 2 remains blocked. Human
approval changes the decision to `CLOSED` without authorizing any broader Task
2 or later runtime work; Task 2 still requires its own explicit approval.
