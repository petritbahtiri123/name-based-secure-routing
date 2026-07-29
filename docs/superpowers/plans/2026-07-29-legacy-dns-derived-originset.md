# Legacy DNS-backed Derived OriginSet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert normalized legacy DNS discovery into bounded internal
`DerivedOriginSet` state with safe refresh, rollback protection, and a
five-minute last-known-good window.

**Architecture:** Add one isolated WP2 module. An injected resolver boundary
produces immutable snapshots; the module validates policy and converts them to
the existing internal OriginSet model. A bounded in-memory cache owns refresh
deadlines and failure behavior but has no threads, public DNS access, client
serialization, or relay integration.

**Tech Stack:** Python 3.12+, frozen dataclasses, `ipaddress`, existing
`nbsr.originset`, pytest, Ruff.

## Global Constraints

- Preserve every frozen Core v0.1 key, code, state, transition, CBOR rule, and
  COSE rule.
- Never expose an Origin Endpoint in a DNS answer, API response, ordinary
  error, or ordinary log.
- Use no public DNS or network access in tests.
- Maximum accepted endpoint count is configurable from 1 through 32.
- Prototype maximum DNS TTL and last-known-good grace are each 300 seconds.
- Timeout/SERVFAIL may use bounded last-known-good; authenticated negative,
  DNSSEC bogus/downgrade, policy mismatch, rollback, and equivocation fail
  closed immediately.
- Do not integrate with `NameRelay`, implement Web PKI network validation,
  create background tasks, or begin WP3.

---

### Task 1: Normalized snapshot and deterministic conversion

**Files:**

- Create: `nbsr/legacy_origin.py`
- Create: `tests/test_legacy_origin.py`

**Interfaces:**

- Produces `LegacyDnsResult`, `LegacyDnsSnapshot`, `LegacyOriginRequest`,
  `LegacyOriginValidationError`, and `derive_originset(...)`.
- `derive_originset(request, snapshot, *, sequence, previous_digest,
  validator)` returns a validated `DerivedOriginSet`.

- [ ] **Step 1: Write failing model and conversion tests**

```python
def test_positive_snapshot_derives_deterministic_originset() -> None:
    candidate = derive_originset(
        request(),
        positive_snapshot(),
        sequence=1,
        previous_digest=None,
        validator=lambda _request, _endpoint: True,
    )
    assert candidate.service_id == "svc_api"
    assert candidate.sequence == 1
    assert [endpoint.address for endpoint in candidate.endpoints] == [
        "192.0.2.10",
        "2001:db8::10",
    ]
```

Also freeze exact-type validation, canonical names, allowed ports/networks,
1–32 endpoints, DNSSEC-bogus rejection, secure-to-insecure downgrade
rejection, and origin-free exception text.

- [ ] **Step 2: Verify RED**

Run:

```text
python -m pytest tests/test_legacy_origin.py -q -p no:cacheprovider
```

Expected: collection fails because `nbsr.legacy_origin` does not exist.

- [ ] **Step 3: Implement the minimal immutable models and converter**

Use frozen, slotted dataclasses. Require canonical Service/origin names, exact
integers, canonical CIDRs, unique ports, normalized endpoint ordering, and a
fail-closed injected validator. Derive:

```python
DerivedOriginSet(
    service_id=request.service_id,
    service_record_generation=request.service_record_generation,
    origin_generation=1,
    sequence=sequence,
    endpoints=accepted_endpoints,
    publication_mode=PublicationMode.LEGACY_DNS,
    authority_kind=AuthorityKind.LOCAL_DERIVATION,
    issuer_id=request.issuer_id,
    not_before=snapshot.observed_at,
    expires_at=snapshot.observed_at + accepted_ttl + 300,
    dnssec_status=snapshot.dnssec_status,
    previous_digest=previous_digest,
)
```

Temporary and negative snapshots are not convertible to OriginSets.

- [ ] **Step 4: Verify GREEN and format**

Run focused pytest, Ruff check, and Ruff format check for the two files.

- [ ] **Step 5: Commit**

```text
git commit -m "feat: derive OriginSet from legacy DNS snapshots"
```

### Task 2: Bounded refresh and last-known-good cache

**Files:**

- Modify: `nbsr/legacy_origin.py`
- Modify: `tests/test_legacy_origin.py`

**Interfaces:**

- Produces `LegacyOriginCache`, `LegacyOriginView`,
  `LegacyOriginUnavailable`, `apply_snapshot(...)`, and `lookup(...)`.
- The cache key is `(service_id, issuer_id)`.

- [ ] **Step 1: Write failing cache tests**

```python
def test_temporary_failure_uses_last_known_good_only_within_grace() -> None:
    cache = LegacyOriginCache()
    cache.apply_snapshot(request(), positive_snapshot(observed_at=100, ttl_seconds=60), validator=allow)
    stale = cache.apply_snapshot(request(), temporary_snapshot(observed_at=161), validator=allow)
    assert stale.fresh is False
    assert stale.next_refresh_at == 162
    with pytest.raises(LegacyOriginUnavailable):
        cache.lookup(request(), now=461)
```

Also test proactive refresh at 80 percent TTL; retry delays
`1, 2, 4, 8, 16, 30`; hard invalidation for authenticated negative,
DNSSEC-bogus, and downgrade; atomic replacement; previous-digest continuity;
stale/equivocation rejection; capacity failure without eviction; and
tombstone resurrection protection.

- [ ] **Step 2: Verify RED**

Run the focused cache tests and confirm the missing cache API is the cause.

- [ ] **Step 3: Implement minimal cache behavior**

Store only accepted OriginSet state, deadlines, failure count, and tombstones.
Do not start a scheduler. Return `LegacyOriginView(originset, fresh,
dns_fresh_until, last_known_good_until, next_refresh_at)`.

Temporary failure returns the accepted set until
`last_known_good_until`; hard failure creates/retains a tombstone and rejects
new use immediately. When capacity is reached, reject a new key without
evicting existing state.

- [ ] **Step 4: Verify GREEN and format**

Run focused pytest and scoped Ruff checks.

- [ ] **Step 5: Commit**

```text
git commit -m "feat: add bounded legacy OriginSet refresh cache"
```

### Task 3: Documentation and anti-drift reconciliation

**Files:**

- Modify: `docs/architecture/legacy-compatibility-profile.md`
- Modify: `docs/protocol/resource-timeout-profile.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`
- Modify: `tests/test_standards_reuse_documentation.py`
- Modify: `tests/test_v36_documentation.py`

**Interfaces:**

- Documents the approved outage policy and prototype-only values.
- Preserves the pending production timeout/resource decision gate.

- [ ] **Step 1: Write failing documentation assertions**

Assert that documentation contains bounded last-known-good, 300-second
prototype grace, temporary-only use, authenticated-negative/DNSSEC-bogus hard
failure, no direct fallback, and non-normative production status.

- [ ] **Step 2: Verify RED**

Run the two focused documentation test modules and confirm the new assertions
fail against the unresolved text.

- [ ] **Step 3: Update documentation**

Replace the unresolved last-known-good wording with the approved Phase D
profile. Mark Phase D implemented for review while keeping production values,
relay integration, Web PKI, active health checking, native publication, and
WP3 gated.

- [ ] **Step 4: Verify GREEN**

Run focused documentation tests and `git diff --check`.

- [ ] **Step 5: Commit**

```text
git commit -m "docs: record bounded legacy origin refresh policy"
```

### Task 4: Final verification

**Files:** No production changes expected.

- [ ] Run focused legacy-origin and documentation tests.
- [ ] Run frozen registry, state, CBOR, model, and schema tests.
- [ ] Run full pytest with an isolated base temp and cache provider disabled.
- [ ] Run scoped Ruff check and Ruff format check.
- [ ] Run `python -m pip check`.
- [ ] Run `git diff --check`.
- [ ] Confirm the current branch is not `main`, unrelated untracked files are
  untouched, and no Core v0.1 production file changed.
- [ ] Stop for human review before `NameRelay` integration or WP3.
