# WP8 Federation v0.1 direction and decision register

**Status:** Approved architecture direction; ready for implementation planning
and Development Profile freeze work. This is not a Federation v0.1 wire
freeze, public/global production authorization, or interoperability claim.

**Historical decision source:** `NBSR WP8 Federation Decisions and Design
Questions.txt`, reviewed 2026-08-05, 2,664 lines, SHA-256
`6058485d07d9c827c0cb62dad325fb389b213e35801c0799414bb6338d89848e`,
was not repository-accessible during Task 0. The repository-contained
`wp8-federation-v0.1-decisions.md` now states F1-F119 and V1-V6 individually
and is the reviewable proposed authority. The digest remains provenance only.

**Repository baseline inspected:** branch `codex/nbsr-v3-wp0-wp1`, commit
`b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914`. The checked-in Core v0.2
manifest SHA-256 at that commit is
`d4cc06347be4ce7d4f118c004130a1ac7ab9a7d5fda6de3354fbb26bf72a3eeb`.

## Normative precedence

1. Frozen Core v0.1 D1-D6 schemas, registries, COSE profile, and state
   semantics remain unchanged.
2. Approved Core v0.2 candidate documents, D8 version selection, checked-in
   vectors, and the Node verifier define the candidate session/control base.
3. Repository-contained F1-F119 and validation corrections V1-V6 in
   `wp8-federation-v0.1-decisions.md` define the proposed WP8 architecture.
4. The future Federation v0.1 Development Profile freezes exact encodings,
   identifiers, bounds, registries, authority matrices, and error precedence.
5. V2 corrections override an earlier general statement only for the named
   conflict. They do not rewrite historical Core decisions.

No implementation may infer a missing wire value from prose, reuse a Core
numeric namespace, add fields to a frozen Core object, or turn a development
default into a production constant without a reviewed profile decision and
vectors.

## Imported approved decisions

The external decision record is incorporated by digest. Its decision groups
are authoritative as follows:

| Decisions | Frozen direction |
|---|---|
| F1-F8 | Hybrid private/public operator identities; canonical binary and textual representations; stable self-certifying identity derived from immutable genesis commitment; public registration and verified organization metadata; hierarchical independent IDs; permanent non-reuse and signed lifecycle continuity. |
| F9-F15 | Offline stable identity root; strictly single-purpose operational keys; Ed25519-only current profile; mandatory operational validity/rotation; production custody requirements; root- or recovery-authorized Key Authorization Records. |
| F16-F26 | Registry-rooted name ownership; owner-controlled, composite, scope-narrowing delegation; bounded acyclic sub-delegation; monotonic validity, revocation, and hash-linked continuity; one authoritative owner with multiple explicit operators. |
| F27-F34 | Unified registration/onboarding; existing Internet ownership evidence as bootstrap; stable Service ID; multi-operator delivery; dual-authorized transfer; restricted threshold recovery. |
| F35-F46 | Trust-critical transparency only; privacy-preserving commitments; federated append-only logs; signed checkpoints, inclusion/consistency proofs, witnesses, gossip, split-view containment, and isolated private transparency domains. |
| F47-F60 | Canonical scoped trust bundles; scope-authorized signatures; automated reconciliation; hierarchical restrictive composition; explicit key lifecycle; bounded overlap; monotonic/hash-linked continuity; rollback resistance; bounded skew/staleness; emergency revocation and threshold recovery; transparency verification. |
| F61-F69 | Federation discovery inside the NBSR Name Plane; DNS/HTTPS/static sources provide candidates only; cryptographically bound operator endpoints; signed freshness caching; conflict reconciliation; explicit bilateral and private-consortium modes. |
| F70-F78 | Full authority-chain validation; independent source and destination authorization; compatible checkpoint synchronization; exact bilateral operator/service binding; separate FederationAuthorizationContext beside immutable RouteGrant; selective invalidation and minimal disclosure. |
| F79-F85 | Anti-enumeration discovery; privacy-aware transparency; subscriber-blind delegation discovery; scoped pseudonyms; minimum inter-operator audit; session-unlinkable abuse evidence with controlled escalation. |
| F86-F94 | Typed revocation; reason-dependent terminal state; permanent tombstones; bounded degraded/LKG operation; explicit outage matrix; severity-based session enforcement; complete operator quarantine, recovery, and re-entry. |
| F95-F103 | Tiered object/control-plane/end-to-end conformance; Go clean-room second implementation; comprehensive deterministic and stateful vectors; exact outcomes and errors; resource/timing tests; byte, object-exchange, live control-plane, and end-to-end gates; reproducible independence evidence. |
| F104-F111 | Federation v0.1 is a separately versioned extension over the ratified Core v0.2 candidate; dedicated message/object namespaces; closed critical-field rules; safe unsupported behavior; explicit WP7 static-trust compatibility; no automatic federation-to-static downgrade. |
| F112-F119 | Multi-stakeholder governance; neutral registry; verifiable lifecycle; evidence-first conflicts; separate appeal and recovery; no unilateral root control; risk-based authority/witness thresholds; sponsor anti-capture rules. |

Canonical federation object names are exactly:

1. `OperatorRegistryRecord`
2. `KeyAuthorizationRecord`
3. `NameOwnershipRecord`
4. `DelegationRecord`
5. `FederationTrustBundle`
6. `TransparencyCheckpoint`
7. `InclusionProof`
8. `ConsistencyProof`
9. `WitnessStatement`
10. `OperatorEndpointRecord`
11. `FederationAuthorityProof`
12. `FederationAuthorizationContext`
13. `TypedRevocationRecord`
14. `ConflictEvidence`
15. `OperatorLifecycleRecord`
16. `RecoveryTransitionRecord`
17. `ConflictResolutionRecord`
18. `AppealDecisionRecord`

Descriptive aliases do not create additional schemas.

## Selected implementation strategy

Three approaches were evaluated:

- A broad federation runtime before schema freeze is rejected because it would
  create implementation-defined wire semantics.
- Documentation-only roadmap work is rejected because it would leave the next
  session to rediscover exact repository boundaries.
- The selected strategy is freeze-first and vector-first: ratify the Core v0.2
  base, freeze one Development Profile, freeze schemas/registries, generate
  deterministic vectors, implement the Python reference, then implement Go
  clean-room, and only then bind live Rust transport behavior.

## Development Profile freeze proposal

The first implementation task must ratify these proposed values in a dedicated
decision before runtime code uses them:

### Base and profiles

- Required Core version: `2`.
- Core baseline repository commit:
  `b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914`.
- Core vector manifest SHA-256:
  `d4cc06347be4ce7d4f118c004130a1ac7ab9a7d5fda6de3354fbb26bf72a3eeb`.
- Federation extension ID: `1`; extension version: `1`.
- Development profile: `nbsr-federation-dev-v1`.
- Explicit static compatibility profile: `nbsr-static-trust-v1`.
- Signature profile: tagged COSE Sign1, protected `alg=-8`, protected `kid`,
  empty external AAD, Ed25519 only, matching the current Core profile.
- Hash profile: SHA-256 only.

### Operator identity

- Genesis key encoding: one algorithm discriminator byte `0x01` followed by
  the raw 32-byte Ed25519 identity-root public key.
- Commitment input: ASCII
  `NBSR-FEDERATION-OPERATOR-ID-v1` followed by `0x00` and the 33-byte genesis
  key encoding.
- Binary Operator ID: the 32-byte SHA-256 commitment digest.
- Text Operator ID: lowercase Bech32m using HRP `nbsr`, encoding exactly the
  same 32 bytes; uppercase or mixed-case input is rejected. The resulting
  63-character value fits the existing 64-character textual identifier bound.
- Operational-key rotation does not change the genesis commitment or Operator
  ID. Continuity-preserving recovery retains it at a higher identity
  generation; lineage-breaking recovery tombstones it and creates a new ID.
  A retired or terminally revoked ID is never reused.

### Shared hard bounds

- Unsigned counters: `0..2^64-1`; generations and sequences start at `1`.
- Timestamps: `0..253402300799`.
- Encoded signed object/extension message: at most 65,536 bytes.
- CBOR depth: 16; array items: 256; map pairs: 128; text: 4,096 bytes;
  byte strings: 32,768 bytes.
- Key ID: 1..64 bytes; digest: exactly 32 bytes; Ed25519 public key: exactly
  32 bytes; signature: exactly 64 bytes.
- Delegation depth: 8; verified chain objects: 16; dependency graph nodes:
  256; graph traversal depth: 16; Merkle proof path: 64 digests.
- Trust bundle: at most 256 keys, 32 roots/authorities, 32 logs, 32 witnesses,
  64 profiles, and 64 revocation sources.
- One stateful vector manifest: at most 4,096 artifacts and 1,024 scenarios;
  one scenario: at most 256 ordered steps.
- Rejected over-limit input causes deterministic `REJECT/ERR_RESOURCE_LIMIT`
  before accepted authority state mutates.

### Development timing values

These are exact deterministic Development Profile values, not production
recommendations:

- Allowed wall-clock skew: 300 seconds.
- Operational-key lifetime ceiling: 30 days.
- Normal key overlap: minimum 1 hour, maximum 24 hours.
- Checkpoint publication interval: 60 seconds; emergency publication deadline:
  30 seconds.
- Normal trust freshness: 300 seconds; degraded maximum staleness: 900 seconds.
- Cache lifetime ceiling: 300 seconds. Replay-state retention minimum: 86,400
  seconds. Terminal tombstones are permanent and non-expiring.
- Missing-evidence pending timeout: 30 seconds; quarantine reevaluation:
  300 seconds; route/channel drain ceiling: 30 seconds.
- Static recovery activation: warning at 15 minutes, hard expiry at 60 minutes;
  no automatic timer reset.

### Development thresholds

- Public-style demo global trust: five configured authorities, 3-of-5 approval,
  and three independent witnesses with 2-of-3 matching statements.
- High-risk root/threshold change: 4-of-5 authorities and 3-of-5 witnesses.
- Temporary deny-only emergency action: 2-of-5 authorities, bounded and unable
  to add or expand trust.
- Demo operator registration: one development registrar plus 2-of-3 witnesses.
- Operator recovery: 2-of-3 operator recovery approvals plus development
  registry verification and 2-of-3 witnesses.
- Private lab profile: 1-of-1 and optional witnesses, explicitly barred from a
  public/global assurance claim.

### State and result invariants

- Lower generation or sequence: `REJECT/ERR_ROLLBACK`.
- Equal version and equal canonical digest: `ACCEPT`, `state_changed=false`.
- Equal version and different digest: `QUARANTINE/ERR_EQUIVOCATION` with both
  branches retained as evidence.
- Higher version: validate signer, purpose, scope, continuity, revocation,
  transparency, freshness, and policy before atomic acceptance.
- Every result contains exactly one outcome from `ACCEPT`, `REJECT`, `PENDING`,
  `RESTRICTED`, `QUARANTINE`, and one enforcement mode from `NONE`,
  `DENY_NEW_USE`, `REAUTHENTICATE`, `DRAIN`, `TERMINATE_ACTIVE_USE`.
- Validation precedence is resource/parsing safety, canonical encoding,
  cryptographic structure/signature, identity/key purpose, schema/version,
  authority/scope, generation/sequence/continuity, revocation/terminal state,
  transparency/checkpoint, freshness/outage policy, then local policy.

## Architecture boundary

Federation v0.1 is a control-plane extension. It may reference frozen Core
objects by canonical digest, but it does not alter their fields or meanings.
`FederationAuthorizationContext` is the sole first-version federation binding
beside the immutable RouteGrant; the later schema decision must bind its digest
to the route-establishment transcript or an explicitly versioned extension
container.

The Python implementation owns normative reference semantics and vectors. The
existing Node verifier remains an independent byte/object verifier. Go is the
clean-room second federation implementation. Rust consumes only frozen
federation artifacts and authorization results at the transport boundary after
byte and state-machine agreement.

## Evidence and claim gates

- Passing Python/Node vectors permits only an object/vector agreement claim.
- Independent Go parsing, generation, and state transitions permit an
  independent federation-object/control-plane claim at the tested scope.
- Go plus Rust shared-transport live exchange permits a shared-transport
  control-plane interoperability claim, not independent end-to-end runtime.
- Independent end-to-end interoperability requires two complete independent
  stacks, role reversal, negative cases, route establishment, revocation,
  outage, quarantine, and recovery.
- A real public/global or production claim additionally requires real
  accredited governance, registry/log/witness independence, production key
  custody, deployment evidence, external review, and Internet-scale testing.

## Non-claims

This direction does not implement or claim a frozen Federation v0.1 wire
protocol, a public registry, global governance, production HSM/KMS custody,
live federation, live multi-operator routing, independent Go runtime,
independent end-to-end interoperability, Internet-Draft consensus, production
readiness, origin anonymity, DDoS elimination, or complete partition
tolerance.

## Task 0 planning errata (proposed for human approval)

Task 0 internalizes F1-F119 and V1-V6 in `wp8-federation-v0.1-decisions.md`, proposes exact allocations in `registries/federation-v0.1-development.json`, and adds a Core v0.2 baseline lock. These are proposed Development Profile values, not permanent wire allocations.

Replay-state retention minimum: 86,400 seconds. Terminal tombstones are permanent through garbage collection, restart, compaction, backup restoration, and fresh-node synchronization. Continuity-preserving recovery retains the Operator ID at a strictly higher identity generation; lineage-breaking recovery terminally tombstones it and requires a new Operator ID.

Execution is registry and schema literal vectors; Python codecs and object validation; stateful scenario manifests with literal expected outcomes; Python state-machine implementation; complete generated vectors; then Node and Go verification. The Development Profile contains the actual freeze gate. No federation runtime is implemented by Task 0.

The generic Core v0.2 verifier owns the root package except the exact
`wp4-exporter/` subtree. Its dedicated manifest and verifier own that subtree
exclusively; no file belongs to both inventories.
