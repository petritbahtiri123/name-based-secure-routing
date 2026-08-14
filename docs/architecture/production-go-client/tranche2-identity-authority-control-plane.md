# Tranche 2 identity and Authority Control Plane design

**Status:** Proposed freeze; human decision 1 approved, decisions 2-3 pending

**Baseline:** `codex/nbsr-v3-wp0-wp1` at
`8189d917e50df67e740fc3f3e8a5195f7cac7219`

**Scope:** Documentation only. This design does not implement enrollment,
Authority Control Plane (ACP) networking, new wire messages, Transport Session
(TS) rotation, or any Core/P1F/P2D change. Tranche 1 state semantics remain
unchanged.

Normative words **MUST**, **SHOULD**, and **MAY** are requirements for a future
approved implementation. Every new ACP wire object described here remains
**REQUIRES SEPARATE PROTOCOL APPROVAL** until its schema, registry allocation,
vectors, and interoperability evidence are approved.

## Evidence and reuse table

| Required capability | Existing reusable contract | Missing contract | Wire change required? |
|---|---|---|---|
| Client/device identity | Purpose-separated federation operator/key identity patterns; opaque `kid`; exact key purpose, lifecycle, generation, sequence, validity, and revocation checks | Production client identity namespace, credential profile, enrollment and recovery | Yes, separate enrollment/ACP protocol approval |
| Workload/user identity | Existing RouteGrant client/policy bindings and local policy boundary | Portable workload assertion format and enterprise IAM adapter | Only if transmitted; optional local context needs no Core change |
| TS proof identity | `client_session_key_thumbprint` in RouteGrant; HELLO/ROUTE proof-of-possession and exact authenticated-edge validation | Client key-generation lifecycle and ACP proof challenge | ACP messages only; no RouteGrant/Core field change |
| Local state integrity | Existing design requires minimal versioned integrity-protected durable state | Selected OS keystore/TPM/external rollback anchor | No network wire change unless remote freshness is selected |
| RouteIntent | Frozen bounded deterministic-CBOR fields: resolution digest, canonical name, service/operator/edge sets, transport/ports, time, record sequence, policy hash, route/lease IDs | ACP request wrapper and request authentication | ACP message approval only |
| RouteGrant | Frozen signed claims and maximum 600-second lifetime; exact service, edge, transport, port, policy, sequence, TS thumbprint, nonce, validity | Live acquisition/renewal response | ACP message approval only; RouteGrant unchanged |
| Signature verification | Deterministic CBOR, tagged COSE Sign1, protected `alg=-8`, protected opaque nonempty `kid`, Ed25519, empty external AAD, caller-supplied issuer trust | Production issuer distribution and client trust-store lifecycle | Trust distribution/enrollment approval; no new signature stack |
| Grant consumption | One fresh signed grant/nonce per channel; bind to one `channel_id`; consumed grants never authorize recreation or another TS | Go ownership and cache transition | Client implementation only |
| Revocation | Signed revocation object, monotonic generation, target/mode/time; WP4 terminal channel revocation and tombstone behavior | Client delivery, freshness SLA, restart floor, cross-generation fan-out | ACP messages require approval; Core behavior unchanged |
| Authority generation | Approved client coordinator and final pre-credit/stream recheck; federation generation/sequence rollback rules | ACP checkpoint cursor and publication ordering | ACP checkpoint approval plus client implementation |
| Trust/federation profile | Development profile has exact profile IDs, authority classes, key purposes, continuity, revocation and fail-closed precedence | Production authority registry/governance and ACP endpoint authorization | Separate production-profile approval |
| Existing control services | Prototype FastAPI `/v1/routes/resolve` and HTTPS/name-control foundations | Standard authentication, canonical bodies, signed responses, idempotency and freshness | Replace/standardize as new ACP protocol; prototype is not authority |
| Rust/Go verification | Rust independently validates COSE and exact grant claims; Go/Node independently verify federation artifacts; live Go-to-Rust Core/P1F/P2D evidence exists | Production Go grant verifier/API integration | Client implementation only |
| F75/P1F/P2D bindings | Exact carried grant bytes/digest, bilateral context, channel generation, credit epoch/slot and actual QUIC stream ID | None for ACP; authority must arrive before these state machines | No Core/F75/P1F/P2D change |

Conclusion: there is no contradiction. Existing NBSR authority is sufficient to
verify and consume grants, but not to enroll clients or deliver live authority.

## Identity hierarchy and ownership

### Device enrollment identity

The **DeviceIdentity** is the long-lived managed-client identity. It is owned by
the Identity Manager through an opaque, non-exportable signing-key reference
where the platform supports one. Its stable identifier and monotonically
increasing key generation are assigned by the enrollment authority. It MUST be
accepted only inside the configured operator/profile trust context; a `kid` is
never a global identity.

The DeviceIdentity authenticates ACP requests and authorizes enrollment-state
changes. It MUST NOT sign RouteGrants, act as a TS proof key, or protect local
files. Theft is handled by revocation and reenrollment, never by silently
creating an equivalent local identity.

### Workload/user policy identity

Workload/user context is **optional deployment context**. Home/personal clients
MAY use a single local principal governed by local policy. Enterprise, ISP, and
server deployments MAY attach an authenticated workload/user assertion or an
opaque policy-subject reference. Go Core consumes only a normalized, bounded
`PolicyContext` (subject reference/digest, assurance class, policy generation),
not vendor IAM tokens. Whether an ACP requires that context is profile policy.
The context MUST be included in the cache/acquisition key whenever it can alter
authorization. Synthetic IP, process ID, executable path, username, and
`ServiceHandle` are not network identities.

### TS proof key

Each TS generation owns a distinct proof-key generation and SHA-256 public-key
thumbprint. The key SHOULD be freshly generated per TS. A profile MAY permit a
pre-created key only when the credential is explicitly bound to exactly one TS
generation and cannot be concurrently reused. The private key remains behind
an Identity Manager handle. ACP possession proof binds the request digest,
request ID, ACP challenge/nonces, intended source operator/edge/profile, and TS
generation. The existing RouteGrant
`client_session_key_thumbprint` carries the resulting binding. Grant A for TS-A
MUST fail for TS-B even if all other claims and wall-clock validity match.

### Local state integrity key

The LocalStateIntegrityKey is a separate OS-protected key used only to
authenticate versioned durable client configuration and key references. It is
not sent on the network and is not identity or RouteGrant authority. Integrity
alone does not stop restoration of an older valid snapshot; startup also needs
the ACP freshness floor or another approved external monotonic anchor.

## Enrollment lifecycle

One core state machine serves personal, enterprise, router, and workload
deployments; optional management systems supply the bootstrap authorization.

`Unenrolled -> PendingOwnership -> Enrolled -> Rotating -> Enrolled`

`Enrolled/Rotating -> Suspended/Revoked -> ReenrollmentRequired`

1. On first installation the client creates a non-exportable DeviceIdentity key
   and local-state key, records no live authority, and obtains a bounded,
   single-use bootstrap authorization through a deployment-specific layer
   (user pairing, enterprise provisioning, ISP claim, or workload bootstrap).
2. Registration submits the bootstrap authorization, device public key,
   supported enrollment profile, and ownership proof. The authority assigns a
   device identifier, operator/profile, credential generation, trust roots,
   ACP endpoint set, maximum freshness policy, and credential validity.
3. The client verifies the signed enrollment result and trust/profile binding,
   persists only credential/key references and rollback metadata atomically,
   then starts from an empty grant/session cache.
4. Duplicate byte-equivalent registration under the same bootstrap request ID
   returns the same result while retained. A changed duplicate is rejected.
   Bootstrap authorizations are single-use and server retention is bounded.
5. Reenrollment always creates a new credential generation and invalidates or
   supersedes the old generation. Lost key, reset, revoked device, or corrupt
   security state cannot be repaired using cached grants.
6. Client reset erases local references and ephemeral state, but does not erase
   server revocation. A reset device must prove a new bootstrap authorization.
7. Rotation proves possession of both old and new device keys when the old key
   remains trusted. On loss/compromise it instead uses the reenrollment path and
   an administrator/user recovery authorization.

The lifecycle and state requirements above are frozen for this proposal. The
actual enrollment request/result/challenge schemas, bootstrap-token semantics,
production credential profile, and recovery authority are **REQUIRES SEPARATE
PROTOCOL APPROVAL**. No current NBSR message represents them.

## Narrow Go `AuthorityProvider` contract

The future interface is transport-neutral and context-cancellable:

```go
type AuthorityProvider interface {
    Acquire(context.Context, AcquireRequest) (ProviderVerifiedGrant, error)
    Renew(context.Context, RenewRequest) (ProviderVerifiedGrant, error)
    Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error)
    Close() error
}
```

`AcquireRequest` is immutable and contains the canonical RouteIntent bytes and
digest, stable ServiceIdentity, DeviceIdentity reference/generation,
PolicyContext digest/generation if applicable, target operator/edge/profile,
TS generation and proof-key thumbprint, requested transport/port subset,
128-bit client-generated request ID, and an absolute deadline. It contains no
QUIC connection, stream, channel, credit, or platform-adapter object.

`RenewRequest` contains the full acquisition key, prior verified grant digest,
prior authority generation, and a fresh request ID. Renewal is a new authority
decision and returns a new unique grant nonce; it is not an extension or reuse.

`FreshnessRequest` contains the enrolled device/profile scope and last accepted
checkpoint cursor. `ProviderFreshness` contains a provider-verified signed
checkpoint/snapshot, authority generation, issue/expiry times, revocation set
or bounded delta, next cursor, and continuity proof/status.

`ProviderVerifiedGrant` contains the exact signed RouteGrant bytes, provider
verification metadata, issuer/profile identity, authority generation,
freshness checkpoint reference, exact expiry, and revocation status. It never
contains an unsigned synthesized grant. Despite its name, it is not directly
usable by TS/SC code: the RouteGrant Manager MUST pass the signed bytes through
the independent Go Core verifier and construct an internal, unforgeable
`VerifiedRouteGrant`. Only that internal type can enter the cache or SC owner.

`Invalidate` is deliberately not a provider operation. Invalidation is a local
coordinator transition caused by a verified freshness update, expiry, policy or
identity generation change. This prevents a backend from directly mutating
session/stream state. Push/long-poll mechanics, if used, stay inside the
standard provider and cause an immediate bounded `Freshness` refresh.

## Grant acquisition contract

1. **Request authentication.** TLS 1.3 authenticates the configured ACP service.
   The request is authenticated by the enrolled DeviceIdentity credential and
   includes a signature over the canonical request body and ACP challenge or
   exporter context. Mutual TLS MAY carry that credential, but transport
   authentication does not replace the application proof or grant signature.
2. **RouteIntent binding.** The request carries the exact canonical RouteIntent
   or its exact bytes plus digest; the ACP decision binds every RouteIntent
   authorization dimension. Requested transport/port must be a subset.
3. **TS binding.** The signed proof demonstrates possession of the exact TS key;
   the returned RouteGrant thumbprint must equal that key and TS generation's
   local binding. The TS generation itself is acquisition correlation, not a
   new RouteGrant claim.
4. **Service/policy binding.** Exact service ID, canonical-name digest, route and
   lease IDs, accepted record sequence, operators/edges, policy hash/profile,
   DeviceIdentity generation and applicable PolicyContext are checked against
   the request and local accepted state. Context not representable in the
   existing RouteGrant MUST constrain issuance and be carried in the signed ACP
   response wrapper; changing RouteGrant claims requires separate approval.
5. **Response.** The ACP returns a signed result wrapper containing the exact
   COSE RouteGrant bytes, request ID/digest, authority generation, checkpoint
   reference, result expiry, and profile. Denials return a signed stable class
   when policy permits; unsigned transport errors never become authority.
6. **Independent verification.** Go Core checks canonical encoding, bounds,
   version/profile, protected `alg` and `kid`, issuer purpose/trust/lifecycle,
   Ed25519 signature, every grant/request/local-state binding, time window,
   record/policy generation, checkpoint freshness and revocation. Unknown or
   extra fields fail closed according to the approved schema.
7. **Consumption.** An unconsumed grant is atomically reserved by one SC
   admission owner and bound to one channel ID at the existing commit boundary.
   Cancellation before commit may release only when non-consumption is proven.
   Ambiguous completion quarantines the grant; recreation acquires fresh
   authority. Wall-clock validity never permits consumed-grant reuse.

## Standard ACP transport decision

| Option | Complexity/reuse | Authentication/replay | Deployment/operations | Coupling | Decision |
|---|---|---|---|---|---|
| A. HTTP/1.1 or HTTP/2 over TLS 1.3 | Lowest; existing Go/Python ecosystem and prototype control APIs; pooled connection | Server TLS plus device application proof/mTLS; canonical request ID and signature | Best firewall/NAT and router support; familiar proxies, rate limits and observability | ACP-specific, independent of Core/QUIC | **Recommended standard** |
| B. QUIC/TLS NBSR ACP transport | Reuses QUIC expertise but needs new connection/message lifecycle | Strong TLS; still needs application idempotency and signed objects | UDP blocking/NAT timeout and embedded operations are harder | Risks coupling authority availability to data-plane stack | Optional future profile only |
| C. Existing Core control stream | Appears reusable but entangles grant acquisition with a TS that needs the grant | Circular trust/binding and replay ownership | One connection, but poor failure isolation and harder inspection | Violates backend/state-machine separation | Rejected |

The standard is bounded request/response HTTP over TLS 1.3, preferring HTTP/2
connection reuse when available and permitting HTTP/1.1 without semantic
change. There is one reusable connection pool per ACP authority/profile, not
one connection or call per Application Stream. Redirects are disabled unless
the target is explicitly configured and identity-equivalent. Compression is
disabled for secret-bearing requests unless separately analyzed. HTTP status is
transport metadata; the signed bounded body determines NBSR result semantics.

The endpoints and canonical message bodies for enrollment, acquire, renew, and
freshness are new protocol messages and **REQUIRE SEPARATE PROTOCOL APPROVAL**.

## Encoding and signing profile

New ACP application bodies MUST use bounded deterministic CBOR and versioned
integer-key maps. Signed authority MUST reuse tagged COSE Sign1, protected
`alg=-8`, protected opaque `kid` of 1..64 bytes, Ed25519, SHA-256 bindings, empty
external AAD unless a separately approved profile defines a nonempty value, and
caller-supplied exact-purpose trust. Enrollment keys, ACP request keys,
RouteGrant issuer keys, freshness/revocation keys, and federation governance
keys are distinct purposes even if an operator controls several. JWT/JWS and a
second signature stack are forbidden. Each message has exact byte/depth/array
limits, a fixed version/profile, a purpose/domain separator, and independent
vectors before runtime use.

## Idempotency and replay

The client owns an unpredictable 128-bit request ID and persists it only for the
bounded lifetime of one in-flight acquisition/renewal. Its request signature
binds request ID, canonical body digest, device credential generation, ACP
authority/profile, TS proof thumbprint, and server challenge/freshness context.

The ACP keys idempotency by `(device identity, credential generation, operation,
request ID)`. During a configured finite retry horizon it stores only request
digest, terminal result digest/bytes, expiry, and status. An exact duplicate
returns the byte-identical signed result. A same-key/different-digest duplicate
is a terminal conflict. Entries are capped per device and globally and expire
no earlier than the permitted client retry horizon; saturation rejects before
minting. After the horizon, a duplicate is `AmbiguousRequest`, never a signal to
reuse an old response. The client uses one request ID across transport retries,
coalesces identical acquisitions, uses finite attempts/deadline/backoff, and
quarantines timeout-ambiguous grants. A new request ID can mint a fresh grant
only after the prior result is known unusable or is deliberately abandoned.

Exact horizons, entry/byte caps, challenges, and schemas are profile
configuration requiring measurement and separate protocol approval; no
unbounded idempotency database is required.

## Renewal

Renewal begins before the earliest of grant expiry, freshness expiry, policy
expiry, credential expiry, or TS replacement deadline. The threshold is a
bounded profile setting expressed as a fraction plus minimum/maximum lead time;
its production default requires measurement. Per-client cryptographic jitter
is bounded so it never schedules after the latest safe start. Identical renewal
keys coalesce to one pending operation, with caps per service and globally.

A successful renewal yields a separately signed, independently verified grant
with a fresh nonce and current authority generation. The manager atomically
publishes the new unconsumed entry; the old unconsumed entry is invalidated.
Already-consumed SC authority follows existing expiry/revocation rules. Failure
never extends local validity: retry only within the finite budget while the old
authority and freshness remain valid, then reject new authority-dependent work.
Generation change forces full reacquisition, not ordinary renewal.

## Revocation and freshness

The standard is a **hybrid bounded-poll plus optional push hint** model. The
security authority is an independently signed freshness checkpoint/snapshot;
push only reduces latency and cannot extend trust. The provider polls before the
checkpoint's explicit `fresh_until` and immediately after a valid push hint,
network recovery, wake, credential/config change, or generation discontinuity.
Polling coalesces per authority/profile and has bounded jitter/retries.

The client may trust cached unconsumed grants only while all are true:

- grant and enclosing result are unexpired;
- the latest verified checkpoint is unexpired;
- its generation/sequence is not below the durable accepted floor;
- no matching revocation, replacement, identity/policy change, or profile
  downgrade applies; and
- the grant's authority generation equals the current coordinator generation.

Therefore the maximum disconnected trust is explicit:

`min(grant expiry, checkpoint fresh_until, credential/policy expiry) - now`.

It is never unlimited and can be zero. When freshness cannot be established,
new grant acquisition, SC creation, TS-B preparation, credit allocation, and
new Application Streams fail closed once the checkpoint expires. Existing
streams obey frozen WP4 behavior: verified terminal RouteGrant/channel
revocation resets them; ordinary inability to refresh alone stops new work and
does not invent a retroactive revoke before existing authority expires. An
operator profile MAY require earlier stream termination, but that policy must
be explicit and cannot extend any authority.

## Authority-generation barrier

The coordinator owns one monotonic uint64 `AuthorityGeneration` per accepted
authority/profile scope and a nondecreasing durable restart floor. A verified
checkpoint update is applied as one ordered transaction:

1. validate signature, continuity, time, profile, generation and all deltas;
2. reserve bounded invalidation work and reject the whole update on resource
   failure before publishing partial authority;
3. publish the higher generation/freshness state;
4. invalidate affected grant-cache entries and SC readiness across active and
   replacement TS generations;
5. prevent subsequent selector snapshots until publication is visible.

A new flow atomically captures TS generation, authority generation and SC
binding. SC admission commits only if unchanged. Credit allocation and the
final payload-gating boundary re-read the generation and live revocation state.
Mismatch releases/quarantines reserved state and rejects the flow. Thus an
update ordered before the final gate cannot be bypassed by a stale selector or
prepared TS-B. Generation overflow is terminal and requires reenrollment/new
profile; it never wraps. TS rotation is not implemented in this tranche.

## Bounded RouteGrant cache and coalescing

The cache key is a canonical digest over: exact RouteIntent bytes/digest;
ServiceIdentity; canonical name digest; route/lease/record sequence; requested
transport/port; source/destination operator and edge set; authority/profile;
DeviceIdentity and credential generation; PolicyContext digest/generation;
policy hash; TS generation and proof-key thumbprint; and authority generation.

Each entry stores exact signed bytes, verified parsed claims, issuer/profile,
grant/result/checkpoint expiry, authority generation, revocation status, digest,
byte cost, and lifecycle `Available`, `Reserved`, `Consumed`, `Quarantined`, or
`Invalid`. Only `Available` is returned. `Consumed`, `Quarantined`, and `Invalid`
are never resurrected. The cache has configured entry and byte caps, per-service
caps, bounded pending acquisitions, deterministic least-useful eviction of only
available entries, and reservation-before-insert. It is ephemeral by default;
restart begins empty. No Application Stream calls the ACP when a valid SC and
credit already exist.

## Failure and retry taxonomy

| Failure | Class | Client rule |
|---|---|---|
| ACP unreachable / timeout before authenticated result | Retryable within budget | Same request ID, coalesced exponential backoff+jitter; then stable unavailable/timeout |
| TLS server-auth or client-auth failure | Conditional | No retry until endpoint/trust/credential state changes; never ignore validation |
| Malformed/noncanonical/oversized response | Terminal security | Reject, quarantine bytes, open endpoint circuit, bounded safe audit |
| Invalid signature, issuer purpose, or response substitution | Terminal security | Reject; no fallback endpoint unless independently configured/trusted |
| Stale authority/checkpoint generation | Conditional | Reject; refresh from approved endpoint; never lower local floor |
| Expired or revoked authority | Terminal for object | Invalidate; reacquire only if current policy/identity permits |
| Unknown service / policy denial | Terminal until state changes | Stable local denial; no automatic endpoint fan-out |
| Quota/capacity denial | Conditional | Honor bounded signed retry guidance if present; cap wait and attempts |
| Ambiguous request/result | Conditional, fail closed | Reconcile exact request ID within horizon; otherwise quarantine and acquire fresh only under policy |
| Operator disagreement / continuity gap | Terminal security pending fresh consistent state | Publish no partial generation; fail affected new work |
| Profile/version downgrade attempt | Terminal security | Reject without mutation; no legacy fallback |
| Local cache/provider capacity | Conditional local overload | Reject before work; cleanup/expiry may permit retry |
| Device revoked/lost key/credential generation rejected | Terminal | Destroy live authority as policy requires; reenrollment only |

Every retry has an absolute deadline, finite attempt/time budget, bounded jitter,
per-scope circuit, cancellation, and queue reservation. Server `Retry-After` is
only a bounded hint and cannot override local safety deadlines.

## Threat-model amendment

| Threat | Required mitigation |
|---|---|
| Stolen enrollment key | Non-exportable storage, generation/revocation, bounded credential validity, recovery reenrollment, no cached-authority recovery |
| Malicious local process | Privilege separation, opaque key handles, authenticated local policy context, no grant/credential exposure, bounded requests |
| Malicious ACP endpoint | Exact TLS identity plus independently signed request/result objects; Go Core re-verifies issuer/purpose/bindings/freshness |
| Compromised resolver authority confusion | RouteIntent is constrained input; exact ServiceIdentity/name/record/policy binding; resolver cannot issue grants |
| Replayed/substituted RouteGrant | Exact request/TS/service/policy binding, unique nonce, signature, current checkpoint, one-owner consumption |
| Stale freshness / restart rollback | Expiring signed checkpoint, durable nondecreasing floor/external anchor, empty ephemeral cache after restart, fail closed |
| Downgrade | Exact version/profile pinning; unknown/legacy fields and redirects rejected without mutation |
| Cross-service or cross-TS use | Complete cache key and verification; distinct TS proof key; SC/channel/credit/final-gate binding |
| Request amplification/resource exhaustion | Client coalescing and caps; server per-device/global quotas, bounded bodies/idempotency records, cheap validation first |
| Malformed ACP traffic | Size/depth/count limits, deterministic parser errors, fuzzing, no panic/crash, bounded audit |
| Compromised device | Cannot be fully contained locally; revoke credential/grants, deny new work, reimage/reenroll; residual access lasts no longer than earliest authority/freshness expiry |

Required invariants are explicit: a provider cannot mint authority; TLS alone is
not grant validation; every grant is exact-service/exact-TS; restart cannot make
old authority live; cache cannot undo revocation; all authority state is
bounded; and malformed ACP traffic cannot crash the client.

## Protocol gap register for Tranche 2

| Item | Classification | Frozen disposition |
|---|---|---|
| ACP authentication | REQUIRES SEPARATE PROTOCOL APPROVAL | TLS 1.3 server identity plus DeviceIdentity application proof/mTLS profile |
| ACP transport | REQUIRES SEPARATE PROTOCOL APPROVAL | HTTP request/response over TLS 1.3; HTTP/2 preferred, HTTP/1.1 semantically equivalent |
| Grant acquisition | REQUIRES SEPARATE PROTOCOL APPROVAL | Canonical signed request/result wrapper carrying unchanged COSE RouteGrant |
| Idempotency | REQUIRES SEPARATE PROTOCOL APPROVAL | 128-bit client request ID, exact duplicate replay, bounded retention/caps |
| Renewal | REQUIRES SEPARATE PROTOCOL APPROVAL | Fresh decision/grant/nonce; never local extension |
| Freshness checkpoint | REQUIRES SEPARATE PROTOCOL APPROVAL | Signed expiring generation/sequence checkpoint/snapshot |
| Revocation delivery | REQUIRES SEPARATE PROTOCOL APPROVAL | Bounded polling is authoritative; optional push is a refresh hint |
| Enrollment | REQUIRES SEPARATE PROTOCOL APPROVAL | One core lifecycle with deployment-specific bootstrap layers |
| Device key rotation/recovery | REQUIRES SEPARATE PROTOCOL APPROVAL | Higher credential generation; old+new proof or recovery reenrollment |
| TS proof-key binding | RESOLVED BY EXISTING PROTOCOL | Existing RouteGrant thumbprint; CLIENT IMPLEMENTATION owns distinct TS generation key |
| RouteIntent/RouteGrant encoding | RESOLVED BY EXISTING PROTOCOL | Reuse exact deterministic CBOR and existing claims |
| RouteGrant signature verification | RESOLVED BY EXISTING PROTOCOL | Reuse COSE Sign1/Ed25519/protected `kid`; Core always re-verifies |
| Grant single consumption | RESOLVED BY EXISTING PROTOCOL | CLIENT IMPLEMENTATION owns atomic available/reserved/consumed lifecycle |
| Grant cache/coalescing | CLIENT IMPLEMENTATION | Complete key, finite entries/bytes/pending work, ephemeral by default |
| Authority generation barrier | CLIENT IMPLEMENTATION | Ordered provider update, invalidation fan-out, selector and final-gate recheck |
| ACP endpoint/rate-limit service | CONTROL-PLANE IMPLEMENTATION | Connection reuse, quotas, bounded parser/idempotency storage and observability |
| Workload identity requiredness | RESOLVED BY EXISTING PROTOCOL | Optional policy context; deployment profile may require it |
| Client ACP trust domain | CLIENT IMPLEMENTATION | Approved: authenticate only the enrolled Source Operator ACP; all cross-operator/federation authority remains behind that boundary |
| Maximum freshness/offline window | HUMAN DECISION REQUIRED | Approve profile policy/bounds after measurement; cannot exceed earliest signed expiry |
| Durable rollback anchor | HUMAN DECISION REQUIRED | Remote ACP floor recommended; TPM is stronger optional local layer |

## Human protocol/security decisions

**Approved decision 1 — client ACP trust boundary.** The client MUST trust and
authenticate only to its enrolled Source Operator ACP. It MUST NOT discover,
select, negotiate with, or directly trust a destination-operator or federation
ACP. Cross-operator route authorization, federation trust, issuer validation,
and operator-to-operator negotiation are responsibilities of the NBSR
operator/federation layer and remain transparent to the client. The Source
Operator ACP returns only the final authority material required by the client.
Go Core still independently verifies the applicable signed RouteGrant, exact
issuer trust supplied by the enrolled profile, and every service, operator,
policy, TS-key, validity, revocation, and profile binding. This approval does
not permit the client to accept a grant merely because the enrolled ACP
transport delivered it, and it does not define or modify federation wire
semantics.

The following decisions remain pending:

1. **Freshness/offline policy bounds.** Recommended: signed operator/profile
   bounds with a short checkpoint lifetime measured separately for router and
   interactive-client availability, always capped by grant/credential expiry.
   Alternative: zero offline trust (online checkpoint for every new authority
   lifecycle). Zero offline trust minimizes stale permission but makes ACP
   outages stop all new service/channel work and increases load; bounded
   checkpoints preserve lightweight operation while creating an explicit
   maximum revocation-latency window.
2. **Rollback anchor.** Recommended: persist a signed ACP checkpoint generation
   floor and require a fresh ACP checkpoint after restart before new
   authority-dependent work; use TPM monotonic storage when available as an
   additional defense. Alternative: require TPM/secure-element monotonic state
   on every platform. The recommendation works on laptops, servers, and routers
   but loses offline startup; mandatory hardware gives stronger local rollback
   resistance but excludes or complicates unsupported devices.

The two pending decisions do not block a coherent design: they are explicit
approval inputs to the protocol profile and implementation plan. None permits
a Core, P1F, or P2D wire change.

## Proposed Tranche 2 implementation decomposition

Implementation remains prohibited until this design and the separate ACP wire
profile are approved.

1. Identity/key-reference types and deterministic enrollment lifecycle model.
2. Transport-neutral `AuthorityProvider` types, sealed verified-authority
   boundary, stable errors, and fake clock/randomness.
3. Exact Go RouteGrant/COSE verifier using frozen vectors and independent
   negative/mutation tests.
4. Bounded complete-key grant cache, one-owner consumption, acquisition and
   renewal coalescing.
5. Signed freshness state, durable generation floor, invalidation fan-out, and
   authority-generation barrier model.
6. Bounded idempotency/retry/ambiguity state machine with cancellation tests.
7. Mock/in-memory provider that can only return signed fixtures and inject
   deterministic failures; it must not mint production authority.
8. Cross-component deterministic, property, fuzz, concurrency, capacity,
   restart/rollback, revocation-race and malformed-input tests.
9. Only after separate protocol approval: HTTP/TLS ACP provider, enrollment
   adapter, canonical wire vectors, independent verifier, and live interop.

## Acceptance criteria

- Documentation contains no runtime or wire implementation and changes no
  Tranche 1, Core, F75, P1F, or P2D semantics.
- Every ACP/enrollment wire addition is separately approval-gated.
- AuthorityProvider cannot produce a TS/SC-usable object without independent
  Go verification.
- Identity purposes, TS generation binding, cache dimensions, freshness limit,
  restart floor, generation barrier, and retry terminal states are unambiguous.
- No cached grant is reusable after consumption, ambiguity, revocation,
  generation change, expiry, or restart.
- All client/server state described has entry, byte, time, retry, or concurrency
  bounds whose shipping values require measurement rather than invention.
- Application Stream creation has no ACP round trip when valid SC and credit
  authority already exist.

## Self-review

Placeholder scan: no unresolved placeholders or invented timing defaults remain.
Consistency: the proposed ACP carries unchanged signed RouteGrant bytes and does
not alter Core admission. Scope: runtime, live networking, rotation, resolver,
and platform adapters are excluded. Ambiguity: all new wire behavior, the
approved Source Operator ACP boundary, and the two pending human policy choices
are explicitly classified.
