# P2D Stream Credit Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and validate `nbsr-stream-credit-1`, providing 64 bounded one-time admissions per active Service Channel without per-flow control-stream coordination.

**Architecture:** Add a closed deterministic preface codec and compact epoch/bitmap state. Reuse `ControlSession` as the sole authority for channel, lease, revocation, capacity, audit, and P1F commits; add Quinn same-stream ACCEPT/REJECT gating. Keep legacy STREAM_OPEN unchanged and select credit mode explicitly.

**Tech Stack:** Rust 2024, Quinn 0.11, Tokio, existing deterministic CBOR helpers, Python evidence tooling, pytest.

## Global Constraints

- Base exactly `366bbfcfdf5aba9155b476e935f40356eb5fbefa`; branch `codex/nbsr-perf-p2d-stream-credit-window`; no push, pull, merge, rebase, or protected-ref mutation.
- Preserve Core v0.1 bytes/numeric meanings, P1F `used_stream_ids` and `ReplayHistoryLimit`, payload quarantine, route/service/session isolation, and prior evidence.
- Fixed profile values: `nbsr-stream-credit-1`, 64 credits, low watermark 16, current plus one draining epoch, one pending refill.
- No bearer tokens, per-credit heap objects, origin data, speculative payload, or new global admission queue.

---

### Task 1: Preface codec, profile selection, and deterministic vectors

**Files:** Create `crates/nbsr-transport/src/stream_credit.rs`, `crates/nbsr-transport/tests/stream_credit_vectors.rs`, `vectors/stream-credit-v1/manifest.json`, vector `.cbor` files; modify `src/lib.rs`.

**Interfaces:** Produce `StreamCreditProfile`, `StreamCreditPreface`, `StreamCreditReject`, `encode_stream_credit_preface`, and `decode_stream_credit_preface`; decoder accepts a 128-byte maximum and actual authenticated session/QUIC identity context.

- [ ] Write literal RED vector tests for negotiated/unsupported/downgrade/fallback behavior and valid/malformed/wrong-binding prefices; run `cargo test --test stream_credit_vectors` and record the expected missing API failure.
- [ ] Implement the minimal closed deterministic codec and explicit profile selector without modifying Core v0.1; rerun the focused test to GREEN.
- [ ] Generate fixed valid and invalid vector bytes, closed manifest hashes, and a verifier test that derives decisions from bytes/context rather than expected labels; mutation-test slot, epoch, channel, session, and stream fields.

### Task 2: Compact credit lifecycle and atomic session admission

**Files:** Modify `src/stream_credit.rs`, `src/channel_streams.rs`, `src/channel_registry.rs`, `src/session.rs`; add unit tests beside each module.

**Interfaces:** Produce `StreamCreditWindows` with `activate`, `allocate`, `request_refill`, `activate_refill`, `cancel_refill`, `prepare_consume`, `commit_consume`, `retire`, and `remove_channel`; `ControlSession::authorize_credited_stream` performs live authority checks and commits credit plus P1F state atomically.

- [ ] Write RED tests covering requirements 5-28 and 34-40: 64 exact-once slots, bounds/bindings, low-water refill, two-epoch transition, revocation/expiry, RouteGrant/service/session isolation, capacity, P1F, races, and cleanup; verify failures are missing behavior rather than fixture errors.
- [ ] Implement two `u64` bitmaps, counters, one pending refill flag, exact epoch transitions, and channel cleanup; do not allocate slot objects.
- [ ] Integrate credited prepare/commit with existing stream state so failed validation/audit never mutates credit or replay state, while post-commit failures never restore either; rerun focused unit tests.
- [ ] Add resource/abuse tests for thousands of channels, one-slot reuse loops, random invalid slots, stale epochs, refill floods, never-consumed windows, and fixed state-size assertions.

### Task 3: Same-stream Quinn admission and payload quarantine

**Files:** Modify `src/quinn_adapter.rs`, `src/session.rs`, `tests/application_stream.rs`; create `tests/stream_credit_integration.rs`.

**Interfaces:** Produce `open_credited_session_stream` and `accept_credited_session_stream`; the source writes only the bounded preface, waits for one-byte ACCEPT, then returns `ApplicationStream`; destination parses, authorizes, writes decision, and returns a stream only after commit.

- [ ] Write RED integration tests for independent streams, no STREAM_OPEN dependency, concurrent distinct/same-slot behavior, malformed/preface flood, payload before ACCEPT, revoke races at preface/decision/refill/transition, and rejection cleanup.
- [ ] Implement bounded preface read/write and same-stream decision framing with per-stream resets; keep existing legacy methods byte/behavior compatible.
- [ ] Run application, channel, replay, revocation, expiry, capacity, concurrency, payload-quarantine, fallback, and abuse suites to GREEN.

### Task 4: Benchmark harness, evidence, and acceptance decision

**Files:** Create `scripts/performance/p2d_stream_credit.py`, `scripts/run_p2d_stream_credit.py`, `tests/test_p2d_stream_credit.py`, and additive files under `evidence/performance/stream-credit-window-p2d/`; modify benchmark-only Rust binaries if required.

**Interfaces:** Harness emits immutable JSON cells with mode, concurrency, 1 KiB payload correctness, throughput, p50/p95/p99, CPU, errors, credit/refill/epoch/replay counters; analyzer applies throughput >=20%, p99 <=5%, zero errors, security/refill/soak gates and CV <=5% three-pair stopping rule.

- [ ] Write RED tests for concurrency list `1,2,4,8,16,32,64`, matched BEFORE/AFTER manifests, median/CV math, gate precedence, ten-window continuity, and checksum closure; run focused pytest.
- [ ] Implement the minimum harness/analyzer and short synthetic smoke; verify first window, exhaustion, automatic/multiple refill, and concurrency correctness.
- [ ] Run short concurrency sweep, then three paired 60-120 second cells; expand to five only when noisy/near threshold. Run ten-window continuity and one 5-10 minute soak only after short gates pass.
- [ ] Package design, vectors, raw/summary cells, security matrix, resource analysis, `analysis.json`, checksums, and final report additively; classify Outcome A only if every mandatory gate passes, otherwise revert production behavior after at most three evidence-driven corrections while retaining safe evidence.

### Task 5: Fresh verification, independent review, and local commit

**Files:** All scoped files from Tasks 1-4; no protected or prior-evidence paths.

**Interfaces:** Produce a clean local branch with one final SHA and a self-contained evidence report.

- [ ] Run fresh focused and broader affected Rust tests, vector verifier, P1F/revocation/expiry/capacity/concurrency/payload/fallback/abuse/benchmark tests, `cargo fmt --check`, and feature-complete `cargo clippy -- -D warnings`; record exact counts.
- [ ] Inspect diff/status, prior-evidence path hashes, protected local/remote refs, evidence checksums, `git diff --check`, and staged file list; request an independent code/security review and resolve Critical/Important findings.
- [ ] Commit only scoped files locally, run `git show --check`, verify final worktree clean and remote protected SHAs unchanged, and write the exact final report required by P2D. Do not push.
