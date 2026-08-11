# P2C Bounded Pipelined STREAM_OPEN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test and, only if all gates pass, keep bounded source-side pipelining of independently authorized `STREAM_OPEN` admissions on one Transport Session.

**Architecture:** Reserve real silent Quinn bidirectional streams to obtain exclusive IDs, track at most a validated small window by request ID, send existing control envelopes in order, correlate exact existing responses, and activate only accepted reservations. Destination authorization remains sequential; the benchmark drains each bounded admission batch before accepting its application streams.

**Tech Stack:** Rust 2024, Tokio, Quinn 0.11.11, Python standard library, existing benchmark harness and process sampler.

## Global Constraints

- Base exactly `e82b7cfa7b3c4dc14bdae605caf1eeded0dacaa7` on `codex/nbsr-perf-p2c-pipelined-stream-open`.
- No wire schema, authority, replay, sequencing, audit, capacity, F75/federation, Go, or established-data-path change.
- Pending window is deterministic, bounded, and limited to `1..=16`; window 1 preserves sequential behavior.
- No push, pull, merge, rebase, protected-branch modification, or follow-on optimization.
- Preserve P1A-P2B evidence byte-for-byte and create only additive P2C evidence.

---

### Task 1: Semantic eligibility and actual stream reservation

**Files:** create `evidence/performance/pipelined-stream-open-p2c/semantic-eligibility.md`; modify `crates/nbsr-transport/src/quinn_adapter.rs`, `crates/nbsr-transport/src/lib.rs`; test `crates/nbsr-transport/tests/pipelined_admission.rs`.

**Interfaces:** Produce `ReservedApplicationStream::id() -> u64`, `AuthenticatedConnection::reserve_application_stream() -> Result<ReservedApplicationStream, TransportError>`, and `activate_reserved_stream(&self, ReservedApplicationStream, &ApplicationStreamPermit) -> Result<ApplicationStream, TransportError>`.

- [ ] Write the concrete 18-point state/order trace with exact code and frozen protocol citations.
- [ ] Write RED live-Quinn tests proving reservations expose actual IDs 4/8/12, stay silent before acceptance, cannot be stolen by another opener, activate only against an exact permit, and reset/drop safely on mismatch or close.
- [ ] Run `cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test pipelined_admission --features benchmark-harness` and verify missing-interface failures.
- [ ] Implement the minimal reserved-stream handle and exact activation checks without changing `open_session_stream` behavior.
- [ ] Re-run the focused test to GREEN.

### Task 2: Bounded pending admission coordinator

**Files:** create `crates/nbsr-transport/src/pipelined_admission.rs`; modify `crates/nbsr-transport/src/lib.rs`; extend `crates/nbsr-transport/tests/pipelined_admission.rs`.

**Interfaces:** Produce `AdmissionWindow::try_from(usize)`, `PendingStreamAdmissions::new(AdmissionWindow)`, insertion by exact request/channel/stream binding, exact correlated accept/reject removal, channel/all cleanup, `len()`, `high_water()`, and leak-free ownership of reservations.

- [ ] Write RED behavioral tests for windows 1/2/4, hard bound, duplicate request/stream rejection, exact response correlation, A-accept/B-reject/C-accept, reject/timeout/cancel cleanup, revoke cleanup, connection cleanup, bounded diagnostics, and cross-request binding rejection.
- [ ] Verify RED because the coordinator does not exist.
- [ ] Implement the smallest bounded map with deterministic cleanup and typed errors.
- [ ] Run the focused tests to GREEN and mutation-check wrong request, stream, channel, and route fields.

### Task 3: Security and resource interaction

**Files:** extend `crates/nbsr-transport/tests/pipelined_admission.rs` and only if a proven defect requires it modify `session.rs` or `channel_streams.rs`.

**Interfaces:** Reuse existing `ControlSession::authorize_stream_open`, `confirm_stream_accept`, `ChannelStreams::prepare_open`, and `commit_open` without bypass.

- [ ] Write RED integration scenarios for request replay, stream replay, strict monotonic sequence, P1F remaining-capacity 2 with 8 candidates, channel capacity at limit minus/at/plus one, revoke while pending, and shutdown with multiple pending entries.
- [ ] Verify each test fails only for missing pipeline orchestration, not because the frozen invariant is absent.
- [ ] Connect the coordinator exclusively through existing session authorization/permit paths; do not add a speculative authorization path.
- [ ] Run pipeline, multi-stream, channel-lifecycle, drain, resumption, and application-stream tests to GREEN.

### Task 4: Windowed lifecycle harness

**Files:** modify `crates/nbsr-transport/src/bin/perf_rust_source.rs`, `crates/nbsr-transport/src/bin/wp8_interop_server.rs`, `scripts/run_p2c_pipeline.py`; create `scripts/performance/p2c_pipeline.py`, `tests/test_p2c_pipeline.py`.

**Interfaces:** `NBSR_P2C_ADMISSION_WINDOW` accepts only 1/2/4/8/16; JSON output adds window, pending high-water, protocol-error count, replay entries, CPU, and memory while retaining lifecycle latency fields.

- [ ] Write RED Python/Rust tests for accepted windows, invalid-window fail-closed behavior, batch bounds, window-1 ordering, metric completeness, paired-cell matching, acceptance calculations, and evidence error rejection.
- [ ] Verify RED against the P2B sequential runner/binaries.
- [ ] Implement bounded batch reservation/send/read/activate at source and sequential read/authorize/respond followed by application accept at destination.
- [ ] Run unit/integration smoke to GREEN with zero errors and exact stream IDs.

### Task 5: Short measurements and KEEP/REVERT gate

**Files:** create additive raw/manifests/analysis under `evidence/performance/pipelined-stream-open-p2c/`.

- [ ] Run smoke windows 1/2/4/8 at no more than about 30 seconds each.
- [ ] Run approximately 60-second windows 1/2/4/8/16, stopping escalation when the stated saturation/resource rule applies.
- [ ] Select the smallest window providing most benefit and run three paired 60-120-second BEFORE/AFTER high-load cells; expand to five only for CV above 5% or a result within one percentage point of 10%.
- [ ] Evaluate every security, correctness, performance, and quality gate without lowering thresholds.
- [ ] If any mandatory gate fails after at most three evidence-backed corrections for one mode, revert production optimization and retain only safe tests/design/evidence as Outcome B.
- [ ] If short acceptance passes, run one 5-10-minute moderate-concurrency soak and verify no pending/state/replay/memory growth.

### Task 6: Evidence, independent review, and local completion

**Files:** finalize `analysis.json`, `checksums.sha256`, and `final-report.md` under the P2C evidence root.

- [ ] Run fresh pipeline, STREAM_OPEN, replay, sequence, ChannelStreams, P1F, capacity, revocation, lifecycle, and QUIC binding tests plus affected broader Rust regression.
- [ ] Run `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check` and `cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings` with an external target directory.
- [ ] Verify P1A-P2B evidence hashes/trees unchanged, P2C checksums complete, `git diff --check`, and protected remote refs unchanged.
- [ ] Request an independent scoped review, resolve all critical/important findings, then repeat fresh verification.
- [ ] Stage only scoped files, inspect staged names/stat/diff, commit locally, run `git show --check`, and verify the final worktree is clean without pushing.
