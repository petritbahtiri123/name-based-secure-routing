# P1E Active/Standby Session Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved Go-owned active/standby rotation plus Rust destination replay cap only if the repository contains an existing fresh-RouteGrant acquisition contract that can authorize TS-B without new wire semantics.

**Architecture:** Gate production work on a repository-backed ownership trace. The Rust hard cap is independently expressible with the existing typed `StreamReject::OverCapacity`, but the requested fix is one coordinated mechanism and must not substitute the standalone interoperability benchmark peer for a production client/agent. If no production Go authority acquisition boundary exists, record Outcome C and make no partial production change.

**Tech Stack:** Go 1.26.5 inventory, Rust `nbsr-transport`, Python 3 repository feasibility check, pytest.

## Global Constraints

- Start exactly at `611e8287e9785513cbd021aefedeee0364353745` and do not push, pull, merge, or rebase.
- Preserve all frozen Core v0.2, F75, Federation v0.1, RouteGrant, replay, channel, revocation, and resume semantics.
- Go client/agent owns authority acquisition and session generations; Rust owns session-local admission and the hard replay bound.
- Do not treat `interop/nbsr-go-peer` benchmark fixture loading as production RouteGrant acquisition.
- Do not implement only one half of the coordinated fix after a code-level protocol gate fails.

---

### Task 1: Code-level ownership and wire-contract trace

**Files:**
- Create: `evidence/performance/active-standby-session-rotation-p1e/code-level-trace.md`

**Interfaces:**
- Consumes: every repository Go module/file, Core message registry, Go peer authority loading, Rust admission/capacity types, and P1D decision.
- Produces: exact evidence for whether fresh TS-B authority can be acquired through an existing production path.

- [ ] Inventory all Go modules and classify verifier, interoperability/benchmark, and production ownership.
- [ ] Trace RouteGrant bytes from origin to Go `ROUTE_OPEN` and identify whether any live acquisition API/message exists.
- [ ] Trace the Rust cap insertion point and existing typed error without changing production code.
- [ ] Decide the production implementation gate strictly from the approved ownership split.

### Task 2: Repository-backed feasibility gate using RED then GREEN

**Files:**
- Create: `tests/performance/test_p1e_implementation_gate.py`
- Create: `scripts/performance/p1e_implementation_gate.py`
- Create: `evidence/performance/active-standby-session-rotation-p1e/gate-result.json`

**Interfaces:**
- Produces: deterministic `evaluate_repository(root) -> dict` with exact Go ownership, authority source, Core acquisition-message, Rust-cap, and final-gate fields.

- [ ] Write literal tests requiring the actual repository inventory and Outcome C when production Go ownership or live authority acquisition is absent.
- [ ] Run pytest and retain the expected missing-module RED.
- [ ] Implement the smallest read-only evaluator; do not infer capability from names or expected labels.
- [ ] Run pytest to GREEN and generate the machine-readable result.

### Task 3: Outcome-C evidence and verification

**Files:**
- Create: `evidence/performance/active-standby-session-rotation-p1e/analysis.json`
- Create: `evidence/performance/active-standby-session-rotation-p1e/report.md`
- Create: `evidence/performance/active-standby-session-rotation-p1e/checksums.json`

**Interfaces:**
- Produces: final code-level blocker, exact missing contract, additive integrity evidence, and a local clean commit.

- [ ] Explain why a Rust-only cap or benchmark-peer session manager would not satisfy the authorized coordinated production mechanism.
- [ ] Run P1C/P1D/P1E model and focused Rust/Go regression checks plus format/static analysis.
- [ ] Verify P1A-P1D evidence trees and protected remote refs are unchanged.
- [ ] Generate and verify checksums, inspect/stage exact files, commit locally, and require a clean worktree.
