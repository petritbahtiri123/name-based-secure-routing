# WP8 Task 9 Clean-room Go Federation Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dependency-free, independent Go verifier that reproduces the complete frozen Federation v0.1 Task 7 conformance package without deriving decisions from expected outputs.

**Architecture:** A dedicated `verifiers/federation-go` Go module verifies the closed package before loading semantic fixtures. Focused internal packages own strict JSON/filesystem handling, deterministic CBOR, identity/COSE, schema and protocol semantics, and deterministic state replay; the CLI composes them and compares computed results with oracle fields only after evaluation.

**Tech Stack:** Go 1.26 standard library, `crypto/ed25519`, `crypto/sha256`, table-driven Go tests, checked-in Federation v0.1 authorities and vectors.

## Global Constraints

- Do not modify frozen Core v0.1, the 110-artifact Core v0.2 baseline, Federation authorities, schema/threshold literals, or `vectors/federation-v0.1`.
- Do not invoke or import Python, Node, their verifiers, generators, or generated answers from Go.
- Expected outcome, reason, enforcement, mutation, and state digest fields are comparison oracles only.
- Use only the Go standard library; no external dependency or license surface.
- Begin each implementation tranche with an observed failing Go test and retain regression coverage.
- Manifest failure aborts all semantic verification.
- Stop before Rust transport integration, live discovery, live two-operator federation, or deployment work.
- Deliver one focused commit: `test(wp8): add clean-room go federation verifier`.

---

### Task 1: Closed package and strict JSON boundary

**Files:** create `verifiers/federation-go/go.mod`, `internal/strictjson/strictjson.go`, `internal/packageverify/package.go`, and focused tests.

- [ ] Write RED tests for duplicate/unknown JSON fields, unsafe paths, symlinks, hash/length drift, extra files, oversized/truncated files, dependency/version/profile/authority-lock failures.
- [ ] Run focused tests and record the expected failures.
- [ ] Implement bounded stable regular-file reads, duplicate-aware strict JSON, exact inventory and manifest/authority validation.
- [ ] Re-run focused tests GREEN.

### Task 2: Deterministic CBOR and primitives

**Files:** create `internal/cbor/cbor.go`, `internal/identity/identity.go`, and focused tests.

- [ ] Write RED tests for every approved CBOR type plus non-shortest forms, duplicate/reordered map keys, indefinite values, malformed tags, floats/simple values, limits, trailing input, and exact round trips.
- [ ] Implement a bounded canonical decoder/encoder with encoded-key ordering and complete consumption.
- [ ] Write RED tests for the frozen Operator ID digest, Bech32m presentation, decoding, checksum/case/HRP/padding rejection.
- [ ] Implement SHA-256, Operator ID derivation, and independent Bech32m.
- [ ] Re-run focused tests GREEN.

### Task 3: COSE Sign1

**Files:** create `internal/cose/sign1.go` and focused tests.

- [ ] Write RED tests for tag/shape/protected headers/alg/kid/unprotected/AAD/payload/signature length/critical semantics and byte/signature/kid mutations.
- [ ] Implement exact Sig_structure construction and standard-library Ed25519 verification.
- [ ] Re-run focused tests GREEN.

### Task 4: Registry, schema, static, and signed vectors

**Files:** create `internal/registry/registry.go`, `internal/schema/schema.go`, `internal/verifier/static.go`, `internal/verifier/signed.go`, and tests.

- [ ] Write RED coverage that loads the machine authorities, identifies all 18 object classes, and rejects exact-key/type/bound/composite/extension/lineage/lifecycle/validity/recovery defects.
- [ ] Implement registry-driven closed schema validation and contextual semantic checks without mirroring Python/Node class structure.
- [ ] Compute canonicality/digest/schema/context decisions for all 35 static vectors before oracle comparison.
- [ ] Verify exact COSE payload/digest/kid/purpose/authority/Operator ID/validity/lifecycle/context for all 12 signed vectors.
- [ ] Re-run focused and full module tests GREEN.

### Task 5: Threshold evidence v1

**Files:** create `internal/threshold/threshold.go` and tests.

- [ ] Write RED tests for the approved envelope, capability/session keys 11-12, policy/group selection, signer ordering/duplicates/cross-group reuse, identity and organization diversity, partial evidence, deny-only/resource behavior, and COSE context binding.
- [ ] Implement all final Option C rules and independently evaluate all 89 fixtures.
- [ ] Re-run focused tests GREEN.

### Task 6: Capability agreement and precedence

**Files:** create `internal/capability/capability.go`, `internal/precedence/precedence.go`, and tests.

- [ ] Write RED tests for all authenticated agreement/downgrade/replay/version/profile/transcript cases and exact 11-rank simultaneous-defect precedence.
- [ ] Implement offer/selection/signature/transcript/session/capability-set/threshold-context binding and independent primary-error selection.
- [ ] Evaluate all 12 capability and all precedence vectors, then compare with their oracles.
- [ ] Re-run focused tests GREEN.

### Task 7: Deterministic state model

**Files:** create `internal/state/state.go`, `internal/verifier/stateful.go`, and tests.

- [ ] Write RED scenario tests for watermarks, idempotency, rollback, equivocation, quarantine, revocation dependencies, terminal tombstones, replay, trust/checkpoint continuity, LKG degradation/expiry, recovery, conflict, and appeal.
- [ ] Implement Go-owned canonical state serialization and SHA-256 digesting.
- [ ] Independently replay all 43 scenarios and calculate every outcome/reason/enforcement/mutation/state digest before comparison.
- [ ] Re-run focused tests GREEN.

### Task 8: CLI, adversarial suite, and documentation

**Files:** create `cmd/verify/main.go`, `internal/verifier/verifier.go`, `internal/adversarial/adversarial_test.go`, and `README.md`.

- [ ] Add Go-native package/CBOR/COSE/threshold/capability/state mutations covering the requested minimum set and assert semantic error classes.
- [ ] Implement a manifest-first CLI with exact category counts and divergence reporting.
- [ ] Document clean-room boundary, usage, dependencies, and non-claims.
- [ ] Run `go test ./...`, full Go verification, and `go vet ./...`.

### Task 9: Independent reviews and complete validation

- [ ] Dispatch a correctness reviewer with the exact independence question from the approval.
- [ ] Dispatch a security/privacy reviewer over parser, filesystem, crypto, downgrade, threshold, replay, deterministic state, and resurrection risks.
- [ ] For each confirmed issue, add an observed RED regression, correct it, and re-run GREEN.
- [ ] Run Python, Node, Go, generators/checkers, schema/threshold literals, Core baseline/vector suites, full Python, Ruff, pip check, secret/privacy scan, and `git diff --check`.
- [ ] Confirm immutable-authority byte identity and clean Git scope, then create the single requested commit.
