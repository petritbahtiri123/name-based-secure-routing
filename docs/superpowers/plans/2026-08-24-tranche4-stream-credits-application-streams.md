# Tranche 4 Stream Credits and Application Streams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded accepted P2D Stream Credit and Application Stream ownership to the production Go client and prove real Go-to-Rust interoperability.

**Architecture:** Extend the existing `internal/session.Manager` hierarchy with focused credit and application-stream files. Reserve state atomically, perform QUIC admission without locks, and publish only after an authority and ownership commit barrier.

**Tech Stack:** Go, Rust/Quinn, deterministic CBOR, QUIC v1/TLS 1.3, Go testing/race/vet, Cargo tests, Python interop harness.

**Spec:** `docs/superpowers/specs/2026-08-24-tranche4-stream-credits-application-streams-design.md`

## Global Constraints

- Preserve `nbsr-stream-credit-1`: 64 credits, watermark 16, refill to 64, one-use bitmap, current plus draining only, and one pending refill.
- Preserve RouteGrant as authority; a credit is only synchronized admission state.
- Use actual QUIC StreamID and the accepted P2D preface/ACCEPT/REJECT behavior.
- Never permit application payload before ACCEPT.
- Hold no ownership lock across network I/O, callbacks, authority-provider calls, or blocking reads.
- Do not implement rotation/recovery, replay, migration, Synthetic IP, resolver, proxy, UI, or unrelated cleanup.

---

### Task 1: Bounded Stream Credit Ownership

**Files:**
- Create: `client/nbsr-go-client/internal/session/credit.go`
- Create: `client/nbsr-go-client/internal/session/credit_test.go`
- Modify: `client/nbsr-go-client/internal/session/types.go`
- Modify: `client/nbsr-go-client/internal/session/errors.go`
- Modify: `client/nbsr-go-client/internal/session/manager.go`

**Interfaces:**
- Produces: `CreditSnapshot`, `ReserveStreamCredit`, `BeginCreditRefill`, `CompleteCreditRefill`, and `CancelCreditRefill` bound to `(TSGeneration, ServiceHandle)`.
- Produces: internal immutable `creditReservation` carrying epoch, slot, and the full SC/TS binding.

- [ ] Write literal tests for initial 64, one-use allocation, binding errors, maximum two epochs, watermark/refill coalescing, revocation/teardown, concurrency, and cleanup.
- [ ] Run each focused test before production code and retain the expected missing-behavior RED result.
- [ ] Implement a 64-bit used bitmap per epoch, one draining epoch, one pending refill, strict monotonic epochs, and bounded accounting.
- [ ] Integrate SC/TS teardown invalidation and expose bounded usage snapshots.
- [ ] Run `go test ./internal/session -run 'Test(StreamCredit|Credit)' -count=1`, then `go test ./internal/session -count=1`.
- [ ] Inspect diff/hygiene, stage explicit Task 1 paths, and commit `client: own bounded stream credits`.

### Task 2: Application Stream Admission and Ownership

**Files:**
- Create: `client/nbsr-go-client/internal/session/application_stream.go`
- Create: `client/nbsr-go-client/internal/session/application_stream_test.go`
- Create: `client/nbsr-go-client/internal/session/stream_credit_codec.go`
- Create: `client/nbsr-go-client/internal/session/stream_credit_codec_test.go`
- Modify: `client/nbsr-go-client/internal/session/types.go`
- Modify: `client/nbsr-go-client/internal/session/errors.go`
- Modify: `client/nbsr-go-client/internal/session/manager.go`

**Interfaces:**
- Consumes: Task 1 `creditReservation` and SC ownership state.
- Produces: `ApplicationStream`, `OpenApplicationStream`, `Write`, `Close`, exact P2D preface encoding, and narrow `ApplicationStreamOpener`/wire-stream interfaces.

- [ ] Write and run RED tests for actual StreamID binding, pending/accepted/closed states, pre-ACCEPT write rejection, malformed/rejected admission, final-barrier races, duplicate IDs, sibling isolation, repeated close, bounds, and recursive teardown.
- [ ] Write and run RED vector tests using literal accepted P2D encodings and wrong-profile/downgrade cases.
- [ ] Implement open/preface/admission with network I/O outside locks and a local final commit barrier.
- [ ] Enforce payload gating in the stream object and deterministic cleanup without credit reuse.
- [ ] Run focused Application Stream/codec tests and the full `internal/session` package.
- [ ] Inspect diff/hygiene, stage explicit Task 2 paths, and commit `client: own admitted application streams`.

### Task 3: Real Interop, Documentation, and Closure

**Files:**
- Create or modify the narrow production-client/Rust interop harness discovered from existing P1F/P2D tooling.
- Create: `docs/protocol/tranche4-implementation-status.md`
- Create: `docs/reviews/2026-08-24-production-go-client-tranche4-stream-credits.md`
- Modify: `docs/protocol/implementation-tranches.md`

**Interfaces:**
- Consumes: production `session.Manager` Application Stream path and existing Rust gateway.
- Produces: independent-process loopback evidence for valid, replayed, wrong-profile/binding, multiple-stream, refill, and payload-quarantine cases.

- [ ] Add a real-process test that drives the production client path against the existing Rust gateway; run it first to obtain RED before wiring the harness.
- [ ] Implement only the adapter/harness code needed to connect production interfaces to existing Go QUIC and Rust gateway behavior.
- [ ] Run real valid and negative interop cases and record exact results without broader production claims.
- [ ] Update status and closure documents with semantics, invariants, evidence, and nonclaims.
- [ ] Run full Go test/race/vet plus relevant Rust P1F/P2D/vector and protocol checks.
- [ ] Request one focused review against the starting SHA; add RED regressions and fixes for confirmed Critical/Important findings; request one scoped re-review.
- [ ] Run fresh final verification, inspect/stage explicit paths, commit `docs: close Tranche 4 stream ownership`, fast-forward push only `origin/codex/nbsr-v3-wp0-wp1`, and verify clean/ref equality and unchanged main.
