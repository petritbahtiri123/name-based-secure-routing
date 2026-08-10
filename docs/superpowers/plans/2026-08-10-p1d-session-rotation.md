# P1D Bounded Transport-Session Rotation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove whether the existing NBSR transport architecture can rotate a session at a deterministic committed-stream bound without weakening frozen security semantics or exposing flow disruption, and implement only if all six authorization gates pass.

**Architecture:** Trace the current QUIC, `ControlSession`, RouteGrant, Service Channel, stream, replay, drain, and resume owners. Model TS-A and TS-B as independent authorities and test adversarial transition events. Treat absence of a production owner for parallel-session selection or fresh authority acquisition as a design blocker rather than inventing wire or application semantics.

**Tech Stack:** Rust `nbsr-transport`, Python 3 deterministic model, pytest, Git LFS evidence conventions.

## Global Constraints

- Base exactly `a13ead66e65896260a44da19da0ae27b0c98cd96`; do not push, pull, merge, or rebase.
- Preserve frozen Core v0.2, F75, Federation v0.1, RouteGrant, replay, channel-binding, downgrade, revocation, resource-limit, and fail-closed semantics.
- Do not replace or bound `ChannelStreams.used_stream_ids` directly.
- Production implementation is permitted only if all six gates in P1D section 10 are proven true.
- Preserve all P1A/P1B/P1C evidence byte-for-byte and write only additive P1D evidence.

---

### Task 1: Lifecycle and authority trace

**Files:**
- Create: `evidence/performance/rust-session-rotation-p1d/security-analysis.md`

**Interfaces:**
- Consumes: `AuthenticatedConnection`, `ControlSession`, `DestinationAdmission`, `SameEdgeResumeManager`, and current integration tests.
- Produces: exact creation, admission, cleanup, authority, and concurrency findings used by the gate.

- [ ] Record code/test paths for all thirteen requested lifecycle stages.
- [ ] Identify fresh material, reusable identity/trust policy, and authority that must never cross sessions.
- [ ] Determine whether parallel session creation, independent channel reauthorization, and application-transparent stream selection have production owners.

### Task 2: Adversarial rotation model using RED then GREEN

**Files:**
- Create: `scripts/performance/session_rotation_model.py`
- Create: `tests/performance/test_session_rotation_model.py`
- Create: `evidence/performance/rust-session-rotation-p1d/model-results.json`

**Interfaces:**
- Produces: `RotationModel`, whose methods accept typed session/channel/grant/request/sequence/stream/resume authority and return literal `ACCEPT` or fail-closed rejection reasons.

- [ ] Write literal tests for old stream replay, channel/grant/request resurrection, monotonic rollback, resume replay, revocation, admission failure, boundary concurrency, drain, and fresh numeric stream reuse.
- [ ] Run pytest and capture the expected import failure as RED.
- [ ] Implement only the deterministic model needed by those tests.
- [ ] Run pytest to GREEN and generate canonical JSON results.

### Task 3: Conditional implementation decision

**Files:**
- Create: `evidence/performance/rust-session-rotation-p1d/analysis.json`
- Create: `evidence/performance/rust-session-rotation-p1d/report.md`

**Interfaces:**
- Consumes: Tasks 1-2 evidence.
- Produces: one explicit outcome A, B, or C and six Boolean implementation gates.

- [ ] Mark each gate PASS or FAIL from code and model evidence.
- [ ] If every gate passes, create a separate TDD implementation extension before production edits.
- [ ] If any gate fails, make no production edits and state the exact protocol/application ownership decision required.

### Task 4: Integrity and final verification

**Files:**
- Create: `evidence/performance/rust-session-rotation-p1d/checksums.json`

**Interfaces:**
- Produces: additive evidence integrity and final local commit.

- [ ] Run the focused model tests and relevant Rust replay/session/channel/RouteGrant/request/sequence/resumption/revocation suites.
- [ ] Run `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and the broader relevant Rust suite once.
- [ ] Verify P1A/P1B/P1C tree hashes are unchanged, generate P1D checksums, inspect diff/status, and verify protected remote refs.
- [ ] Commit only the safe outcome, record final SHA, and require a clean worktree.
