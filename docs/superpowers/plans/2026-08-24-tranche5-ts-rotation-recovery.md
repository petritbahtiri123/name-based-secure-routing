# Tranche 5 Transport Session Rotation and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded, authority-safe Transport Session generation rotation, draining, and recovery to the production Go client without changing wire semantics or replaying application payload.

**Architecture:** Add a generation-local rotation coordinator to `internal/session.Manager`. Replacement connection happens outside the ownership lock; one final locked commit installs B as current and marks A draining, while runtime-owned deadlines close draining descendants. Existing SC, credit, and Application Stream maps remain attached to their original generation.

**Tech Stack:** Go standard library, existing `internal/session`, `internal/authority`, Go-to-Rust QUIC interoperability harness, Rust `nbsr-transport` regressions.

**Spec:** `docs/superpowers/specs/2026-08-24-tranche5-ts-rotation-recovery-design.md`

## Global Constraints

- Preserve frozen TS, SC, P1F, P2D, credit, StreamID, RouteGrant, and authority semantics.
- Maximum committed generations per reuse key is exactly two.
- Coalesced triggers may only escalate to stricter no-new-work semantics.
- Never promote a draining generation back to current.
- Every draining generation has a finite runtime-configured deadline.
- Never automatically replay application bytes or migrate descendants.
- Do not add Synthetic IP, DNS, resolver, proxy, or new wire behavior.
- Do not hold ownership locks across network I/O.

---

### Task 1: Rotation state machine and atomic handoff

**Files:**
- Create: `client/nbsr-go-client/internal/session/rotation.go`
- Create: `client/nbsr-go-client/internal/session/rotation_test.go`
- Modify: `client/nbsr-go-client/internal/session/types.go`
- Modify: `client/nbsr-go-client/internal/session/manager.go`
- Modify: `client/nbsr-go-client/internal/session/errors.go`

**Interfaces:**
- Produce `RotationTrigger`, `RotationRequest`, `RotationResult`, `Manager.RotateTransportSession(context.Context, RotationRequest)`, `Manager.CurrentTransportSession(ReuseKey)`, and bounded rotation fields in `Limits`/`Usage`.
- Preserve `CreateTransportSession` as cold-start creation and reuse its exact proof/authority validation.

- [ ] Write failing tests proving A-current to A-draining/B-current is atomic, new work selects B, old descendants stay on A, a third committed generation is rejected, failed B preserves only a still-valid A, and final authority/proof changes reject B.
- [ ] Run the focused rotation tests and retain the expected compile/failure output as RED.
- [ ] Implement the smallest coordinator: validate/capture, reserve one pending attempt, connect outside the lock, final barrier, atomic commit, and uncommitted transport cleanup.
- [ ] Run focused rotation plus existing session package tests to GREEN.
- [ ] Commit explicit Task 1 paths.

### Task 2: Trigger escalation, failure recovery, and finite draining

**Files:**
- Modify: `client/nbsr-go-client/internal/session/rotation.go`
- Modify: `client/nbsr-go-client/internal/session/rotation_test.go`
- Modify: `client/nbsr-go-client/internal/session/manager.go`
- Modify: `client/nbsr-go-client/internal/session/application_stream.go`
- Modify: `client/nbsr-go-client/internal/session/credit.go`

**Interfaces:**
- Produce `Manager.RecoverTransportSession(context.Context, RotationRequest)`, `Manager.FailTransportSession(...)`, trigger severity escalation, bounded attempts/backoff, and runtime drain expiry.
- Consume existing recursive `CloseTransportSession` teardown and generation-local descendant ownership.

- [ ] Write failing tests for concurrent coalescing, benign-to-revocation escalation, cancellation/shutdown, bounded attempts, B failure while A drains, no C before A removal, drain-deadline forced teardown, and no orphan pending state.
- [ ] Run focused tests and verify literal RED.
- [ ] Implement monotonic trigger escalation, bounded retry/backoff with context cancellation, no-current fail-closed states, and finite local drain timers without holding locks during connect/close.
- [ ] Add RED then GREEN integration tests proving draining A rejects SC/credit/stream/refill admissions, unused credits are invalidated, accepted streams remain pinned until close/deadline, and teardown is idempotent.
- [ ] Run session package tests and race-focused rotation tests to GREEN.
- [ ] Commit explicit Task 2 paths.

### Task 3: Replay-cap, restart, and no-application-replay integration

**Files:**
- Modify: `client/nbsr-go-client/internal/session/rotation.go`
- Modify: `client/nbsr-go-client/internal/session/rotation_test.go`
- Modify: `client/nbsr-go-client/internal/authority/runtime_test.go`
- Modify: `client/nbsr-go-client/streamclient/streamclient.go`
- Modify: relevant focused Go-to-Rust interop test/harness only if its existing adapter exposes the local lifecycle hook.

**Interfaces:**
- Map the existing local replay-cap/transport-failure condition to `RotationTriggerReplayCapacity` without changing Rust or wire values.
- Preserve fresh manager construction after restart and expose no payload-copy/retry path.

- [ ] Write failing tests proving replay-cap makes A no-new-work, never resets A replay state, creates fresh B state, and never resends bytes written on A.
- [ ] Write failing restart tests proving a reconstructed runtime/manager has zero TS/SC/credit/stream/rotation state, starts not ready, and creates only a fresh generation after freshness.
- [ ] Implement only the local lifecycle hook needed by those tests; if the real harness cannot expose replay-cap without protocol change, document that limitation and keep the unit boundary typed.
- [ ] Extend the existing real local Go-to-Rust lifecycle to establish/use A, rotate, establish/use B, close A, and reject all A-owned reuse, without resolver/Synthetic-IP work.
- [ ] Run focused Go interop and relevant Rust P1F/P2D/vector regressions.
- [ ] Commit explicit Task 3 paths.

### Task 4: Documentation, one review, and closure

**Files:**
- Create: `docs/protocol/tranche5-implementation-status.md`
- Create: `docs/reviews/2026-08-24-production-go-client-tranche5-rotation-recovery.md`
- Modify: only confirmed Critical/Important finding paths from the single focused review.

**Interfaces:**
- Record exact state machine, trigger escalation, max-two behavior, drain deadline, replay-cap/restart/no-replay behavior, tests, interop, and honest limitations.

- [ ] Run complete Go tests, UCRT race tests, and vet fresh.
- [ ] Run relevant Go/Rust interop, Rust transport, P1F, P2D, and protocol/vector regressions once.
- [ ] Inspect the complete Tranche 5 diff once for the requested security/correctness failure modes; fix only confirmed Critical/Important findings with RED tests.
- [ ] Perform one scoped re-review of the fixes and stop reviewing.
- [ ] Write status and closure reports with exact PASS/FAIL/INCONCLUSIVE results.
- [ ] Run final verification, inspect/stage explicit files, make coherent closure commits, push normally, and verify clean worktree, local/remote equality, and unchanged main.
