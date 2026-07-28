# OriginSet compatibility and authority decision

**Decision ID:** D7 proposal

**Status:** Human approval required

**Date:** 2026-07-28

**Scope:** Architecture placement, authority, trust, publication-mode mapping,
rollback, and future wrapper direction only

**Runtime authorization:** None. This decision package does not authorize
runtime implementation.

## Decision to review

Adopt a two-layer OriginSet design:

1. **Derived OriginSet:** an internal WP2/WP3 model built from constrained
   legacy or delegated reachability metadata. It is not serialized and does
   not cross an NBSR protocol boundary.
2. **Native OriginSet:** a future signed NBSR publication object. NBSR-native
   OriginSet is a Core v0.2 candidate, not a Core v0.1 extension.

This is the smallest change that lets WP2 use deterministic origin metadata
without inventing premature wire bytes or weakening the frozen Core.

## Alternatives considered

### A. Internal model now, Core v0.2 native object later — recommended

WP2 and WP3 use a bounded immutable Derived OriginSet behind an internal API.
The future native object receives a versioned schema, registry review, signing
profile, and interoperability vectors under Core v0.2.

**Advantages:** zero Core v0.1 impact, no false interoperability promise,
supports deterministic legacy work, and gives native publication a clean
review boundary.

**Cost:** native publication remains unavailable until the Core v0.2 gate.

### B. Add OriginSet as a Core v0.1 extension — rejected

The six D6 signed-object schemas are closed and Core v0.1 has no OriginSet
message or object wrapper. Adding keys, a critical extension, message code, or
COSE wrapper would change the approved compatibility surface.

**Reason rejected:** the change is not demonstrably backward-compatible and
would silently weaken the D1-D6 freeze.

### C. Keep OriginSet internal forever — rejected

This would support legacy reachability but could not provide interoperable
NBSR-native owner publication, delegation, revocation, or federation.

**Reason rejected:** it does not satisfy the V3.6 migration target.

## D7-1 — Compatibility placement

If approved:

- Derived OriginSet is an internal WP2/WP3 model.
- It is not serialized, signed as an object, cached as protocol bytes, or sent
  in a Core v0.1 ControlEnvelope.
- It is not a Core v0.1 extension.
- Native OriginSet belongs to a separately versioned Core v0.2 proposal.
- WP2 may build deterministic Derived OriginSet fixtures only after a separate
  runtime-task approval.

This proposal allocates no new numeric key, no new message code, no new error
code, no new state or transition, no critical extension, and no new Core v0.1
COSE wrapper.

## D7-2 — Authority and trust contexts

Authority is mode-specific. Reachability does not confer publication authority.

### LEGACY_DNS

The local NBSR adapter is the local derivation authority for a Derived
OriginSet. It records:

- the requested Service Name and accepted ServiceRecord generation;
- DNS questions, aliases, RRsets, TTLs, and resolver provenance;
- DNSSEC status as secure, insecure, bogus, or indeterminate;
- Web PKI validation results for applicable TLS origin candidates;
- deterministic endpoint-policy decisions; and
- derivation time, expiry, and deterministic content digest.

The adapter does not become the service owner. DNSSEC authenticates DNS data,
and Web PKI authenticates an applicable legacy TLS endpoint; neither can mint
an NBSR ServiceRecord, RouteGrant, delegation, or native OriginSet.

### HYBRID

Legacy DNS and delegated Destination Edge or connector metadata may contribute
reachability candidates. Delegated metadata is accepted only inside a
caller-supplied trust context bound to:

- Service Identity and ServiceRecord generation;
- delegating owner or authority;
- authorized issuer role;
- allowed publication mode and endpoint scope;
- validity, generation, sequence, and revocation state; and
- the consuming operator or federation boundary.

A Destination Edge or connector has no authority merely because it can reach
the origin. It needs explicit delegation from the ServiceRecord owner or an
approved authority chain. Internal authenticated transport is evidence about
the peer, not automatic publication authority.

### NBSR_NATIVE

The default authority root is the ServiceRecord owner. A native publisher is:

1. the ServiceRecord owner; or
2. an explicitly delegated Destination Edge, connector, or publication
   service whose delegation is service-bound, scope-bound, time-bound,
   generation-bound, and revocable.

Trust resolution occurs only inside the caller-supplied service/federation
trust context. An OriginSet `kid` cannot be a global identity, filesystem
lookup, network locator, or self-authenticating authorization.

## D7-3 — Publication-mode relationship

The frozen D6 ServiceRecord `publication_mode` is owner policy. The V3.6 mode
is the observed reachability-publication lifecycle. The policy value is not a wire alias for the observed lifecycle mode.

| Frozen D6 ServiceRecord policy | Allowed V3.6 lifecycle mode |
|---|---|
| `legacy` | `LEGACY_DNS` |
| `dual-published` | `LEGACY_DNS`, `HYBRID`, or `NBSR_NATIVE` |
| `nbsr-preferred` | `HYBRID` or `NBSR_NATIVE`; constrained legacy fallback remains separately gated |
| `nbsr-secure-only` | `NBSR_NATIVE` only |

Additional rules:

- `dual-published` permits coexistence but still applies V3.6 precedence:
  valid native, valid delegated metadata, constrained DNS, otherwise fail
  closed.
- `nbsr-preferred` does not approve legacy fallback during outage; that
  behavior remains a separate human decision.
- `nbsr-secure-only` rejects DNS-derived or undelegated reachability for new
  channels.
- A policy transition cannot resurrect an expired, revoked, or superseded
  origin generation.

## D7-4 — Generation, sequence, rollback, and equivocation

For each service and authorized issuer context:

1. bind origin state to the accepted ServiceRecord generation;
2. persist the highest accepted generation and sequence for the origin issuer;
3. compute a deterministic digest over the normalized OriginSet content;
4. accept a higher authorized generation/sequence only after all validation;
5. same sequence and same deterministic digest is idempotent;
6. same sequence and different digest is equivocation and must fail closed;
7. lower generation or sequence is rejected;
8. retain revocation and replacement tombstone state long enough to prevent
   rollback across restart, replication, and policy changes; and
9. a missing or stale replica cannot resurrect an earlier accepted set.

Publisher conflicts are retained as security evidence. Whether a later
transparency or quorum process can select a winner remains a Core v0.2/federation
decision. WP2 does not invent that process.

## D7-5 — Proposed Core v0.2 wrapper

The proposed Core v0.2 wrapper is:

- an immutable deterministic-CBOR OriginSet payload with no embedded
  signature;
- exclusively wrapped by COSE Sign1;
- signed by the owner or explicitly delegated publisher;
- verified using an opaque `kid` only inside the caller-supplied authorized
  service/federation trust context; and
- bound to the ServiceRecord generation, origin generation, sequence,
  validity, issuer role, and rollback/equivocation state.

This wrapper is not approved by D1-D6. D2's Ed25519 COSE Sign1 constraints are
a candidate profile to reuse, but OriginSet is a new object class. The exact
payload keys, message code, kid binding, and vectors require separate approval.
No implementation may infer them from this proposal.

## Safe replacement behavior

An accepted candidate does not trigger blind delete-and-replace:

1. authenticate provenance or issuer;
2. validate policy, generation, sequence, digest, validity, and endpoint
   bounds;
3. validate and health-check new endpoints under an approved trust model;
4. use valid replacements for new Service Channels;
5. preserve or drain existing streams according to approved policy; and
6. remove old endpoints only after bounded drain or explicit invalidation.

Origin updates preserve the Synthetic IP mapping and never expose an Origin
Endpoint to the client.

## Compatibility impact

| Surface | D7 proposal impact |
|---|---|
| D1 deterministic CBOR | Unchanged; future native payload may reuse it only after Core v0.2 approval |
| D2 COSE Sign1 | Unchanged; future OriginSet wrapper is a new approval |
| D3-D6 registries and schemas | Unchanged |
| 17 message codes | Unchanged |
| 19 error codes | Unchanged |
| Frozen state machines | Unchanged |
| WP2 | May later implement internal Derived OriginSet after runtime approval |
| WP3 | May later consume only the internal validated model |
| WP6/Core v0.2 | Owns native serialization, authority exchange, replication, and federation behavior |

## Approval ballot

Human approval is required separately for:

1. D7-1 internal/Core v0.2 placement;
2. D7-2 authority hierarchy and caller trust context;
3. D7-3 publication-mode policy mapping;
4. D7-4 rollback, equivocation, and tombstone rules; and
5. D7-5 future COSE Sign1 direction.

Approval of D7-1 through D7-4 would permit planning the internal model but
would not authorize runtime code. Approval of D7-5 would approve only the
wrapper direction; numeric schemas, messages, `kid` binding, vectors, and
implementation would still require dedicated review.
