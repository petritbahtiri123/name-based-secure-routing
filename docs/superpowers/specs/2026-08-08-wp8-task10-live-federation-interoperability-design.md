# WP8 Task 10 live federation interoperability design

**Status:** Human-approved design recorded for Task 10 planning.

**Baseline:** `7af982239dc8fbc67ae142037f192458c797f4d4`

## Goal and closure rule

Task 10 binds already-verified Federation v0.1 authority into the existing
native Rust/Quinn `nbsr/1` transport, proves a deterministic live two-operator
route, produces public-safe wire evidence, publishes a reproducible
conformance entrypoint and implementation-derived public draft, and closes the
remaining WP8 evidence review without changing frozen Core or Federation
authority.

WP8 is evidence-closed only if two genuinely independent wire-capable
implementations exchange the frozen route and stream protocol. A local
two-operator lab in which both peers use `nbsr-transport` proves live
federation integration across independently configured administrative domains,
but it does not prove independent route/stream wire interoperability. Python,
Node, and Go federation vector agreement proves independent federation
semantic verification only. The final evidence and status documents must keep
these claim tiers separate.

## Frozen authority and stop conditions

Task 10 consumes the approved Core v0.2 and Federation v0.1 Development
Profile artifacts exactly as they exist at the baseline. It allocates no new
wire object, message code, field, transcript, serialization, registry value,
signer authority, key purpose, trust rule, lifecycle rule, threshold, error
precedence, capability, or fallback.

Implementation stops for human review if any required behavior needs:

- a new or changed Core or Federation wire value;
- a serialized form for the internal federation-to-transport boundary;
- a new transcript or exporter layout;
- weakened validation or oracle/descriptive metadata as authority;
- a second wire peer that cannot reproduce the existing protocol without
  architectural expansion or new semantics;
- public-safe packet evidence that cannot be captured credibly; or
- a contradiction among the approved normative sources.

## Existing implementation inventory

The baseline contains one live wire implementation:
`crates/nbsr-transport`, using Quinn/rustls and the existing `nbsr/1` profile.
It implements authenticated Transport Sessions, Core v0.2 control envelopes,
RouteGrant admission, Route Context and Service Channel isolation, exporter
binding, Application Streams, lifecycle controls, and QUIC DATAGRAM support.

The Python implementation is the Federation v0.1 reference authority. The
dependency-free Node and Go implementations independently verify the immutable
Federation vector package. The Python Core v0.2 reference and Node Core v0.2
verifier implement deterministic control semantics but do not open QUIC
connections or act as live `nbsr/1` peers. WP7 is a deterministic in-process
two-operator administrative model, not a wire implementation. Consequently,
the baseline has no second independent live route/stream peer.

## Architecture

### Python federation and WP7 boundary

The Task 10 lab extends WP7 rather than creating a parallel operator model.
Operator A and Operator B retain separate Operator IDs, signing keys,
transport identities, policies, trust roots and bundles, audit logs, rate-limit
state, replay state, and destination admission state. Python validates signed
ownership and delegation, signer identity and purpose, trust and transparency
state, lifecycle and revocation, freshness, capability agreement, and the
bilateral `FederationAuthorizationContext`.

Source admission executes first and destination admission executes
independently. A source acceptance cannot mint destination authority, and a
destination acceptance cannot replace owner authority. Invalid or incomplete
state produces no transport authority and no resource allocation.

### Sealed non-wire Rust boundary

Rust adds a private-constructor `VerifiedFederationAuthorization` value. It is
an in-process implementation type, not a protocol object. It contains only
typed values already bound by verified Federation authority:

- source and destination Operator IDs;
- service ID;
- transport and port;
- Federation authorization-context digest;
- route-context digest;
- authorization validity interval;
- affected generation and sequence;
- dependency digest/set needed for selective invalidation; and
- accepted, revoked, quarantined, or otherwise fail-closed status.

Construction is available only through the federation admission module after
all invariants are validated. Tests may use an explicitly named test-only
builder. Runtime code cannot construct the value from JSON, debug labels,
expected results, or unchecked byte arrays. No serializer or decoder is added.

The exact value gates existing route admission beside the immutable
`RouteGrant`. Both must bind the same source/destination identities, service,
transport, port, route context, and current validity. A mismatch, expiry,
revoked dependency, quarantine, replay, unsupported profile, or downgrade
rejects before a channel becomes active. Stream and datagram gates accept only
the exact active channel produced by this combined admission.

### Live two-operator Rust/Quinn lab

The deterministic live lab runs two separately configured administrative
domains over loopback QUIC. It performs authenticated Transport Session
establishment, source and destination authorization, Route Context binding,
Service Channel activation, and deterministic Application Stream transfer.
Where the current transport profile supports application TLS pass-through
semantics, the lab verifies unchanged SNI/certificate expectations without
claiming Origin Endpoint forwarding that the repository does not implement.

The live lab proves that Federation-authorized state gates the existing native
wire path and that application payload is unavailable before all required
admission succeeds. It does not by itself prove independent wire
interoperability because both endpoints use the Rust implementation.

### Independent wire-peer gate

Task 10 first records that no current second wire peer exists. A minimal
independent peer may then be implemented only if it can use an independent
QUIC/TLS stack and independently encode, decode, validate, and exchange the
already-frozen `CLIENT_HELLO`, `EDGE_HELLO`, `ROUTE_OPEN`, `ROUTE_ACCEPT`,
`STREAM_OPEN`, and `STREAM_ACCEPT` bytes plus deterministic Application Stream
payload framing.

The peer must not import, execute, wrap, FFI-call, or shell out to the Rust
runtime. It must make decisions from frozen documents, registries, vectors,
authenticated session state, and typed inputs. It must reproduce the existing
ALPN, TLS identity, Core v0.2 envelope, RouteGrant proof-of-possession,
request/stream binding, and payload gating exactly.

The feasibility RED test is a role-specific live exchange against Rust using
existing frozen fixtures. If implementing the peer requires any new wire
semantics, transcript, authority, or material architecture, work stops for
human review. If no peer is completed, Task 10 may still report live federation
integration and independent semantic verification, but independent
route/stream wire interoperability remains `NOT YET PROVEN` and WP8 is not
evidence-closed.

### Rotation and compromise drills

The live/deterministic drill layer uses the existing Federation state model and
the typed transport boundary to exercise operational signer rotation,
trust-bundle rotation, old-key revocation, new-key activation, stale bundles,
stale ownership, rollback, conflicting generation, split view/equivocation,
and compromised-signer removal. Safe rotation authorizes new channels under
current authority. Stale, revoked, conflicting, or malicious state denies new
use and applies only already-frozen enforcement to existing channels.

### Packet evidence

The live Rust/Quinn path is captured with the locally available Windows
`pktmon` facility and converted to a standard public-safe capture format when
the local tool supports credible loopback capture. The procedure scopes capture
to the test flow, uses deterministic non-secret payload fixtures, and packages
no TLS keys, private keys, credentials, subscriber identifiers, or protected
Origin Endpoint.

The public evidence records visible network and QUIC/TLS metadata and explains
that ciphertext alone cannot prove application authorization, payload meaning,
or internal authority validation. Decryption material, if used locally for
debugging, is excluded from tracked artifacts. A capture that does not observe
the actual live flow or cannot be privacy-reviewed is an acceptance blocker.

### Public conformance entrypoint

A single repository entrypoint validates manifests and authority locks before
orchestrating the existing deterministic generators and checks, Python
Federation and full suites, Node federation and Core verifiers, Go tests/vet
and verifier, Rust formatting/lints/tests, WP4 exporter checks, WP7 and Task 10
live scenarios, documentation tests, dependency inspection, artifact-drift
checks, privacy/secret scans, and `git diff --check`.

Every child command is explicit. Non-zero child status fails the runner. The
summary reports exact observed pass/fail/skip counts and identifies tools or
scenarios not exercised. The deterministic path has no public DNS or Internet
dependency. The runner never upgrades a verifier-only implementation into a
wire-interoperability claim.

### Public draft and status evidence

The implementation-derived public draft documents terminology, architecture,
Operator ID, ownership/delegation, trust bundles, transparency, key purposes,
lifecycle/revocation, rollback and split-view handling, deterministic
encoding, validation/error behavior, privacy and operational considerations,
transport/session/channel relationships, conformance tiers, and
extension/versioning rules.

Normative `MUST`, `SHOULD`, and `MAY` text is separated from implementation
evidence, deployment guidance, and future work. The draft claims neither IETF
status nor production readiness. Status, README, roadmap, conformance catalog,
capture documentation, and final evidence must agree on the strongest proven
claim tier.

## Error handling and mandatory negative evidence

All federation and transport failures are fail-closed and mutation-safe.
Negative evidence covers unknown/untrusted operator, wrong Operator ID,
signing key, `kid`, purpose, service/class authority, destination operator,
service, transport, port/capability, expired or revoked authority, stale
generation/sequence, rollback, split view/equivocation, malicious/incomplete
bundle, replay, unsupported/downgraded profile, source-minted destination
authority, and destination-minted owner authority.

No application payload is forwarded before both federation admissions,
RouteGrant validation, route acceptance, channel binding, and stream acceptance
succeed. No failure path returns or logs a protected Origin Endpoint. Existing
streams survive disturbances only within the already-frozen lease,
revocation, drain, and resumption policy.

## RED-first testing sequence

1. Add inventory and claim-tier tests proving that existing Node, Go, Python,
   WP7, and Rust components are classified accurately.
2. Add Rust RED tests for construction sealing, complete binding, expiry,
   revocation, replay, downgrade, selective invalidation, and payload gating.
3. Add Python/WP7 RED tests for signed federation authority feeding separate
   source and destination admission and for every required malicious case.
4. Add the live Rust/Quinn two-operator RED scenario, then implement the
   smallest typed integration that makes it pass.
5. Add rotation and compromise RED drills and implement only required state
   transitions/adapters.
6. Add an independent-peer feasibility RED exchange. Implement a peer only
   while every byte and decision remains derivable from frozen authority;
   otherwise stop for human review.
7. Add capture validation and privacy RED tests, execute the live capture, and
   package only reviewed public-safe evidence.
8. Add conformance-runner RED tests for manifest-first execution, non-zero
   divergence, exact accounting, skips, and drift.
9. Add documentation RED tests before writing the public draft and closure
   evidence.
10. Run independent correctness/interoperability and security/privacy reviews;
    reproduce confirmed findings with RED regression tests before fixes.
11. Run the complete fresh validation matrix, stage explicit Task 10 paths,
    and create one final commit only after all applicable gates pass.

## Acceptance and claim matrix

| Evidence | Required result |
|---|---|
| Python, Node, and Go Federation vectors | Exact valid/invalid semantic parity; verifier roles stated accurately |
| Rust Federation transport binding | Verified typed authority gates the existing live route/channel/stream path |
| Two-operator live lab | Separate administrative state; successful route and deterministic payload; required negatives fail closed |
| Rotation and compromise | Safe rotation succeeds; stale, revoked, rollback, conflict, and split view fail under frozen policy |
| Packet capture | Actual supported live flow captured and privacy-reviewed, or Task 10 remains blocked |
| Independent wire peer | Actual frozen route/stream exchange with Rust; otherwise `NOT YET PROVEN` and WP8 remains open |
| Public conformance entrypoint | Reproducible, manifest-first, exact counts, non-zero on divergence |
| Public draft and evidence | Matches implemented authority and preserves all non-claims |
| Independent reviews | Correctness/interoperability `READY`; security/privacy `READY` |
| Git | One focused Task 10 commit; clean tree; no push without instruction |

## Non-claims

Task 10 does not prove production readiness, global Internet federation,
Internet-scale performance, vendor or ISP adoption, production key custody or
HSM operation, global governance, anonymity, DDoS elimination, production
SLA/SLO, or formal IETF standardization. It does not claim a second independent
transport stack unless that stack actually exchanges the frozen route and
stream protocol with Rust. Dedicated latency/performance work, deployment
expansion, demonstrations, and new protocol development remain outside scope.

## Commit boundary

The design, plan, implementation, tests, captures, conformance entrypoint,
draft, evidence, and review fixes remain uncommitted until the final validation
gate. Task 10 ends in one focused commit with preferred message
`feat(wp8): complete live federation interoperability`. No push occurs during
Task 10 without separate human instruction.
