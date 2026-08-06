# WP8 Federation v0.1 design

**Status:** Approved for implementation planning from F1-F119 and V1-V6. The
first implementation tranche is profile/schema/vector freeze work, not an
unfrozen production runtime.

## Goal

Cross the boundary from one-project behavior to a testable federation protocol
without changing frozen Core v0.1 objects or silently redefining the approved
Core v0.2 candidate. The deliverable sequence is a frozen Development Profile,
closed federation objects/messages, deterministic vectors, a Python reference
state machine, an independent clean-room Go implementation, and progressively
stronger interoperability evidence.

## Component boundaries

### Federation profile and registries

`docs/protocol/federation-v0.1-development-profile.md` will be the normative
implementation profile. It pins the Core baseline, Operator ID encoding,
extension/object/message/error/field registries, signer-authority matrix,
bounds, timing, thresholds, genesis/update rules, idempotency, and failure
precedence. Generated registry tables must be derived from one checked-in
machine-readable source and verified against the document.

### Federation object package

`nbsr/federation/` will contain small modules by responsibility: profile and
registry constants; bounded common fields; identity/key objects; ownership and
delegation; bundles; transparency; endpoints/discovery; authorization;
revocation/lifecycle/recovery/conflicts; COSE verification; and canonical
result types. Frozen `nbsr.protocol` models are imported read-only and never
modified.

All 18 object schemas are closed, versioned, canonical CBOR maps. Required,
optional-critical, and optional-non-critical fields are explicit. Unknown base
fields, unknown critical extensions, wrong types/classes, duplicate keys,
unsafe references, cycles, over-limit data, or ambiguous contextual
requiredness fail closed before state mutation.

### Reference federation state machine

A storage-neutral immutable Python state machine accepts verified signed
objects and produces one deterministic outcome, enforcement mode, reason,
state digest, dependency set, emitted-object set, and mutation flag. It retains
monotonic watermarks, terminal tombstones, equivocation branches, accepted
checkpoints, proof state, pending evidence, and selective dependency indexes.
Persistence is a separate bounded secure-file adapter using existing atomic
private-file patterns; parser and planner code never mutate live systems.

### Transparency and witnesses

The development implementation uses a deterministic RFC-6962-style binary
Merkle tree with profile-frozen domain separators, SHA-256, signed checkpoints,
inclusion/consistency proofs, and witness statements. Public-style demo
thresholds are simulated with distinct configured keys and organizational
labels. This is evidence for protocol semantics, not independent real-world
logs or governance.

### Vector and conformance package

`vectors/federation-v0.1/` follows the existing closed-manifest model. Each
artifact records exact length/digest, object/flow class, applicability classes,
fixed time, dependencies, expected outcome/reason/enforcement, expected state
digest, and permitted side effects. Generation is deterministic and check mode
must prove byte identity.

Node independently verifies manifest, CBOR/COSE, object bytes, digests, Merkle
proofs, and static outcomes. Stateful reference scenarios remain Python until
the clean-room Go implementation independently reproduces them.

### Clean-room Go implementation

`implementations/go-federation/` is built only from normative documents,
registries, vectors, public test keys, and external standards. It must not
import, execute, query, mechanically translate, or inspect Python/Rust/Node
runtime logic as a behavioral oracle. Ambiguity becomes a public erratum and a
new vector before either implementation changes behavior.

### Rust transport integration

Rust integration starts only after Python, Node, and Go agree on frozen
objects. The transport consumes a verified `FederationAuthorizationContext`
digest and authenticated capability agreement; it does not parse arbitrary
global governance state inside the stream gate. Existing source/destination
admission, exporter binding, quotas, drain, revocation, and origin privacy
remain mandatory.

## Data flow

1. Core v0.2 is selected exactly under D8 and authenticated.
2. Peers agree on one Federation Extension version and critical capabilities.
3. Discovery returns candidates only.
4. Operator, endpoint, ownership, delegation, bundle, checkpoint, proof, and
   revocation objects validate independently against exact profile authority.
5. Source and destination each derive an exact bilateral authorization result.
6. The accepted `FederationAuthorizationContext` digest is bound beside the
   immutable RouteGrant at the approved route-establishment boundary.
7. The Name Node returns only scoped Synthetic IP state; clients never receive
   operator, federation endpoint, or Origin Endpoint data.
8. Selective updates invalidate only dependent grants/channels. Compromise,
   equivocation, split view, or terminal state applies the exact enforcement
   mode and preserves evidence.

## Failure and recovery model

Missing evidence may become bounded `PENDING`; stale but previously verified
state may become `RESTRICTED` only inside the profile's LKG window. Invalid
evidence, rollback, authority expansion, known revocation, unsupported critical
semantics, or downgrade attempts are `REJECT`. Same-version conflicts,
split-view evidence, uncertain compromise scope, or invalid recovery lineage
are `QUARANTINE`.

No outcome creates partial authority. Retry is idempotent. Terminal identities,
keys, revocations, and tombstones do not resurrect. Recovery creates a new
generation through the approved threshold path and never changes the stable
genesis-derived Operator ID. Static trust is a separate pre-authorized profile,
never an automatic fallback.

## Testing and review

Every behavior change follows observed RED, minimal GREEN, broader affected
tests, and a focused commit. Coverage includes canonical boundaries, every
signature and purpose binding, genesis/update requiredness, rollback,
equivocation, rotation, split view, revocation, recovery, stale/outage state,
unknown critical fields, graph/proof/resource abuse, deterministic retries,
privacy, downgrade resistance, and exact error precedence.

Independent reviews occur after the schema/vector tranche, reference state
machine, Go object/control-plane tranche, and live integration tranche.
Confirmed issues receive failing regression tests before fixes. Claims are
limited to the strongest completed evidence gate.

## Delivery stages

1. Ratify Core v0.2 and freeze Federation v0.1 Development Profile.
2. Freeze object/message/field/error registries and all 18 schemas.
3. Generate deterministic object and stateful vector packages.
4. Implement Python reference validation/state transitions.
5. Extend independent Node byte/object verification.
6. Implement clean-room Go object and control-plane semantics.
7. Integrate the federation context with Rust Core v0.2 transport.
8. Run role-reversed live control-plane tests, then progressively stronger
   routing, revocation, outage, quarantine, and recovery tests.
9. Publish evidence, draft protocol text, and maintain explicit non-claims.

## Explicit exclusions from the first execution plan

The first plan does not operate a real global registry, claim accredited
organization verification, require a vendor HSM, deploy public logs, allocate
Internet-wide authority, promise anonymity or DDoS elimination, implement a
second complete transport stack, publish a standards-consensus Internet-Draft,
or claim production readiness.
