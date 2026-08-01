# WP6 Replicated Origin and Continuity State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded storage-neutral continuity state machine, deterministic snapshot repository, multi-replica quorum simulator, and fail-closed continuity decisions without new wire semantics.

**Architecture:** Immutable tenant-scoped records are accepted through monotonic compare-and-swap rules and serialized as closed canonical snapshots. A private-file repository persists those snapshots, while a deterministic quorum reader and continuity evaluator simulate replica agreement, bounded failover, drain, and non-resurrection behavior.

**Tech Stack:** Python 3.12+, standard-library dataclasses/JSON/hashlib/path APIs, existing `nbsr.secure_files`, pytest, Ruff.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not switch, merge, rebase, or push.
- Do not allocate any wire value or change frozen Core v0.1 semantics.
- Maximums are 32 replicas, 4096 records, and 256 KiB per snapshot.
- Quorum is a configured strict majority; replica identity is trusted local configuration.
- Failover is at most 5 seconds; drain is at most 30 seconds.
- No Origin Endpoint, raw client ID, credential, exporter, grant bytes, secret, or payload may enter snapshots, logs, errors, or reports.
- Evidence is deterministic and simulated, not live consensus, multi-host HA, crash recovery, or production readiness.

---

### Task 1: State model and monotonic repository

**Files:**
- Create: `nbsr/continuity.py`
- Create: `tests/test_wp6_continuity_state.py`

**Interfaces:**
- Produces: `StateKey`, `ContinuityRecord`, `ContinuityState`, `StateRejected`, and `ContinuityState.apply(record) -> ContinuityState`.

- [ ] **Step 1: Write failing state tests** for closed kinds, tenant/service key validation, bounds, canonical digest literals, idempotence, stale versions, missing prior digest, same-sequence equivocation, policy rollback, tenant confusion, terminal non-resurrection, and capacity failure.
- [ ] **Step 2: Run `python -m pytest -q tests/test_wp6_continuity_state.py`** and confirm failures are caused by the missing module/API.
- [ ] **Step 3: Implement immutable key/record/state types** with exact type checks, uint64 bounds, safe ASCII IDs, canonical record digest, sorted storage, and atomic `apply` that returns a new state only after all checks pass.
- [ ] **Step 4: Rerun the focused tests** and refactor only while green.
- [ ] **Step 5: Commit** `nbsr/continuity.py` and `tests/test_wp6_continuity_state.py` as `feat(wp6): model replicated continuity state`.

### Task 2: Deterministic snapshots and persistence

**Files:**
- Modify: `nbsr/continuity.py`
- Create: `tests/test_wp6_continuity_snapshot.py`
- Create: `scripts/verify_wp6_snapshot.py`
- Create: `vectors/wp6-continuity/snapshot.json`

**Interfaces:**
- Consumes: `ContinuityState` and `ContinuityRecord` from Task 1.
- Produces: `ReplicaConfig`, `ContinuitySnapshot`, `SnapshotRepository`, `encode_snapshot`, and `decode_snapshot`.

- [ ] **Step 1: Write failing snapshot tests** with a hand-derived canonical byte fixture and digest, strict schema/type/order checks, duplicate rejection, record/count/size bounds, corruption, rollback, partial file, directory/symlink/non-regular input, and unchanged state after failed persistence.
- [ ] **Step 2: Run `python -m pytest -q tests/test_wp6_continuity_snapshot.py`** and confirm the expected missing behavior.
- [ ] **Step 3: Implement canonical encoding/strict decoding** and a repository whose load uses a descriptor-bound no-follow regular-file check and whose save delegates to `secure_write_private` only after complete encoding.
- [ ] **Step 4: Add an independent standard-library verifier** that parses the checked-in fixture, reconstructs canonical JSON without importing `nbsr.continuity`, and checks schema, order, bounds, and SHA-256.
- [ ] **Step 5: Run focused tests and `python scripts/verify_wp6_snapshot.py vectors/wp6-continuity/snapshot.json`**; keep the fixture byte-for-byte deterministic.
- [ ] **Step 6: Commit** the module, tests, verifier, and fixture as `feat(wp6): persist deterministic replica snapshots`.

### Task 3: Replica quorum and split-brain rejection

**Files:**
- Modify: `nbsr/continuity.py`
- Create: `tests/test_wp6_replication.py`

**Interfaces:**
- Consumes: trusted `ReplicaConfig` and decoded `ContinuitySnapshot` values.
- Produces: `ReplicaObservation`, `QuorumView`, and `resolve_quorum(config, observations, minimum_generation) -> QuorumView`.

- [ ] **Step 1: Write failing quorum tests** for exact quorum, duplicate/unknown/forged identities, stale replicas, unavailable/partial observations, conflicting digests, two quorum-capable views, replica-set/tenant mismatch, and deterministic observation ordering.
- [ ] **Step 2: Run the focused file** and confirm failures name missing quorum behavior.
- [ ] **Step 3: Implement quorum resolution** using distinct configured replica identities and exact `(tenant, replica_set, generation, digest)` agreement; reject any ambiguity and expose only the agreed immutable state.
- [ ] **Step 4: Rerun focused and all WP6 tests**, then commit as `feat(wp6): resolve simulated replica quorum`.

### Task 4: Failover, drain, and continuity decisions

**Files:**
- Modify: `nbsr/continuity.py`
- Create: `tests/test_wp6_failover.py`

**Interfaces:**
- Consumes: `QuorumView`, safe state keys, caller wall time, and caller monotonic elapsed milliseconds.
- Produces: `ContinuityPermit`, `evaluate_continuity`, `bounded_failover`, and `drain_deadline`.

- [ ] **Step 1: Write failing behavior tests** proving the 5-second failover bound, 30-second drain bound, fresh quorum requirement, grant/policy/channel/replay requirements, revocation/tombstone denial, expiry denial, tenant/service isolation, wall/monotonic time separation, revoked channel and consumed replay non-resurrection, and no cross-edge authority field.
- [ ] **Step 2: Run the focused file** and confirm the expected failures.
- [ ] **Step 3: Implement pure fail-closed evaluators** that return only a safe local permit or raise a stable denial and never mutate state or a live system.
- [ ] **Step 4: Rerun focused and all WP6 tests**, then commit as `feat(wp6): enforce bounded continuity failover`.

### Task 5: Review, security fixes, and anti-drift evidence

**Files:**
- Modify only confirmed affected WP6 source/tests.
- Create: `tests/test_wp6_runtime_documentation.py`
- Modify: `docs/protocol/status.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`
- Modify: `docs/protocol/wp6-replicated-continuity-state-decision.md`

**Interfaces:**
- Consumes: the complete WP6 commit range and work request review checklist.
- Produces: reviewed code, regression tests for every confirmed defect, and authoritative bounded evidence.

- [ ] **Step 1: Dispatch independent correctness and security reviewers** over the exact WP6 range, including stale/replay/rollback/equivocation, identity/quorum, corruption/filesystem, bounds, privacy, time, mutation, and claims.
- [ ] **Step 2: Reproduce each plausible finding** with the narrowest failing regression test; reject unsupported candidates with written evidence.
- [ ] **Step 3: Fix confirmed defects minimally**, rerun their focused tests, and commit security fixes separately as `fix(wp6): close continuity review findings` when needed.
- [ ] **Step 4: Add runtime-documentation tests** that assert implemented/simulated/planned boundaries and explicit non-claims, then update the roadmap, status, README, and decision evidence.
- [ ] **Step 5: Run the full required validation matrix**, record exact fresh counts/results, rerun documentation tests and `git diff --check`, and commit as `docs(wp6): record final validation evidence`.
- [ ] **Step 6: Verify final Git invariants**: named branch, clean tree, unchanged `main` refs, explicit upstream divergence, no merge/rebase/switch/push, no tracked temporary files, and ignored secrets still ignored.
