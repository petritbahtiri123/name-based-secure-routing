# Production Go client design package

**Status:** Ready for human design review; no production implementation exists

**Repository baseline:** `codex/nbsr-v3-wp0-wp1` at
`61be7e8280d4a74da0d81c54c01b350af7343e24`

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
