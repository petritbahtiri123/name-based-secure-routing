# P1F Rust Replay-History Hard Cap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce a validated, deterministic upper bound on committed destination replay-history entries per Rust Transport Session without weakening replay semantics.

**Architecture:** Add a validated operational limit type and snapshot it into each `ChannelStreams` owner at `ControlSession` construction. Preserve `prepare_open` error precedence, then reject an otherwise-authorized fresh ID with `StreamReject::OverCapacity` before audit-success and `commit_open`; retain the existing audit-before-commit transaction boundary. Reuse existing replay diagnostics and add only counters required to distinguish capacity and duplicate rejections.

**Tech Stack:** Rust, Cargo tests, existing NBSR loopback performance harness, JSON/NDJSON evidence.

## Global Constraints

- Base exactly `aa41bd0c46fd9ef8a97532f499ca0edc9ddaa446` on `codex/nbsr-perf-p1f-rust-replay-hard-cap`.
- Rust destination only; no Go, session rotation, wire-schema, replay-lifetime, HashSet, QUIC, allocator, Tokio, pooling, RouteGrant, resumption, federation, identity, or key changes.
- Duplicate and security rejection precedence remains authoritative; capacity is checked only for a fresh otherwise-authorized open.
- No push, pull, merge, or rebase; protected remote refs remain unchanged.
- Performance guardrails: median throughput regression at most 5%, median p99 regression at most 5%, zero unexpected errors.

---

### Task 1: RED boundary and lifecycle tests

**Files:**
- Modify: `crates/nbsr-transport/src/channel_streams.rs`
- Modify/Test: directly relevant `crates/nbsr-transport` integration test only if upstream connection proof cannot be expressed in the unit boundary

**Interfaces:**
- Consumes: existing `ChannelStreams::prepare_open`, `commit_open`, release/revoke, diagnostics, and `StreamReject` behavior.
- Produces: behavioral tests for exact N/N+1, non-mutation, precedence, retry-before-commit, audit-before-commit, shared sibling budget, close/reopen persistence, independent owner reset, limit one, invalid limits, large/adversarial sequences, and no-upstream prepared admission.

- [ ] Write focused tests using deliberately small literal limits; name the production branch each test catches.
- [ ] Run the focused test target and record expected RED failures caused by the missing validated limit API/capacity branch.

### Task 2: Minimal validated configuration and enforcement

**Files:**
- Modify: `crates/nbsr-transport/src/channel_streams.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Modify: Rust destination binary configuration call sites only as required

**Interfaces:**
- Produces: a public validated positive bounded replay-history limit and a `ControlSession` construction path that snapshots it immutably; `ChannelStreams::prepare_open` returns `OverCapacity` only after existing duplicate and authorization checks.

- [ ] Implement the smallest validated limit type and snapshot it in `ChannelStreams`.
- [ ] Add the post-authorization/pre-commit cardinality check and rejection diagnostics.
- [ ] Thread explicit operational configuration through Rust destination startup without an attacker-controlled or silent production default.
- [ ] Run the focused tests to GREEN, then format and rerun them.

### Task 3: Side-effect and adversarial proof

**Files:**
- Modify/Create: focused Rust transport test/harness files following existing conventions

**Interfaces:**
- Produces: proof that unique attempts beyond the cap never prepare/commit/connect upstream, duplicates retain replay rejection, destination survives, and owner drop reports zero replay state.

- [ ] Add/run the upstream-side-effect regression and a 10,000-limit substantially-over-limit adversarial case.
- [ ] Capture exact attempts, commits, rejections, entries, HashSet capacity, upstream attempts, and post-drop state.

### Task 4: Fast performance and memory evidence

**Files:**
- Create: `evidence/performance/rust-replay-hard-cap-p1f/**`

**Interfaces:**
- Produces: immutable manifest, smoke result, three paired before/after short cells, bounded-memory plateau result, analysis, report, and checksums.

- [ ] Run smoke with a non-binding cap.
- [ ] Run three identical short before/after pairs; expand to five only under the specified noise/threshold rule.
- [ ] Run one bounded adversarial session long enough to establish the replay plateau and post-cap memory shape.
- [ ] Compute acceptance metrics without weakening thresholds and package additive evidence.

### Task 5: Fresh verification and local commit

**Files:**
- Modify/Create: operational contract documentation and P1F evidence only

**Interfaces:**
- Produces: one clean local P1F commit and the comprehensive Outcome A/B/C report.

- [ ] Run focused ChannelStreams/replay/STREAM_OPEN/channel/session/side-effect/fail-closed/resumption tests.
- [ ] Run `cargo test -p nbsr-transport` once, `cargo fmt --check`, and `cargo clippy -p nbsr-transport --all-targets -- -D warnings`.
- [ ] Verify diff/checksums, prior P1A-P1E evidence identity, remote main/accepted SHAs, and Git/LFS state.
- [ ] Stage exact files, inspect staged names/stat/check, commit locally, and verify a clean worktree.
