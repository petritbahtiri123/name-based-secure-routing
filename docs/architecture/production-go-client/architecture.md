# Production Go client architecture

## Recommended shape

Build one platform-independent **NBSR Go Core** behind narrow platform adapter
interfaces. Start with a user-space proxy adapter to validate real ownership
and lifecycle semantics without kernel code, while keeping TUN and native
interception as later adapters. The proxy is the initial implementation path,
not the final transparency claim.

The core owns authority and transport decisions. The adapter owns OS capture,
local peer attribution, synthetic-route containment, and byte plumbing; it
cannot manufacture RouteIntents, RouteGrants, credits, or fallback routes.

## Data and ownership flow

`resolver input → Mapping Manager → Service Identity → RouteIntent → RouteGrant
Manager → TS Pool and Selector → SC Manager/ServiceHandle → Credit Manager →
Stream Forwarder`

For a captured flow, the Mapping Manager resolves the complete scoped mapping.
The RouteGrant Manager returns an exact verified grant or a stable failure. The
TS selector pins the new flow to one generation. The SC Manager returns an
active service-bound channel on that generation. The Credit Manager atomically
allocates a one-use slot. The Stream Forwarder opens the actual QUIC stream,
binds its real stream ID, waits for ACCEPT, and only then forwards payload.

## Component model

| Component | Responsibility and state | Inputs → outputs |
|---|---|---|
| Platform Adapter | Capture/resolution integration, local peer identity, bypass containment; bounded pending flows | OS event/flow → scoped flow or failure |
| Mapping Manager | Atomic Synthetic-IP/MappingID allocation, service correlation, expiry, invalidation, collision state | canonical name/context → mapping + Service Identity + RouteIntent |
| Identity Manager | Purpose-separated key references, signing/TLS operations, enrollment state | identity request → proof/key handle/status |
| Authority Provider interface | Narrow internal boundary to the standard NBSR Authority Control Plane; never mints locally | authenticated RouteIntent/TS key context → signed RouteGrant/revocation/freshness status |
| RouteGrant Manager | Coalescing, verification, bounded cache, renewal/invalidation | RouteIntent + identity + TS key → verified exact grant |
| TS Manager/Pool | Connections, reuse keys, health, lifetime, two-generation rotation | edge/profile/identity/policy → TS handle |
| Atomic Session Selector | Single linearization point for each new flow | reuse key → pinned active generation |
| SC Manager/Service Registry | Service-specific admission, fixed-width session-local ServiceHandle allocation, quotas, drain/revoke/delete | TS + grant + service → authenticated channel + compact handle |
| Credit Manager | Two-epoch windows, slot allocation, one pending refill | channel → bound credit or backpressure |
| Stream Registry/Forwarder | O(1)-style lookup by TS generation + ServiceHandle + actual stream ID; ACCEPT/payload forwarding, half-close/cancel | pinned handle + local flow → terminal result |
| Retry Controller | Typed deadlines, budgets, jitter, circuits; no payload retry | operation class/result → retry/stop decision |
| Policy Manager | Validated local configuration and local-app authorization | app identity + destination → allow/deny/context |
| Durable State Store | Atomic versioned security config/key references only | signed/admin update → durable snapshot/status |
| Metrics/Health | Bounded-cardinality counters, gauges, traces, redacted events | internal events → operator-safe signals |

Each manager exclusively mutates its state. Callers use immutable handles with
generation identifiers; shutdown uses context cancellation plus explicit drain,
and no component launches an unaccounted goroutine.

The managers share a monotonic **authority generation** through a coordinator,
not mutable authority objects. Publishing revocation increments the generation,
invalidates dependent handles across both TS generations, then permits later
selector reads. New-flow selection captures `(TS generation, authority
generation, channel binding)` atomically; the credit/stream boundary validates
the same generation again. This is the linearization barrier that prevents a
selector/revocation race from reviving authority.

## Lightweight mapping, service, and stream registries

Synthetic IP is not Service Identity. The authoritative in-memory path is:

`Synthetic Mapping → Service Identity → authenticated Service Channel →
ServiceHandle`

`ServiceHandle` is a nonzero fixed-width integer local to one TS generation.
Use `uint32` initially unless measured channel capacity requires `uint64`.
Client and server may each choose their own local handle value; it aliases the
already negotiated channel and is never compared across peers or treated as
authority. The existing `channel_id`, channel generation, RouteGrant digest,
service binding, and P2D validation remain unchanged on wire and at admission.
Allocation is monotonic and a numeric value is never reused within the same TS
generation, even after its SC is removed. Handle-space exhaustion triggers
fail-closed TS replacement; a new TS generation starts a fresh handle space.

| Registry | Key | Bounded value | Lifetime/teardown |
|---|---|---|---|
| MappingTable | SyntheticMappingID; adapter may additionally index local Synthetic IP/context | Service Identity, expiry, policy context, RouteIntent reference | Expire/invalidate; reject new flows; release only after flow references reach zero |
| ServiceTable | `(TS generation, ServiceHandle)` with reverse SC/channel-ID index | SC identity, stable service digest, authority generation, credit reference, active-stream count | Remove after revoke/close/drain and active-stream count reaches zero; stale handles fail |
| StreamTable | `(TS generation, ServiceHandle, QUIC Stream ID)` | local flow reference and compact lifecycle state | Insert after bounded reservation; remove on terminal close/reset/cancel; then decrement service count |

All registries have configured entry and byte caps, preallocation or bounded
growth policy, O(1)-style hash/array lookup, explicit overload errors, and
periodic plus event-driven cleanup. Capacity is reserved before attacker-driven
work or goroutine creation. ServiceTable and StreamTable are never persisted.
The stable service digest is computed/verified once at SC negotiation and kept
for integrity/correlation/audit; normal stream routing does not hash the service
again. Neither that digest nor the RouteGrant digest authorizes a stream by
equality: current RouteGrant and SC authority must still validate.

The server routes an admitted stream through the existing authenticated
Service Channel identity and may use its own corresponding local ServiceHandle
for fast lookup. It never routes by gateway/destination IP alone. The frozen
P2D stream preface still carries `channel_id` and generation; replacing that
with ServiceHandle or adding a new hash field would be **REQUIRES SEPARATE
PROTOCOL APPROVAL**.

## Synthetic-IP correlation strategies

| Approach | Properties | Decision |
|---|---|---|
| A — per-active-service local Synthetic IP | Universal IP/TCP correlation, lowest adapter complexity; local mappings still share one gateway/TS | **Initial proxy-first recommendation** |
| B — shared Synthetic IP plus MappingID/FlowContext | Reduces local address use but requires the adapter to preserve resolver-to-socket context safely | Core-compatible future option after platform proof |
| C — infer SNI/Host/application metadata | Protocol-specific, encrypted or absent for many workloads, creates parsing/confusion surface | Rejected as generic NBSR mechanism |

One literal Synthetic IP plus identical destination port cannot distinguish
simultaneous unrelated services from ordinary IP/TCP metadata alone. Therefore
Approach B requires an OS/platform correlation mechanism delivered to Go Core
before admission; MappingID is correlation only and does not grant authority.
Approach A does not mean one public/server address per service: many local
Synthetic IPs converge on one regional gateway, one TS, and many SCs.

## Identity model

The device enrollment identity establishes the managed device. A workload/user
policy identity scopes local authorization where deployments require it. A
fresh TS proof key (or approved generation of one) binds RouteGrants and the
authenticated transport. A separate OS-protected local-state key protects
durable configuration integrity. Authority signing keys and gateway TLS keys
remain outside the client.

Key rotation builds new authority using the new key generation, atomically
switches only after validation, and drains old-key state. Loss invokes
reenrollment; the client does not recover by weakening proof or revocation.

## Authority Control Plane and RouteGrant lifecycle

The standard production client requests grants from the NBSR Authority Control
Plane through Go Core's narrow `AuthorityProvider` boundary because Core v0.2
contains no acquisition exchange. The control plane owns or coordinates client
authentication, acquisition, renewal, revocation freshness, approved
authority/profile selection, and replacement-generation freshness. The request includes the
normalized RouteIntent, client/workload context, desired transport/port,
destination constraints, policy version, and fresh TS public-key thumbprint.
The manager independently verifies the returned signed grant before caching it.

The cache key contains every authorization dimension, including TS key
generation. Renewal is proactive but never extends a grant locally. Expiry,
revocation, policy/config generation, identity change, edge incompatibility, or
mapping invalidation evicts it and denies dependent new work. Rotation acquires
fresh TS-B-bound grants; TS-A grants never authorize TS-B.

A cached grant is only an unconsumed single-use object. The SC admission owner
atomically assigns it to one channel ID and marks it consumed at the established
commit boundary. Channel recreation, retry requiring a distinct channel, and
every TS generation obtain a fresh grant/nonce; remaining validity never makes a
consumed grant reusable.

Go Core independently verifies all returned authority and the provider never
manufactures authority locally. Provider backend/transport details do not enter
session, channel, credit, or stream state machines. Exact control-plane
transport, authentication, request idempotency, response freshness, renewal,
and revocation-feed contracts remain to be frozen; any new Core/wire message is
separate protocol work.

## TS and SC lifecycle

A TS reuse key is narrower than an edge address: it binds authenticated edge
roles, trust/profile/version, client key generation, policy compatibility, and
path/capacity class. Same-edge validated QUIC migration can preserve it; an
incompatible identity, edge, policy, or network transition creates a fresh TS.

SCs are indexed under a TS generation and exact service/grant binding. Admission
is coalesced. Expiry or revocation prevents new streams immediately and applies
the approved close/drain rule to existing streams. Channel deletion releases
credits, queues, metrics references, and handles; tombstone/replay semantics
remain owned by the existing protocol implementation.

## Rotation and failure semantics

For each reuse key there is at most an active generation plus one replacement
or draining generation. Only the selector can switch new flows.

1. TS-A remains active while TS-B connects and authenticates independently.
2. The client acquires fresh TS-B-bound RouteGrants and establishes the minimum
   SC/credit readiness required by policy.
3. A compare-and-swap changes the selector from TS-A to TS-B. A flow reads the
   selector once and retains that pinned generation for life.
4. TS-A refuses new flows, drains eligible existing streams to its deadline,
   then is destroyed, releasing its P1F replay history.

If TS-B fails before cutover, destroy it and retain TS-A only while valid and
below hard bounds. Cutover is global per reuse key: after the selector switches,
no service falls back to TS-A. A service whose SC was not eagerly prepared may
be created lazily on TS-B, but its flow is not admitted until TS-B SC/credit
readiness succeeds; failure rejects that flow. A revocation increments the
authority-generation barrier, invalidates both generations, and orders before
later selector reads. At the P1F hard cap, new affected flows fail closed if
TS-B is not ready. If both TSs fail, terminate only actually broken streams and
reject new flows under bounded circuit/backoff state.

An SC admission response lost after possible destination commit is ambiguous.
The client does not blindly retry it or reuse its grant. Recovery requires an
existing deterministic reconciliation path or a fresh authority decision; until
that contract is approved, ambiguous SC completion fails closed.

Triggers are configurable safety policies: replay high-water (strictly below
10,000), absolute age, key/grant/policy generation, edge drain, health,
administrator action, or incompatible network transition. They are triggers,
not new wire semantics.

## Persistence and recovery

Durable: key references/enrollment metadata; trusted authority/profile roots;
resolver and policy configuration; schema version, monotonic configuration
generation, and integrity metadata. Atomic replacement and rollback detection
are required. Local integrity detects modification but cannot detect restoration
of an older valid snapshot; production rollback resistance therefore requires
an approved TPM counter, remote authority freshness record, or equivalent
external monotonic anchor. Without one, startup fails closed when freshness is
security-relevant and cannot be proven.

Ephemeral: TSs, SCs, credits, streams, flow pins, pending refills, retry state,
and by default RouteGrants and synthetic mappings. Clean shutdown drains within
policy and deletes ephemeral state. Crash, reboot, or power loss starts with no
live authority, reacquires/reconstructs mappings and grants, and creates fresh
sessions. Corrupt security state is quarantined and startup fails closed;
discardable caches are rebuilt. Upgrade uses versioned migration for durable
configuration, never serialization of live security state.

## Resource bounds model

| Category | Safety bound | Default/tunable rule | Acceptance measurement |
|---|---|---|---|
| TS generations | Maximum 2 per reuse key; normally 1 | Global TS/reuse-key cap is deployment-tunable | peak/open/cleanup counts |
| Replay history | P1F cap 10,000 per Transport/Control Session, aggregated across sibling SCs | rotate below cap; high-water measured then configured | session-wide usage/cap and rejection |
| Credit state | 64 slots, watermark 16, ≤2 epochs, ≤1 refill/channel | not widened by deployment | exact state cardinality |
| SCs/streams | Existing protocol caps remain authoritative | lower client/global/per-service limits configurable | concurrency and fairness |
| Pending flows/requests | Always finite | per-service and global caps; overload rejects/backpressures | queue high-water/wait |
| Mapping/grant caches | Always finite and expiring | entry/byte limits and LRU only among safely discardable entries | entries/bytes/evictions |
| ServiceTable | One entry per admitted live/draining SC, bounded by SC caps | fixed-width handle; reverse channel index; no per-stream digest copy | entries/bytes/lookup/cleanup |
| StreamTable | One compact entry per active/pending admitted flow, bounded by stream/queue caps | key is TS generation + handle + actual stream ID | entries/bytes/allocations/terminal cleanup |
| Goroutines | Proportional to configured live work, never input packets | worker pools/semaphores; no detached retry goroutine | idle/peak/leak count |
| Memory/GC | Derived after representative measurements | byte budgets and buffer pools are implementation defaults | RSS/heap/allocs/pauses |
| Handles | Bound by TS/stream/config limits and OS ceiling | startup rejects inconsistent limits | idle/peak handle count |
| CPU | No arbitrary product claim | timers coalesced; no busy polling | idle and workload CPU |

Protocol safety bounds are immutable for the profile. Product defaults require
measurement on laptops, servers, and router-class targets. Deployment limits
may only reduce or safely aggregate work. Benchmark targets come after a named
hardware/workload baseline and matched methodology.

## Architecture options

| Criterion | A: user-space proxy first | B: TUN/interface | C: platform-native interception |
|---|---|---|---|
| Transparency | Opt-in/configured apps | Broad IP transparency | Broadest platform integration |
| Privilege | Low to moderate | Admin/root for interface/routes | High; driver/filter privileges |
| Windows | Feasible for SOCKS/HTTP-aware apps | Feasible, adapter complexity | WFP/service/driver engineering |
| Linux | Straightforward | Mature TUN/policy routing | nftables/eBPF/TPROXY variants |
| Router | Limited app model | Strong fit | Platform/vendor-specific |
| Performance | Extra proxy copies/protocol constraints | Good general path, measurable overhead | Potentially best, platform-dependent |
| Attack surface | Smallest initial OS surface | Packet parser/routing surface | Kernel/filter and installer surface |
| Operability | Easiest debug/rollback | Route/MTU/DNS complexity | Signing, upgrades, OS-version matrix |
| Deployment | Simple but not transparent | Privileged package/config | Most complex lifecycle |

**Recommendation:** implement and validate the shared Go core with Option A,
then add Option B for Linux/router coverage. Pursue Option C for production
Windows transparency only after core invariants and local privilege boundaries
are stable. This sequencing avoids binding protocol ownership to one OS while
acknowledging that proxy-first does not satisfy universal transparency.

## Observability

Counters and histograms use reason codes and bounded pseudonymous identifiers,
not raw names or origins. Gauges expose active TS generations, SCs, streams,
queue occupancy, credit remaining, refill state, replay usage, goroutines,
heap/RSS, CPU, and handles. Events cover rotation trigger/result/duration,
network transition, resolver/grant failure, revocation, circuit state, and
startup recovery. Sampling and rate limits are mandatory. Debug modes retain
the same secret/payload/origin prohibitions and have explicit expiry.
