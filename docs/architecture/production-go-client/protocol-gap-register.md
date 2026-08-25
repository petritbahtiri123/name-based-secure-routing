# Production Go client gap register

No gap in this register authorizes a wire change. Every wire-affecting proposal
is **REQUIRES SEPARATE PROTOCOL APPROVAL**.

The proposed resolutions for identity, enrollment, ACP transport,
authentication, acquisition, idempotency, renewal, freshness, revocation,
generation ordering, and rollback are consolidated in
[the Tranche 2 design](tranche2-identity-authority-control-plane.md). Its new
wire contracts remain approval-gated; its client-only boundaries may be planned
only after human approval of that design.

Approved Tranche 2 decision 1 fixes the client-facing trust boundary: the
client authenticates only to its enrolled Source Operator ACP. Destination
operator selection, federation trust, cross-operator issuer validation, and
operator negotiation are not client responsibilities. Go Core nevertheless
independently verifies the final signed RouteGrant and enrolled-profile
bindings; authenticated ACP delivery is not authority by itself.

Approved Tranche 2 decision 2 fixes client freshness behavior: checkpoints are
obtained through bounded polling, push is only a refresh hint, and no ACP check
occurs per Application Stream. Local authority remains usable only through the
earliest applicable grant, checkpoint, credential/policy, or generation limit.
After freshness expiry, new authority-dependent state fails closed; existing
admitted streams are not silently reauthorized and remain subject to the
separately defined revocation and close-versus-drain policy.

Approved Tranche 2 decision 3 resolves restart rollback protection. The client
persists a durable signed ACP authority-generation floor, restores no live
RouteGrant/session/channel/credit/stream authority, and requires fresh
validation with its enrolled Source Operator ACP before new authority-dependent
work after restart. Failure to prove a non-rolled-back floor fails closed until
freshness is restored. TPM or secure monotonic hardware is optional additional
defense, not a universal requirement.

| Gap | Why unresolved | Blocking what | Protocol or implementation | Recommended decision |
|---|---|---|---|---|
| Authority source direction | Core verifies/uses grants; Go peer loads fixtures; no live acquisition exchange | Production channel creation and TS-B authorization | Decision resolved; contract not frozen | Standard source is the NBSR Authority Control Plane behind `AuthorityProvider`; freeze its API/transport/authentication without changing Core wire |
| Grant renewal/idempotency | No provider request/correlation/freshness contract | Proactive renewal and safe retry | **REQUIRES_PROTOCOL_DECISION** | Define exact request key, response freshness, cancellation, and duplicate semantics |
| RouteGrant single consumption | Existing semantics make each grant/nonce specific to one channel; a cache could obscure consumption | Safe caching, retry, recreation, rotation | EXISTING_PROTOCOL/CLIENT_IMPLEMENTATION | Cache only unconsumed grants; atomically bind/consume once; acquire fresh authority for every distinct channel |
| Revocation delivery/freshness | Runtime rules exist, but no production client feed/SLA | Timely invalidation and cross-generation fan-out | **REQUIRES_PROTOCOL_DECISION** | Approve authenticated snapshot/stream semantics, monotonic generation, outage rule, and maximum staleness |
| Client/workload identity and enrollment | Verification primitives do not define production client credential lifecycle | Startup auth, local app isolation, managed recovery | **REQUIRES_PROTOCOL_DECISION** | Approve purpose-separated identity profile, enrollment, rotation, revocation, recovery, and key storage requirements |
| TS-specific grant key lifecycle | Grant thumbprint binding exists; production key generation/rotation ownership does not | Fresh authority during rotation | **REQUIRES_PROTOCOL_DECISION** | Bind each TS generation to an approved proof-key generation and prohibit cross-generation reuse |
| RouteGrant use during rotation | Evidence says TS-A authority cannot authorize TS-B | Make-before-break rotation | Protocol rule exists; client contract missing | Acquire and verify fresh TS-B grant before selector switch |
| Atomic new-flow selector | No production application/session owner exists | Race-free cutover | CLIENT_IMPLEMENTATION | One global compare-and-swap selector per TS reuse key; pin each flow for life; no per-service fallback after cutover |
| Cross-generation revocation | Current code-level client fan-out owner and ordering barrier are absent | Rotation security | CLIENT_IMPLEMENTATION plus provider freshness decision | Use a monotonic authority-generation barrier across fan-out, selector read, SC readiness, and final credit/stream validation |
| Rotation hard-limit behavior | Trigger owner/default high-water unmeasured | Guaranteed pre-cap replacement | CLIENT_IMPLEMENTATION/OPERATIONS | Fail new flows before 10,000 if replacement is not ready; derive proactive threshold by measurement |
| SC readiness at cutover | No production policy for eager vs lazy recreation | Per-service availability during rotation | CLIENT_IMPLEMENTATION | Permit lazy recreation only if selection waits for that service's SC/credit readiness; never select unusable generation |
| Ambiguous SC admission completion | Destination may commit while the response is lost; blind retry conflicts with single-use grant semantics | Safe SC recovery/retry | **REQUIRES_PROTOCOL_DECISION** | Treat as non-retryable unless existing semantics prove deterministic reconciliation; otherwise approve a separate recovery contract |
| Existing-stream revoke policy | Architecture allows immediate revoke or approved bounded drain | Exact user-visible termination | **REQUIRES_PROTOCOL_DECISION** | Approve per-revocation-class immediate-close versus bounded-drain rule; rotation must obey it |
| Synthetic mapping TTL/invalidation | Tranche 6 now enforces earliest-authority expiry, immutable replacement, active-reference retention, and empty restart | Transparent/platform resolver ownership beyond the explicit proxy | CLIENT_IMPLEMENTATION complete for explicit-proxy scope | Reuse the bounded ephemeral Tranche 6 mapping contract; separately approve platform resolver ownership |
| Literal shared Synthetic IP correlation | Identical IP/port flows do not encode original service | Transparent adapters | CLIENT_IMPLEMENTATION complete for explicit proxy; PLATFORM_INTEGRATION remains | The explicit SOCKS5-domain/HTTP CONNECT adapter supplies a local single-use MappingID/FlowContext; native transparent correlation remains a separate platform tranche |
| ServiceHandle wire representation | Existing P2D authenticates with channel ID/generation; a compact handle is not currently a wire identifier | Only a proposal to transmit/replace identifiers | No gap for local lookup; wire change gated | Use local client/server aliases over existing SC state; any transmitted handle/new field is **REQUIRES SEPARATE PROTOCOL APPROVAL** |
| Resolver failover | Multiple replies may conflict or be stale | Availability without poisoning | **REQUIRES_PROTOCOL_DECISION** | Define approved resolver set, authenticated precedence, conflict/freshness failure rule |
| OS interception model | Windows/Linux/router require different mechanisms | Transparent production deployment | PLATFORM_INTEGRATION | Proxy-first core validation; TUN for Linux/router; separately approve Windows native adapter |
| Local application identity | OS attribution strength varies by adapter | Compromised-app containment | PLATFORM_INTEGRATION/SECURITY | Define adapter-specific authenticated peer metadata and policy fallback; Synthetic IP alone is insufficient |
| Network-change classification | QUIC migration exists but capture/policy compatibility is platform-specific | Wi-Fi/Ethernet/VPN/sleep behavior | CLIENT_IMPLEMENTATION/PLATFORM_INTEGRATION | Event-driven revalidation; preserve only same-edge compatible sessions, otherwise create fresh TS |
| Durable rollback protection | A local integrity key alone cannot detect restoration of an older valid snapshot | Corruption/power-loss/rollback safety | CLIENT_IMPLEMENTATION/SECURITY | Persist the approved signed ACP generation floor, restore no live authority, require fresh enrolled-ACP validation after restart, and use TPM only as optional defense |
| Resource defaults | Tranche 7 measured one bounded Windows laptop proxy-disconnect workload, but product hardware/workload profiles do not exist | Shipping configuration | OPERATIONS | Retain current explicit bounds; measure representative laptop/server/router profiles before setting defaults or targets |
| UDP/IP application profiles | Initial verified path is reliable streams/TCP | UDP and transparent IP support | **REQUIRES_PROTOCOL_DECISION** | Keep out of first client; separately approve CONNECT-UDP/QUIC DATAGRAM or CONNECT-IP profile |
| Cross-edge handover/resume | Current approved behavior is same-edge bounded resume | Mobility/failover across gateways | **REQUIRES_PROTOCOL_DECISION** | Use fresh TS/grant today; approve explicit handover only in a separate protocol tranche |

## Human-decision status

All three Tranche 2 client identity/authority decisions are resolved: enrolled
Source Operator ACP trust, bounded polling/offline freshness, and signed ACP
generation-floor restart protection. A Tranche 2 implementation plan may use
those approved client contracts, but live enrollment/ACP message schemas and
networking still require separate protocol approval.

The following decisions belong to later or separately scoped tranches and are
not silently resolved here:

1. Resolver authority failover/conflict behavior and transparent platform DNS
   ownership beyond the bounded explicit-proxy Tranche 6 implementation.
2. Existing-stream behavior for each revocation class: immediate close or
   explicitly bounded drain.
3. The first adapter is the approved **explicit user-space SOCKS5-domain/HTTP
   CONNECT proxy with one shared Synthetic IP and local MappingID/FlowContext
   correlation**. TUN and Windows-native transparent adapters remain separate
   platform tranches.
4. TS-rotation implementation and global-per-reuse-key cutover integration.
5. An SC ambiguous-completion reconciliation path; the current default remains
   fail closed with no blind retry.

The `REQUIRES_PROTOCOL_DECISION` classification includes unresolved control-plane
or security contracts because it is the required gap category; it does not imply
a Core wire change. These decisions need not change frozen P1F/P2D semantics.
Any decision that adds a Core message or changes wire fields is **REQUIRES
SEPARATE PROTOCOL APPROVAL**.
