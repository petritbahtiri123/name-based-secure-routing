# Tranche 6: Resolution to Shared Synthetic IP to Secure Routing

**Status:** Approved for implementation. The human-selected Tranche 6 adapter is an explicit local proxy using SOCKS5 domain-name and HTTP CONNECT correlation. No transparent-platform claim is implied.

## Purpose

Tranche 6 connects ordinary application name resolution to the existing production Go authority, Transport Session (TS), Service Channel (SC), Stream Credit, and Application Stream stack. It adds the missing resolution-provenance prefix without changing any frozen NBSR wire message.

The required end-to-end path is:

```text
configured NBSR Resolution IP
  -> ordinary DNS query
  -> canonical NBSR resolution
  -> SHA-256 canonical-name ServiceDigest
  -> bounded ephemeral ResolutionContext and MappingID
  -> one shared local Synthetic IP returned to the application
  -> ordinary application connection
  -> adapter-supplied exact FlowContext
  -> MappingID lookup and reference acquisition
  -> existing RouteIntent / AuthorityKey / verified RouteGrant
  -> existing TS / SC / Stream Credit / Application Stream
```

## Approved decisions

The following decisions are authoritative for Tranche 6 and supersede earlier per-active-service Synthetic-IP recommendations where they conflict:

1. Devices use a fixed configured NBSR Resolution IP through the normal DNS layer.
2. Every NBSR-resolved name returns one shared application-facing Synthetic IP; Tranche 6 does not allocate one IP per service.
3. The Synthetic IP means only “enter NBSR Secure Routing.” It is not identity, authority, policy, or a service selector.
4. `ServiceDigest = SHA-256(canonical_name ASCII bytes)` after existing canonical-name normalization. It is never derived from opaque `service_id`.
5. Every successful resolution creates a bounded, immutable, ephemeral local resolution/mapping context.
6. `MappingID` and `FlowContext` are local correlation state and are never transmitted.
7. The adapter must bind each application flow to exactly one resolution context before authority selection; IP+port, recency, and mutable current-service state are forbidden.
8. HTTP Host and TLS SNI are not generic service-selection or authority inputs.
9. Platform interception stays outside the core; the core consumes an adapter-supplied `FlowContext`/`MappingID`.
10. Resolution, mapping, AuthorityKey, verified RouteGrant, and SC service digests must be equal or fail closed.
11. Opaque `ServiceIdentity`/`service_id` remains distinct from canonical name and digest and is preserved from signed resolution state.
12. Live mappings are immutable. A material service or route-context change creates a new MappingID.
13. Effective mapping expiry is the earliest authoritative expiry, optionally shortened by a local safety ceiling.
14. Expiry rejects new acquisition immediately, retains referenced bookkeeping, and never migrates or replays existing admitted streams.
15. Fresh materially changed resolution state creates a new mapping rather than mutating an old one.
16. Mapping IDs, resolution contexts, flow contexts, correlations, and indexes restart empty. Only shared-IP configuration may persist.
17. Mapping lookup feeds the existing authority/session/stream stack; there is no second routing path.
18. RouteGrant, ACP, TS, SC, `channel_id`, ServiceHandle wire behavior, credits, and Application Stream wire formats do not change.
19. Resolution, mapping, pending correlation, and flow state have explicit entry/byte/work limits, no live eviction, and deterministic overload failure.
20. Multiple simultaneous services share the one Synthetic IP but every admitted flow resolves to exactly one local context.
21. Transport and port remain RouteIntent/authority dimensions; identical shared IP and port may serve unrelated contexts.
22. Missing, stale, expired, or ambiguous correlation fails closed without direct-routing fallback.
23. Applications retain the conceptual experience of ordinary resolve then connect and do not handle NBSR cryptographic/session identifiers.
24. Demo packaging, cleanup, and orchestration are outside Tranche 6.

## Current repository evidence and reuse

### Reuse unchanged

- Python WP2 establishes the semantic sequence presentation-name canonicalization -> signed `ServiceRecord` -> immutable `RouteIntent` -> bounded `ResolutionBinding`. It remains reference semantics, not production ownership to port wholesale.
- Canonicalization uses IDNA ASCII, lowercase conversion, one trailing-dot removal, DNS-label validation, the 253-byte limit, and IP-literal rejection.
- The frozen Core rule defines `name_digest`/`ServiceDigest` as SHA-256 over canonical-name ASCII bytes.
- Go `corestate.Store` already provides monotonic non-reused `MappingID`, entry/byte caps, reference acquisition/release, exact-expiry rejection, referenced-expiry retention, and deterministic removal.
- Go authority already verifies `AuthorityKey.ServiceDigest` against signed RouteGrant field 2 and exact `ServiceIdentity` against the RouteIntent/RouteGrant.
- Go session ownership already binds the same service identity, service digest, RouteGrant digest, authority generation, proof thumbprint, `channel_id`, and channel generation into SC state.
- Existing TS, SC, Stream Credit, and Application Stream ownership is reused without wire changes.

### Do not reuse as production architecture

- Python `SyntheticAddressPool` allocates one address pair per hostname, which conflicts with the approved single shared IP.
- Python `RouteTable` and `ResolutionContextStore` use synthetic address as a reverse index. That cannot disambiguate shared-IP same-port services.
- `windows_agent.LoopbackInterceptor` stores one hostname per address and keys listeners by IP+port. With a shared IP this would collapse contexts and is forbidden.
- Prototype FastAPI/JWT/name-relay authority and Host/SNI behavior are not the production authority path.

## Exact production data models

Names below are the planned Go API. Fixed-width digest aliases may be shared with `corestate` through explicit conversions; no wire type is added.

### Canonical resolution result

```go
type CanonicalName string

type ResolutionResult struct {
    CanonicalName   CanonicalName
    ServiceDigest  corestate.ServiceDigest
    ServiceIdentity string
    RouteIntent     authority.RouteIntent
    ExpiresAtUnix   uint64
}
```

Construction, rather than exported field mutation, enforces:

- canonical ASCII name validation;
- exact SHA-256 digest derivation;
- nonempty valid `ServiceIdentity` equal to `RouteIntent.ServiceIdentity`;
- exact canonical RouteIntent bytes and digest validation through the existing authority validator;
- effective expiry equal to the minimum of the signed resolution/record expiry, RouteIntent expiry, and optional configured safety ceiling;
- no accepted zero digest or already-expired result.

### Mapping / ResolutionContext

The production mapping is the local `ResolutionContext`; one immutable `MappingSnapshot` is sufficient rather than duplicating an independent cache object.

```go
type MappingSpec struct {
    CanonicalName    string
    ServiceIdentity  string
    ServiceDigest    ServiceDigest
    RouteIntent      RouteIntentSnapshot
    ExpiresAtUnix    uint64
    PolicyContext    PolicyContext
}

type RouteIntentSnapshot struct {
    Canonical         []byte
    Digest            [32]byte
    SourceOperator    string
    SourceEdge        string
    TargetOperator    string
    TargetEdges       []string
    Transport         string
    Port              uint16
    RecordSequence    uint64
    PolicyHash        [32]byte
    RouteID           [16]byte
    LeaseID           [16]byte
    ExpiresAt         uint64
}

type MappingSnapshot struct {
    MappingSpec
    ID               MappingID
    ActiveReferences uint64
    AccountedBytes   uint64
}
```

`RouteIntentSnapshot` is an immutable stdlib-only ownership copy used by `corestate`; the authority integration layer performs an explicit lossless conversion to `authority.RouteIntent`. It avoids importing authority/session packages into the bounded core.

The mapping does not store the shared Synthetic IP: that IP is adapter configuration common to all mappings and conveys no per-service information. It also does not store RouteGrant, TS, SC, credit, or stream state.

### FlowContext

```go
type FlowContext struct {
    MappingID  corestate.MappingID
    LocalFlowID corestate.LocalFlowID
}
```

The adapter creates a nonzero, single-use local flow correlation only after it can associate the application flow with exactly one valid MappingID. The core atomically consumes that correlation and calls `AcquireMapping`. A consumed, unknown, stale, expired, or ambiguous context fails closed. `ReleaseMapping` occurs exactly once when flow ownership ends, including failed authority/session admission.

Flow contexts have independent entry and logical-byte caps plus a bounded pending-correlation cap. They are not inferred from destination IP, destination port, Host, SNI, process recency, or the most recently resolved name.

## Flow-correlation boundary and approved adapter

The current repository contains no mechanism that can carry a per-resolution MappingID through an ordinary DNS result containing only one shared IP into a later same-IP/same-port `connect()` call.

This is an information boundary, not an implementation omission inside Go Core: the normal socket call exposes destination address and port, both intentionally shared. The current loopback proxy receives no resolver token, and no existing wire field carries one.

The approved implementation is an **explicit local proxy protocol**. Supported applications or the OS proxy layer send the requested destination name through SOCKS5 domain-name or HTTP CONNECT metadata. The proxy canonicalizes and resolves that name to a MappingID before opening secure routing. The name is correlation input only: it cannot override mapping-owned ServiceIdentity, ServiceDigest, RouteIntent, or authority state. HTTP Host and TLS SNI remain excluded.

This choice deliberately limits Tranche 6 to proxy-aware/configured applications. Platform-native transparent correlation and application SDK/interposition remain separate later work.

No OS-neutral user-space proxy can reconstruct the missing value from standard shared-IP DNS and `connect()` metadata alone. The core interface can be implemented and tested with a fake adapter, but Tranche 6 cannot claim end-to-end completion until one choice is approved and proven.

## ServiceDigest derivation and equality chain

The single derivation point is canonical resolution-result construction:

```text
canonical_name = canonicalize(presentation_name)
derived = SHA-256([]byte(canonical_name))
```

Required checks:

1. `ResolutionResult.ServiceDigest == derived`.
2. Inserted `MappingSpec.ServiceDigest == ResolutionResult.ServiceDigest`.
3. Mapping-to-authority conversion sets `AuthorityKey.ServiceDigest` from the acquired mapping, never from adapter input.
4. Existing verifier requires signed RouteGrant field 2 to equal `AuthorityKey.ServiceDigest`.
5. Existing authority reservation and SC preflight require the SC request digest to equal sealed verified authority.
6. The committed SC snapshot retains the same digest.

Any mismatch fails before mutation or before application payload admission. Equality is a binding invariant, not standalone authorization.

## Lifecycle

- A successful resolution inserts a new immutable mapping. An identical concurrent result may coalesce only when every immutable field is byte-equal.
- A material change always receives a new monotonic MappingID. Old referenced state remains separate.
- Lookup and acquisition reject at `now >= ExpiresAtUnix`.
- Expiry cleanup removes unreferenced entries and reports referenced expired entries without admitting new references.
- Existing admitted streams remain owned by existing SC/credit/stream lifecycle and are not replayed, refreshed, migrated, or terminated merely by mapping expiry.
- Flow failure before stream handoff releases its mapping reference. Successful handoff retains/releases according to the owning forwarding lifecycle.
- Restart creates empty mapping and flow-correlation tables with reset process-local allocators. No serialized mapping material is accepted.

## Bounds

Configuration must provide nonzero mutually consistent limits for:

- mapping entries and logical bytes;
- canonical-name, service-identity, RouteIntent canonical bytes, target-edge count/bytes, and policy-context bytes;
- active flow contexts, pending correlations, correlation waiters, and logical bytes;
- concurrent resolution work and resolver response size;
- goroutines/workers created by the chosen adapter.

Capacity is reserved before attacker-controlled work or goroutine creation. Live mappings and flow contexts are never evicted to admit new work. Defaults are implementation values to be measured later, not protocol claims.

## Failure behavior

Fail closed without direct routing when:

- canonicalization, signed resolution, RouteIntent, or digest validation fails;
- mapping or flow capacity is exhausted;
- the adapter supplies zero, unknown, expired, stale, consumed, or ambiguous context;
- mapping identity/digest/context differs from the resolution result;
- mapping removal races with acquisition;
- authority, RouteGrant, TS, SC, credit, or stream admission fails;
- adapter attribution/correlation cannot prove exactly one context.

No failure selects a context by recency, destination IP/port, Host, SNI, or fallback DNS.

## Security invariants

- Shared Synthetic IP possession grants nothing.
- Only derived canonical-name digest enters the mapping.
- Adapter input selects a local MappingID but cannot override mapping service/authority fields.
- One FlowContext is consumed by at most one application flow.
- A mapping reference is acquired before authority work and released exactly once.
- Mapping immutable fields never change under an existing MappingID.
- Verified RouteGrant and fresh authority remain mandatory.
- ServiceHandle remains local and `channel_id`/generation remain wire identity.
- No application payload precedes existing Application Stream acceptance.
- Restart restores no authority-bearing or correlation state.

## Platform-adapter boundary

The platform adapter owns:

- binding the configured NBSR Resolution IP and shared Synthetic IP according to platform policy;
- intercepting or explicitly receiving the application flow;
- establishing exact resolution-to-flow correlation by the approved mechanism;
- providing a bounded `FlowContext` to Go Core;
- local peer/application attribution available on that platform;
- cleanup, rollback, and fail-closed bypass prevention within its declared platform scope.

Go Core owns canonical resolution validation, digest derivation, mappings, references, authority/session selection, and secure-stream lifecycle. It does not inspect Host/SNI, configure OS routes, or guess platform correlation.

## Nonclaims and out of scope

- No permanent protocol Synthetic-IP address or range is defined. Deployment uses a validated local address compatible with current platform constraints.
- No generic transparent adapter is claimed; Tranche 6 covers explicitly proxy-configured applications only.
- No RouteGrant, ACP, TS, SC, credit, stream, ServiceHandle, or `channel_id` wire change.
- No shared-IP selection by IP+port, Host, SNI, DNS recency, or mutable global state.
- No persistence/recovery of mappings or live flows.
- No demo packaging, Docker orchestration, cleanup tranche, TUN/router adapter, WFP driver, native installer, or production-readiness claim.
