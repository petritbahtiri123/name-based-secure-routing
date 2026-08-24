# Production Go Client Tranche 6 Resolution Secure Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded resolution-provenance prefix from canonical NBSR name through local mapping and exact flow correlation into the existing verified authority/session/application-stream stack while returning one shared Synthetic IP.

**Architecture:** Canonical resolution derives `ServiceDigest` once, stores an immutable stdlib-only snapshot under monotonic `MappingID`, and admits a flow only after an approved adapter supplies a single-use local `FlowContext`. Mapping-owned values construct the existing AuthorityKey and RouteIntent; the existing RouteGrant, TS, SC, credit, and Application Stream path remains unchanged.

**Tech Stack:** Go 1.26.5 standard library for core state and resolution; existing production Go authority/session packages; platform adapter chosen by the required human gate; focused Go tests and existing Go-to-Rust interop harness.

**Spec:** `docs/architecture/production-go-client/tranche6-resolution-secure-routing.md`

## Global constraints

- The approved adapter is an explicit local proxy using SOCKS5 domain-name and HTTP CONNECT correlation. Transparent platform interception is excluded.
- Return one configured shared local Synthetic IP for every successful NBSR resolution; do not allocate per-service IPs or define a permanent protocol address.
- `ServiceDigest` is exactly SHA-256 of canonical-name ASCII bytes and never of `service_id`.
- MappingID, LocalFlowID, FlowContext, and ServiceHandle remain local-only.
- Do not modify RouteGrant, ACP, TS, SC, `channel_id`, Stream Credit, or Application Stream wire formats.
- Do not use IP+port, Host, SNI, last resolution, or mutable current-service state for generic service selection.
- Mapping and flow state are bounded, immutable, non-persistent, and fail closed.
- Use literal RED tests before implementation in every task. Stage only exact task paths; do not modify or push `main`.
- Each task receives one focused correctness/security review and one scoped re-review only if confirmed findings require fixes.

## File structure

- `internal/resolution/canonical.go`: canonical presentation-name validation and ServiceDigest derivation.
- `internal/resolution/context.go`: immutable validated production resolution result and conversion into corestate mapping input.
- `internal/resolution/flow.go`: bounded single-use adapter-to-core FlowContext ownership.
- `internal/resolution/router.go`: mapping acquisition and construction of existing authority/session inputs without an alternate authority path.
- `internal/corestate/types.go`, `mapping.go`, `limits.go`, `teardown.go`: immutable Mapping/RouteIntent snapshot, accounting, lifecycle, and invariants.
- `internal/adapter/adapter.go`: OS-neutral contract implemented by the human-approved adapter; no platform inference in core.
- `internal/adapter/proxy/`: bounded SOCKS5-domain and HTTP CONNECT parsing and correlation for explicitly proxy-configured applications.

---

### Task 1: Canonical resolution result and exact ServiceDigest derivation

**Goal:** Produce one immutable validated Go resolution result whose digest and service identity have signed-resolution provenance.

**Files:**
- Create: `client/nbsr-go-client/internal/resolution/canonical.go`
- Create: `client/nbsr-go-client/internal/resolution/context.go`
- Create: `client/nbsr-go-client/internal/resolution/canonical_test.go`
- Create: `client/nbsr-go-client/internal/resolution/context_test.go`
- Reuse: `nbsr/protocol/fields.py`, `nbsr/protocol/models.py`, `nbsr/name_node.py` as semantic evidence only
- Reuse unchanged: `client/nbsr-go-client/internal/authority/types.go` RouteIntent and validation

**Interfaces:**

```go
type CanonicalName string

func CanonicalizePresentationName(string) (CanonicalName, error)
func DigestCanonicalName(CanonicalName) corestate.ServiceDigest

type ResultInput struct {
    PresentationName string
    ServiceIdentity string
    Intent authority.RouteIntent
    RecordExpiresAt uint64
    SafetyExpiresAt uint64 // zero means no additional local ceiling
}

type Result struct {
    CanonicalName CanonicalName
    ServiceDigest corestate.ServiceDigest
    ServiceIdentity string
    Intent authority.RouteIntent
    ExpiresAtUnix uint64
}

func NewResult(ResultInput, now uint64) (Result, error)
```

`NewResult` derives rather than accepts `ServiceDigest`. It copies mutable RouteIntent bytes/slices, requires exact `ServiceIdentity` equality, validates RouteIntent canonical bytes/digest using an exported narrow authority validator or constructor, and selects the earliest nonzero authoritative expiry.

**Explicit bounds:** Canonical name ≤253 ASCII bytes; service identity uses the existing 64-byte protocol limit; RouteIntent canonical bytes and target-edge cardinality use existing authority limits; no cache or goroutine is created.

**TDD RED cases:**

- [ ] Add table tests for ASCII lowercase, mixed case, one trailing dot, Unicode IDNA conversion, empty/oversized/invalid labels, repeated dots, noncanonical punycode failure where applicable, and IPv4/IPv6 literal rejection.
- [ ] Add exact vectors proving `DigestCanonicalName("api.example") == sha256.Sum256([]byte("api.example"))` and proving hashing `service_id` gives a rejected mismatch.
- [ ] Add tests that `NewResult` rejects service-identity mismatch, malformed/zero RouteIntent digest, mutable-input aliasing, expired record/intent, and a safety ceiling that attempts to extend authority.
- [ ] Run `go test ./internal/resolution -run 'TestCanonical|TestDigest|TestNewResult' -count=1`; record literal RED caused by missing package/API.
- [ ] Implement the minimum canonicalizer, digest function, immutable copies, and narrow authority validation entrypoint.
- [ ] Re-run the focused command and require PASS.
- [ ] Run `go test ./internal/authority ./internal/resolution -count=1`; require PASS.
- [ ] Inspect the diff for accidental Unicode normalization beyond existing IDNA rules, digest inputs other than canonical ASCII, or authority duplication.

**Security-sensitive boundaries:** IDNA/canonical-name equivalence, immutable RouteIntent bytes, service-id distinction, expiry minimum, zero digest rejection.

**Completion criteria:** All required canonicalization vectors pass; there is one derivation function; callers cannot supply an independent digest; no runtime source outside authority validation and the new resolution package changes.

**MUST NOT implement:** DNS listener, cache, synthetic-address allocation, flow correlation, authority acquisition, persistence, wire fields, or Python class ports.

---

### Task 2: Bounded immutable MappingTable and FlowContext core

**Goal:** Extend existing bounded corestate ownership so each MappingID retains exact resolution provenance and each adapter-supplied local flow correlation is bounded and single-use.

**Files:**
- Modify: `client/nbsr-go-client/internal/corestate/types.go`
- Modify: `client/nbsr-go-client/internal/corestate/limits.go`
- Modify: `client/nbsr-go-client/internal/corestate/mapping.go`
- Modify: `client/nbsr-go-client/internal/corestate/teardown.go`
- Modify: `client/nbsr-go-client/internal/corestate/mapping_test.go`
- Modify: `client/nbsr-go-client/internal/corestate/limits_test.go`
- Modify: `client/nbsr-go-client/internal/corestate/teardown_test.go`
- Modify: `client/nbsr-go-client/internal/corestate/fuzz_test.go`
- Create: `client/nbsr-go-client/internal/resolution/flow.go`
- Create: `client/nbsr-go-client/internal/resolution/flow_test.go`
- Modify: `client/nbsr-go-client/internal/resolution/context.go`

**Interfaces:**

```go
type RouteIntentSnapshot struct {
    Canonical []byte
    Digest [32]byte
    SourceOperator, SourceEdge, TargetOperator string
    TargetEdges []string
    Transport string
    Port uint16
    RecordSequence uint64
    PolicyHash [32]byte
    RouteID, LeaseID [16]byte
    ExpiresAt uint64
}

type MappingSpec struct {
    CanonicalName string
    ServiceIdentity string
    ServiceDigest ServiceDigest
    RouteIntent RouteIntentSnapshot
    ExpiresAtUnix uint64
    PolicyContext PolicyContext
}

type FlowContext struct {
    MappingID corestate.MappingID
    LocalFlowID corestate.LocalFlowID
}

type FlowStore interface {
    Bind(FlowContext) error
    Consume(corestate.LocalFlowID) (corestate.MappingID, error)
    Remove(corestate.LocalFlowID) error
    Close() error
}
```

`Result.MappingSpec()` is the only production constructor path. `FlowStore.Consume` atomically removes the entry so a correlation cannot authorize two flows.

**Explicit bounds:** Existing `MaxMappings` and `MaxMappingBytes` remain mandatory; add canonical-name, RouteIntent-canonical, target-edge aggregate, and flow-context entry/byte limits. Account every owned byte including copied slices/strings. Active reference and ID counters retain overflow checks. No live mapping or flow correlation is evicted.

**TDD RED cases:**

- [ ] Extend mapping fixtures and add RED tests for missing/zero digest, digest not matching canonical name, service identity not matching RouteIntent input, effective expiry beyond RouteIntent expiry, mutable slice aliasing, and same-ID context mutation.
- [ ] Add exact below/equal/above tests for mapping entries, logical bytes, canonical bytes, edge bytes, flow entries, and flow bytes.
- [ ] Preserve and expand monotonic MappingID, no reuse, stale ID, overflow, duplicate insertion, expiry, referenced-expiry, concurrent acquire/release, and final removal tests.
- [ ] Add replacement tests: byte-identical concurrent input may coalesce only at the resolution owner; any changed canonical name, digest, service identity, or RouteIntent creates a new MappingID.
- [ ] Add flow tests for zero IDs, duplicate LocalFlowID, one consume only, unknown/removed/closed flow, bounded capacity, concurrent consume, no context crossover, and restart with an empty new store.
- [ ] Run `go test ./internal/corestate ./internal/resolution -run 'TestMapping|TestFlow|TestResolutionReplacement' -count=1`; record RED.
- [ ] Implement the minimum owned snapshots, accounting, validators, immutable copy functions, and bounded FlowStore.
- [ ] Re-run focused tests, then `go test ./internal/corestate ./internal/resolution -count=1`; require PASS.
- [ ] Run bounded fuzzing only at the existing corestate state-machine boundary and require invariants after every operation.
- [ ] Inspect for unbounded maps/slices, implicit eviction, persisted state, reference leaks, and partial mutation on rejection.

**Security-sensitive boundaries:** immutable context ownership, digest revalidation at insertion, exact expiry, atomic single-use flow consumption, reference cleanup, logical-byte arithmetic.

**Completion criteria:** MappingTable can recover all immutable authority inputs from MappingID; FlowStore returns only MappingID; bounds and teardown reconcile exactly; a newly constructed process has no prior mappings or correlations.

**MUST NOT implement:** shared-IP selection, Host/SNI inspection, RouteGrant storage, automatic refresh, live eviction, persistence, adapter goroutines, or session/stream changes.

---

### Task 3: Human-approved single-Synthetic-IP correlation adapter

**Goal:** Supply exactly one valid local FlowContext for each intercepted application flow to the one shared Synthetic IP without guessing from IP, port, recency, Host, or SNI.

**Approved choice:** Explicit local proxy using SOCKS5 domain-name and HTTP CONNECT correlation. This scope does not claim transparent support for applications that bypass configured proxy behavior.

**Common files independent of the choice:**
- Create: `client/nbsr-go-client/internal/adapter/adapter.go`
- Create: `client/nbsr-go-client/internal/adapter/adapter_test.go`
- Reuse: `client/nbsr-go-client/internal/resolution/flow.go`
- Reference only: `nbsr/dns_stub.py`, `nbsr/name_node_dns.py`, `nbsr/windows_agent.py`

**Common interface:**

```go
type CapturedFlow struct {
    Context resolution.FlowContext
    Transport string
    Port uint16
    Peer LocalPeer
    Downstream io.ReadWriteCloser
}

type FlowSource interface {
    Accept(context.Context) (CapturedFlow, error)
    Close() error
}
```

`FlowSource` must produce the context before the router selects authority. The shared Synthetic IP is validated adapter configuration and is absent from MappingSpec authority fields.

**Concrete files:**

- Create: `client/nbsr-go-client/internal/adapter/proxy/parser.go`
- Create: `client/nbsr-go-client/internal/adapter/proxy/server.go`
- Create: `client/nbsr-go-client/internal/adapter/proxy/parser_test.go`
- Create: `client/nbsr-go-client/internal/adapter/proxy/server_test.go`

**Explicit bounds:** Shared listener count, accepted connections, pending handshakes/correlations, per-peer work, bytes before correlation, timeouts, workers/goroutines, and FlowStore entries are all finite. Capacity is reserved before spawning work.

**Required RED cases:**

- [ ] Two services resolve concurrently to the identical shared IP and identical port 443; each flow receives its own exact MappingID.
- [ ] Reverse connection order and high concurrency do not cross contexts or implement last-resolution-wins.
- [ ] Missing, duplicate, stale, expired, already-consumed, or ambiguous correlation fails closed before authority lookup.
- [ ] Destination IP+port alone, Host, and SNI cannot select a mapping.
- [ ] Adapter failure never opens direct routing and never allocates a second Synthetic IP.
- [ ] Entry/byte/pending/worker capacity rejects deterministically without evicting live flows.
- [ ] Shutdown cancels pending work, closes listeners, removes unused correlations, and leaves active ownership to explicit teardown.
- [ ] Run the exact chosen package tests with `-count=1`, then `go test ./internal/adapter/... ./internal/resolution -count=1`; require PASS.

**Security-sensitive boundaries:** local peer attribution, correlation authenticity/integrity, proxy-protocol parsing if selected, bypass prevention within declared scope, pre-authority buffering, cancellation and resource release.

**Completion criteria:** The explicit proxy demonstrates exact same-IP/same-port multi-service correlation from SOCKS5 domain-name and HTTP CONNECT targets without Host/SNI or recency; its proxy-aware limitation is explicit; adversarial tests prove fail-closed behavior and bounded work.

**MUST NOT implement:** an unapproved adapter class, hostname inference from application payload, multiple synthetic IPs, direct fallback, kernel/driver work under an explicit-proxy approval, or new NBSR wire identifiers.

---

### Task 4: Mapping-owned authority/session/stream integration

**Goal:** Convert an acquired mapping into the existing RouteIntent/AuthorityKey path, then reuse verified authority, TS/SC, credits, and Application Streams with digest equality checks at every handoff.

**Files:**
- Create: `client/nbsr-go-client/internal/resolution/router.go`
- Create: `client/nbsr-go-client/internal/resolution/router_test.go`
- Modify: `client/nbsr-go-client/internal/session/manager_test.go` only for cross-boundary negative tests if existing public behavior is insufficient
- Modify: `client/nbsr-go-client/streamclient/streamclient.go` to accept mapping-owned routing input rather than unconstrained duplicate service fields
- Modify: `client/nbsr-go-client/streamclient/streamclient_test.go`
- Reuse unchanged unless a RED test proves a defect: `internal/authority`, `internal/session`, credit and Application Stream implementations

**Interfaces:**

```go
type Router struct {
    mappings corestate.MappingRegistry
    flows FlowStore
    authority AuthorityOwner
    sessions SessionOwner
}

func (r *Router) OpenFlow(context.Context, corestate.LocalFlowID) (*RoutedStream, error)
```

`OpenFlow` atomically consumes LocalFlowID, acquires MappingID, reconstructs the exact existing `authority.RouteIntent`, derives `AuthorityKey.ServiceDigest` only from the acquired mapping, obtains verified authority through the existing manager, selects/creates the existing TS/SC, verifies the SC snapshot digest, and opens the existing Application Stream. All failure paths release the mapping reference exactly once.

**Explicit bounds:** No new caches. Existing authority pending/cache, TS/SC, credit, stream, and mapping limits remain authoritative. Router pending opens have a finite configured cap and are included in logical state accounting.

**TDD RED cases:**

- [ ] Build a fake approved adapter and two same-IP/same-port mappings; prove each LocalFlowID reaches its expected RouteIntent, AuthorityKey and SC.
- [ ] Add negative mutations at resolution→mapping, mapping→AuthorityKey, signed RouteGrant→verified authority, verified authority→SC request, and SC snapshot→stream open. Each must fail before payload admission.
- [ ] Prove ServiceIdentity is copied from mapping-owned signed-resolution state and cannot be replaced by canonical name, digest text, or adapter input.
- [ ] Prove unverified provider bytes, zero/expired authority, stale authority generation, wrong TS proof, wrong channel ID/generation, exhausted credits, and rejected Application Stream cannot bypass existing gates.
- [ ] Prove transport/port come from the acquired RouteIntent and same-port unrelated services remain isolated.
- [ ] Prove cancellation and every partial failure release mapping references and pending capacity exactly once.
- [ ] Run `go test ./internal/resolution ./internal/authority ./internal/session ./streamclient -run 'TestRouter|TestResolutionDigestChain|TestServiceChannel' -count=1`; record RED.
- [ ] Implement only the mapping-owned conversion/orchestration; do not duplicate verifier or session state machines.
- [ ] Re-run focused and affected package tests; require PASS.
- [ ] Run the existing focused Go-to-Rust application-stream interoperability test with unchanged vectors and require PASS.
- [ ] Inspect the diff to prove no wire schema/codec/vector changed and no adapter field became authority.

**Security-sensitive boundaries:** authority input provenance, sealed verification, generation barriers, SC digest equality, credit/stream admission, payload quarantine, reference ownership.

**Completion criteria:** The complete digest chain is mechanically tested; only verified authority can create/reuse SC state; existing credit and stream code handles the flow; all failure paths are fail closed and leak free.

**MUST NOT implement:** alternate grant verification, RouteGrant/SC/credit/stream fields, MappingID transmission, direct origin path, application-payload parsing, or broad session refactoring.

---

### Task 5: Lifecycle, adversarial integration, and Tranche 6 closure

**Goal:** Prove the approved shared-IP architecture under replacement, expiry, concurrency, restart, teardown, and bounded overload, then publish precise nonclaims.

**Files:**
- Create: `client/nbsr-go-client/internal/resolution/integration_test.go`
- Create: `client/nbsr-go-client/internal/resolution/lifecycle_test.go`
- Add the concrete approved adapter integration test under its Task 3 package
- Modify: `docs/protocol/status.md`
- Modify: `docs/architecture/production-go-client/protocol-gap-register.md`
- Create after implementation evidence exists: `docs/protocol/tranche6-implementation-status.md`

**Interfaces:** Uses Task 1 `Result`, Task 2 mappings/FlowStore, Task 3 approved `FlowSource`, and Task 4 `Router.OpenFlow` without adding public wire interfaces.

**Explicit bounds:** Exercise exact configured mapping/flow/pending/worker limits and reconcile all usage counters to zero after teardown. Do not invent performance or production defaults from test fixtures.

**TDD RED and closure cases:**

- [ ] Resolve several services to the identical shared IP, including unrelated services on port 443, and open concurrent flows in a different order from resolution.
- [ ] Prove exact context recovery, no crossover, no last-resolution-wins, no IP+port selection, no Host/SNI dependency, and no direct fallback.
- [ ] Prove byte-identical resolution coalescing where owned by resolution, material replacement with a new MappingID, stale old ID rejection for new flow, and no mutation of referenced old context.
- [ ] At exact expiry, reject new acquisition while an existing reference and admitted stream remain correctly owned; remove bookkeeping after final release without replay/migration.
- [ ] Race resolution insertion, flow consume, mapping acquisition/removal, expiry, cancellation, release, and shutdown; require one terminal owner and exact accounting.
- [ ] Construct a fresh runtime and prove mappings, flow contexts, reverse indexes, and live correlations are empty; require fresh resolution.
- [ ] Fill mapping, mapping bytes, flow, pending correlation, authority pending, channel, credit, and stream limits; require deterministic typed failure and no live eviction.
- [ ] Run focused packages, then affected Go client packages in increasing scope. Use Windows race prerequisites when running `go test -race ./internal/resolution ./internal/corestate ./internal/adapter/...`.
- [ ] Run `go vet` only on affected packages, existing unchanged Go-to-Rust secure-stream integration, and targeted malformed/fuzz cases at parser/state boundaries.
- [ ] Inspect `git diff --check`, exact changed paths, frozen protocol paths, generated vectors, and worktree status.
- [ ] Perform one focused correctness/security review of changed files and the adapter→mapping→authority boundary; fix confirmed Critical/Important findings and perform one scoped re-review.
- [ ] Write status evidence with exact commands/counts and explicit lab/platform limits; do not claim generic transparency or production readiness.

**Security-sensitive boundaries:** concurrent expiry/acquisition, replacement isolation, restart emptiness, capacity reservation, adapter bypass, full provenance equality chain, teardown ownership.

**Completion criteria:** All required test categories pass with fresh counts; no frozen wire file changed; one shared IP supports simultaneous same-port services through exact approved correlation; bounded state reconciles; independent focused review has no unresolved Critical/Important finding; status records precise nonclaims.

**MUST NOT implement:** demo packaging, cleanup, Docker orchestration, unrelated observability hardening, additional platform adapters, durable mapping recovery, performance claims, protocol changes, merge, or push without separate instruction.

## Plan self-review gates

- Every approved decision is implemented or explicitly preserved by Tasks 1–5.
- Task 3 consistently uses the approved explicit SOCKS5/HTTP CONNECT proxy; no transparent adapter is implied.
- Type names and handoffs are consistent: `Result -> MappingSpec -> MappingID/FlowContext -> Router -> existing authority/session stack`.
- Required tests cover canonicalization, mapping, shared-IP correlation, pinning, lifecycle, secure routing, bounds, restart, and negative mismatch at every boundary.
- No task adds a wire field, per-service IP, Host/SNI selection, recency selection, persistence, demo packaging, or broad cleanup.
