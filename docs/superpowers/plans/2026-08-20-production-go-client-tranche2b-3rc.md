# Production Go Client Tranche 2B 3R-C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete frozen ACP wire, HTTP/2 client/server transport, readiness orchestration, and real control-plane interoperability without entering Tranche 3.

**Architecture:** Deterministic CBOR/COSE codecs remain separate from HTTP transport. The Go client treats network bytes as untrusted until existing independent verification seals them; the Source Operator exposes only the two frozen HTTP/2 endpoints and uses a transactional durable idempotency contract. Startup publishes readiness only after authenticated identity load/enrollment and a fresh signed ACP check.

**Tech Stack:** Go standard library plus existing module dependencies, Python repository runtime where repository-native, TLS 1.3, HTTP/2, deterministic CBOR, COSE Sign1, Ed25519, SHA-256.

**Spec:** `docs/protocol/tranche2b-acp-wire-semantics.md` and `docs/protocol/tranche2b-enrollment-wire-semantics.md`; execution authority is the user-supplied 3R-C brief attached to this task.

## Global Constraints

- Working branch starts at local/remote `1dad39dda6083202bf210c86ce192eb48dbea089`; `main` and `origin/main` remain `1938154d498b32d81a3564319969430644e8a688`.
- Frozen ACP SHA-256 is `e795abf0a078c2dfe9bdf56d705fde67a1355bd28eb1cd35b5dc6efb0a5dad24`.
- Frozen Enrollment SHA-256 is `9d73983828f48b51a2b2e31c4637f1fe6f00b1505071faeef0be43d0e9504cd0`.
- Preserve application-layer `PurposeDeviceACPRequest`, outer `ACP_RESULT_SIGNING = 15`, outer `ENROLLMENT_RESULT_SIGNING = 16`, and independent inner artifact verification.
- HTTP transport is TLS 1.3 and HTTP/2 only, with no redirect, HTTP/1.1 fallback, automatic downgrade, or semantic-changing hidden retry.
- Do not implement QUIC data plane, Transport Sessions, Service Channels, Stream Credits, Application Streams, resolver/interception, reenrollment, or credential rotation/recovery.
- Use literal RED-first regression tests where practical; stage explicit paths only; no reset, rebase, force-push, or changes to `main`.

---

### Task 1: Frozen ACP wire codec and cryptographic binding

**Files:** Create `client/nbsr-go-client/internal/authority/acp_wire.go` and focused tests/fuzz seeds; modify only directly required authority helpers and concise recovery status.

**Interfaces:** Consume existing authority request/value types and generic CBOR/COSE helpers. Produce deterministic signed Acquire/Renew/Freshness request bytes and strict verified outer-result candidates for the HTTP adapter.

- [ ] Add golden and negative tests for exact key tables, three operations, bounds, malformed/noncanonical CBOR/COSE, purpose and request/result bindings; run them to establish RED.
- [ ] Implement minimal deterministic request encoding/signing and strict result parsing/verification with exact operation limits.
- [ ] Run focused authority tests, package regression, bounded parser fuzz, diff review, and frozen-hash checks.
- [ ] Obtain one independent spec/security review; fix Critical/Important findings once and obtain one scoped re-review.
- [ ] Update recovery status, commit `feat(go-client): implement frozen ACP wire codec`, push, and verify local/remote equality.

### Task 2: Go HTTP/2 ACP and Enrollment clients

**Files:** Create `internal/authority/http_provider.go`, `http_provider_test.go`, `enrollment_client.go`, and `enrollment_client_test.go`; add only small TLS/config helpers required by these adapters.

**Interfaces:** Consume Task 1 ACP wire and existing enrollment codec. Produce the existing `AuthorityProvider` implementation and an initial-enrollment client that return untrusted candidates to existing verification boundaries.

- [ ] Add RED tests for TLS 1.3/HTTP2-only, identity, redirect/fallback refusal, deadlines, bounds, retry byte stability, concurrency, reuse, signed deny, and enrollment success/failures.
- [ ] Implement reusable bounded HTTP/2-only adapters with finite explicit retry and exact-byte replay.
- [ ] Run focused tests, affected package race tests and vet, diff review, frozen hashes, independent review/fix/re-review.
- [ ] Update recovery status, commit `feat(go-client): add HTTP2 ACP and enrollment clients`, push, and verify local/remote equality.

### Task 3: Minimal Source Operator HTTP/2 runtime

**Files:** Choose the smallest repository-native production package after narrow architecture inspection; add only `/acp/authority`, `/acp/enroll`, bootstrap authorization, and durable idempotency components/tests.

**Interfaces:** Consume frozen codecs and existing authority/enrollment decision/verifier primitives. Produce a TLS 1.3 HTTP/2 handler/runtime plus transactional idempotency-store interface and explicit single-node production backend that refuses unsupported multi-replica configuration.

- [ ] Add RED tests for endpoint success, malformed/authentication/binding failures, signed purposes 15/16, bootstrap and reenrollment rejection, exact replay/collapse/conflict, expiry, bounds, restart, and transport-vs-semantic errors.
- [ ] Implement the two endpoints, bounded admission, durable exact-byte terminal replay, and fail-closed replica mode.
- [ ] Run focused/regression/race or Python tests and Ruff as applicable, diff review, frozen hashes, independent review/fix/re-review.
- [ ] Update recovery status, commit `feat(acp): add source operator control-plane runtime`, push, and verify local/remote equality.

### Task 4: Startup orchestration and real interoperability

**Files:** Create `internal/authority/runtime.go`, focused tests, and process/network integration fixtures; modify persistence boundaries only if integration proves a regression.

**Interfaces:** Consume Task 2 clients, existing authenticated enrollment state, generation floor, and sealed freshness verifier; interoperate with Task 3 runtime. Produce a lifecycle owner whose `Ready` becomes true only after live freshness verification.

- [ ] Add RED lifecycle, restart, fail-closed, adversarial network, shutdown, and bounded-concurrency integration tests.
- [ ] Implement existing-state and initial-enrollment startup flows, Freshness-before-Ready, and restart invalidation of all live authority state.
- [ ] Run focused E2E and affected regressions, diff review, frozen hashes, independent review/fix/re-review.
- [ ] Update recovery status, commit `feat(go-client): orchestrate tranche2b authority readiness`, push, and verify local/remote equality.

### Task 5: Whole-scope acceptance and closure

- [ ] Run fresh Go full suite, race suite with process-local UCRT PATH, vet, relevant Python suites, Ruff on changed Python, bounded ACP parser fuzz, protocol hashes, and `git diff --check`.
- [ ] Obtain one final independent requirement-by-requirement 3R-C review; apply one combined Critical/Important fix wave and one scoped re-review if required.
- [ ] Update `docs/protocol/tranche2b-implementation-status.md` and create `docs/reviews/production-go-client-tranche2b-3rc-closure.md` with exact evidence and nonclaims.
- [ ] Commit/push closure, verify clean worktree, local/remote equality, frozen `main`, and no merge/rebase.
