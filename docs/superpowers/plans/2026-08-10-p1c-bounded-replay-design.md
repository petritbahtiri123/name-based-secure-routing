# P1C Bounded Replay-State Design Investigation Plan

> **For Codex:** Execute this plan sequentially. Preserve production replay semantics and stop after the P1C report.

**Goal:** Determine whether the destination `ChannelStreams.used_stream_ids` full-history oracle can be represented by a strict high-water mark or a finite sliding bitmap without changing any frozen legal or adversarial outcome.

**Architecture:** Treat the current committed-open `HashSet<u64>` as the behavioral oracle. Trace identifier generation, authenticated control admission, QUIC binding, lifecycle, and replay scope from implementation plus frozen tests. Add a test-only deterministic model that compares strict-high-water and parameterized sliding-window candidates with the oracle; preserve the model results and scaling calculations in one additive P1C report/evidence directory. Do not alter production replay code.

**Tech Stack:** Rust workspace tests, deterministic model/property enumeration, Markdown/JSON evidence, Git.

---

### Task 1: Freeze boundaries and semantic evidence

**Files:**
- Read: `crates/nbsr-transport/src/channel_streams.rs`
- Read: `crates/nbsr-transport/src/control_session.rs`
- Read: `crates/nbsr-transport/src/quinn_adapter.rs`
- Read: directly relevant transport tests and frozen Core v0.2 protocol documents

1. Verify branch, base SHA, clean worktree, and required remote SHAs.
2. Trace `STREAM_OPEN` from source QUIC stream creation through envelope construction, destination decode/prepare/commit, release, channel close, and session drop.
3. Inventory focused replay, stream, channel, lifecycle, fail-closed, and resume/migration tests.
4. Record exact evidence citations and unresolved protocol facts; do not infer from names.

### Task 2: Build the candidate/oracle model with literal RED

**Files:**
- Create or modify only test/model files under the existing transport test layout.

1. Write tests that require an unimplemented HashSet oracle, strict-high-water candidate, sliding-window candidate, boundary scopes, and mismatch accounting.
2. Run the focused test target and confirm RED due to missing model behavior.
3. Implement the smallest test-only model needed to run deterministic cases and reproducible generated sequences.
4. Cover sequential IDs, protocol-valid gaps, legal reorderings if any, duplicates, very old duplicates, concurrent permutations, reset/rejection, close/reopen, session boundaries, and numeric limits/overflow.
5. Run focused model tests to GREEN and record exact case/sequence counts, false accepts, false rejects, and maximum state sizes.

### Task 3: Produce the security and scaling decision report

**Files:**
- Create: `evidence/performance/bounded-replay-design-p1c/report.md`
- Create: `evidence/performance/bounded-replay-design-p1c/model-results.json`
- Create: `evidence/performance/bounded-replay-design-p1c/checksums.json`

1. Build the ACCEPT/REJECT attacker matrix from current frozen semantics.
2. Compare HashSet, strict high-water, and every evidence-justified finite-window constraint.
3. Calculate measured-versus-estimated replay state for 1k/10k/100k streams per second over 1/10/60 minutes, including channel/session scope.
4. Select exactly one A/B/C/D classification and state the exact invariant or missing protocol decision.
5. Name exactly one next task and do not start it.

### Task 4: Fresh verification and independent review

**Files:**
- Update P1C evidence files with fresh command outcomes only.

1. Run focused replay/model tests first.
2. Run STREAM_OPEN, Service Channel, session lifecycle, fail-closed, and implemented migration/resumption tests.
3. Run `cargo fmt --check` and `cargo clippy --all-targets -- -D warnings` with a writable non-OneDrive target directory.
4. Run the relevant broader regression suite once; compare known Windows baseline failures without changing vectors or manifests.
5. Review the diff against the objective and security invariants; correct any material issue and rerun affected verification.
6. Generate checksums, commit only scoped files, verify clean status, branch/base ancestry, remote SHAs, and absence of push/merge/rebase/pull actions.
