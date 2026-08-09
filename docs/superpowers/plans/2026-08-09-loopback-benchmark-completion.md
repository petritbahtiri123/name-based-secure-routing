# Loopback Benchmark Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce additive, reproducible evidence that resolves the capacity, memory-stability, and typed 640-stream blockers without optimizing or changing NBSR.

**Architecture:** Extend the existing Python performance harness with small typed decision and evidence modules, while continuing to invoke the unchanged Rust and Go benchmark peers. Generate a new completion evidence root whose summaries and classification are regenerated from raw records and whose manifest cryptographically binds both new artifacts and the immutable prior tranche.

**Tech Stack:** Python 3.12, pytest, Ruff, Rust/Cargo, Go, gzip NDJSON, JSON manifests, SHA-256, Windows process counters, Go runtime metrics.

## Global Constraints

- Continue on `codex/nbsr-v3-wp0-wp1` from design baseline `6a971ba` and initial benchmark HEAD `e4492c4fc4b5124e71e218c56efd16114c147238`.
- Do not optimize NBSR or alter protocol, admission, scheduling, allocation, serialization, QUIC, caching, batching, or concurrency-limit behavior.
- Do not modify existing evidence under `evidence/performance/complete-loopback-db55d18-partial`.
- Capacity confirmations require at least 60 seconds warm-up and 600 seconds steady state; all three confirmations must pass independently.
- Memory evidence requires six runs, each with the same explicit warm-up and cadence and at least 1,800 seconds steady state.
- Keep 640 streams unsupported; require complete typed fail-closed evidence rather than success.
- Use a writable `CARGO_TARGET_DIR` outside OneDrive for Rust validation.
- Stage only explicit task paths. Do not push, merge, rebase, or modify `main`.

---

### Task 1: Freeze repeated capacity and same-path formal-load decisions

**Files:**
- Modify: `scripts/performance/driver.py`
- Modify: `tests/performance/test_driver.py`

**Interfaces:**
- Produces: `CapacityConfirmation`, `accept_confirmed_capacity(confirmations, required_runs=3)`, `formal_load_rate(path, percent, accepted_capacities)`, and `validate_formal_load_result(...)`.
- Consumes: existing `CapacityObservation.sustainable()` frozen criteria.

- [ ] **Step 1: Write failing confirmation tests**

Add literal tests showing that one or two passing runs cannot accept a point, three passing independent runs can, any failed run invalidates the point, and paths cannot be combined.

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `python -m pytest tests/performance/test_driver.py -k "confirmation or formal_load" -q`

Expected: collection/import failure for the new interfaces.

- [ ] **Step 3: Implement the minimal immutable decision types**

Group confirmations by `(path, offered_rate)`, reject duplicate run IDs, require exactly the configured minimum or more, reject the group if any observation fails, and return only conservative independently confirmed capacities. Calculate formal load as `accepted_capacities[path] * percent / 100` for literal percentages 25, 50, 75, and 90. A failing 90% result raises a capacity-re-evaluation result instead of returning acceptance.

- [ ] **Step 4: Run focused and complete driver tests**

Run: `python -m pytest tests/performance/test_driver.py -q`

- [ ] **Step 5: Commit the task**

Stage only `scripts/performance/driver.py` and `tests/performance/test_driver.py` and commit `test(perf): enforce repeated capacity acceptance`.

### Task 2: Make open-loop queue and terminal accounting explicit

**Files:**
- Modify: `scripts/performance/driver.py`
- Modify: `scripts/run_performance_validation.py`
- Modify: `scripts/run_performance_load_cell.py`
- Modify: `tests/performance/test_driver.py`

**Interfaces:**
- Produces: expanded `OpenLoopIssue` fields for queue/active/backlog and lag observations; terminal-count reconciliation used by the cell runner.
- Consumes: absolute `scheduled_ns` deadlines emitted by unchanged Rust and Go peers.

- [ ] **Step 1: Write RED tests for backlog visibility**

Use hand-authored issues where scheduled arrivals continue while starts lag. Assert offered count, maximum and percentile scheduler lag, peak queued/active/backlog counts, and typed failed terminal counts. Assert missing terminal records fail.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/performance/test_driver.py -k "open_loop" -q`

- [ ] **Step 3: Implement minimal accounting and normalization**

Derive observable backlog from scheduled-versus-terminal progress without changing peer scheduling. Preserve offered, queued, active, completed, failed, timeout, rejection, scheduler-lag, send-lag, and receive-lag fields when present. Fail the run when offered and terminal counts differ.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/performance/test_driver.py -q`

- [ ] **Step 5: Commit the task**

Commit explicit paths as `fix(perf): expose open-loop backlog integrity`.

### Task 3: Add fail-closed memory sampling and post-warm-up trend analysis

**Files:**
- Modify: `scripts/performance/resources.py`
- Modify: `tests/performance/test_resources.py`
- Modify: `scripts/run_performance_load_cell.py`

**Interfaces:**
- Produces: `MemorySample`, `MemoryWindow`, `analyze_memory_window(samples, warmup_end_ns, expected_cadence_ns)`, and `classify_memory_stability(path, load_results)`.
- Consumes: existing Windows process counter samples and request/backlog snapshots from the load runner.

- [ ] **Step 1: Write RED tests for phase, cadence, and allocator behavior**

Add literal series proving warm-up exclusion, missing-cadence failure, full/second-half/final-quarter working-set and private-byte slopes, request-normalized slope, a bounded allocator step classified `PASS`, persistent correlated growth classified `FAIL`, and noisy indistinguishable evidence classified `INCONCLUSIVE`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/performance/test_resources.py -q`

- [ ] **Step 3: Implement minimal analysis**

Preserve raw samples and calculate trends only after the recorded warm-up boundary. Treat slope evidence as one input, not an automatic leak rule. Require both 50% and 75% valid runs before a path receives `PASS` or `FAIL`; otherwise return `INCONCLUSIVE` with reasons.

- [ ] **Step 4: Extend resource records without contaminating latency**

At the fixed cadence, join request count, active concurrency, queue/backlog, CPU, working set, private bytes, and peak working set. Keep Go runtime snapshots alongside the cadence records when available. Reject sample gaps rather than interpolating them.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/performance/test_resources.py tests/performance/test_driver.py -q`

- [ ] **Step 6: Commit the task**

Commit explicit paths as `feat(perf): add post-warmup memory stability analysis`.

### Task 4: Preserve typed raw evidence for unsupported 640-stream attempts

**Files:**
- Create: `scripts/performance/failure_evidence.py`
- Create: `tests/performance/test_failure_evidence.py`
- Modify: `scripts/run_performance_validation.py`

**Interfaces:**
- Produces: `UnsupportedAttempt`, `terminal_failure_record(attempt, outcome)`, and `reconcile_attempt_records(attempts, records)`.
- Consumes: Rust `AuditUnavailable`, Go no-recent-network-activity timeout, configured service/channel limits, and the existing scaling runner command outcomes.

- [ ] **Step 1: Write RED tests for one-record-per-attempt evidence**

Use literal Rust and Go attempts. Assert all required fields, pre/post-admission phase, expected fail-closed status, supported/unsupported classification, distinct timeout/rejection categories, preservation of request IDs, and failure on a missing terminal record.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/performance/test_failure_evidence.py -q`

- [ ] **Step 3: Implement typed conversion and reconciliation**

Convert command failure outcomes into typed evidence without changing peer limits or behavior. Never synthesize success, and never drop an attempt after process failure.

- [ ] **Step 4: Integrate only the scaling evidence path**

Wrap each 640-stream request attempt before invocation and write a terminal record in success, typed rejection, timeout, or process-failure paths. Preserve the existing 320-stream runner and conclusions.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/performance/test_failure_evidence.py tests/performance/test_driver.py -q`

- [ ] **Step 6: Commit the task**

Commit explicit paths as `fix(perf): retain typed unsupported stream evidence`.

### Task 5: Regenerate summaries from raw evidence and verify additive immutability

**Files:**
- Create: `scripts/performance/completion_evidence.py`
- Create: `tests/performance/test_completion_evidence.py`
- Modify: `scripts/verify_performance_evidence.py`
- Modify: `tests/performance/test_evidence_verifier.py`

**Interfaces:**
- Produces: `summarize_completion_root(root)`, `write_completion_manifest(root, prior_root)`, and verifier support for `nbsr-performance-completion-v1`.
- Consumes: capacity, formal-load, memory, explanatory, and unsupported-attempt raw records.

- [ ] **Step 1: Write RED fixtures**

Construct a small literal completion root. Assert raw-to-summary regeneration, exact counts, candidate-versus-accepted labels, completion-criteria derivation, prior-root digest binding, closed inventory, and mutation detection for both new and prior evidence.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/performance/test_completion_evidence.py tests/performance/test_evidence_verifier.py -q`

- [ ] **Step 3: Implement deterministic regeneration and manifest verification**

Sort records and paths deterministically, calculate summaries only from raw records, bind the immutable prior checksums, and permit `COMPLETE_LOOPBACK_BASELINE` only when every frozen criterion is true. Otherwise emit `PARTIAL_BASELINE` with exact unresolved reasons.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/performance/test_completion_evidence.py tests/performance/test_evidence_verifier.py -q`

- [ ] **Step 5: Commit the task**

Commit explicit paths as `feat(perf): verify additive completion evidence`.

### Task 6: Add bounded completion orchestration

**Files:**
- Create: `scripts/run_performance_completion.py`
- Create: `tests/performance/test_completion_runner.py`
- Modify: `scripts/run_performance_load_cell.py`

**Interfaces:**
- Produces: CLI phases `discover`, `confirm`, `formal`, `memory`, `unsupported`, `summarize`, and `verify` with explicit path/rate/run IDs.
- Consumes: Tasks 1-5 interfaces and the existing release benchmark binaries.

- [ ] **Step 1: Write RED command-plan tests**

Assert independent bounded search brackets, three confirmation commands per candidate, same-path 25/50/75/90 calculations, six memory commands with identical warm-up/cadence and at least 1,800 seconds steady state, and one unsupported evidence command per implementation.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/performance/test_completion_runner.py -q`

- [ ] **Step 3: Implement the smallest resumable orchestrator**

Write phase results to unique directories, refuse overwrite, require a clean tree for authoritative runs, resume only from verified completed phase artifacts, and stop for downward re-evaluation after any confirmation or 90% failure.

- [ ] **Step 4: Verify GREEN and dry-run plans**

Run: `python -m pytest tests/performance/test_completion_runner.py tests/performance -q`

Run the CLI in plan-only mode and inspect that it schedules no cloud, WAN, HTTP/3, demo, optimization, or protocol work.

- [ ] **Step 5: Commit the task**

Commit explicit paths as `feat(perf): orchestrate loopback completion runs`.

### Task 7: Run bounded capacity discovery and confirmations

**Files:**
- Create additively: `evidence/performance/loopback-completion-<commit>/capacity/**`

**Interfaces:**
- Produces: independent raw discovery points, brackets, and three-run confirmation sets for Direct, Rust, and Go.

- [ ] **Step 1: Build release binaries once**

Set `NBSR_PERF_CARGO_TARGET=C:\codex-target\nbsr-perf-completion` and build the unchanged benchmark peers.

- [ ] **Step 2: Run coarse, bracket, and fine discovery independently**

Start from the prior known regions but do not assume historical candidates are near enough. Record every pass and fail. Do not run paths in parallel on the benchmark host.

- [ ] **Step 3: Run at least three full confirmations per candidate**

Each uses 60-second warm-up and 600-second steady state. If one fails, move down and restart the three-run confirmation set.

- [ ] **Step 4: Verify raw counts and frozen criteria**

Regenerate capacity summaries from raw evidence and record accepted values only after all confirmations reproduce.

- [ ] **Step 5: Commit additive capacity evidence**

Commit explicit new evidence paths as `evidence(perf): establish reproducible capacities`.

### Task 8: Run formal load cells and explanatory backlog experiment if needed

**Files:**
- Create additively: `evidence/performance/loopback-completion-<commit>/formal/**`
- Create conditionally: `evidence/performance/loopback-completion-<commit>/explanatory/**`

- [ ] **Step 1: Run 25/50/75/90 cells from each same-path accepted capacity**

Use 60-second warm-up and 600-second steady state. Preserve every offered terminal sample.

- [ ] **Step 2: Re-evaluate any path whose 90% cell fails**

Return to Task 7 for that path, lower the candidate, repeat confirmations, and rerun all four formal cells for that path.

- [ ] **Step 3: Run explanatory backlog instrumentation only if authoritative evidence cannot explain observed saturation**

Label it `EXPLANATORY — NOT AUTHORITATIVE LATENCY` and do not use its latency percentiles as formal results.

- [ ] **Step 4: Commit additive formal evidence**

Commit explicit paths as `evidence(perf): validate accepted capacity loads`.

### Task 9: Run six primary memory experiments

**Files:**
- Create additively: `evidence/performance/loopback-completion-<commit>/memory/**`

- [ ] **Step 1: Run Direct at approximately 50% and 75%**

Use the frozen warm-up, fixed cadence, and at least 1,800-second steady state for each run.

- [ ] **Step 2: Run Rust-to-Rust at approximately 50% and 75%**

Use identical phase and cadence rules; retain process-level memory evidence.

- [ ] **Step 3: Run Go-to-Rust at approximately 50% and 75%**

Use identical phase and cadence rules; retain all available Go heap, allocation, GC-count, and pause evidence.

- [ ] **Step 4: Regenerate and review classifications**

Classify each path `PASS`, `FAIL`, or `INCONCLUSIVE` without forcing certainty. Correlate time, requests, CPU, backlog, and runtime evidence.

- [ ] **Step 5: Commit additive memory evidence**

Commit explicit paths as `evidence(perf): measure long-lived memory stability`.

### Task 10: Capture typed Rust and Go 640-stream evidence

**Files:**
- Create additively: `evidence/performance/loopback-completion-<commit>/unsupported/**`

- [ ] **Step 1: Run the Rust unsupported point**

Preserve one terminal typed raw record for every attempt, including `AuditUnavailable`, admission phase, configured limit, and expected fail-closed classification.

- [ ] **Step 2: Run the Go unsupported point**

Preserve one terminal typed raw record for every attempt, including no-recent-network-activity timeout category, admission phase, configured limit, and expected fail-closed classification.

- [ ] **Step 3: Reconcile attempts and terminal records**

Require exact request-ID equality and retain the supported 320-stream conclusion unchanged.

- [ ] **Step 4: Commit additive unsupported evidence**

Commit explicit paths as `evidence(perf): capture typed 640-stream failures`.

### Task 11: Produce the final additive report and machine-readable analysis

**Files:**
- Create: `evidence/performance/loopback-completion-<commit>/reports/latency-and-performance-validation.md`
- Create: `evidence/performance/loopback-completion-<commit>/summaries/analysis.json`
- Create: `evidence/performance/loopback-completion-<commit>/manifest.json`
- Create: `evidence/performance/loopback-completion-<commit>/checksums.json`

- [ ] **Step 1: Regenerate all summaries from raw evidence**

Include previous candidates, new brackets, confirmations, accepted capacities, formal percentiles, queue observations, memory conclusions, Go/Rust runtime observations, typed unsupported outcomes, exact raw counts, and engineering-budget decisions.

- [ ] **Step 2: Derive classification mechanically**

Emit `COMPLETE_LOOPBACK_BASELINE` only if all frozen criteria pass; otherwise retain `PARTIAL_BASELINE` and enumerate unresolved blockers.

- [ ] **Step 3: Record non-claims and unimplemented opportunities**

Include `Candidate optimization opportunities — NOT IMPLEMENTED`, protocol/security defect count, limitations, and human-review readiness without demo work.

- [ ] **Step 4: Verify checksums and prior evidence immutability**

Run `python scripts/verify_performance_evidence.py <new-root>` and verify the prior root separately.

- [ ] **Step 5: Commit report and closed evidence manifest**

Commit explicit paths as `evidence(perf): close loopback baseline analysis`.

### Task 12: Full regression and security validation

**Files:**
- Modify only if a validation failure exposes a scoped benchmark-harness defect, using a new RED test first.

- [ ] **Step 1: Run focused performance validation**

Run: `python -m pytest tests/performance -q`

- [ ] **Step 2: Run full Python and Ruff validation**

Run the repository's full pytest command and `python -m ruff check .`; report exact passed/skipped/failed counts.

- [ ] **Step 3: Run Rust validation outside OneDrive**

Run `cargo fmt --all -- --check`, `cargo test --workspace --all-targets`, and `cargo clippy --workspace --all-targets -- -D warnings` with the external target directory.

- [ ] **Step 4: Run Go validation**

In each scoped Go module, run `go test ./...`, `go vet ./...`, and `go mod verify`.

- [ ] **Step 5: Run federation, interoperability, conformance, and security regressions**

Use repository-listed focused suites and vector/evidence verification commands; report each exact result separately.

- [ ] **Step 6: Run final integrity checks**

Run both evidence verifications, checksum verification, prior-evidence digest comparison, and `git diff --check`.

- [ ] **Step 7: Inspect final Git scope and commit only scoped fixes if any**

Use `git status --short`, `git diff --cached --name-only`, and `git diff --cached --stat`. Do not use `git add .`.
