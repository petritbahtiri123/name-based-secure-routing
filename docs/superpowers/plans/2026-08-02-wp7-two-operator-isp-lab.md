# WP7 Two-Operator ISP Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic evidence that ISP-A and ISP-B independently admit and constrain a protected route without exposing its Origin Endpoint outside ISP-B's connector.

**Architecture:** Add one storage-neutral lab module with immutable closed inputs and isolated state machines for trust, admission, quotas, audit, connector confinement, and topology scanning. Reuse existing authority only through verified digests and denial gates; do not add wire values or production adapters.

**Tech Stack:** Python 3.12+, dataclasses, hashlib/hmac, pytest, Ruff.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; never merge, rebase, switch, push, or touch main.
- No Core v0.1/v0.2, OriginSet, federation, handover, resume, ownership, delegation, transparency, or trust-rotation wire changes.
- All collections and integers are bounded; overload and missing/mismatched authority fail closed.
- Origin Endpoint data is confined to the ISP-B connector and excluded from all other state and output.
- Every behavior change follows observed RED, minimal GREEN, broader verification, and a focused commit.

---

### Task 1: Operator profiles and cross-operator trust

**Files:** Create `nbsr/two_operator_lab.py`; create `tests/test_wp7_operator_model.py`.

**Interfaces:** Produce `OperatorProfile.from_dict()`, `RouteTrust`, `AdmissionContext`, and `LabRejected` with closed schemas, canonical IDs, unique key purposes, exact operator ownership, policy/gateway/continuity digests, and bounded uint64 versions.

- [ ] Write tests that reject forged operators, duplicate/purpose-confused fingerprints, unknown fields, invalid IDs, stale policy versions, and substituted trust tuples.
- [ ] Run `python -m pytest -q tests/test_wp7_operator_model.py` and observe failures because the module/API is absent.
- [ ] Implement only immutable validation and exact trust matching; no wire serialization or endpoint fields.
- [ ] Rerun the focused test, then `python -m pytest -q tests/test_wp6_continuity_state.py tests/test_gateway_profile.py`.
- [ ] Commit the exact two new paths as `feat(wp7): model isolated operator trust`.

### Task 2: Independent source and destination admission

**Files:** Modify `nbsr/two_operator_lab.py`; create `tests/test_wp7_admission.py`.

**Interfaces:** Produce `TwoOperatorLab.admit(request, now_ms)` returning `AdmissionReceipt`; source checks ISP-A subscriber/name/edge/policy/gateway/continuity first, destination independently checks ISP-B service/route/channel/tunnel/edge/policy/trust, and all authority digests must match exactly.

- [ ] Write table-driven failing tests for every spoofed context, source/destination bypass, stale/denied continuity, grant replay/substitution, wrong ordering, and sibling success after denial.
- [ ] Run the focused test and verify expected missing behavior failures.
- [ ] Implement explicit source and destination gate methods and denial codes, with no resource mutation before both gates pass.
- [ ] Rerun focused admission and operator tests.
- [ ] Commit exact paths as `feat(wp7): enforce independent operator admission`.

### Task 3: Independent token buckets and fair resource ownership

**Files:** Modify `nbsr/two_operator_lab.py`; create `tests/test_wp7_limits.py`.

**Interfaces:** Produce `LimitProfile`, saturating `TokenBucket`, atomic multi-scope consumption, and active allocation ownership keyed by operator/tenant/subscriber/name/service/route/channel/tunnel.

- [ ] Write failing tests for per-client/name/route/service/channel/tunnel/operator independence, cross-context inheritance, refill/burst/saturation, uint64/clock rollback, atomic denial, fair share, and noisy-neighbor isolation.
- [ ] Run the focused test and observe failures.
- [ ] Implement integer-millisecond refill with saturation and preflight-before-consume, plus bounded allocation maps.
- [ ] Rerun all WP7 tests.
- [ ] Commit exact paths as `feat(wp7): isolate subscriber and resource limits`.

### Task 4: Audit, overload, connector privacy, and topology scan

**Files:** Modify `nbsr/two_operator_lab.py`; create `tests/test_wp7_conformance.py`; create `config/wp7-two-operator-lab.json`; create `scripts/verify_wp7_lab.py`.

**Interfaces:** Produce independent bounded `AuditLog`, connector-only endpoint receipt, safe `OperatorReport`, closed `LabTopology`, deterministic `simulate_raw_scan()`, and verifier exit status.

- [ ] Write failing tests for audit ownership/sequence/capacity, safe reports/errors, overload without fallback, endpoint leakage probes, deterministic config, topology collection bounds, direct-edge rejection, and scan non-discovery/reachability.
- [ ] Run focused tests and verifier, observing missing behavior failures.
- [ ] Implement bounded audit-before-success semantics, safe aggregate reports, private connector closure, and closed canonical topology verification.
- [ ] Rerun all WP7 tests and verifier twice to confirm identical output.
- [ ] Commit exact paths as `feat(wp7): simulate abuse overload and origin scans`.

### Task 5: Independent reviews and regression-first fixes

**Files:** Modify only confirmed affected WP7 source/tests; optionally create no fix commit if there are zero confirmed defects.

**Interfaces:** Reviewers receive the frozen design, plan, and diff read-only; candidate findings require a concrete exploit/counterexample and are independently reproduced.

- [ ] Dispatch separate correctness and security reviewers covering every threat named in the work request.
- [ ] Independently reproduce each candidate; reject unsupported candidates with evidence.
- [ ] For each confirmed issue, add a focused failing regression test, observe RED, implement minimal fix, and observe GREEN.
- [ ] Run all WP7 and affected legacy tests.
- [ ] If fixes exist, commit exact paths as `fix(wp7): close lab review findings`.

### Task 6: Evidence and complete validation

**Files:** Create `docs/protocol/wp7-two-operator-isp-lab-decision.md`; create `tests/test_wp7_runtime_documentation.py`; modify `docs/protocol/status.md`, `README.md`, and `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`.

**Interfaces:** Authoritative docs record exact observed counts, simulated/live boundary, review disposition, connector boundary, and every mandatory non-claim.

- [ ] Add documentation anti-drift tests that require conservative status and non-claims; observe RED before documentation changes.
- [ ] Update only the listed authoritative documents and rerun the focused documentation tests.
- [ ] Run all required Python, vector, Node, Rust, Compose, OPA, WP7 verifier, privacy scans, and `git diff --check` commands fresh.
- [ ] Record exact results, rerun affected documentation tests, inspect tracked/ignored paths and staged files explicitly.
- [ ] Commit exact documentation/test paths as `docs(wp7): record final validation evidence` and verify final Git invariants.
