# Durable Memory Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Durably retain long-run memory evidence across completion, timeout, and failure, then obtain scientifically classifiable loopback memory evidence without changing NBSR behavior.

**Architecture:** A memory-only orchestration layer runs the existing benchmark child, incrementally routes typed NDJSON events to bounded durable writers, owns Windows process-tree cleanup, reconciles counters, and writes a non-authoritative timeout/failure manifest. Existing non-memory completion commands bypass this layer unchanged.

**Tech Stack:** Python 3, pytest, NDJSON, deterministic JSON, Windows process APIs/PowerShell process-tree inspection, existing Rust and Go benchmark binaries.

## Global Constraints

- Do not optimize NBSR or change frozen protocol/security semantics.
- Do not rerun accepted lifecycle, scaling, capacity-discovery, capacity-confirmation, or formal-load workloads.
- Do not run a 30-minute workload until short timeout, durability, reconciliation, and cleanup tests pass.
- Preserve prior evidence byte-for-byte and add a new memory-completion root.
- Run benchmark workloads serially.

---

### Task 1: Literal RED durability contract

**Files:**
- Create: `tests/performance/test_durable_memory_runner.py`
- Create: `tests/performance/fixtures/long_run_child.py`

**Interfaces:**
- Consumes: wished-for `run_durable_memory_child(command, output, timeout_seconds, offered_requests)` API.
- Produces: observable contracts for files, manifests, counters, and child cleanup.

- [ ] Write synthetic-child tests for incremental request/resource/runtime persistence, normal flush, timeout/failure flush, timeout authority denial, terminal states, reconciliation, descendant cleanup, and unaffected short-path dispatch.
- [ ] Run `python -m pytest tests/performance/test_durable_memory_runner.py -q` and record the expected import/API failure as RED.
- [ ] Commit only the failing tests as `test(perf): reproduce long-run evidence retention defect`.

### Task 2: Minimal durable runner

**Files:**
- Create: `scripts/performance/durable_memory.py`
- Modify: `scripts/run_performance_completion.py`
- Modify only if event streaming requires it: `scripts/run_performance_load_cell.py`, `scripts/run_performance_validation.py`, `scripts/performance/resources.py`

**Interfaces:**
- Consumes: a child command emitting typed NDJSON events and an expected offered count.
- Produces: append-only `raw.ndjson`, `resources.ndjson`, optional `go-runtime-series.ndjson`, and `terminal-manifest.json`.

- [ ] Implement a bounded NDJSON writer with record-count and time-bounded flush plus `fsync` on flush and close.
- [ ] Implement typed event routing and literal offered/started/completed/failed/timed_out/persisted reconciliation.
- [ ] Implement timeout/failure handling that retains files and writes terminal metadata separately from request records.
- [ ] Implement deterministic full-process-tree termination and post-cleanup verification on Windows.
- [ ] Route only `phase == "memory"` execution through the durable runner; leave all other phases on existing `subprocess.run` behavior.
- [ ] Run the focused test file until GREEN, then run existing completion, evidence-writer, failure-evidence, resource, and evidence-verifier tests.
- [ ] Commit as `fix(perf): persist long-run evidence and clean timed-out children`.

### Task 3: Short validation profiles

**Files:**
- Modify: `tests/performance/test_durable_memory_runner.py`
- Create additive generated evidence under the tranche root only when the repository convention requires checked-in validation fixtures.

**Interfaces:**
- Consumes: completed durable runner.
- Produces: regenerated summaries and verified partial evidence from deliberate short timeout/failure runs.

- [ ] Add generated-behavior tests for writer overflow, summary regeneration, and cleanup verification failure.
- [ ] Run short normal, failure, and deliberate timeout profiles; inspect counts and process state.
- [ ] Run raw evidence and checksum verification against generated roots.
- [ ] Commit as `test(perf): validate durable timeout recovery`.

### Task 4: Targeted additive memory evidence

**Files:**
- Create: `evidence/performance/memory-completion-<commit>/...`
- Modify: performance evidence analysis/report generation code only as required for the new terminal schema.

**Interfaces:**
- Consumes: accepted capacities `4750`, `1687.5`, and `400` requests/second and prior memory evidence.
- Produces: two defensible stable memory points per path or an honest unresolved classification.

- [ ] Bind the new root to prior partial-baseline checksums, accepted capacity evidence, and prior memory evidence.
- [ ] Reuse valid Direct 50% evidence and capture one justified stable upper point near 65-70%.
- [ ] Capture Rust 50% and 70-75% evidence, including a repeat for ambiguous behavior.
- [ ] Capture Go 50% and 75% evidence with durable request/resource/runtime series.
- [ ] Stop and report rather than broaden scope if a newly proven integrity defect invalidates accepted evidence.
- [ ] Commit additive evidence as `evidence(perf): capture targeted memory completion runs`.

### Task 5: Classification and validation

**Files:**
- Modify: new memory-completion manifest, analysis, and report files.

**Interfaces:**
- Consumes: raw/resource/runtime series and frozen classification methodology.
- Produces: final `PARTIAL_BASELINE` or `COMPLETE_LOOPBACK_BASELINE` decision.

- [ ] Regenerate full, second-half, and final-quarter working-set/private-byte trends, confidence bounds, R-squared, bytes/request, backlog, and Go runtime observations.
- [ ] Verify new checksums and prior-evidence immutability.
- [ ] Run focused Python tests, full Python suite, Rust test/Clippy/format, Go test/vet/module verification, federation/conformance/security regressions, Ruff, evidence regeneration, and `git diff --check` without unrelated performance workloads.
- [ ] Review the exact diff and commits, then commit reports as `docs(perf): finalize loopback memory classification`.
