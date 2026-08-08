# NBSR Latency and Performance Validation

## Environment

Repository `010a403ffdea70f8b461a9900b4f6a2581b67c9c` on `Windows-11-10.0.26200-SP0`; Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz, 4 cores/8 logical processors, 16942501888 bytes RAM. Power plan: `Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)`. Rust `rustc 1.97.1 (8bab26f4f 2026-07-14)`; Go `go version go1.26.5 windows/amd64`; Python `3.14.6`. Release builds, Windows loopback, inherited affinity.

## Methodology

This initial unoptimized headline cell used 1 KiB payloads and an existing accepted Service Channel. Direct QUIC used equivalent QUIC v1/TLS 1.3 mTLS and echo behavior without NBSR control. Rust-Rust and Go-Rust used the real frozen Federation/F75/channel/stream gates. Per-process monotonic durations were never subtracted across processes.

## Integrity controls

0-RTT remained disabled. Peer observations were buffered until after measurement. Failed samples remain schema fields; this formal cell contains zero failures. Matched cells share repository, environment digest, topology, build profile, payload, load, lifecycle, and run ordinal.

## Direct QUIC results

Warm request latency: p50 0.135 ms, p95 0.264 ms, p99 0.476 ms, p99.9 1.031 ms; count 100000.

## Rust -> Rust NBSR results

Warm-existing request latency: p50 0.182 ms, p95 0.284 ms, p99 0.371 ms.

## Go -> Rust results

Warm-existing request latency: p50 0.199 ms, p95 0.343 ms, p99 0.499 ms.

## Multi-service reuse

INCONCLUSIVE in this baseline tranche. The real peers prove repeated streams on one accepted channel; the required 20 distinct signed service authorities were not executed.

## Stream scaling

Sequential stream reuse is measured by the headline cell. Concurrent stream scaling is INCONCLUSIVE.

## Capacity

INCONCLUSIVE. Open-loop capacity discovery and 25/50/75/90% load cells were not executed.

## Resource consumption

INCONCLUSIVE. Native Windows resource-sampling primitives are validated, but formal resource time series were not captured for this headline tranche.

## NBSR incremental overhead

Rust-Rust minus direct: p50 0.047 ms, p95 0.020 ms, p99 -0.105 ms.

Go-Rust minus direct: p50 0.064 ms, p95 0.079 ms, p99 0.022 ms.

## Budget evaluation

| Implementation | p50 +5 ms | p95 +10 ms | p99 +20 ms |
|---|---:|---:|---:|
| Rust-Rust | PASS | PASS | PASS |
| Go-Rust | PASS | PASS | PASS |

Cold, warm-new-service, throughput, capacity, error-rate-under-load, and memory-growth budgets are INCONCLUSIVE.

## Known limitations

Loopback only; no same-region or cross-region claim. This tranche covers the full primary warm-existing headline cell only. It does not establish cold, warm-new-service, multi-service, concurrency, capacity, load, or resource conclusions. HTTP/3 is NOT SUPPORTED BY CURRENT TEST SURFACE.

## Raw evidence references

See `raw/*.ndjson.gz`, `summaries/latency.json`, and `checksums.json`.

## Candidate optimization opportunities — NOT IMPLEMENTED

None are implemented or recommended from this baseline alone.

## Conclusions

Only the matched warm-existing 1 KiB loopback results and their incremental overhead are supported. These results do not establish production readiness or Internet-scale performance.
