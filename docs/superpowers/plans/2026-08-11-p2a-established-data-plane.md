# P2A Established Data-Plane Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a matched persistent Direct QUIC versus Rust-to-Rust NBSR established-data-plane benchmark with lifecycle-isolation proof and additive evidence.

**Architecture:** A disabled-by-default benchmark feature exposes non-finishing framed I/O on authenticated application streams. Dedicated Rust peers establish all lifecycle objects before warm-up, while a Python runner executes the matrix and packages reproducible evidence.

**Tech Stack:** Rust 2024, Tokio, Quinn, SHA-256, Python 3 standard library, Windows process counters.

## Global Constraints

- Benchmark only; no production optimization or protocol/security semantic change.
- Base is exactly `55a5de9f636fe7e4d61cc62ac343591421907bec`.
- Matrix is paths Direct/NBSR, streams 1/8/64, payloads 1/1024/16384, three 30-second repeats after 10-second warm-up.
- One outstanding request per stream; lifecycle and replay deltas during measurement must be zero.
- No push, pull, merge, rebase, protected-ref change, or P2B work.

---

### Task 1: Framing and phase accounting

**Files:**
- Create: `crates/nbsr-transport/src/bin/p2a_established_peer.rs`
- Modify: `crates/nbsr-transport/Cargo.toml`
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`

**Interfaces:**
- Produces benchmark-only framed read/write methods and JSON repeat output.

- [ ] Write literal unit tests for frame round-trip, corrupt tag, wrong sequence, phase counter delta, and invalid manifest arguments.
- [ ] Run the focused test target and observe expected missing-interface failures.
- [ ] Add the disabled `benchmark-harness` feature, minimal non-finishing I/O, and peer setup/measurement implementation.
- [ ] Run the focused test target and observe all tests pass.

### Task 2: Matched persistence integration

**Files:**
- Modify: `crates/nbsr-transport/src/bin/p2a_established_peer.rs`
- Create: `crates/nbsr-transport/tests/p2a_established.rs`

**Interfaces:**
- Consumes peer CLI and output schema.
- Produces process-level proof that Direct and NBSR retain their initial connection/streams and surface errors.

- [ ] Write process integration tests for persistent Direct, persistent NBSR, zero creation/replay deltas, payload validation, and no replacement after failure.
- [ ] Run tests and observe the expected failures.
- [ ] Implement only the setup/phase/error behavior required by the tests.
- [ ] Re-run focused tests to green.

### Task 3: Matrix runner and analysis

**Files:**
- Create: `scripts/performance/p2a_established.py`
- Create: `scripts/run_p2a_established.py`
- Create: `tests/test_p2a_established.py`

**Interfaces:**
- Consumes peer JSON and exact matrix configuration.
- Produces per-repeat manifests/raw data, medians, CV, ratios, latency deltas, scaling, report, and checksums.

- [ ] Write failing Python tests for exact matrix, reset semantics, invalid repeat rejection, selective reruns, medians/CV, and closed checksums.
- [ ] Run the focused Python tests and verify RED.
- [ ] Implement the minimum runner/analysis/evidence package.
- [ ] Run focused Python tests to green and execute a short synthetic matched validation.

### Task 4: Authoritative benchmark evidence

**Files:**
- Create: `evidence/performance/established-data-plane-p2a/**`

**Interfaces:**
- Consumes the validated release binaries and runner.
- Produces the complete 18-cell evidence package and final baseline report.

- [ ] Record pre-run environment and Git/prior-evidence boundaries.
- [ ] Execute three repeats for every cell, rerunning only unstable cells up to two times.
- [ ] Verify every valid repeat has zero lifecycle/replay deltas and zero correctness errors.
- [ ] Generate `analysis.json`, summaries, final report, and SHA-256 inventory.

### Task 5: Final verification and local commit

**Files:**
- Modify only evidence metadata/report if fresh verification results require it.

**Interfaces:**
- Produces a clean locally committed branch with auditable boundaries.

- [ ] Run relevant Rust transport, persistent benchmark, payload/counter, and P1F replay tests.
- [ ] Run `cargo fmt --check`, clippy with warnings denied, and broader affected Rust regression.
- [ ] Verify P2A checksums, prior evidence unchanged, protected remote-tracking refs unchanged, and `git diff --check`/`git show --check`.
- [ ] Stage only scoped files, inspect staged names/stat, commit locally, and verify clean status and final SHA.
