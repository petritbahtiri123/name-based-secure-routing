# NBSR Benchmark Design v0.1

## Scope

This benchmark measures the unoptimized loopback behavior of direct QUIC/TLS,
Rust-to-Rust NBSR, and independent Go-to-Rust NBSR. It does not change Core
v0.2, F75, Federation v0.1, RouteGrant, exporter, channel, stream, replay,
lifecycle, or downgrade behavior. QUIC 0-RTT remains disabled. HTTP/3 is `NOT
SUPPORTED BY CURRENT TEST SURFACE`.

## Measurement boundaries

All durations use monotonic clocks and integer nanoseconds.

| Field | Exact boundary |
|---|---|
| `transport_handshake_ns` | source dial start through authenticated QUIC availability |
| `hello_rtt_ns` | source CLIENT_HELLO send through valid EDGE_HELLO receipt |
| `source_admission_ns` | source-local federation authorization only |
| `destination_admission_ns` | destination-local federation, RouteGrant, and F75 admission only |
| `route_open_rtt_ns` | source ROUTE_OPEN send through valid ROUTE_ACCEPT receipt |
| `channel_binding_ns` | local accepted-route state through exporter-bound active channel |
| `stream_open_rtt_ns` | source STREAM_OPEN send through valid STREAM_ACCEPT receipt |
| `ttfab_ns` | scenario start through first response application byte |
| `request_latency_ns` | application write start through complete response receipt |
| `application_processing_ns` | destination-local application read/echo processing |
| `total_scenario_ns` | scenario start through complete response receipt |

Unrelated process monotonic clocks MUST NOT be subtracted to derive one-way
network latency. Source-observed RTTs and destination-local processing remain
separate unless clocks are explicitly synchronized and the synchronization
method is recorded in the environment manifest.

## Paths and lifecycle

`direct-quic` uses QUIC v1, TLS 1.3, the same mTLS identities, socket topology,
payload, echo response, freshness, and release build profile as NBSR, but
executes no NBSR control processing. `rust-rust` and `go-rust` use the real
frozen control and security implementations.

Cold creates a new Transport Session. Warm-new-service reuses an authenticated
Transport Session but performs fresh service-specific federation/F75 admission
and channel binding. Warm-existing-service reuses an accepted Service Channel
and performs only new stream admission and application transfer.

## Measurement integrity

The primary headline payload is 1,024 bytes. Other payloads are 1, 16,384,
262,144, and 1,048,576 bytes. Every raw record binds repository state,
environment digest, implementation, lifecycle, cardinality, load, build
profile, result, typed error, bytes, and durations. Failed requests are raw
samples. Buffered evidence output is bounded and overflow is a fatal run error.

Closed-loop tests measure latency. Open-loop tests schedule against an absolute
monotonic timeline and preserve late requests, preventing coordinated omission.
Capacity is independently discovered for each path. Formal warm cells require
at least 100,000 successes, cold cells 2,000 fresh connections, and five runs.
P99.9 is emitted only at 100,000 or more successful samples.

## Attribution

Matched overhead is NBSR minus direct within identical payload, load,
environment, topology, lifecycle, and release-build cells. Total RTT is never
reported as NBSR overhead. Destination-local application processing, NBSR
control processing, network waiting, and implementation/runtime behavior are
reported separately. Go-versus-Rust observations apply only to these
implementations.

## Security boundary

Benchmark mode cannot construct protocol authority. It consumes the same
authenticated TLS identities, signed authorization, F75 transcript, exporter
binding, replay state, lifecycle checks, stream gates, and limits as normal
execution. Instrumentation observes boundaries but cannot select outcomes or
authorize payload.

