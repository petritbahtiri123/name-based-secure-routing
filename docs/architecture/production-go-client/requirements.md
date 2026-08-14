# Production Go client requirements

Requirement labels combine normative strength and classification. A requirement
may have multiple classifications where the concern crosses boundaries.

## Mission and boundaries

- **PGC-001 — MUST — CLIENT_IMPLEMENTATION:** The client owns the path from an
  NBSR name or captured Synthetic-IP flow through RouteIntent correlation,
  RouteGrant acquisition, Transport Session selection, Service Channel
  admission, Stream Credit allocation, and Application Stream forwarding.
- **PGC-002 — MUST — EXISTING_PROTOCOL:** Preserve the hierarchy Resolver →
  synthetic mapping → RouteIntent → RouteGrant → Transport Session → Service
  Channel → Stream Credits → Application Streams.
- **PGC-003 — MUST — SECURITY:** Never send application payload before the
  corresponding stream is accepted, and never fall back to a direct origin.
- **PGC-004 — MUST — CLIENT_IMPLEMENTATION:** Keep the protocol/session core
  independent of OS interception; adapters provide resolved/captured flows and
  receive bounded forwarding results.
- **PGC-005 — MUST — EXISTING_PROTOCOL:** Preserve QUIC v1, TLS 1.3, exact ALPN
  `nbsr-quic-1`, P1F replay semantics, and P2D `nbsr-stream-credit-1` semantics.
- **PGC-006 — MUST — SECURITY:** Treat the interop peer and Python agent as
  evidence/prototypes, not reusable production ownership by assertion.

## Resolution and interception

- **PGC-010 — MUST — PLATFORM_INTEGRATION, SECURITY:** Resolve NBSR names to
  scoped Synthetic IPs and atomically bind each mapping to tenant/trust context,
  canonical service identity, RouteIntent generation, expiry, and policy.
- **PGC-011 — MUST — SECURITY:** An unmapped, expired, collided, or
  wrong-context Synthetic IP fails closed and cannot escape ordinary routing.
- **PGC-012 — MUST — CLIENT_IMPLEMENTATION:** Concurrent resolutions of the
  same service coalesce without collapsing distinct tenant, identity, policy,
  or transport contexts.
- **PGC-013 — SHOULD — CLIENT_IMPLEMENTATION:** Positive mappings may be cached
  only to the earliest authority/policy expiry; negative caching is short,
  bounded, and invalidated by configuration or authority change.
- **PGC-014 — MUST — PLATFORM_INTEGRATION:** Revalidate prefix ownership after
  interface, route, VPN, network, or resume events; ambiguity disables capture.
- **PGC-015 — MUST — REQUIRES_PROTOCOL_DECISION:** Freeze the resolver authority,
  authenticated response contract, mapping TTL/invalidation semantics, and
  resolver failover policy before production implementation.
- **PGC-016 — MAY — PLATFORM_INTEGRATION:** Support proxy, TUN, and native
  interception adapters around the same core; no adapter may broaden authority.
- **PGC-017 — MUST — CLIENT_IMPLEMENTATION, SECURITY:** Synthetic IP is only the
  local application-facing correlation entry point. It is never authoritative
  service identity, authorization, or an origin identifier.
- **PGC-018 — MUST — PLATFORM_INTEGRATION:** The initial proxy-first adapter uses
  one local Synthetic IP mapping per simultaneously active service/context when
  destination IP and port would otherwise be ambiguous. These virtual mappings
  do not imply one public or gateway IP per service.
- **PGC-019 — MAY — PLATFORM_INTEGRATION:** A later adapter may reuse one literal
  Synthetic IP across services only when it supplies Go Core a bounded local
  `MappingID`/`FlowContext` that preserves resolver-to-flow correlation. That
  identifier is local state, not authority. SNI, Host, or other application
  metadata must not be the generic correlation mechanism.

## Identity and authority

- **PGC-020 — MUST — SECURITY:** Separate device enrollment identity, workload
  or user policy identity, TLS/Transport Session proof key, and local state
  protection key by purpose and rotation domain; never use one key for all.
- **PGC-021 — MUST — SECURITY, OPERATIONS:** Private keys are non-exportable
  where the platform supports it, referenced by identifier, least-privilege
  accessible, zeroized where practical, and never logged.
- **PGC-022 — MUST — CLIENT_IMPLEMENTATION:** Startup validates credential
  purpose, issuer, validity, revocation/freshness, storage permissions, and
  profile before creating authority-bearing state.
- **PGC-023 — MUST — SECURITY:** Credential loss or corruption disables new
  authority and requires authenticated reenrollment; cached grants or sessions
  cannot substitute for identity recovery.
- **PGC-024 — SHOULD — OPERATIONS:** Rotate keys make-before-break only where
  both identities are explicitly authorized; revoke the old key and drain its
  dependent state without cross-binding.
- **PGC-025 — MUST — REQUIRES_PROTOCOL_DECISION:** Approve enrollment,
  workload/device identity binding, key proof, rotation, revocation, and
  recovery contracts separately from Core transport messages.

## RouteGrant lifecycle

- **PGC-030 — MUST — CLIENT_IMPLEMENTATION:** A RouteGrant Manager requests
  authority for a normalized RouteIntent using the selected client/workload
  identity, current policy context, and fresh TS key thumbprint.
- **PGC-031 — MUST — SECURITY:** Verify issuer, signature, service/name,
  transport/port, destination edge, policy, validity, nonce, sequence, and
  session-key binding before cache insertion or channel admission.
- **PGC-032 — MUST — CLIENT_IMPLEMENTATION:** Coalesce identical concurrent
  acquisitions; bound waiters and cache entries; cancellation of one waiter
  does not cancel a request still needed by others.
- **PGC-033 — MUST — CLIENT_IMPLEMENTATION:** Cache only exact verified grants
  under the complete authority key and until the earliest expiry/revocation;
  never reuse a TS-A-bound grant for TS-B.
- **PGC-037 — MUST — EXISTING_PROTOCOL, SECURITY:** A RouteGrant cache entry is
  an unconsumed single-use authority. Atomically transition it to consumed for
  exactly one channel ID/admission attempt at the existing protocol commit
  point. Every distinct channel, recreation, or TS generation requires a fresh
  grant and nonce; expiry-valid consumed grants are never reusable.
- **PGC-034 — SHOULD — CLIENT_IMPLEMENTATION:** Renew before expiry using a
  configured safety window and jitter; a failed renewal leaves the old grant
  usable only while independently valid and not revoked.
- **PGC-035 — MUST — SECURITY:** Offline mode creates no fresh authority. It may
  use still-valid cached authority only if the approved freshness policy permits
  it; otherwise it fails closed.
- **PGC-036 — MUST — REQUIRES_PROTOCOL_DECISION:** Existing Core wire contracts
  are sufficient to verify/use a supplied RouteGrant but not to acquire,
  renew, or receive revocation. The approved production source is the NBSR
  Authority Control Plane behind a narrow internal `AuthorityProvider`; its
  authentication, transport, freshness, and failure contract must be frozen
  separately, and any new NBSR wire message requires separate protocol approval.
- **PGC-038 — MUST — CLIENT_IMPLEMENTATION, SECURITY:** The Authority Control
  Plane owns or coordinates client authentication, RouteGrant acquisition and
  renewal, revocation freshness, authority/profile selection, and generation
  information for TS replacement. Go Core accepts only independently verified
  authority; neither the interface nor its implementation may mint authority.
- **PGC-039 — MUST — CLIENT_IMPLEMENTATION:** Authority-provider transport and
  backend details remain outside resolver, TS, SC, credit, and stream logic.

## Transport Sessions and rotation

- **PGC-040 — MUST — CLIENT_IMPLEMENTATION:** A Transport Session Manager owns
  creation, health, idle/absolute lifetime, migration, drain, close, and cleanup.
- **PGC-041 — MUST — SECURITY:** A reuse key includes authenticated edge pair,
  trust/profile/version, client identity/key generation, policy compatibility,
  path constraints, and capacity; a TS is not universal service authority.
- **PGC-042 — MUST — CLIENT_IMPLEMENTATION:** One atomic selector chooses the TS
  generation for each new application flow. Existing streams remain on their
  original generation.
- **PGC-043 — MUST — CLIENT_IMPLEMENTATION, SECURITY:** Own at most two TS
  generations per reuse key: active plus exactly one preparing or draining
  replacement. A failed replacement is destroyed before another is attempted.
- **PGC-044 — SHOULD — CLIENT_IMPLEMENTATION:** Rotation triggers include replay
  high-water before the 10,000 cap, absolute age, credential/grant generation,
  edge drain, health degradation, administrator policy, and incompatible
  network migration; replay count is not the sole trigger.
- **PGC-045 — MUST — CLIENT_IMPLEMENTATION:** Rotation is TS-A active → TS-B
  preparation → fresh TS-B authorization/channels/credits → atomic selector
  switch → TS-A drain → destruction. Readiness is all-or-nothing per selected
  service, with lazy channel recreation allowed only before a flow is selected.
- **PGC-046 — MUST — SECURITY:** Revocation fans out by service, grant, identity,
  edge, policy, or session scope across both generations and cannot be undone
  by cutover, retry, resume, or restart.
- **PGC-059 — MUST — CLIENT_IMPLEMENTATION, SECURITY:** Revocation publication,
  selector reads, channel readiness, and final credit/stream admission share one
  monotonic authority-generation barrier. A flow may pin a generation only if
  its channel was validated under the same current generation, and must recheck
  that generation immediately before credit allocation/stream open; mismatch
  aborts without payload or authority consumption beyond existing commit rules.
- **PGC-047 — MUST — CLIENT_IMPLEMENTATION:** If TS-B transport, grant, channel,
  or credits fail, keep TS-A selected only while healthy, authorized, and below
  hard limits; otherwise reject new flows. Never cross the P1F replay cap.
- **PGC-048 — MUST — CLIENT_IMPLEMENTATION:** If both generations are unhealthy,
  reject new flows, terminate only flows whose transport has failed, apply a
  bounded backoff/circuit policy, and expose a stable local error.
- **PGC-049 — MUST — CLIENT_IMPLEMENTATION:** Sleep/wake, network/IP/interface
  change, server disconnect, upgrade, and crash trigger revalidation or fresh
  construction; QUIC path validation alone never creates NBSR authority.

## Service Channels, credits, and streams

- **PGC-050 — MUST — CLIENT_IMPLEMENTATION:** Index a Service Channel by TS
  generation plus exact service/RouteGrant/policy/identity binding; create it
  once, coalesce callers, and independently revoke, drain, expire, and delete it.
- **PGC-051 — MUST — SECURITY:** Service failure or revocation does not poison
  unrelated channels unless their shared TS authority is invalid.
- **PGC-052 — MUST — EXISTING_PROTOCOL:** Preserve the P2D initial 64-credit
  window, refill watermark 16, one-use slots, maximum two recognized epochs,
  ordered control-stream refill ownership, and fail-closed downgrade behavior.
- **PGC-053 — MUST — CLIENT_IMPLEMENTATION:** The credit manager stores only
  current and optional draining epoch per channel, uses atomic slot allocation,
  permits at most one refill request, and binds every allocation to TS, route,
  grant, channel, channel generation, and revocation generation.
- **PGC-054 — MUST — CLIENT_IMPLEMENTATION:** Credit exhaustion/refill failure
  backpressures or rejects new flows; it never falls back to legacy admission,
  borrows another service/TS credit, or creates unbounded waiters.
- **PGC-055 — MUST — SECURITY:** Credits, QUIC streams, and channels are strictly
  ephemeral after crash; fresh state is authorized after restart.
- **PGC-056 — MUST — CLIENT_IMPLEMENTATION:** One accepted local TCP connection
  maps to one Application Stream in the initial profile. Cancellation/reset and
  half-close propagate directionally without leaking goroutines or buffers.
- **PGC-057 — MUST — CLIENT_IMPLEMENTATION:** Admission retry may create a fresh
  stream only before payload and only when authority remains valid. Application
  payload is never implicitly replayed; retry after any payload write is owned
  by the application protocol.
- **PGC-058 — MUST — CLIENT_IMPLEMENTATION:** Enforce bounded per-stream buffers,
  end-to-end backpressure, deadlines, and fair scheduling across services.

## Persistence, resources, retries, and operations

- **PGC-060 — MUST — CLIENT_IMPLEMENTATION:** Durable state is limited to
  identity/key references, trusted authority/profile configuration, resolver
  and local policy configuration, and integrity/version metadata.
- **PGC-061 — MUST — SECURITY:** TSs, SCs, credits, QUIC streams, in-flight
  requests, and live selectors are ephemeral. RouteGrants and synthetic mappings
  are reconstructed by default rather than persisted.
- **PGC-062 — MUST — SECURITY:** Corrupt, rolled-back, unsupported, or
  permission-unsafe security state is quarantined and causes fail-closed startup;
  non-security cache corruption may be discarded and rebuilt. Claims of rollback
  resistance require an approved external/TPM/authority monotonic anchor; local
  integrity protection alone detects modification, not restored old snapshots.
- **PGC-063 — MUST — CLIENT_IMPLEMENTATION:** Every queue, map, retry loop,
  goroutine source, log buffer, session generation, and refill request has an
  explicit configured bound and overload behavior.
- **PGC-064 — MUST — OPERATIONS:** Distinguish protocol safety bounds (immutable
  for a profile), implementation defaults, deployment tunables, and measured
  benchmark targets. Do not promote lab limits or estimates to product claims.
- **PGC-065 — SHOULD — OPERATIONS:** Configuration exposes bounded limits for
  TSs, channels, streams, queued flows, grant/mapping caches, file handles,
  memory, goroutines, and log rate; startup validates their consistency.
- **PGC-066 — MUST — CLIENT_IMPLEMENTATION:** Retry classification is explicit:
  resolution, grant acquisition, TS creation, and pre-commit SC creation are
  conditionally safe; credit refill is safe only as the existing correlated
  idempotent lifecycle allows; post-accept application payload retry is forbidden.
- **PGC-067 — MUST — CLIENT_IMPLEMENTATION:** Each retryable operation has a
  deadline, finite attempt/time budget, exponential backoff with jitter, and
  scope-specific circuit breaker. Permanent auth/schema/revocation/downgrade
  failures are not retried until relevant state changes.
- **PGC-068 — SHOULD — CLIENT_IMPLEMENTATION:** Failover may choose another
  approved resolver, authority endpoint, or destination edge only when the
  existing signed authority permits it; failover never widens authority.
- **PGC-069 — MUST — OPERATIONS:** Metrics cover resolution, grants, TS/rotation,
  SCs, streams, credits/refills/rejections, replay usage/cap, admission latency,
  failures/retries, CPU/memory/GC/goroutines/handles, and network transitions.
- **PGC-070 — MUST — SECURITY, OPERATIONS:** Logs/metrics exclude keys,
  credentials, payload, origin endpoints, raw proofs, and unnecessary subscriber
  identity; use bounded-cardinality pseudonymous service/session labels.

## Multi-service behavior and acceptance

- **PGC-080 — MUST — CLIENT_IMPLEMENTATION:** Index flow ownership as Synthetic
  destination/context → service identity → exact RouteGrant → Service Channel →
  TS generation; many processes may share eligible state without sharing local
  application identity or unauthorized services.
- **PGC-081 — MUST — CLIENT_IMPLEMENTATION:** Permit many services on one TS
  with per-service capacity/fairness and aggregate session/client capacity; do
  not assume one TS per service.
- **PGC-082 — MUST — SECURITY:** A compromised local application receives only
  authority implied by its authenticated local identity/policy and destination;
  possession of a Synthetic IP alone is not authority.
- **PGC-083 — MUST — CLIENT_IMPLEMENTATION:** After resolution, correlate the
  mapping to the stable NBSR Service Identity. During SC establishment allocate
  a nonzero, fixed-width, session-local `ServiceHandle` (prefer `uint32` unless
  measured capacity requires `uint64`) and bind it bijectively to one live SC.
- **PGC-084 — MUST — CLIENT_IMPLEMENTATION, SECURITY:** `ServiceHandle` is an
  opaque lookup key, never authorization or a bearer credential. Reuse after
  teardown must not alias delayed references: handle values are monotonically
  allocated and never reused within one TS generation. Exhaustion forces safe TS
  replacement; only destruction of that TS generation resets the handle space.
- **PGC-085 — MUST — EXISTING_PROTOCOL, CLIENT_IMPLEMENTATION:** Retain the
  verified service identity, RouteGrant digest, channel ID/generation, and
  authority generation once in bounded SC state. Normal per-stream lookup uses
  `(TS generation, ServiceHandle, actual QUIC Stream ID)` and performs no new
  service hash solely for routing.
- **PGC-086 — MUST — EXISTING_PROTOCOL:** Preserve the existing authenticated
  `channel_id` and generation in P2D wire/admission. `ServiceHandle` is a local
  client/server alias for that accepted SC; replacing or adding a wire field is
  **REQUIRES SEPARATE PROTOCOL APPROVAL**.
- **PGC-087 — MUST — CLIENT_IMPLEMENTATION:** Maintain bounded O(1)-style
  `MappingTable`, `ServiceTable`, and `StreamTable` registries with explicit
  entry/byte capacities, expiry or terminal cleanup, deterministic teardown,
  and overload rejection. No registry grows from attacker input without a
  successful bounded reservation.
- **PGC-088 — MUST — CLIENT_IMPLEMENTATION:** `MappingTable` contains mapping ID,
  service identity, expiry, and policy context. `ServiceTable` contains TS
  generation, handle, SC identity, stable service digest, authority generation,
  credit reference, and active-stream count. `StreamTable` contains TS
  generation, handle, actual QUIC stream ID, local-flow reference, and lifecycle.
- **PGC-089 — MUST — SECURITY:** `ServiceTable` and `StreamTable` are strictly
  ephemeral and are rebuilt only from fresh verified authority after restart.
  Teardown removes streams before their service/handle and releases all counts.
- **PGC-090 — MUST — OPERATIONS:** Future core acceptance includes deterministic
  unit/state-machine tests; Go↔Rust interop; multi-service isolation; expiry,
  revocation, recovery, rotation, SC/credit lifecycle, cancellation, downgrade,
  replay, malformed input, cross-service/TS confusion, and bounded DoS tests.
- **PGC-091 — MUST — OPERATIONS:** Resource acceptance measures idle CPU/memory,
  goroutine/queue/map/handle bounds, memory soak, and GC/allocation profiles on
  named hardware and workloads.
- **PGC-092 — MUST — OPERATIONS:** Performance acceptance defines workloads,
  target hardware, controls, lifecycle boundaries, raw evidence, and measured
  baselines before targets; the P2D evidence remains immutable input, not a
  production-client target.
- **PGC-093 — MUST — PLATFORM_INTEGRATION:** Core acceptance is separate from
  Windows, Linux, and router adapter acceptance. Each adapter proves capture,
  bypass blocking, collision/network-change handling, least privilege,
  install/upgrade/rollback, and platform-specific resource behavior.
- **PGC-094 — SHOULD — CLIENT_IMPLEMENTATION, OPERATIONS:** Structural priority
  is correctness, bounded state, minimal memory, minimal allocations, O(1)-style
  lookups, no unnecessary per-stream cryptography, and shared TS reuse across
  many independently authorized SCs. Further optimization requires measurement.
- **PGC-095 — MUST — SECURITY:** A stable service or RouteGrant digest is only
  an integrity, correlation, and audit binding. Digest equality never authorizes
  routing or admission; current RouteGrant and Service Channel authority must be
  independently live and valid.

## Retry matrix

| Operation | Classification | Boundary |
|---|---|---|
| Resolution | Conditionally safe | Retry only approved resolvers within deadline; stale/contradictory authority fails closed |
| RouteGrant acquisition | Conditionally safe | Coalesced fresh request; never reuse an invalid grant; provider contract must define idempotency |
| TS creation | Safe before authorization | Fresh connection/state; finite attempts; no authority transfer |
| SC creation | Conditionally safe | Retry only when existing wire evidence proves no destination commit; lost/ambiguous response is non-retryable and requires fresh reconciliation/authority decision |
| Credit refill | Conditionally safe | One correlated pending refill; obey ordered control stream and two-epoch bound |
| App-stream admission | Conditionally safe | Only before payload and with a fresh credit/stream; preserve replay semantics |
| Application payload | Forbidden implicitly | Application protocol alone may decide semantic retry |
