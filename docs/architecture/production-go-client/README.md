# Production Go client design package

**Status:** Tranche 2 design approved; no production authority implementation exists

**Repository baseline:** `codex/nbsr-v3-wp0-wp1` at
`8189d917e50df67e740fc3f3e8a5195f7cac7219`

This package defines the future production NBSR Go client without changing
Core, F75, P1F, P2D, federation, or transport wire semantics.

Accepted P2D evidence is an immutable design input: median lifecycle throughput
`4,282.05 → 15,567.44 streams/s` (+263.55%), p99
`18.6981 → 5.4623 ms`, and a 300.387-second soak with 4,832,000 successful
lifecycles under the validated 10,000-entry replay limit. This package neither
regenerates those results nor converts them into production-client targets.

- [Requirements](requirements.md)
- [Architecture](architecture.md)
- [Client subsystem threat model](threat-model.md)
- [Protocol gap register](protocol-gap-register.md)
- [Future implementation tranches](implementation-tranches.md)
- [Tranche 2 identity and Authority Control Plane design](tranche2-identity-authority-control-plane.md)

The repository-wide [threat model](../../threat-model.md) remains authoritative.
The client threat model narrows that model; it does not replace it.

## Approved amendment: lightweight tracking and authority source

The approved internal lookup path is `Synthetic Mapping → Service Identity →
Service Channel → ServiceHandle`. `ServiceHandle` is a bounded, fixed-width,
session-local implementation identifier, not wire authority. Active streams are
indexed by `(TS generation, ServiceHandle, QUIC Stream ID)`. The standard
production authority source is the NBSR Authority Control Plane behind the Go
Core's narrow `AuthorityProvider` interface.

## Evidence inventory

| Capability | Exists | Language | Production-ready | Missing |
|---|---|---|---|---|
| Core RouteIntent/RouteGrant models and verification | Yes | Python, Rust, Go verifier/peer | No; protocol/reference evidence | Live client acquisition, renewal, revocation feed |
| Go-to-Rust QUIC/TLS/ALPN and P1F/P2D interop | Yes | Go and Rust | No; standalone interop/benchmark peer | Application ownership, long-lived agent lifecycle |
| Resolver and synthetic mapping prototype | Yes | Python | No; loopback/demo scope | OS integration, durable policy, collision/recovery proof |
| Windows agent prototype | Yes | Python | No | Signed service/driver, full-device interception |
| Transport Session runtime | Yes | Rust destination/reference | No production Go owner | Pool, selector, recovery, network-change handling |
| Service Channel runtime | Yes | Rust destination/reference | Lab/reference only | Go lifecycle owner and multi-service pool |
| Stream Credit `nbsr-stream-credit-1` | Yes | Rust plus Go interop peer | Accepted wire evidence, not a production client | Concurrent Go owner, refill/recovery integration |
| Application Streams | Yes | Rust plus Go interop peer | Interop/benchmark only | Local-flow forwarding and retry boundary |
| Session rotation model/evidence | Design/model only | Python/docs | No | Production Go owner and fresh authority path |
| Federation/profile authority | Yes | Python, Rust, Go/Node verifiers | Development profile, not production authority service | Managed production distribution and freshness |
| Identity/key primitives | Partial | Python, Rust, Go verification | No managed client identity lifecycle | Device/workload enrollment, secure storage, rotation/recovery |
| Revocation/tombstones | Partial | Python/Rust reference | Not end-to-end client production behavior | Authenticated client feed and cross-generation fan-out |
| Routing/tunnel adapters | Prototype/design only | Python/docs | No | Chosen OS adapter and bypass containment |
| Crash/recovery documentation | Partial | Docs/reference state | No production client procedure | Client journal/config integrity and recovery tests |

Production readiness is explicitly not inferred from file names or successful
lab interoperability.

## Tranche 2 proposed freeze

The Tranche 2 design freezes the purpose-separated client identity hierarchy,
transport-neutral `AuthorityProvider`, independently verified RouteGrant
lifecycle, bounded cache/idempotency/retry behavior, hybrid freshness model,
and authority-generation barrier. It recommends HTTP request/response over TLS
1.3 as the standard ACP transport while retaining deterministic CBOR and COSE
Sign1/Ed25519 authority. Enrollment and ACP message schemas remain
**REQUIRES SEPARATE PROTOCOL APPROVAL**; no Core/P1F/P2D change is authorized.
Human decision 1 is approved: the client authenticates only to its enrolled
Source Operator ACP. Cross-operator authorization and federation negotiation
remain operator-layer responsibilities transparent to the client; delivery by
that ACP never replaces independent RouteGrant/profile verification.
Human decision 2 is approved: there is no ACP freshness check per Application
Stream. Local authority is usable only while its grant, signed checkpoint,
credential/policy validity, and authority generation remain current; after
freshness expiry, new authority-dependent work fails closed until refresh.
Human decision 3 is approved: restart retains only a durable signed ACP
authority-generation floor and requires fresh validation with the enrolled
Source Operator ACP before new authority-dependent work. No live authority
state is restored from disk; TPM or secure monotonic hardware is optional
defense-in-depth rather than a universal requirement.
