# Phase C OriginSet Internal Model Plan

**Goal:** Implement the smallest bounded, immutable Derived OriginSet model
approved by D7, without serialization, wire allocations, DNS integration, or
runtime routing changes.

**Scope:** One production module, one focused test module, and documentation
status updates. Service Channel models remain outside this task.

## Task 1 - Freeze behavior in focused tests

**Files:**

- Create: `tests/test_originset.py`

Add failing tests for:

- immutable endpoint, OriginSet, and tombstone objects;
- exact type and bound validation;
- mode-specific derivation authority;
- deterministic normalized endpoint ordering and content digest;
- stale generation/sequence rejection;
- same-version same-digest idempotence;
- same-version different-content equivocation rejection;
- previous-digest continuity; and
- tombstone protection against resurrection.

Run:

```text
python -m pytest tests/test_originset.py -q
```

Expected result before implementation: failure because `nbsr.originset` does
not exist.

## Task 2 - Implement the internal model

**Files:**

- Create: `nbsr/originset.py`

Implement:

- frozen, slotted `OriginEndpoint`, `DerivedOriginSet`, and
  `OriginSetTombstone` dataclasses;
- small enums for lifecycle mode, derivation authority, DNSSEC status, and the
  initial TCP transport profile;
- local validation exceptions that do not allocate protocol error codes;
- deterministic SHA-256 over a documented internal JSON tuple used only for
  comparison and tests;
- `accept_originset` and `make_tombstone` pure functions.

The module must not implement CBOR, COSE, a message, a numeric key, a new state
machine, DNS discovery, caching, routing, logging, or client-visible output.

Run:

```text
python -m pytest tests/test_originset.py -q
```

Expected result: pass.

## Task 3 - Record approval and model boundary

**Files:**

- Modify: `docs/protocol/originset-compatibility-authority-decision.md`
- Modify: `docs/protocol/v3.6-decisions.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

Record that D7-1 through D7-5 were approved on 2026-07-28 and that the current
authorization covers only the Phase C internal Derived OriginSet model. Keep
native wire form, COSE schema, message codes, DNS adapter, Service Channel,
and runtime integration pending.

## Task 4 - Validate and commit

Run focused tests first, then the full supported suite, scoped Ruff checks,
format verification, dependency consistency, and `git diff --check`.

Create one commit containing only this approved Phase C OriginSet scope. Do not
push without a separate instruction.
