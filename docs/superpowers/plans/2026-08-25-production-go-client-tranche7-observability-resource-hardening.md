# Production Go Client Tranche 7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing production Go client with bounded privacy-preserving observability, deterministic resource-overload evidence, and repeatable lifecycle/leak diagnostics without changing protocol behavior.

**Architecture:** Add a stdlib-only in-memory observability package whose dimensions are closed enums and whose counters are fixed-size atomics. Existing package observers and newly added session/resolution/proxy lifecycle hooks feed only redacted event categories; a health snapshot composes aggregate resource usage without identifiers, names, digests, RouteGrants, credentials, or endpoints. Exercise existing stores and managers under saturation, cancellation, restart, and churn, changing production ownership only when a literal RED test proves a leak or nondeterministic overflow.

**Tech Stack:** Go 1.26.5 standard library, existing production-client packages, Go race detector, repository Go-to-Rust interop procedures.

**Spec:** `docs/architecture/production-go-client/implementation-tranches.md` Tranche 7 and the user-approved Tranche 7 task specification.

## Global Constraints

- Preserve all frozen Core, ACP, P1F, P2D, RouteGrant, channel, credit, and Application Stream wire semantics.
- Keep the explicit SOCKS5-domain/HTTP CONNECT adapter; add no transparent interception or demo behavior.
- Telemetry has bounded cardinality and never carries origin endpoints, names, full digests, IDs, grants, keys, credentials, tokens, or payload.
- Every attacker-influenced structure remains explicitly bounded, non-evicting for live security state, and fail closed on overload.
- Use literal RED-first tests for every production behavior change.

---

### Task 1: Privacy-safe aggregate observability

**Files:**
- Create: `client/nbsr-go-client/internal/observability/collector.go`
- Create: `client/nbsr-go-client/internal/observability/collector_test.go`
- Modify only as required after RED: observer/lifecycle boundaries under `internal/corestate`, `internal/authority`, `internal/resolution`, `internal/session`, and `internal/adapter/proxy`

**Interfaces:**
- Produces a closed `Domain`, `Event`, and `Outcome` vocabulary; `Recorder.Record(Event)`; and immutable aggregate `Snapshot`/`Health` values.
- Fixed arrays indexed only by validated enums prevent label growth; invalid events are counted in one bounded internal-failure bucket.

- [ ] Write tests proving fixed cardinality, concurrent recording, redacted public types, expected-denial versus internal-failure classification, exhaustion/fail-closed visibility, and immutable snapshots.
- [ ] Run the focused test and verify RED because the collector does not exist.
- [ ] Implement the minimal atomic collector and aggregate health model.
- [ ] Run focused and race tests; keep event payloads identifier-free.

### Task 2: Lifecycle instrumentation and health composition

**Files:**
- Modify only the package boundaries demonstrated missing by Task 1 tests.
- Create/modify focused tests beside each changed package.

**Interfaces:**
- Components accept a nil-safe recorder/observer at construction or expose an adapter around an existing observer; no external backend is added.
- Health reports only readiness state, bounded aggregate usage/capacity, and closed reason categories.

- [ ] Write focused RED tests for mapping/flow/proxy/session/channel/credit/stream lifecycle, overload rejection, fail-closed decisions, and cleanup release.
- [ ] Verify each RED failure names the absent observable transition.
- [ ] Add the smallest lifecycle calls outside locks where callbacks could re-enter.
- [ ] Run each focused test and affected package race test GREEN.

### Task 3: Resource, adversarial cleanup, and churn evidence

**Files:**
- Add focused `*_test.go` files in the affected production packages; add a bounded diagnostic test under `internal/observability` only if cross-package composition requires it.

**Interfaces:**
- Tests use existing `Usage`/snapshot APIs and real stores/managers to assert capacity returns to steady state.
- Churn evidence records literal iterations, concurrency, duration, goroutine delta, state counts, allocation/heap/GC observations, and rejection counts without production-scale claims.

- [ ] Add deterministic tests for saturation, cancellation at each ownership boundary, replacement/expiry races, double consumption, stale/mismatched bindings, active shutdown, restart-empty state, and same-IP/same-port service isolation where applicable.
- [ ] Run focused tests and classify any RED as a real production defect or missing evidence.
- [ ] For each real defect, add the minimal production fix, rerun GREEN, and inspect cleanup ordering.
- [ ] Run bounded race/churn/soak diagnostics and capture measured current-machine results.

### Task 4: Documentation and final closure

**Files:**
- Create: `docs/protocol/tranche7-implementation-status.md`
- Modify: `docs/architecture/production-go-client/implementation-tranches.md`
- Modify: `docs/architecture/production-go-client/protocol-gap-register.md` only for gaps directly changed by measured evidence.

- [ ] Document scope, nonclaims, privacy/cardinality model, bounds, overload behavior, measured workload, tests, limitations, and demo-readiness conclusion.
- [ ] Run the V3.6 anti-drift checklist against the diff and record the result without changing frozen authorities.
- [ ] Run full Go tests, all affected race tests, vet, gofmt verification, diff/whitespace checks, relevant Go-to-Rust interop, and the new churn/overload tests.
- [ ] Perform one focused correctness/security review of changed files and their dependency boundaries; fix confirmed Critical/Important findings and re-run scoped verification once.
- [ ] Stage explicit paths, commit a focused Tranche 7 series, push only `codex/nbsr-v3-wp0-wp1`, and verify local/remote equality plus unchanged `main`.
