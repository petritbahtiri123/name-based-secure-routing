# P1B Destination Memory Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely attribute Rust destination-process retained-memory growth without changing protocol, security, replay, capacity, allocator, Quinn, or Tokio behavior.

**Architecture:** Reuse P1A's disabled-by-default aggregate atomics at existing ownership boundaries. Add a destination-only `std::thread` sampler that reads only atomic snapshots and writes NDJSON to a pre-opened append-only file; wire that file into the existing durable evidence stream, then execute short smoke/observer gates before the frozen attribution cells.

**Tech Stack:** Rust, Tokio/Quinn public wrappers, Python 3, pytest, NDJSON, Windows process counters, SHA-256, Git LFS under existing policy.

## Global Constraints

- Branch from `275315e3fb6e57ee272264a6b0385813bb60a8f7`; accepted product base is `4e25ee026618a502327331f352d90e26d29284e3`.
- Do not push, pull, merge, rebase, optimize, alter protocol/security/replay semantics, change capacity/limits, tune Quinn/Tokio, or change allocator behavior.
- Diagnostics remain aggregate, bounded, destination-only, opt-in, and disabled by default.
- Observer guardrails are median throughput degradation at most 3%, median p99 degradation at most 5%, and zero additional protocol errors.
- Attribution cells are one 50% control (60s warm-up, 600s measured, 20s drain) and three 75% runs (60s warm-up, 900s measured, 20s drain), extended only if genuinely ambiguous.
- Preserve P1A and accepted benchmark evidence byte-for-byte; P1B evidence is additive.

---

### Task 1: Record baseline and make destination sampler behavior testable

**Files:**
- Modify: `crates/nbsr-transport/src/diagnostics.rs`
- Modify: `crates/nbsr-transport/tests/diagnostics.rs`
- Modify: `tests/performance/test_long_run_streaming.py`

**Interfaces:**
- Produces: `DestinationDiagnosticSampler` (or equivalent bounded handle) with start and clean join semantics.
- Consumes: `Diagnostics::snapshot()` values only; retains no NBSR or Quinn object.

- [ ] Add focused RED tests for pre-opened append-only output, monotonic approximately one-second snapshots, safe periodic/final flush, clean join, no sensitive/high-cardinality fields, disabled-by-default behavior, and file-write failure isolation.
- [ ] Run the exact tests and preserve the expected failures before production edits.
- [ ] Implement minimal `std::thread` sampling with a bounded `BufWriter`, atomic stop signal, and snapshot-only ownership.
- [ ] Fix the P1A streaming fixture assertion from 9 to the hand-derived 12 emitted records and run focused GREEN tests.

### Task 2: Wire destination-only diagnostics without protocol participation

**Files:**
- Modify: `crates/nbsr-transport/src/bin/wp8_interop_server.rs`
- Modify: `scripts/run_performance_validation.py`
- Modify: `scripts/run_performance_load_cell.py`
- Modify: `scripts/run_rust_memory_attribution.py`
- Test: focused Rust/Python performance tests.

**Interfaces:**
- Consumes: a destination diagnostics file path supplied before server launch.
- Produces: raw destination NDJSON plus same-timeline destination process resources in durable evidence.

- [ ] Add RED tests proving the server gets no diagnostic arguments/environment by default, gets one pre-created destination path only when enabled, and protocol success is independent of sampler open/write errors.
- [ ] Run RED, then add minimal launch/configuration wiring; enable atomics before workload, start sampler after file open, stop/join after the existing protocol lifecycle, and never write diagnostics to protocol stdout.
- [ ] Route destination snapshots into durable evidence without changing request/completion parsing; run focused GREEN transport, replay/security, and performance tests.

### Task 3: Add P1B analysis and integrity packaging

**Files:**
- Create: `scripts/build_rust_destination_memory_attribution_report.py`
- Create: `tests/performance/test_rust_destination_memory_attribution.py`
- Create additively: `evidence/performance/rust-memory-attribution-p1b/`

**Interfaces:**
- Consumes: destination snapshots, source/destination resource series, finalized summaries/manifests, observer pairs.
- Produces: machine-readable `analysis.json`, exact A/B/C/D/E decision, checksums, and final Markdown report.

- [ ] Write RED fixtures independently covering lifecycle conservation, replay entry/capacity correlations, post-drain comparisons, observer thresholds, and classifications A-E.
- [ ] Run RED; implement deterministic parsing/slopes/ratios/classification and strict manifest/checksum verification; run GREEN.
- [ ] Record Git preflight and baseline-failure reproduction evidence additively.

### Task 4: Execute bounded evidence progression

**Files:**
- Create additively under: `evidence/performance/rust-memory-attribution-p1b/`

**Interfaces:**
- Consumes: Tasks 1-3 binaries and runner.
- Produces: smoke, five observer pairs, and four attribution run manifests/raw series.

- [ ] Run one 30s warm-up + 60-90s measured smoke with short drain; verify destination snapshots, conservation, shutdown, and zero protocol errors.
- [ ] Run five 30s warm-up + 60s disabled/enabled observer pairs; stop after at most three evidence-based architecture corrections if zero-additional-errors cannot be met.
- [ ] Only after observer PASS, run one 50% control and three 75% attribution cells serially with frozen rates/payload; extend only ambiguous evidence.
- [ ] Build analysis/report/checksums and verify all raw files and prior-evidence digests.

### Task 5: Final verification, protected-ref audit, and local commit

**Files:**
- Modify only files already named above plus additive P1B evidence.

**Interfaces:**
- Produces: fresh validation counts, clean diff checks, protected-ref proof, and final local SHA.

- [ ] Run focused Rust transport/diagnostic/replay/security/F75/federation/performance tests, `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and checksum verification.
- [ ] Run the broader repository suite exactly once and compare its failures to the established 37 environmental failures plus corrected P1A test defect.
- [ ] Inspect `git diff`, `git status`, `git diff --check`, LFS state, and protected remote refs; stage explicit paths only and inspect staged names/stat/check.
- [ ] Commit locally without push, then re-run protected-ref/status/integrity checks and record the final SHA in the report.

