# P2A Established Data-Plane Benchmark Design

## Scope and invariants

P2A adds benchmark-only persistent request/response measurement. It does not optimize or change protocol, admission, replay, crypto, buffer, scheduler, or concurrency semantics. The default transport build is unchanged. Existing P1A-P1F evidence is immutable.

One completed operation is one length-delimited request frame containing a u64 sequence, payload length, deterministic payload, and SHA-256-derived validation tag, followed by the corresponding response frame with the same sequence, length, payload, and tag. Each stream permits one outstanding request. Direct and NBSR use identical framing and validation.

## Architecture

Add a `benchmark-harness` Cargo feature disabled by default. Under that feature only, `ApplicationStream` gains non-finishing frame read/write primitives needed by a dedicated P2A peer. These primitives reuse the already-authenticated, admitted, tracked stream and do not open or authorize anything.

The dedicated peer supports Direct and NBSR roles. Setup creates one QUIC connection, one NBSR Transport Session and Service Channel for NBSR, and exactly 1, 8, or 64 bidirectional Application Streams. Warm-up and measurement reuse those streams. A phase gate snapshots lifecycle and replay counters immediately before and after measurement and rejects any nonzero creation or replay-entry delta.

A Python runner builds once, executes matched Direct then NBSR cells with 10-second warm-up, 30-second measurement, three repeats, and only reruns cells whose throughput CV exceeds 5%, up to two additional repeats. It samples process CPU, working set, and private bytes using existing Windows resource helpers, writes each repeat durably, computes medians/ratios/latency deltas/scaling, and packages checksums and a final report.

## Integrity and failure behavior

All streams are established before warm-up. No stream replacement path exists: any stream error terminates and invalidates the repeat. Counters reset by taking a fresh measurement baseline after warm-up; setup and fixture/certificate loading are excluded. Missing, duplicate, corrupt, reordered, or wrong-stream responses are counted as errors and invalidate the repeat. Evidence records exact path, stream count, payload, one-outstanding model, warm-up, duration, phase timestamps, counters, and environment.

Allocation telemetry is reported only if already available without an invasive profiler; otherwise it is explicitly unavailable.

## Validation

Literal RED tests cover framing, corruption/sequence rejection, manifest exactness, phase reset, zero lifecycle/replay deltas, no replacement stream behavior, persistent Direct/NBSR setup, and surfaced failures. Focused tests precede a short synthetic two-path run. Final validation includes affected Rust tests, P1F replay-limit regressions, formatting, clippy, broader affected Rust regression, evidence checksum verification, protected-ref verification, and byte comparison proving prior evidence unchanged.

## Alternatives considered

1. Reuse `send_and_receive`: rejected because it finishes each stream and measures stream lifecycle.
2. Use raw Quinn only for NBSR: rejected because it would bypass the admitted `ApplicationStream` object and weaken lifecycle proof.
3. Benchmark-feature framing on the authenticated stream: selected because it is matched, testable, disabled in production builds, and changes no protocol semantics.
