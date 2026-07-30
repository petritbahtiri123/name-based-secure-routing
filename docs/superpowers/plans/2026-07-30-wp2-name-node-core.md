# WP2A Name Node Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded lab-grade NBSR Name Node core that verifies signed
local service state, converts configured legacy reachability into internal
state, returns only stable Synthetic IP addresses, and prepares immutable
RouteIntent bindings without starting WP3.

**Architecture:** Add four isolated flat modules following the repository's
current Python layout: a signed registry, a resolution-context store, the Name
Node orchestrator, and a DNS/lab-server adapter. Reuse the frozen
`nbsr.protocol` API, `SyntheticAddressPool`, `LegacyOriginCache`, and `DnsStub`;
inject time, IDs, DNS snapshots, candidate validation, trust contexts, and
event sinks so tests never use public infrastructure.

**Tech Stack:** Python 3.12–3.13 target, dataclasses, `dnslib`, `cryptography`,
frozen `nbsr.protocol` Core v0.1, pytest, Hypothesis, Ruff.

## Global Constraints

- Implement only the approved
  `docs/superpowers/specs/2026-07-30-wp2-name-node-core-design.md`.
- Work on `codex/nbsr-v3-wp0-wp1`; do not merge to `main` or modify the Build
  Week submission branch.
- D1–D7, the 17 message codes, 19 error codes, state machines, six D6 schemas,
  deterministic CBOR, and COSE wrappers remain byte-for-byte unchanged.
- Add no numeric key, message code, error code, state, transition, critical
  extension, COSE wrapper, or Core v0.2 object.
- Every successful configured-name resolution returns only a Synthetic IP.
- Origin names, addresses, endpoint objects, DNS snapshots, raw Resolution
  Context IDs, keys, signatures, and reusable credentials never enter DNS
  answers, public result objects, normal events, or client-visible errors.
- An invalid configured NBSR record fails closed and never downgrades to legacy.
- DNS TTL, Derived OriginSet validity, SyntheticMapping lifetime, RouteIntent
  expiry, RouteGrant expiry, and transport lifetime remain separate.
- Use no public DNS, Azure/cloud resource, external service, or runtime relay
  integration in tests.
- Prototype bounds are: 1,024 signed records, 1,024 resolution bindings,
  32 legacy endpoints, 300-second RouteIntent maximum, 300-second accepted
  legacy DNS TTL/grace, and 60-second client DNS TTL.
- Production Synthetic IP prefixes, recursive resolver/DNSSEC integration,
  Web PKI origin validation, HA persistence, native OriginSet, WP3 transport,
  and platform interception remain human gates.
- Use TDD: write one failing behavioral test, observe the expected failure,
  implement the minimum, and rerun focused tests before each commit.
- Preserve unrelated untracked files and do not push without explicit
  instruction.

---

### Task 1: Add the signed local ServiceRecord registry

**Files:**

- Create: `nbsr/name_registry.py`
- Create: `tests/test_name_registry.py`

**Interfaces:**

- Consumes:
  `verify_sign1(message, keys, ErrorCode.NBSR_E_RECORD_UNTRUSTED)`,
  `require_kid`, `decode_service_record`, `decode_revocation`,
  `ServiceRecord.require_valid_at`, `ServiceRecord.require_newer_than`,
  `Revocation.require_valid_at`, and
  `Revocation.require_newer_generation`.
- Produces:
  `SignedServiceRegistry.install_record(cose_sign1: bytes, *, now: int) ->
  ServiceRecord`,
  `SignedServiceRegistry.apply_revocation(cose_sign1: bytes, *, now: int) ->
  Revocation`, and
  `SignedServiceRegistry.resolve(canonical_name: str, *, now: int) ->
  ServiceRecord | None`.

- [ ] **Step 1: Write failing acceptance and atomicity tests**

Add tests using deterministic Ed25519 keys and real WP1 COSE/schema code:

```python
def test_registry_accepts_valid_owner_bound_record_atomically() -> None:
    registry = registry_with_trust()
    record = service_record(sequence=7)
    message = sign1(encode_model(record), record.owner_key_id, OWNER_KEY)

    accepted = registry.install_record(message, now=record.not_before)

    assert accepted == record
    assert registry.resolve(record.canonical_name, now=record.not_before) == record


def test_failed_replacement_preserves_last_accepted_record() -> None:
    registry = registry_with_trust()
    first = install_record(registry, sequence=7)
    stale = signed_record(sequence=7)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.install_record(stale, now=first.not_before)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE
    assert registry.resolve(first.canonical_name, now=first.not_before) == first
```

Cover wrong signature, unknown `kid`, payload/`kid` mismatch, expired/not-yet
valid records, noncanonical names, lower/same sequence, duplicate name at
capacity, and no mutation after failure.

- [ ] **Step 2: Run the registry acceptance tests and verify RED**

Run:

```bash
python -m pytest tests/test_name_registry.py -q
```

Expected: collection fails because `nbsr.name_registry` does not exist.

- [ ] **Step 3: Implement bounded signed-record installation**

Create:

```python
class SignedServiceRegistry:
    def __init__(
        self,
        record_keys: Mapping[bytes, Ed25519PublicKey],
        revocation_keys: Mapping[bytes, Ed25519PublicKey],
        *,
        max_records: int = 1_024,
    ) -> None:
        ...
```

Copy both trust mappings, require opaque byte-string keys of length 1–64,
require typed Ed25519 public keys, and reject `max_records` outside
`1..1_000_000`. Keep:

```python
self._records: dict[str, ServiceRecord]
self._record_sequences: dict[str, int]
self._revocation_generations: dict[bytes, int]
self._revocations: dict[str, Revocation]
```

`install_record` must verify COSE, decode the attached payload, enforce
`owner_key_id`/`kid`, call `require_valid_at(now)`, compare against the
persistent per-name sequence tombstone, check capacity, and only then replace
the record and sequence atomically.

- [ ] **Step 4: Run acceptance tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_name_registry.py -q -k "record or replacement or capacity"
```

Expected: all selected tests pass.

- [ ] **Step 5: Write failing revocation and tombstone tests**

Add:

```python
def test_broad_revocation_blocks_higher_record_sequence_while_active() -> None:
    registry = registry_with_trust()
    record = install_record(registry, sequence=7)
    apply_service_revocation(registry, record, generation=3, target_sequence=None)
    install_record(registry, sequence=8)

    with pytest.raises(ProtocolViolation) as rejected:
        registry.resolve(record.canonical_name, now=record.not_before + 1)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_REVOKED


def test_revocation_generation_tombstone_rejects_replay_after_expiry() -> None:
    registry = registry_with_trust()
    record = install_record(registry, sequence=7)
    apply_expiring_revocation(registry, record, generation=3)

    with pytest.raises(ProtocolViolation) as rejected:
        apply_expiring_revocation(registry, record, generation=2)

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_STALE
```

Also test exact-sequence revocation, wrong target digest, wrong target type,
issuer `kid` mismatch, key-compromise no-expiry validation, and atomic failure.

- [ ] **Step 6: Implement fail-closed ServiceRecord revocation**

Hash the canonical-name ASCII bytes with SHA-256 for the ServiceRecord target
ID. Accept only `RevocationTargetType.SERVICE_RECORD` in this registry. Verify
the revocation wrapper and issuer `kid`, validity and higher issuer generation
before state change.

Store the highest generation even after revocation expiry. A present
`target_sequence` blocks only that sequence. An absent `target_sequence`
blocks every sequence while active. `resolve` returns `None` only for an
unconfigured name; an invalid, expired, or revoked configured record raises
its specific frozen `ProtocolViolation`.

- [ ] **Step 7: Run all registry tests and commit**

Run:

```bash
python -m pytest tests/test_name_registry.py -q
python -m ruff check nbsr/name_registry.py tests/test_name_registry.py
python -m ruff format --check nbsr/name_registry.py tests/test_name_registry.py
```

Expected: all commands exit 0.

Commit:

```bash
git add nbsr/name_registry.py tests/test_name_registry.py
git commit -m "feat(wp2): add signed local service registry"
```

---

### Task 2: Add bounded Resolution Context and RouteIntent state

**Files:**

- Create: `nbsr/resolution_state.py`
- Create: `tests/test_resolution_state.py`

**Interfaces:**

- Consumes: immutable `SyntheticMapping`, `RouteIntent`, and
  `DerivedOriginSet`.
- Produces:
  `NameClassification`, `ResolutionBinding`,
  `ResolutionContextStore.commit(binding: ResolutionBinding, *, now: int) ->
  None`, and
  `ResolutionContextStore.lookup(synthetic_address: str, *, now: int) ->
  ResolutionBinding | None`.

- [ ] **Step 1: Write failing immutable-state tests**

Use literal, independently constructed expected values:

```python
def test_store_commits_one_binding_under_both_synthetic_addresses() -> None:
    binding = resolution_binding()
    store = ResolutionContextStore(max_entries=2)

    store.commit(binding, now=100)

    assert store.lookup(binding.mapping.ipv4, now=100) == binding
    assert store.lookup(binding.mapping.ipv6, now=100) == binding


def test_expiry_removes_both_reverse_entries_atomically() -> None:
    binding = resolution_binding(expires_at=101)
    store = ResolutionContextStore(max_entries=2)
    store.commit(binding, now=100)

    assert store.lookup(binding.mapping.ipv4, now=101) is None
    assert store.lookup(binding.mapping.ipv6, now=101) is None
```

Cover exact 32-byte raw Resolution Context ID, digest equality with
`route_intent.resolution_context_digest`, mapping/intent canonical-name match,
expiry bounded by both mapping and RouteIntent, conflicting live addresses,
same-name atomic replacement, invalid originset service/generation binding,
capacity, booleans-as-times, and mutable input rejection.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/test_resolution_state.py -q
```

Expected: collection fails because `nbsr.resolution_state` does not exist.

- [ ] **Step 3: Implement immutable binding validation**

Create:

```python
class NameClassification(StrEnum):
    NBSR_SERVICE = "nbsr-service"
    LEGACY_SERVICE = "legacy-service"


@dataclass(frozen=True, slots=True)
class ResolutionBinding:
    mapping: SyntheticMapping
    route_intent: RouteIntent
    classification: NameClassification
    originset: DerivedOriginSet | None
    resolution_context_id: bytes = field(repr=False)
    expires_at: int
```

Validate exact types, 32-byte context ID, SHA-256 digest match, canonical name,
service ID, record generation, and expiry. Require `originset is None` for
`NBSR_SERVICE`; require a matching `DerivedOriginSet` for `LEGACY_SERVICE`.

- [ ] **Step 4: Implement bounded atomic store**

Use one `RLock`, a by-name dictionary, and a by-address dictionary. Store at
most `max_entries`; never evict accepted live security state to make room.
Allow replacement only when the canonical name and synthetic pair remain the
same. Expire both address entries and the name entry in one locked operation.
Map invalid/capacity state to
`ProtocolViolation(ErrorCode.NBSR_E_HANDLE_EXHAUSTED)` only for capacity;
profile conflicts use `NBSR_E_PROFILE_UNSUPPORTED`.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
python -m pytest tests/test_resolution_state.py -q
python -m ruff check nbsr/resolution_state.py tests/test_resolution_state.py
python -m ruff format --check nbsr/resolution_state.py tests/test_resolution_state.py
```

Expected: all commands exit 0.

Commit:

```bash
git add nbsr/resolution_state.py tests/test_resolution_state.py
git commit -m "feat(wp2): add bounded resolution context state"
```

---

### Task 3: Implement the injected Name Node resolution core

**Files:**

- Create: `nbsr/name_node.py`
- Create: `tests/test_name_node.py`

**Interfaces:**

- Consumes: `SignedServiceRegistry`, `LegacyOriginCache`,
  `LegacyOriginRequest`, `LegacyDnsSnapshot`, `CandidateValidator`,
  `SyntheticAddressPool`, `ResolutionContextStore`, and frozen RouteIntent.
- Produces: `NbsrServicePolicy`, `LegacyServicePolicy`, `NameResolution`, and
  `NameNode.resolve(presentation_name: str, *, now: int) -> NameResolution`.

- [ ] **Step 1: Write failing policy-validation tests**

Add table-driven tests proving that policy objects reject noncanonical names,
IP-literal names, invalid textual IDs, booleans as generations/ports, duplicate
or unsorted sets, policy hashes not exactly 32 bytes, disallowed networks,
and legacy origin names absent from explicit local policy.

Use these exact shapes:

```python
@dataclass(frozen=True, slots=True)
class NbsrServicePolicy:
    canonical_name: str
    source_operator_id: str
    source_edge_id: str
    policy_hash: bytes


@dataclass(frozen=True, slots=True)
class LegacyServicePolicy:
    canonical_name: str
    service_id: str
    service_record_generation: int
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_set: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    policy_hash: bytes
    issuer_id: bytes
    origin_name: str
    allowed_networks: tuple[str, ...]
```

- [ ] **Step 2: Run policy tests and verify RED**

Run:

```bash
python -m pytest tests/test_name_node.py -q -k policy
```

Expected: collection fails because `nbsr.name_node` does not exist.

- [ ] **Step 3: Implement immutable policy and result types**

Create `NameResolution` with only:

```python
@dataclass(frozen=True, slots=True)
class NameResolution:
    classification: NameClassification
    canonical_name: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    route_id: bytes
    expires_at: int
```

Validate result addresses are exactly the mapping's configured synthetic
addresses. Do not add an OriginSet, origin name/address, record payload,
Resolution Context ID, lease ID, signature, or trust metadata.

- [ ] **Step 4: Write failing NBSR resolution tests**

```python
def test_valid_signed_name_returns_only_stable_synthetic_state() -> None:
    node = configured_node_with_signed_record()

    first = node.resolve("api.example", now=100)
    second = node.resolve("api.example", now=101)

    assert first.synthetic_ipv4 == second.synthetic_ipv4
    assert first.synthetic_ipv6 == second.synthetic_ipv6
    assert first.classification is NameClassification.NBSR_SERVICE
    assert not hasattr(first, "originset")
    assert not hasattr(first, "origin_address")


@pytest.mark.parametrize("failure", ("bad_signature", "stale", "revoked"))
def test_invalid_configured_nbsr_name_never_downgrades_to_legacy(failure: str) -> None:
    legacy_provider = CountingLegacyProvider()
    node = configured_invalid_nbsr_node(failure, legacy_provider)

    with pytest.raises(ProtocolViolation):
        node.resolve("api.example", now=100)

    assert legacy_provider.calls == 0
```

Also assert the RouteIntent fields, raw context digest, distinct route/lease
IDs, 300-second maximum, and atomic binding.

- [ ] **Step 5: Implement the NBSR classification path**

The constructor receives:

```python
def __init__(
    self,
    registry: SignedServiceRegistry,
    nbsr_policies: tuple[NbsrServicePolicy, ...],
    legacy_policies: tuple[LegacyServicePolicy, ...],
    snapshot_provider: LegacySnapshotProvider,
    candidate_validator: CandidateValidator,
    legacy_cache: LegacyOriginCache,
    synthetic_pool: SyntheticAddressPool,
    context_store: ResolutionContextStore,
    id_source: Callable[[int], bytes],
    *,
    route_intent_lifetime_seconds: int = 300,
) -> None:
```

Copy and uniquely index both policy sets. Reject overlap between NBSR and
legacy names. Use one `RLock` around ID generation, RouteIntent creation,
mapping allocation, and binding commit.

For an NBSR policy, require `registry.resolve`; a missing configured record is
`NBSR_E_RECORD_UNTRUSTED`, not a legacy fallback. Generate context/route/lease
IDs with requested lengths 32/16/16 and reject wrong or repeated values. Set
RouteIntent expiry to
`min(record.not_after, now + route_intent_lifetime_seconds)`.

- [ ] **Step 6: Write failing legacy resolution and refresh tests**

```python
def test_legacy_refresh_changes_internal_originset_not_synthetic_mapping() -> None:
    node, provider, store = configured_legacy_node()
    first = node.resolve("legacy.example", now=100)
    first_binding = store.lookup(first.synthetic_ipv4, now=100)
    provider.set_snapshot(second_snapshot(observed_at=101))

    second = node.resolve("legacy.example", now=101)
    second_binding = store.lookup(second.synthetic_ipv4, now=101)

    assert second.synthetic_ipv4 == first.synthetic_ipv4
    assert second.synthetic_ipv6 == first.synthetic_ipv6
    assert second_binding.originset.content_digest != first_binding.originset.content_digest
```

Cover temporary failure within grace, failure after grace, authenticated
negative, DNSSEC bogus/downgrade, policy denial, equivocation, pool exhaustion,
store capacity, and unknown name. Assert no direct origin fallback in every
failure.

- [ ] **Step 7: Implement legacy path and stable mapping**

Convert `LegacyServicePolicy` into `LegacyOriginRequest`, call only the
injected snapshot provider, then call `legacy_cache.apply_snapshot`. Bind the
accepted `LegacyOriginView.originset` internally. Set RouteIntent sequence from
`service_record_generation`; use the explicit policy hash and destination
fields.

Map:

- unknown name to `NBSR_E_NAME_NOT_FOUND`;
- legacy unavailable to `NBSR_E_ORIGIN_UNAVAILABLE`;
- synthetic or context capacity to `NBSR_E_HANDLE_EXHAUSTED`;
- validation/profile failures to `NBSR_E_PROFILE_UNSUPPORTED`;
- unexpected failures to non-sensitive `NBSR_E_INTERNAL`.

Do not include exception causes in public messages.

- [ ] **Step 8: Run all Name Node tests and commit**

Run:

```bash
python -m pytest tests/test_name_node.py tests/test_name_registry.py tests/test_resolution_state.py -q
python -m ruff check nbsr/name_node.py tests/test_name_node.py
python -m ruff format --check nbsr/name_node.py tests/test_name_node.py
```

Expected: all commands exit 0.

Commit:

```bash
git add nbsr/name_node.py tests/test_name_node.py
git commit -m "feat(wp2): add synthetic-only Name Node core"
```

---

### Task 4: Connect the DNS-compatible response boundary

**Files:**

- Create: `nbsr/name_node_dns.py`
- Create: `tests/test_name_node_dns.py`
- Modify: `nbsr/dns_stub.py`
- Modify: `tests/test_dns_stub.py`

**Interfaces:**

- Consumes: `NameNode.resolve`, `NameResolution`, `ClientRoute`, `RouteTable`,
  and `DnsStub`.
- Produces:
  `NameNodeDnsAdapter.__call__(canonical_name: str) -> ClientRoute` and precise
  DNS RCODE mapping.

- [ ] **Step 1: Write failing adapter privacy tests**

```python
def test_adapter_exposes_only_synthetic_client_route() -> None:
    resolution = name_resolution()
    adapter = NameNodeDnsAdapter(FakeNameNode(resolution), now=lambda: 100)

    route = adapter("api.example")

    assert route.synthetic_ipv4 == resolution.synthetic_ipv4
    assert route.synthetic_ipv6 == resolution.synthetic_ipv6
    assert route.route_binding == resolution.route_id.hex()
    assert "origin" not in vars(route)
```

Assert `expires_in` is clamped to `1..60` and never derives from DNS TTL or
OriginSet validity.

- [ ] **Step 2: Run adapter tests and verify RED**

Run:

```bash
python -m pytest tests/test_name_node_dns.py -q
```

Expected: collection fails because `nbsr.name_node_dns` does not exist.

- [ ] **Step 3: Implement the callable adapter**

The adapter accepts a `NameNode`-compatible object and injected integer clock.
It converts only the six `NameResolution` fields to `ClientRoute`, using
`max(1, min(60, resolution.expires_at - now()))`.

- [ ] **Step 4: Write failing DNS RCODE tests**

Add tests proving:

- `NBSR_E_NAME_NOT_FOUND` becomes NXDOMAIN;
- every other `ProtocolViolation` becomes SERVFAIL;
- malformed packets remain FORMERR;
- unsupported questions remain NOTIMP;
- A and AAAA answers contain only configured synthetic prefixes; and
- exceptions containing documentation-only origin literals do not place those
  literals in response bytes.

- [ ] **Step 5: Implement narrow RCODE mapping**

Modify only the `DnsStub.resolve_query` exception boundary:

```python
except ProtocolViolation as exc:
    code = RCODE.NXDOMAIN if exc.code is ErrorCode.NBSR_E_NAME_NOT_FOUND else RCODE.SERVFAIL
    return self._reply_with_error(request, code)
except Exception:
    return self._reply_with_error(request, RCODE.SERVFAIL)
```

Do not serialize exception text.

- [ ] **Step 6: Run DNS tests and commit**

Run:

```bash
python -m pytest tests/test_name_node_dns.py tests/test_dns_stub.py -q
python -m ruff check nbsr/name_node_dns.py nbsr/dns_stub.py tests/test_name_node_dns.py tests/test_dns_stub.py
python -m ruff format --check nbsr/name_node_dns.py nbsr/dns_stub.py tests/test_name_node_dns.py tests/test_dns_stub.py
```

Expected: all commands exit 0.

Commit:

```bash
git add nbsr/name_node_dns.py nbsr/dns_stub.py tests/test_name_node_dns.py tests/test_dns_stub.py
git commit -m "feat(wp2): connect Name Node DNS boundary"
```

---

### Task 5: Add privacy-safe events and bounded lab UDP/TCP DNS

**Files:**

- Create: `nbsr/name_node_observability.py`
- Create: `nbsr/name_node_server.py`
- Create: `tests/test_name_node_observability.py`
- Create: `tests/test_name_node_server.py`
- Modify: `nbsr/name_node.py`

**Interfaces:**

- Consumes: `DnsStub.resolve_query` and Name Node success/failure outcomes.
- Produces:
  `NameNodeEvent`, `BoundedNameNodeMetrics`, and
  `NameNodeLabServer.start() / close()`.

- [ ] **Step 1: Write failing event allowlist tests**

Define an exact event contract:

```python
@dataclass(frozen=True, slots=True)
class NameNodeEvent:
    event_kind: str
    classification: NameClassification | None
    error_code: ErrorCode | None
    service_audit_id: str
    duration_bucket_ms: int
    capacity_bucket: str
```

Tests must inspect `vars(event)` or dataclass fields and prove the absence of
raw name, origin, endpoint, route/lease/context ID, key, signature, payload,
DNS answer, and exception-text fields. `service_audit_id` is the first 16
lowercase hexadecimal characters of HMAC-SHA-256 with an injected audit key
and canonical name. Plain SHA-256 is not accepted.

- [ ] **Step 2: Implement typed events and bounded counters**

`BoundedNameNodeMetrics` stores only aggregate integer counters for result
class and fixed latency/capacity buckets. It exposes an immutable snapshot,
rejects unknown labels, and has no logging backend or retention behavior.
Inject an event sink into `NameNode`; a sink failure must not change the
resolution result and must not receive internal objects.

- [ ] **Step 3: Write failing loopback server tests**

Use OS-assigned loopback ports and real UDP/TCP sockets:

```python
def test_udp_and_tcp_return_equivalent_synthetic_answers() -> None:
    with running_lab_server(dns_stub()) as server:
        udp = query_udp(server.udp_address, a_query("api.example"))
        tcp = query_tcp(server.tcp_address, a_query("api.example"))

    assert DNSRecord.parse(udp).rr == DNSRecord.parse(tcp).rr
    assert answer_address(udp).startswith("127.")
```

Cover TCP two-byte length framing, truncated/oversized frames, request timeout,
worker capacity, non-loopback default rejection, start/close idempotency, and
Name Node availability without any tunnel process.

- [ ] **Step 4: Implement the lab server**

Use standard-library `socketserver.ThreadingUDPServer` and
`socketserver.ThreadingTCPServer` with:

- explicit loopback bind validation;
- maximum DNS frame size 4096 bytes;
- socket timeout 2 seconds;
- at most 32 concurrent requests enforced by a bounded semaphore;
- daemon worker threads for tests;
- one DNS request and response per TCP connection; and
- `close()` performing shutdown and server-close for both listeners.

The server calls only `DnsStub.resolve_query`; it performs no recursion,
origin connection, tunnel work, or cloud access.

- [ ] **Step 5: Run observability/server tests and commit**

Run:

```bash
python -m pytest tests/test_name_node_observability.py tests/test_name_node_server.py -q
python -m ruff check nbsr/name_node_observability.py nbsr/name_node_server.py nbsr/name_node.py tests/test_name_node_observability.py tests/test_name_node_server.py
python -m ruff format --check nbsr/name_node_observability.py nbsr/name_node_server.py nbsr/name_node.py tests/test_name_node_observability.py tests/test_name_node_server.py
```

Expected: all commands exit 0 and use loopback only.

Commit:

```bash
git add nbsr/name_node_observability.py nbsr/name_node_server.py nbsr/name_node.py tests/test_name_node_observability.py tests/test_name_node_server.py
git commit -m "feat(wp2): add bounded Name Node lab service"
```

---

### Task 6: Freeze WP2A conformance and observed status

**Files:**

- Create: `docs/protocol/wp2a-name-node-core.md`
- Create: `tests/test_wp2a_name_node_documentation.py`
- Modify: `docs/protocol/status.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

**Interfaces:**

- Consumes all Task 1–5 public internal interfaces and test evidence.
- Produces the reviewed WP2A capability boundary and explicit remaining human
  gates.

- [ ] **Step 1: Write failing documentation anti-drift tests**

Require the final document to state:

```python
def test_wp2a_document_freezes_security_boundary_without_wire_drift() -> None:
    text = WP2A.read_text(encoding="utf-8")
    for required in (
        "Synthetic IP for every successful resolution",
        "origin endpoints remain internal",
        "invalid NBSR state never downgrades to legacy",
        "DNS TTL is not RouteIntent or RouteGrant lifetime",
        "17 message codes remain unchanged",
        "19 error codes remain unchanged",
        "D1-D7 remain unchanged",
        "WP3 remains gated",
    ):
        assert required in text
```

Also assert status does not claim real recursion, production DNSSEC/Web PKI,
native OriginSet, WP3, federation, HA, or production readiness.

- [ ] **Step 2: Run documentation tests and verify RED**

Run:

```bash
python -m pytest tests/test_wp2a_name_node_documentation.py -q
```

Expected: FAIL because the WP2A final document does not exist.

- [ ] **Step 3: Run focused security and conformance suites**

Run:

```bash
python -m pytest \
  tests/test_name_registry.py \
  tests/test_resolution_state.py \
  tests/test_name_node.py \
  tests/test_name_node_dns.py \
  tests/test_name_node_observability.py \
  tests/test_name_node_server.py \
  tests/test_legacy_origin.py \
  tests/test_originset.py \
  tests/test_synthetic.py \
  tests/test_dns_stub.py -q
```

Expected: every test passes with no public network.

- [ ] **Step 4: Add bounded property and stateful scenarios**

Create deterministic Hypothesis tests in `tests/test_name_node.py` with 300
examples for:

- valid configured names always returning a synthetic pair;
- random invalid signed messages producing only `ProtocolViolation`;
- arbitrary record sequence/update order never decreasing tombstones;
- accepted legacy refresh preserving the synthetic pair; and
- arbitrary failure ordering never exposing origin data or returning a direct
  address.

Use:

```python
@settings(max_examples=300, deadline=None, derandomize=True)
```

- [ ] **Step 5: Run full available verification**

Run:

```bash
python -m pytest -q --basetemp=.wp2a-pytest
python -m ruff check . \
  --exclude .codex-test-temp-w4 \
  --exclude .superpowers \
  --exclude docs/leakguard_phase19_qa_pack
python -m ruff format --check . \
  --exclude .codex-test-temp-w4 \
  --exclude .superpowers \
  --exclude docs/leakguard_phase19_qa_pack
python -m pip check
opa test policy -v
docker compose config --quiet
python tools/generate_core_v01_vectors.py --check
python scripts/generate_core_v02_vectors.py --check vectors/core-v0.2
git diff --check
```

Record exact pass/skip/warning counts only after these commands complete.
Delete only the verified absolute `.wp2a-pytest` directory created by this
task.

- [ ] **Step 6: Scan for origin, secret, and frozen-wire leakage**

Run:

```bash
rg -n \
  'origin_(ip|address)|PRIVATE KEY|Bearer ' \
  nbsr/name_registry.py \
  nbsr/resolution_state.py \
  nbsr/name_node.py \
  nbsr/name_node_dns.py \
  nbsr/name_node_observability.py \
  nbsr/name_node_server.py \
  docs/protocol/wp2a-name-node-core.md
python -m pytest tests/protocol/test_registry.py \
  tests/protocol/test_schemas.py \
  tests/protocol/test_states.py \
  tests/protocol/test_vectors.py -q
```

Expected: the source/document scan has no matches; frozen protocol tests pass
without changes to their expected mappings.

- [ ] **Step 7: Write evidence-based final documentation**

Document:

- lab-grade signed registry and Name Node core;
- exact synthetic-only success path;
- internal-only legacy Derived OriginSet consumption;
- RouteIntent/Resolution Context binding;
- UDP/TCP loopback evidence;
- privacy-safe event contract;
- observed test counts and environment;
- no runtime relay, public recursion, DNSSEC library, Web PKI validation,
  native OriginSet, WP3, HA, federation, or production claim; and
- the next human approval gate.

Mark only proven rows `Implemented`. Keep full WP2 production and WP3
`Planned` or `Partial`.

- [ ] **Step 8: Run documentation tests and commit**

Run:

```bash
python -m pytest tests/test_wp2a_name_node_documentation.py tests/test_documentation.py -q
git diff --check
```

Expected: all tests pass and diff check exits 0.

Commit:

```bash
git add \
  docs/protocol/wp2a-name-node-core.md \
  docs/protocol/status.md \
  docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md \
  tests/test_wp2a_name_node_documentation.py \
  tests/test_name_node.py
git commit -m "docs(wp2): record Name Node core evidence"
```

---

## Stop conditions

Stop implementation and request a new owner decision if:

- a task requires a new Core key/code/state/transition/extension/wrapper;
- signed record or revocation semantics conflict with D1–D7;
- legacy DNS data would mint service identity or authorization;
- an origin endpoint would enter a client-visible structure;
- stable synthetic mapping cannot be preserved;
- the real resolver requires choosing DNSSEC downgrade or Web PKI policy;
- production persistence, multi-replica state, or platform interception becomes
  necessary;
- a public-network test is required;
- a RouteGrant, tunnel, Service Channel, or WP3 runtime is required; or
- safe atomic state requires modifying unrelated prototype runtime.

## Self-review record

- **Spec coverage:** Tasks 1–2 cover signed state and bounded resolution
  context; Task 3 covers classification, RouteIntent, legacy conversion, and
  stable mapping; Task 4 covers DNS compatibility; Task 5 covers bounded lab
  service and observability; Task 6 covers conformance and documentation.
- **Reuse:** The plan reuses `nbsr.protocol`, `SyntheticAddressPool`,
  `LegacyOriginCache`, `DerivedOriginSet`, and `DnsStub`; it does not create a
  second CBOR, COSE, origin, synthetic, or DNS parser.
- **Type consistency:** IDs are raw 16-byte values, Resolution Context is 32
  raw bytes with a 32-byte digest, policy hashes are 32 bytes, time is integer
  Unix seconds, and collections are immutable tuples.
- **Wire impact:** none. All additions are internal Python models, local
  adapters, tests, and documentation.
- **Approval:** the owner-delegated approval applies to this exact plan and
  stop conditions. It does not authorize a broader WP2 or WP3 implementation.
