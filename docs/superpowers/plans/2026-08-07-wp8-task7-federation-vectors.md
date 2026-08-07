# WP8 Task 7 Federation Vector Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the deterministic closed `vectors/federation-v0.1/` cross-language conformance authority without changing any approved upstream protocol authority.

**Architecture:** A Python generator assembles canonical JSON artifact inventories from fixed test material and independently checks three specification-authored oracle sets. A strict manifest binds every package file except the self-describing manifest itself, while check mode generates into memory and compares bytes without writing. Tests exercise the command boundary, closed-manifest validation, capability/session binding, state scenario coverage, error precedence, and immutable-authority digests.

**Tech Stack:** Python 3, pytest, canonical JSON, SHA-256, existing NBSR Federation codecs and fixed Ed25519 test keys.

## Global Constraints

- Preserve Core v0.1, the Core v0.2 110-artifact baseline, all Task 1-6 authorities, threshold-container v1, capability `THRESHOLD_EVIDENCE = 6`, and all 89 threshold literal bytes.
- Use fixed values only; no time, network, DNS, HTTPS, randomness, host path, locale, unordered iteration, or platform newline dependency.
- Check mode verifies mismatches and never rewrites them.
- Create one final commit named `test(wp8): publish federation conformance vectors`; do not start Task 8.

---

### Task 1: Generator and closed-manifest contract

**Files:**
- Create: `tests/federation/test_vectors.py`
- Create: `scripts/generate_federation_v01_vectors.py`
- Create: `scripts/federation_v01_vectors/__init__.py`
- Create: `scripts/federation_v01_vectors/package.py`

**Interfaces:**
- Produces: `build_package() -> dict[str, bytes]`, `verify_package(path: Path) -> list[str]`, and CLI `--check PATH`.
- Enforces: exact manifest fields, safe unique paths and IDs, complete inventory, file length/digest, dependencies, acyclic dependency graph, and supported package version.

- [ ] Write literal command-boundary tests that fail because generator/package APIs do not exist.
- [ ] Run `python -m pytest tests/federation/test_vectors.py -q` and record the expected RED failure.
- [ ] Implement canonical serialization, in-memory generation, strict validation, atomic write mode, and non-writing check mode.
- [ ] Re-run the focused tests to GREEN.

### Task 2: Static, signed, threshold, capability, and precedence vectors

**Files:**
- Modify: `tests/federation/test_vectors.py`
- Modify: `scripts/federation_v01_vectors/package.py`
- Create: `vectors/federation-v0.1/static-vectors.json`
- Create: `vectors/federation-v0.1/signed-vectors.json`
- Create: `vectors/federation-v0.1/threshold-vectors.json`
- Create: `vectors/federation-v0.1/capability-vectors.json`
- Create: `vectors/federation-v0.1/error-precedence.json`

**Interfaces:**
- Consumes: the 18-object registry, 28 schema literal oracle, and 89 threshold literal oracle.
- Produces: fixed vector IDs with payload/signature metadata, context, result/reason/enforcement/mutation, dependencies, limits, and capability/session transcript bindings.

- [ ] Add literal RED assertions for all 18 object classes, required defect families, exact 89 threshold references, required threshold-policy cases, 11 capability cases, and all 11 precedence ranks with simultaneous defects.
- [ ] Run the focused tests and record RED.
- [ ] Add the minimal deterministic vector builders, preserving oracle bytes verbatim and verifying their literal hashes.
- [ ] Re-run the focused tests to GREEN and perform a mutation check on capability/transcript digest validation.

### Task 3: Ordered stateful scenarios and README authority

**Files:**
- Modify: `tests/federation/test_vectors.py`
- Modify: `scripts/federation_v01_vectors/package.py`
- Create: `vectors/federation-v0.1/stateful-scenarios.json`
- Create: `vectors/federation-v0.1/README.md`

**Interfaces:**
- Consumes: the Task 6 specification-authored scenario manifest without regenerating it.
- Produces: all 43 required ordered scenarios and step fields, exact state digests, emitted evidence, dependency/effect records, and explicit normative/non-claim language.

- [ ] Add literal RED assertions for the 43 scenario names, required per-step fields, fixed evaluation times, exact state digests, and Task 6 oracle integration.
- [ ] Run the focused tests and record RED.
- [ ] Implement fixed scenario assembly and README generation.
- [ ] Re-run the focused tests to GREEN.

### Task 4: Determinism, regression, and independent review closure

**Files:**
- Create: `vectors/federation-v0.1/manifest.json`
- Modify only the Task 7 files above for confirmed review findings.

**Interfaces:**
- Generator output is byte-identical across two independent temporary directories and `--check` reports any byte mismatch without mutation.

- [ ] Generate twice into separate temporary directories and compare complete inventories and bytes.
- [ ] Generate the checked-in package and run `--check vectors/federation-v0.1`.
- [ ] Run focused Task 7, all Federation, Task 2-6, renderers/verifiers, Core locks/vectors, Node verifiers, WP4/WP6/WP7, full Python, Ruff, pip, scans, and `git diff --check`.
- [ ] Dispatch independent correctness and security/privacy reviews.
- [ ] For every confirmed finding, first add and observe a failing regression test, then correct it and re-run the covering validation.
- [ ] Verify explicit immutable-authority hashes and clean staging scope, then create the one requested commit.
