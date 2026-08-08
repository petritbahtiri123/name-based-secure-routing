# NBSR Performance Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, validate, and execute the first unoptimized, reproducible loopback benchmark for matched direct QUIC, Rust-to-Rust NBSR, and independent Go-to-Rust NBSR paths.

**Architecture:** Benchmark-only peers use the real QUIC/TLS and NBSR authority paths and emit bounded machine-readable event records. A Python driver owns lifecycle, load scheduling, append-safe raw evidence, resource sampling, statistics, matched comparisons, and manifest validation; it never makes protocol decisions.

**Tech Stack:** Rust 1.97.1, Quinn 0.11.11, rustls 0.23.43, Go 1.26.5, quic-go 0.61.0, Python 3.14.6, Windows process counters, NDJSON, SHA-256.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not push or merge.
- Freeze ALPN `nbsr-quic-1`, Core v0.2, F75, Federation v0.1, RouteGrant, exporter, replay, lifecycle, downgrade, channel, stream, and limit semantics.
- Keep 0-RTT disabled and HTTP/3 labeled `NOT SUPPORTED BY CURRENT TEST SURFACE`.
- Do not optimize NBSR after measurements begin.
- Direct QUIC must use equivalent QUIC v1, TLS 1.3 mTLS, identities, topology, payload, echo, freshness, and release profile.
- Never subtract unrelated process monotonic clocks.
- Preserve every raw success and failure; bounded output overflow fails the run.
- Stop on a discovered protocol correctness or security defect.

---

### Task 1: Freeze documents and evidence contracts

**Files:**
- Create: `docs/performance/benchmark-design-v0.1.md`
- Create: `docs/performance/benchmark-budgets-v0.1.md`
- Create: `docs/performance/benchmark-evidence-schema-v0.1.md`
- Create: `benchmarks/README.md`
- Create: `benchmarks/manifests/loopback-windows.json`
- Create: `benchmarks/schemas/sample-v1.schema.json`

**Interfaces:**
- Produces the exact field names, lifecycle meanings, matching key, formal counts, and immutable engineering budgets consumed by every later task.

- [ ] Record Phase 0 repository, toolchain, OS, CPU, memory, and power-plan evidence.
- [ ] Write the three approved documents and loopback manifest.
- [ ] Define a closed JSON schema requiring raw identity, cell, result, byte, and duration fields.
- [ ] Validate JSON syntax with `python -m json.tool benchmarks/manifests/loopback-windows.json`.
- [ ] Commit only these paths as `docs(perf): freeze benchmark methodology and evidence schemas`.

### Task 2: RED benchmark semantics and analysis

**Files:**
- Create: `tests/performance/test_benchmark_model.py`
- Create: `tests/performance/test_evidence_writer.py`
- Create: `tests/performance/test_statistics.py`
- Create: `scripts/performance/model.py`
- Create: `scripts/performance/evidence.py`
- Create: `scripts/performance/statistics.py`

**Interfaces:**
- Produces `ScenarioState`, `Sample`, `EvidenceWriter`, `percentiles(samples)`, and `matched_overhead(nbsr, direct)`.

- [ ] Write literal RED tests proving cold/warm separation, fresh admission only for new services, 20 independently authorized service IDs, repeated stream reuse, failure retention, overflow failure, exact nearest-rank percentiles, p99.9 suppression below 100,000 successes, and fail-closed matched keys.
- [ ] Run `python -m pytest tests/performance/test_benchmark_model.py tests/performance/test_evidence_writer.py tests/performance/test_statistics.py -q` and retain the missing-module RED.
- [ ] Implement frozen dataclasses/enums and transition validation without importing protocol authority.
- [ ] Implement a bounded writer that writes complete NDJSON lines and verifies submitted equals written.
- [ ] Implement independently hand-checked nearest-rank percentiles, bootstrap intervals with a recorded seed, and exact match validation.
- [ ] Rerun the focused tests and require GREEN.
- [ ] Commit as `test(perf): add benchmark integrity semantics`.

### Task 3: Direct QUIC and Rust benchmark peer

**Files:**
- Create: `crates/nbsr-transport/src/bin/perf_peer.rs`
- Create: `crates/nbsr-transport/tests/performance_peer.rs`

**Interfaces:**
- Consumes existing `TransportListener`, `AuthenticatedConnection`, `ControlSession`, federation/F75 admission, channel binding, and stream admission.
- Produces a release binary with `direct-server`, `direct-client`, `nbsr-server`, and `nbsr-client` modes plus NDJSON readiness/events.

- [ ] Add RED integration tests that direct mode echoes over authenticated QUIC without a control stream and rejects wrong identity/ALPN/0-RTT.
- [ ] Add RED tests that one NBSR session accepts 20 service authorities, repeats streams on existing channels, and preserves real F75/channel/stream gates.
- [ ] Run `cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test performance_peer` and observe the missing binary/API RED.
- [ ] Implement direct mode with the existing TLS builders and no NBSR imports beyond transport configuration.
- [ ] Implement persistent NBSR mode by looping the existing received envelope, admission, binding, stream, and application APIs; instrumentation only observes `Instant` durations.
- [ ] Rerun focused Rust tests and existing federation/application-stream tests.
- [ ] Commit as `feat(perf): add direct and persistent Rust benchmark peers`.

### Task 4: Persistent independent Go source

**Files:**
- Create: `interop/nbsr-go-peer/cmd/nbsr-go-perf/main.go`
- Create: `interop/nbsr-go-peer/cmd/nbsr-go-perf/main_test.go`
- Modify: `interop/nbsr-go-peer/internal/transport/quic.go`

**Interfaces:**
- Consumes the independent Go CBOR/Core/authority/state implementation and public quic-go APIs.
- Produces persistent cold, warm-new-service, warm-existing-service, sequential, concurrent, and 20-service commands with NDJSON results.

- [ ] Add RED Go tests for connection reuse, unique service/channel authority, repeated streams, concurrency, deterministic shutdown, writer failure, and `Allow0RTT == false` behavior.
- [ ] Run `go test ./...` in `interop/nbsr-go-peer` and observe the missing command/behavior RED.
- [ ] Implement the smallest persistent driver without importing or executing Rust, Python NBSR, or the Task 9 verifier.
- [ ] Run Go tests, vet, module verification, and the existing independent-wire pytest.
- [ ] Commit as `feat(perf): extend independent Go benchmark peer`.

### Task 5: Driver, resources, capacity, and evidence

**Files:**
- Create: `scripts/run_performance_validation.py`
- Create: `scripts/verify_performance_evidence.py`
- Create: `scripts/performance/driver.py`
- Create: `scripts/performance/resources.py`
- Create: `tests/performance/test_driver.py`
- Create: `tests/performance/test_resources.py`

**Interfaces:**
- Produces `calibration`, `latency`, `capacity`, and `load` phases and the complete evidence directory.

- [ ] Add RED tests for alternating order, release-binary enforcement, absolute-time open-loop scheduling, independent capacity per path, 60/600-second formal gates, resource fields, child failure propagation, and deterministic cleanup.
- [ ] Run focused pytest and observe missing driver behavior.
- [ ] Implement manifest parsing, peer orchestration, closed/open-loop schedules, process resource sampling, environment capture, and immutable run IDs.
- [ ] Implement capacity acceptance exactly as the frozen budget document states.
- [ ] Rerun focused tests and commit as `feat(perf): add benchmark orchestration and resource measurement`.

### Task 6: Statistical report and closed evidence inventory

**Files:**
- Create: `scripts/summarize_performance_evidence.py`
- Create: `tests/performance/test_report.py`
- Create at execution: `evidence/performance/**`

**Interfaces:**
- Consumes validated raw NDJSON and produces summaries, checksums, budget dispositions, and the Markdown report.

- [ ] Add RED tests using hand-calculated fixtures for counts, failures, percentiles, confidence intervals, matched deltas, exclusions, budgets, and closed inventory rejection.
- [ ] Run the focused report test and observe missing report behavior.
- [ ] Implement deterministic summaries and a report containing every required section and explicit non-claims.
- [ ] Implement SHA-256 inventory validation that rejects missing, extra, truncated, duplicate, or mutated evidence.
- [ ] Rerun focused tests and commit as `feat(perf): add statistical analysis and evidence verification`.

### Task 7: Validation and unoptimized loopback baseline

**Files:**
- Create: `evidence/performance/manifest.json`
- Create: `evidence/performance/environment.json`
- Create: `evidence/performance/calibration.json`
- Create: `evidence/performance/raw/*.ndjson`
- Create: `evidence/performance/summaries/*.json`
- Create: `evidence/performance/reports/latency-and-performance-validation.md`
- Create: `evidence/performance/exclusions.json`
- Create: `evidence/performance/checksums.json`

**Interfaces:**
- Produces the first reviewed unoptimized loopback baseline and no optimization changes.

- [ ] Run focused Python, Rust, Go, protocol, security, conformance, and interoperability validation with exact counts.
- [ ] Build release binaries in a writable non-OneDrive `CARGO_TARGET_DIR` and record their SHA-256 digests.
- [ ] Run calibration, idle direct, Rust-Rust, Go-Rust, lifecycle, 20-service, sequential, concurrent, capacity, load, resource, and summary phases in the approved order.
- [ ] Give the primary 1 KiB warm-existing matched cell the full counts; record any reduced secondary matrix cells explicitly.
- [ ] Validate raw counts, checksums, matched comparisons, exclusions, report sections, and `git diff --check`.
- [ ] Record poor numbers honestly and list candidate optimization opportunities as `NOT IMPLEMENTED`.
- [ ] Commit evidence as `evidence(perf): capture unoptimized loopback baseline` and stop without pushing.

## Plan self-review

- Every executable behavior starts with an observed RED.
- Direct and NBSR paths share transport security and payload behavior but not NBSR control execution.
- The Python layer observes and schedules; it cannot authorize protocol state.
- Cross-process clocks are never subtracted.
- Failed/late samples and exclusions remain auditable.
- Capacity and matching are path-specific and fail closed.
- Full headline counts, security gates, no optimization, loopback-only scope, and final stop are explicit.
