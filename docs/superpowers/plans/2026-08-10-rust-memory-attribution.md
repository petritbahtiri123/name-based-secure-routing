# Rust Retained-Memory Ownership Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute the accepted Rust 75% late-run process-memory growth without changing NBSR behavior.

**Architecture:** Add disabled-by-default aggregate Rust lifecycle diagnostics at existing owner boundaries, stream snapshots through the existing durable benchmark evidence path, then run paired observer checks and four frozen long memory experiments. Generate one additive, checksummed P1A report with lifecycle reconciliation and exactly one A-E classification.

**Tech Stack:** Rust, Tokio, Quinn public wrappers, Python 3.12, pytest, NDJSON, Windows process counters, SHA-256.

## Global Constraints

- Base commit is exactly `4e25ee026618a502327331f352d90e26d29284e3`.
- Do not optimize or fix the attributed owner.
- Do not change protocol, security, resource limits, accepted capacity, or accepted evidence.
- Diagnostics are aggregate, bounded, opt-in, and disabled by default.
- Use 60 seconds warm-up, 1,800 seconds measurement, and a 20-second explicit drain for primary runs.
- Run one Rust 50% control and three Rust 75% attribution runs serially.
- Do not push, merge, rebase, or modify `main` or the accepted branch.

---

### Task 1: Add tested aggregate diagnostic primitives

**Files:**
- Create: `crates/nbsr-transport/src/diagnostics.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: `Diagnostics`, `DiagnosticSnapshot`, lifecycle/collection metric types, opt-in enable/reset/snapshot functions, and checked gauge/high-water operations.
- Consumes: only primitive counts and capacities; never protocol objects.

- [ ] Write focused unit tests proving disabled-by-default snapshots remain zero, enabled lifecycle transitions conserve exactly, duplicate terminal transitions cannot double-count, and high-water marks do not fall.
- [ ] Run the exact Rust test filter and capture the expected RED failure caused by the missing module/API.
- [ ] Implement the minimal atomic registry and immutable aggregate snapshot.
- [ ] Run the same filter and capture GREEN.
- [ ] Commit explicit files as `feat(perf): add opt-in ownership diagnostics`.

### Task 2: Instrument existing logical owners

**Files:**
- Modify only as applicable: `crates/nbsr-transport/src/session.rs`
- Modify only as applicable: `crates/nbsr-transport/src/channel_registry.rs`
- Modify only as applicable: `crates/nbsr-transport/src/channel_streams.rs`
- Modify only as applicable: `crates/nbsr-transport/src/audit.rs`
- Modify only as applicable: `crates/nbsr-transport/src/quinn_adapter.rs`
- Test: focused unit/integration tests beside each owner and under `crates/nbsr-transport/tests/`

**Interfaces:**
- Consumes: Task 1 accounting calls.
- Produces: transport-session, service-channel, application-stream, registry,
  pending, audit, NBSR-task, QUIC-wrapper, and safely observable capacity data.

- [ ] For each applicable owner, write a focused RED lifecycle test asserting its exact conservation equation and expected post-release baseline.
- [ ] Run each focused test and record the expected missing-metric failure before editing production code.
- [ ] Add the minimal increment/decrement/removal/eviction calls at existing successful lifecycle transitions; add failure/cancel accounting only where the implementation has a distinct terminal path.
- [ ] Add aggregate `len`/`capacity` snapshots only at existing container owners; do not retain or enumerate protocol values.
- [ ] Run focused GREEN tests after every owner and then the existing channel, stream, session, audit, replay, and Quinn tests.
- [ ] Commit explicit files as `feat(perf): attribute Rust lifecycle owners`.

### Task 3: Stream bounded diagnostic evidence

**Files:**
- Modify: `crates/nbsr-transport/src/bin/perf_rust_source.rs`
- Modify: `scripts/performance/durable_memory.py`
- Modify: `scripts/run_performance_load_cell.py`
- Test: `tests/performance/test_durable_memory_runner.py`
- Test: focused Rust performance-peer tests where available

**Interfaces:**
- Produces: `diagnostic` durable events with monotonic timestamp and one bounded aggregate snapshot.
- Consumes: existing resource cadence and Task 1 snapshot API.

- [ ] Write RED tests asserting diagnostic records are absent by default, present only with the P1A flag, contain no forbidden/high-cardinality fields, and remain durable on completion or timeout.
- [ ] Run the focused Python/Rust tests and capture RED.
- [ ] Add the opt-in CLI flag, one-second snapshot emission, explicit drain phase, and durable `diagnostics.ndjson` writer.
- [ ] Reconcile diagnostic series counts in the terminal manifest without weakening existing request/resource reconciliation.
- [ ] Run focused GREEN and commit as `feat(perf): retain Rust ownership snapshots`.

### Task 4: Add deterministic attribution analysis and evidence verification

**Files:**
- Create: `scripts/performance/rust_memory_attribution.py`
- Create: `tests/performance/test_rust_memory_attribution.py`
- Modify: `scripts/verify_performance_evidence.py`

**Interfaces:**
- Produces: per-run slopes, observational bytes/completed-operation ratios,
  owner trends, conservation results, post-drain deltas, repeatability decision,
  exact A-E classification, manifest, and checksums.
- Consumes: request, resource, diagnostic, terminal, command, and environment records.

- [ ] Write literal RED fixtures for A, B, C, D, and E, including the two-of-three 75% reproducibility rule and a correlation-without-causation case.
- [ ] Run focused tests and capture RED.
- [ ] Implement deterministic analysis from raw records, closed inventory, checksum generation, and mutation detection.
- [ ] Run focused GREEN and commit as `feat(perf): classify retained memory ownership`.

### Task 5: Validate correctness, security, and observer effect

**Files:**
- Create additively: `evidence/performance/rust-memory-attribution-<commit>/observer/**`

- [ ] Build release binaries with an external writable `CARGO_TARGET_DIR`.
- [ ] Run Rust format, focused lifecycle/security tests, workspace tests, and Clippy with `-D warnings`.
- [ ] Run focused performance tests and the repository-required security/correctness suites.
- [ ] Run at least five alternating disabled/enabled paired short Rust workload comparisons with identical configuration.
- [ ] Calculate median throughput and p99 degradation and compare against 3%/5%; require zero additional protocol errors.
- [ ] If the observer gate fails, change diagnostics only under a new RED/GREEN cycle and repeat the full paired set.
- [ ] Commit additive observer evidence as `evidence(perf): validate diagnostic observer effect`.

### Task 6: Run frozen memory attribution experiments

**Files:**
- Create additively: `evidence/performance/rust-memory-attribution-<commit>/runs/**`

- [ ] Capture exact hardware, OS, toolchain, build, repository, command, and load manifests.
- [ ] Run one Rust 50% control at 843.75 operations/second with 60-second warm-up, 1,800-second measurement, and the frozen explicit drain.
- [ ] Run three serial Rust 75% experiments at 1,265.625 operations/second with the same phase durations and cadence.
- [ ] Verify every run's raw terminal counts, cadence, checksums, conservation equations, and post-drain snapshot before starting analysis.
- [ ] Preserve partial evidence and mark a run invalid rather than silently substituting or rerunning over it.
- [ ] Commit additive raw evidence as `evidence(perf): capture Rust ownership attribution runs`.

### Task 7: Produce and verify the final P1A report

**Files:**
- Create: `evidence/performance/rust-memory-attribution-<commit>/reports/rust-memory-attribution.md`
- Create: `evidence/performance/rust-memory-attribution-<commit>/summaries/analysis.json`
- Create: `evidence/performance/rust-memory-attribution-<commit>/manifest.json`
- Create: `evidence/performance/rust-memory-attribution-<commit>/checksums.json`

- [ ] Regenerate all results from raw evidence and select exactly one A-E classification.
- [ ] Include the metric inventory, increment/decrement sites, expected baselines, exact run manifests, slopes, owner trends, reconciliation, repeatability, ruled-out layers, unresolved layer, and exactly one next hypothesis.
- [ ] Verify the new closed evidence root and separately verify accepted prior evidence unchanged.
- [ ] Run final Python, Rust, security, formatting, lint, checksum, and `git diff --check` validation.
- [ ] Inspect explicit staged paths and commit locally; do not push.
- [ ] Re-read every required final-report field and report exact fresh results.
