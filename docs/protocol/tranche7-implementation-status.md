# Production Go client Tranche 7 implementation status

Status: IMPLEMENTED; final verification is recorded at handoff.

## Implemented scope

The production Go client now provides a stdlib-only, in-process observability
collector with fixed enum dimensions and fixed-size atomic counters. Core-state
and authority observer adapters discard object identity and expose only closed
lifecycle, outcome, exhaustion, and fail-closed categories. Aggregate health
separates expected denial from internal failure and reports fixed resource
usage/capacity slots. FlowStore and the explicit proxy expose aggregate current
usage without names, MappingIDs, LocalFlowIDs, digests, grants, or endpoints.

Core and authority observer event types no longer carry raw generation,
MappingID, ServiceHandle, StreamID, RequestID, or RouteGrant digest values.
Telemetry cannot represent canonical/service names, Origin Endpoints, proofs,
keys, credentials, tokens, or payload. Invalid telemetry dimensions collapse
into one counter rather than creating a label.

A proxy lifecycle defect was fixed: if a client disconnects after the explicit
proxy creates a FlowContext but before the router consumes it, tracked
connection teardown now removes that still-unconsumed correlation. A consume
versus close race remains fail closed: exactly one operation wins and no mapping
authority is reassigned. Closing after successful consumption is harmless.

## Bounds and overload behavior

Existing entry, byte, waiter, concurrency, session-generation, channel, Stream
Credit, Application Stream, retry, and timer bounds remain unchanged. Live
security bindings are not evicted to admit new work. Existing typed capacity
errors remain the rejection boundary, and the new observability layer adds no
queue, goroutine, background worker, timer, network listener, or external
backend.

The collector has compile-time dimensions of ten domains, nine event kinds,
and three outcomes. It uses one fixed atomic counter per valid combination plus
one invalid-event counter. Health uses nine fixed resource slots. The explicit
proxy connection semaphore and FlowStore retain their configured hard limits;
aggregate usage returns to zero after teardown.

## Measured lifecycle evidence

Hardware/software: Intel Core i5-10210U, 16,942,501,888 bytes physical RAM,
Windows 11 Pro 10.0.26200, Go 1.26.5 windows/amd64.

One race-enabled diagnostic ran 300 sequential real `net.Pipe` HTTP CONNECT
accept/disconnect lifecycles at concurrency 1. Observed duration was 33.3894 ms;
goroutines were 2 before and 2 after; heap allocation was 305,208 bytes before
and 280,736 bytes after an explicit final GC; one GC cycle occurred. Every
iteration returned FlowStore entries/bytes and proxy active connections to
zero, with zero failures. This is a bounded current-machine leak diagnostic,
not throughput, production capacity, hardware sizing, or steady-state memory
evidence.

## Verification

Fresh closure validation includes the complete production Go client suite,
UCRT race tests for all changed and lifecycle-integration packages, `go vet`,
gofmt verification, `git diff --check`, the focused churn diagnostic, and the
V3.6 anti-drift review. The full Go run passed 895 tests across ten tested
packages. The existing seven-case live Go-to-Rust P1F/P2D verifier passed with
the current Go peer and the unchanged previously validated Rust binary from
`C:\NBSR-build\tranche5-closure-b124939`.

A separate fresh Rust rebuild with Rust/Cargo 1.97.1 was INCONCLUSIVE: the
positive case returned `session error 29` and the Rust process reported
`ControlStreamFailed`. Binary isolation showed the current Go peer passes all
seven cases against the validated Rust binary, while the fresh Rust binary
fails even with the previously validated Go peer. No Rust source, Cargo
manifest, or lockfile changed since the validated binary. This is classified
as an environment/toolchain build-provenance failure, not a Tranche 7 Go
regression. Exact commands and results are recorded in the handoff report.

## Nonclaims and remaining limitations

This tranche adds no demo, transparent DNS interception, TUN/WFP adapter,
platform installation, proxy autoconfiguration, UDP/CONNECT-UDP, resolver
failover, cross-edge handover, wire field, registry, vector, cryptographic, or
authority-model behavior. Health is an in-process aggregate model, not an
authenticated operating-system health endpoint or external telemetry backend.
No shipping defaults or production sizing are established by the bounded
single-machine diagnostic.

Within the existing explicit-proxy boundary, the client is ready to serve as
the basis of demo construction: its current ownership path remains bounded,
fail closed, diagnosable without sensitive labels, and covered by deterministic
cleanup/race/churn evidence. This is not a production-readiness claim.
