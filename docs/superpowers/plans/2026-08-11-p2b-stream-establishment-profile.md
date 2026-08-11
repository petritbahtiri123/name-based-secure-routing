# P2B Stream-Establishment Profiling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute the Direct-versus-NBSR new-stream lifecycle gap without changing production behavior or optimizing it.

**Architecture:** A disabled-by-default fixed-cardinality aggregate timer instruments benchmark and selected lifecycle boundaries. A P1F-safe sharded runner executes observer pairs and 50%/90% profiles, then packages comparative evidence.

**Tech Stack:** Rust 2024, Tokio, Quinn, atomics/histograms, Python standard library, existing Windows process sampler.

## Global Constraints

- Base exactly `a19b685e1bae6131f897fe8324166e5bacdda83f`.
- Profile-only; no production optimization or protocol/security semantic change.
- Maximum 8,000 lifecycle operations per Transport Session shard.
- Accepted rates are fixed: Direct 2,375/4,275; NBSR 843.75/1,518.75 operations/second.
- No push, pull, merge, rebase, P1F soak, P2A rerun, capacity discovery, or P2C.

---

### Task 1: Aggregate profiler

**Files:** create `src/lifecycle_profile.rs`, test `tests/lifecycle_profile.rs`, modify `src/lib.rs`.

- [ ] Write RED tests for closed labels, disabled no-op, success/failure reconciliation, timer pairing, histogram quantiles, and safe snapshot keys.
- [ ] Run the feature-gated focused test and verify missing-interface failures.
- [ ] Implement the minimal fixed-cardinality aggregate profiler.
- [ ] Run focused tests to GREEN.

### Task 2: Lifecycle instrumentation

**Files:** modify `session.rs`, `channel_streams.rs`, `perf_rust_source.rs`, `wp8_interop_server.rs`, and `perf_direct_peer.rs`.

- [ ] Write RED behavioral tests proving enabled/disabled outcomes match and rejected operations do not increment successful lifecycle counts.
- [ ] Run focused STREAM_OPEN/ChannelStreams tests and verify RED.
- [ ] Add feature-gated timing scopes at the frozen phase boundaries and one aggregate snapshot per process.
- [ ] Run focused lifecycle tests to GREEN.

### Task 3: P1F-safe runner

**Files:** create `scripts/performance/p2b_profile.py`, `scripts/run_p2b_profile.py`, and `tests/test_p2b_profile.py`.

- [ ] Write RED tests for exact rates, 8,000-operation shard cap, matched manifests, aggregation, observer thresholds, and error rejection.
- [ ] Implement build/orchestration/resource/phase aggregation and durable output.
- [ ] Run Python tests to GREEN and a short Direct/NBSR smoke.

### Task 4: Observer effect and authoritative profiles

**Files:** create `evidence/performance/stream-establishment-profile-p2b/**`.

- [ ] Execute three disabled/enabled 30-second pairs per path at 50% and classify observer effect.
- [ ] Execute three 180-second Direct/NBSR runs at 50% and 90%, adding repeats only if permitted.
- [ ] Verify zero errors, no `OverCapacity`, and profiler/counter reconciliation.

### Task 5: Analysis and completion

**Files:** create `scripts/build_p2b_report.py` and final evidence analysis/report/checksums.

- [ ] Decompose incremental NBSR cost, account for measured owners, document serialization/locks/scheduler/allocation evidence, and select one A-F classification.
- [ ] Nominate exactly one optimization hypothesis without implementing it.
- [ ] Run fresh focused/full Rust, Python, fmt, clippy, evidence, prior-evidence, and Git checks.
- [ ] Stage only scoped files, inspect, commit locally, and verify clean status/protected refs/final SHA.
