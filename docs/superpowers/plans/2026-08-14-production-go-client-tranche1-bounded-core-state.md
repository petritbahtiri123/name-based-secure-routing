# Production Go Client Tranche 1 Bounded Core State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build deterministic, concurrency-safe, bounded in-memory state primitives for mappings, session-local services, and application streams without network, protocol, authority-provider, resolver, platform, or persistence behavior.

**Architecture:** Create an isolated production-client Go module at client/nbsr-go-client, separate from interop/nbsr-go-peer. Its internal/corestate package owns one mutex-protected Store, generation-scoped monotonic uint32 ServiceHandle allocators, and bounded mapping, service, and stream maps. Every mutation validates and checks entry plus logical-byte capacity in the same critical section as commit; no method performs I/O, starts goroutines, stores payload, or calls observers while locked.

**Tech Stack:** Go 1.26.5; standard library only; Go testing, race detector, vet, native fuzzing, and benchmarks.

## Global Constraints

- Work only on codex/nbsr-v3-wp0-wp1. Never modify, merge, rebase, or force-push main.
- Preserve main at 1938154d498b32d81a3564319969430644e8a688 and approved design 6127f12113b30c937be197ce40d7ba2648021660.
- Do not modify interop/nbsr-go-peer, verifiers/federation-go, Rust transport, protocol registries/vectors, or P1F/P2D evidence.
- ServiceHandle is uint32; zero is invalid; allocation is monotonic and never reuses a value within one TSGeneration. Overflow fails closed.
- Handles, MappingID, CreditStateRef, and digests are correlation/integrity data, never authority or bearer credentials.
- StreamID is opaque. Tranche 1 creates no QUIC connection and defines no wire representation.
- State is ephemeral. Define no serialization, file storage, restart restoration, authority, resolver, interception, proxy, rotation, or revocation-feed behavior.
- Every table requires explicit nonzero entry and logical-byte limits. Tranche 1 supplies no product defaults; tests use deliberately small limits.
- Logical accounting is conservative and deterministic, not an exact Go heap prediction.
- Never evict live state to admit new state. Exhaustion returns a typed local error without partial mutation.
- Use one sync.RWMutex owned by Store. Registries have no independent locks. No production goroutine, retry, deferred-cleanup queue, or callback-under-lock.
- Each task uses literal RED, minimal GREEN, focused regression, and its own commit.
- Benchmarks are BASELINE ONLY — NOT ACCEPTANCE CAPACITY.

---

## Planned production package structure

~~~text
client/nbsr-go-client/
├── go.mod
└── internal/corestate/
    ├── doc.go
    ├── types.go
    ├── errors.go
    ├── limits.go
    ├── observer.go
    ├── store.go
    ├── handle.go
    ├── mapping.go
    ├── service.go
    ├── stream.go
    ├── teardown.go
    ├── limits_test.go
    ├── handle_test.go
    ├── mapping_test.go
    ├── service_test.go
    ├── stream_test.go
    ├── teardown_test.go
    ├── fuzz_test.go
    └── benchmark_test.go
~~~

The module name is nbsr.local/client/nbsr-go-client, matching the repository convention of isolated Go modules while preventing benchmark-peer coupling. internal/corestate is available to future commands inside this production module only.

## Interfaces and types

~~~go
package corestate

type TSGeneration uint64
type ServiceHandle uint32
type MappingID uint64
type StreamID uint64
type LocalFlowID uint64
type AuthorityGeneration uint64
type CreditStateRef uint64
type ChannelID [16]byte
type ServiceDigest [32]byte
type RouteGrantDigest [32]byte
type PolicyContext string

const InvalidServiceHandle ServiceHandle = 0

type Limits struct {
    MaxGenerations, MaxMappings, MaxServices, MaxStreams int
    MaxMappingBytes, MaxServiceBytes, MaxStreamBytes uint64
    MaxServiceIdentityBytes, MaxPolicyContextBytes int
}
func (l Limits) Validate() error

type MappingSpec struct {
    ServiceIdentity string
    ExpiresAtUnix uint64
    PolicyContext PolicyContext
}
type MappingSnapshot struct {
    MappingSpec
    ID MappingID
    ActiveReferences uint64
    AccountedBytes uint64
}

type ServiceSpec struct {
    Generation TSGeneration
    ChannelID ChannelID
    ChannelGeneration uint64
    ServiceIdentity string
    ServiceDigest ServiceDigest
    RouteGrantDigest RouteGrantDigest
    AuthorityGeneration AuthorityGeneration
    CreditState CreditStateRef
}
type ServiceSnapshot struct {
    ServiceSpec
    Handle ServiceHandle
    State ServiceState
    ActiveStreams uint64
    AccountedBytes uint64
}

type StreamSpec struct {
    Generation TSGeneration
    Handle ServiceHandle
    StreamID StreamID
    LocalFlowID LocalFlowID
}
type StreamSnapshot struct {
    StreamSpec
    State StreamState
    TerminalReason TerminalReason
    AccountedBytes uint64
}

type Usage struct {
    Mappings, Services, Streams int
    MappingBytes, ServiceBytes, StreamBytes uint64
}

type Observer interface { Observe(Event) }
type Event struct {
    Kind EventKind
    Generation TSGeneration
    Handle ServiceHandle
    MappingID MappingID
    StreamID StreamID
}
type EventKind uint8
const (
    EventMappingInserted EventKind = iota + 1
    EventMappingRemoved
    EventServiceInserted
    EventServiceClosed
    EventServiceRemoved
    EventStreamInserted
    EventStreamTerminal
    EventStreamRemoved
    EventGenerationClosed
)

type Clock interface { NowUnix() uint64 }
type MappingRegistry interface {
    AddMapping(MappingSpec) (MappingSnapshot, error)
    LookupMapping(MappingID) (MappingSnapshot, error)
    AcquireMapping(MappingID) (MappingSnapshot, error)
    ReleaseMapping(MappingID) error
    RemoveMapping(MappingID) error
    ExpireMappings() (int, error)
}
type ServiceRegistry interface {
    AddService(ServiceSpec) (ServiceSnapshot, error)
    LookupService(TSGeneration, ServiceHandle) (ServiceSnapshot, error)
    CloseService(TSGeneration, ServiceHandle) error
    RemoveService(TSGeneration, ServiceHandle) error
}
type StreamRegistry interface {
    InsertStream(StreamSpec) error
    LookupStream(TSGeneration, ServiceHandle, StreamID) (StreamSnapshot, error)
    CancelStream(TSGeneration, ServiceHandle, StreamID) error
    FinishStream(TSGeneration, ServiceHandle, StreamID, TerminalReason) error
    RemoveStream(TSGeneration, ServiceHandle, StreamID) error
}

func NewStore(limits Limits, clock Clock, observer Observer) (*Store, error)
func (s *Store) OpenGeneration(generation TSGeneration) error
func (s *Store) CloseGeneration(generation TSGeneration) error
func (s *Store) AddMapping(spec MappingSpec) (MappingSnapshot, error)
func (s *Store) LookupMapping(id MappingID) (MappingSnapshot, error)
func (s *Store) AcquireMapping(id MappingID) (MappingSnapshot, error)
func (s *Store) ReleaseMapping(id MappingID) error
func (s *Store) RemoveMapping(id MappingID) error
func (s *Store) ExpireMappings() (int, error)
func (s *Store) AddService(spec ServiceSpec) (ServiceSnapshot, error)
func (s *Store) LookupService(generation TSGeneration, handle ServiceHandle) (ServiceSnapshot, error)
func (s *Store) CloseService(generation TSGeneration, handle ServiceHandle) error
func (s *Store) RemoveService(generation TSGeneration, handle ServiceHandle) error
func (s *Store) InsertStream(spec StreamSpec) error
func (s *Store) LookupStream(generation TSGeneration, handle ServiceHandle, streamID StreamID) (StreamSnapshot, error)
func (s *Store) CancelStream(generation TSGeneration, handle ServiceHandle, streamID StreamID) error
func (s *Store) FinishStream(generation TSGeneration, handle ServiceHandle, streamID StreamID, reason TerminalReason) error
func (s *Store) RemoveStream(generation TSGeneration, handle ServiceHandle, streamID StreamID) error
func (s *Store) Usage() Usage
func (s *Store) ValidateInvariants() error
~~~

Snapshots are values, never mutable pointers. Nil Observer installs a no-op observer. Mutations record a compact event while locked, unlock, then call Observe.

## Typed local error model

~~~go
type ErrorCode uint8
const (
    CodeInvalidHandle ErrorCode = iota + 1
    CodeUnknownMapping
    CodeExpiredMapping
    CodeMappingConflict
    CodeUnknownService
    CodeDuplicateService
    CodeDuplicateStream
    CodeCapacityExceeded
    CodeByteCapacityExceeded
    CodeGenerationClosed
    CodeServiceClosed
    CodeHandleExhausted
    CodeMappingIDExhausted
    CodeInvalidTransition
    CodeInvalidLimits
    CodeAccountingOverflow
)
type StateError struct { Code ErrorCode; Resource string }
func (e *StateError) Error() string
func (e *StateError) Is(target error) bool
~~~

Export sentinel values ErrInvalidHandle, ErrUnknownMapping, ErrExpiredMapping,
ErrMappingConflict, ErrUnknownService, ErrDuplicateService,
ErrDuplicateStream, ErrCapacityExceeded, ErrByteCapacityExceeded,
ErrGenerationClosed, ErrServiceClosed, ErrHandleExhausted,
ErrMappingIDExhausted, ErrInvalidTransition, ErrInvalidLimits, and
ErrAccountingOverflow. Callers use errors.Is, never string matching. These are
not protocol error numbers.

## Logical byte accounting

~~~go
const (
    mappingBaseBytes uint64 = 8 + 8 + 8 + 1
    serviceBaseBytes uint64 = 8 + 4 + 16 + 8 + 32 + 32 + 8 + 8 + 8 + 1
    streamBaseBytes  uint64 = 8 + 4 + 8 + 8 + 1 + 1
)
func mappingCost(spec MappingSpec) (uint64, error)
func serviceCost(ServiceSpec) (uint64, error)
func streamCost(StreamSpec) uint64
func checkedCost(base uint64, variableLengths ...int) (uint64, error)
~~~

The accounting gate counts logical scalar widths plus owned string bytes. It excludes map buckets, headers, alignment, locks, and allocator behavior. Actual heap profiling belongs to a later resource tranche.

## Bound categories

| Category | Tranche 1 treatment |
|---|---|
| Protocol safety bounds | Frozen P1F/P2D limits remain outside these local containers and are not copied, widened, or reinterpreted. |
| Go implementation defaults | None. NewStore rejects absent or zero generation, entry, byte, or string limits so callers cannot create unbounded state. |
| Deployment-configurable limits | Limits supplies explicit entry, byte, and owned-string caps; later configuration code must provide validated values. |
| Benchmark-derived targets | Deferred. Baselines observe lookup/insert/remove and allocations only and cannot set capacity or throughput requirements. |

## Pre-implementation baseline gate

This plan must be human-approved, committed alone, and present on the working
branch before Task 1 begins. The executor records and verifies the immutable
plan baseline once:

    $planPath = "docs/superpowers/plans/2026-08-14-production-go-client-tranche1-bounded-core-state.md"
    $planCommit = git log -1 --format=%H -- $planPath
    if ([string]::IsNullOrWhiteSpace($planCommit)) { throw "plan baseline is not committed" }
    git show --no-patch --format=%H $planCommit
    git diff-tree --no-commit-id --name-only -r $planCommit

Expected: git show prints the nonempty plan SHA, and diff-tree shows this plan
as the only path in that commit. Record the SHA in the Task 9 closure review
and use that exact value for every changed-path and protected-path comparison.
If the plan commit contains another path, stop before Task 1 and request a clean
documentation-only plan baseline; do not rewrite history automatically.

---

### Task 1: Module, limits, types, errors, accounting, and observer foundation

**Files:**
- Create: client/nbsr-go-client/go.mod
- Create: client/nbsr-go-client/internal/corestate/doc.go
- Create: client/nbsr-go-client/internal/corestate/types.go
- Create: client/nbsr-go-client/internal/corestate/errors.go
- Create: client/nbsr-go-client/internal/corestate/limits.go
- Create: client/nbsr-go-client/internal/corestate/observer.go
- Create: client/nbsr-go-client/internal/corestate/store.go
- Test: client/nbsr-go-client/internal/corestate/limits_test.go

**Interfaces:**
- Consumes: Go standard library only.
- Produces: every shared type, error, lifecycle enum, Clock and registry
  interfaces, cost function, observer contract, Store, and NewStore signature
  above. Compile-time assertions prove Store implements all three registries.

- [ ] **Step 1: Write the failing tests**

~~~go
func TestServiceHandleIsUint32AndZeroInvalid(t *testing.T) {
    if unsafe.Sizeof(ServiceHandle(0)) != 4 { t.Fatal("wrong width") }
    if InvalidServiceHandle != 0 { t.Fatal("zero not reserved") }
}
func TestLimitsRequireEveryBound(t *testing.T) {
    l := Limits{1, 1, 1, 1, 1, 1, 1, 1, 1}
    if err := l.Validate(); err != nil { t.Fatal(err) }
    l.MaxStreams = 0
    if !errors.Is(l.Validate(), ErrInvalidLimits) { t.Fatal("zero accepted") }
}
~~~

Also test errors.Is for every sentinel, generation/entry/byte/string zero-limit
rejection, deterministic costs including ServiceIdentity bytes, checked addition
overflow, nil Clock rejection, injected fake-clock use, nil observer
construction, and compile-time registry conformance.

- [ ] **Step 2: Prove RED**

Run from client/nbsr-go-client:

    go test ./internal/corestate -run 'Test(ServiceHandle|Limits|StateError|LogicalCost|NewStore)' -count=1

Expected RED: compilation fails because the package types and functions do not exist.

- [ ] **Step 3: Implement the minimal foundation**

Create go.mod:

~~~go
module nbsr.local/client/nbsr-go-client

go 1.26.5
~~~

Implement the exact interfaces above. Define ServiceActive/ServiceClosed;
StreamActive/StreamCancelled/StreamFinished; TerminalNone/TerminalCancelled/
TerminalCompleted/TerminalFailed. Store owns one RWMutex, validated limits,
Clock, empty maps, generation high-waters, usage, and observer. Randomness has no
role: mapping and service identifiers are monotonic, so Tranche 1 deliberately
defines no random-source abstraction. Start no goroutine.

- [ ] **Step 4: Prove GREEN and regress**

    gofmt -w internal/corestate/*.go
    go test ./internal/corestate -run 'Test(ServiceHandle|Limits|StateError|LogicalCost|NewStore)' -count=1
    go vet ./...

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/go.mod client/nbsr-go-client/internal/corestate/doc.go client/nbsr-go-client/internal/corestate/types.go client/nbsr-go-client/internal/corestate/errors.go client/nbsr-go-client/internal/corestate/limits.go client/nbsr-go-client/internal/corestate/observer.go client/nbsr-go-client/internal/corestate/store.go client/nbsr-go-client/internal/corestate/limits_test.go
    git commit -m "feat(go-client): add bounded core state foundation"

---

### Task 2: TS-generation lifecycle and monotonic ServiceHandle allocator

**Files:**
- Create: client/nbsr-go-client/internal/corestate/handle.go
- Test: client/nbsr-go-client/internal/corestate/handle_test.go
- Modify: client/nbsr-go-client/internal/corestate/store.go

**Interfaces:**
- Consumes: TSGeneration, ServiceHandle, Store, ErrGenerationClosed, ErrHandleExhausted.
- Produces: OpenGeneration, CloseGeneration coordination seam, and private allocateHandleLocked.

Use generationState { next ServiceHandle }. Store retains one scalar
highestGeneration and a bounded map containing only currently open generation
states. OpenGeneration requires a nonzero value strictly greater than
highestGeneration and atomically rejects at Limits.MaxGenerations. It then
advances the high-water. next begins at 1. Allocation
advances only when service insertion commits. Allocating MaxUint32 succeeds
once, then exhaustion fails closed. CloseGeneration deletes allocator state;
the high-water rejects reopening the same or an older generation without
retaining tombstones or a cleanup list.

Task 2 CloseGeneration succeeds only when the generation owns zero services
and streams, which is necessarily true before Tasks 4–5. It returns
ErrInvalidTransition rather than orphaning later-added state. Task 6 extends the
same public method with coordinated destructive teardown while preserving this
intermediate invariant.

- [ ] **Step 1: Write failing tests**

~~~go
func TestHandlesNeverReuseWithinGeneration(t *testing.T) {
    s := newSmallStore(t); mustOpen(t, s, 7)
    a := allocateHandleForTest(t, s, 7, true)
    b := allocateHandleForTest(t, s, 7, true)
    if a != 1 || b != 2 { t.Fatalf("%d %d", a, b) }
}
func TestGenerationsHaveIndependentNamespaces(t *testing.T) {
    s := newSmallStore(t); mustOpen(t, s, 7); mustOpen(t, s, 8)
    if allocateHandleForTest(t, s, 7, true) != 1 { t.Fatal() }
    if allocateHandleForTest(t, s, 8, true) != 1 { t.Fatal() }
}
~~~

Add zero generation, duplicate open, closed reopen, MaxUint32, overflow, and failed-insert-does-not-consume-handle cases.
Add generation-cap tests named TestGenerationCapacityBelow,
TestGenerationCapacityExact, and TestGenerationCapacityAbove, plus a test that
CloseGeneration rejects a same-package injected nonempty generation without
deleting allocator state.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run 'Test(Handles|Handle|Generation)' -count=1

Expected RED: generation and allocator methods are absent.

- [ ] **Step 3: Implement minimally**

Implement allocator access only under Store.mu. allocateHandleLocked returns a
candidate without advancing; commitHandleLocked verifies that candidate equals
next and advances it, so Task 4 can combine capacity and allocation atomically.
Test helpers in handle_test.go lock and call both functions. Put the overflow
seam in same-package test helpers by setting next; export no test-only method.

- [ ] **Step 4: Prove GREEN**

    gofmt -w internal/corestate/handle.go internal/corestate/handle_test.go internal/corestate/store.go
    go test ./internal/corestate -run 'Test(Handles|Handle|Generation)' -count=1
    go test ./internal/corestate -count=1

Expected: PASS.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/handle.go client/nbsr-go-client/internal/corestate/handle_test.go client/nbsr-go-client/internal/corestate/store.go
    git commit -m "feat(go-client): add generation scoped service handles"

---

### Task 3: Bounded MappingTable with non-reused IDs and references

**Files:**
- Create: client/nbsr-go-client/internal/corestate/mapping.go
- Test: client/nbsr-go-client/internal/corestate/mapping_test.go
- Modify: client/nbsr-go-client/internal/corestate/store.go

**Interfaces:**
- Consumes: MappingSpec, MappingSnapshot, mappingCost, limits, typed errors, usage, store mutex.
- Produces: AddMapping, LookupMapping, AcquireMapping, ReleaseMapping,
  RemoveMapping, ExpireMappings, monotonic MappingID allocation, and mapping
  observer events dispatched after unlock.

Store allocates MappingID monotonically from 1 and never reuses an ID during
Store lifetime; a scalar high-water prevents stale-reference aliasing without a
tombstone map. AddMapping requires nonempty identity, nonzero expiry, bounded
policy context, and rejects at MappingID overflow. Lookup and Acquire use the
injected Clock and reject when NowUnix() >= expiry. Acquire increments a checked
ActiveReferences count. Release decrements exactly and rejects underflow.
RemoveMapping and ExpireMappings require zero references; referenced entries are
left intact and return ErrInvalidTransition. Cleanup is synchronous and
caller-driven. Mapping conflict is exercised through a private
insertMappingWithIDLocked test seam: attempting to bind an already live ID to
different fields returns ErrMappingConflict and never replaces identity.

- [ ] **Step 1: Write failing tests**

~~~go
func TestMappingEntryCapacityAbove(t *testing.T) {
    s := mappingStore(t, 2, exactMappingBytes(t, 2))
    mustAddMapping(t, s, mappingSpec(1)); mustAddMapping(t, s, mappingSpec(2))
    before := s.Usage()
    if _, err := s.AddMapping(mappingSpec(3)); !errors.Is(err, ErrCapacityExceeded) { t.Fatal(err) }
    if s.Usage() != before { t.Fatal("partial mutation") }
}
func TestExpiredMappingCannotBeReturned(t *testing.T) {
    clock := newFakeClock(50); s := mappingStoreAt(t, clock, 1, 1024)
    m := mappingSpec(1); m.ExpiresAtUnix = 50; added := mustAddMapping(t, s, m)
    if _, err := s.LookupMapping(added.ID); !errors.Is(err, ErrExpiredMapping) { t.Fatal(err) }
}
~~~

Add separately named TestMappingEntryCapacityBelow (one entry under cap),
TestMappingEntryCapacityExact (at cap), TestMappingEntryCapacityAbove (cap+1),
and corresponding TestMappingByteCapacityBelow/Exact/Above. Add conflict seam,
exact expiry, acquire/release, removal-with-live-reference rejection, delayed
stale-ID lookup after removal plus later insertion, repeated cycles, MappingID
overflow, observer reentrancy, and accounting reconciliation. Add an 8-goroutine
Acquire/Release test whose final reference count is zero under the race detector.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run TestMapping -count=1

Expected RED: MappingTable methods are absent.

- [ ] **Step 3: Implement minimally**

Use map[MappingID]mappingEntry and a scalar highestMappingID. Copy owned strings.
Perform validation, cost, ID candidate, capacity checks, insertion, usage, and
high-water commit under one Lock. Return copied snapshots. Acquire/Release and
removal checks are atomic. Emit one mapping event per successful public mutation
after unlock; observer panic propagates after committed state and cannot roll
back or corrupt the table.

- [ ] **Step 4: Prove GREEN**

    gofmt -w internal/corestate/mapping.go internal/corestate/mapping_test.go internal/corestate/store.go
    go test ./internal/corestate -run TestMapping -count=1
    go test ./internal/corestate -count=1

Expected: PASS.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/mapping.go client/nbsr-go-client/internal/corestate/mapping_test.go client/nbsr-go-client/internal/corestate/store.go
    git commit -m "feat(go-client): add bounded mapping table"

---

### Task 4: Bounded ServiceTable

**Files:**
- Create: client/nbsr-go-client/internal/corestate/service.go
- Test: client/nbsr-go-client/internal/corestate/service_test.go
- Modify: client/nbsr-go-client/internal/corestate/handle.go
- Modify: client/nbsr-go-client/internal/corestate/store.go

**Interfaces:**
- Consumes: generation allocator, ServiceSpec/Snapshot, serviceCost, errors, mutex.
- Produces: AddService, LookupService, CloseService, RemoveService, reverse channel index, private stream-count helpers.

Use serviceKey { generation TSGeneration; handle ServiceHandle } and channelKey
{ generation TSGeneration; channelID ChannelID }. AddService validates nonzero
generation, ChannelID, ChannelGeneration, ServiceIdentity,
RouteGrantDigest, AuthorityGeneration, and CreditStateRef; bounds the service
identity string; requires open generation; rejects duplicate channel; checks
capacity/bytes; then allocates and commits atomically. ServiceDigest or
RouteGrantDigest equality never deduplicates or authorizes. Close blocks new
streams. Remove requires closed state and zero streams, removes only the exact
entry/reverse index, and never rewinds the allocator.

- [ ] **Step 1: Write failing tests**

~~~go
func TestStableDigestIsNotAuthority(t *testing.T) {
    s := serviceStore(t, 2, 1024); mustOpen(t, s, 1)
    a, b := serviceSpec(1, 1), serviceSpec(1, 2); b.ServiceDigest = a.ServiceDigest
    first := mustAddService(t, s, a); second := mustAddService(t, s, b)
    if first.Handle == second.Handle { t.Fatal("digest collapsed services") }
}
func TestFailedServiceInsertDoesNotConsumeHandle(t *testing.T) {
    s := serviceStore(t, 1, 1024); mustOpen(t, s, 1)
    first := mustAddService(t, s, serviceSpec(1, 1))
    if _, err := s.AddService(serviceSpec(1, 2)); !errors.Is(err, ErrCapacityExceeded) { t.Fatal(err) }
    mustCloseAndRemoveService(t, s, first)
    if got := mustAddService(t, s, serviceSpec(1, 3)).Handle; got != 2 { t.Fatal(got) }
}
~~~

Add unique key, duplicate channel, entry/byte boundaries, close/remove ordering, isolation, closed generation, count underflow protection, and failed-insertion atomicity.
Name the separate boundary tests TestServiceEntryCapacityBelow,
TestServiceEntryCapacityExact, TestServiceEntryCapacityAbove and
TestServiceByteCapacityBelow/Exact/Above. Add cross-binding tests that vary
ServiceIdentity, RouteGrantDigest, ChannelGeneration, and ChannelID independently
while holding the digest equal. Add an 8-goroutine AddService test proving
unique monotonic handles and exact usage under the race detector.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run 'Test(Service|StableDigest|FailedService)' -count=1

Expected RED: ServiceTable methods are absent.

- [ ] **Step 3: Implement minimally**

Use forward and reverse maps. Complete capacity check, candidate handle, both
index inserts, usage, and commitHandleLocked under Store.mu.Lock. A rejected
insert never calls commitHandleLocked. Private incrementStreamsLocked and
decrementStreamsLocked require the lock and check overflow/underflow. Emit one
service event for each successful add/close/remove after unlock.

- [ ] **Step 4: Prove GREEN**

    gofmt -w internal/corestate/service.go internal/corestate/service_test.go internal/corestate/handle.go internal/corestate/store.go
    go test ./internal/corestate -run 'Test(Service|StableDigest|FailedService)' -count=1
    go test ./internal/corestate -count=1

Expected: PASS.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/service.go client/nbsr-go-client/internal/corestate/service_test.go client/nbsr-go-client/internal/corestate/handle.go client/nbsr-go-client/internal/corestate/store.go
    git commit -m "feat(go-client): add bounded service table"

---

### Task 5: Bounded StreamTable

**Files:**
- Create: client/nbsr-go-client/internal/corestate/stream.go
- Test: client/nbsr-go-client/internal/corestate/stream_test.go
- Modify: client/nbsr-go-client/internal/corestate/service.go
- Modify: client/nbsr-go-client/internal/corestate/store.go

**Interfaces:**
- Consumes: StreamSpec/Snapshot, service lookup/count helpers, streamCost, enums, errors.
- Produces: InsertStream, LookupStream, CancelStream, FinishStream, RemoveStream.

Key by generation, handle, and StreamID. Require nonzero generation, handle, and LocalFlowID; StreamID zero remains valid because this tranche imposes no wire direction rule. Require an active owning service. Duplicate exact key is ErrDuplicateStream. Keys never change. Active transitions once to Cancelled or Finished. Removal requires terminal state and atomically removes, decrements owner count, and subtracts cost. Store no payload or authority.

- [ ] **Step 1: Write failing tests**

~~~go
func TestStreamPinnedToGenerationAndService(t *testing.T) {
    s, service := streamStore(t)
    spec := StreamSpec{service.Generation, service.Handle, 4, 9}
    if err := s.InsertStream(spec); err != nil { t.Fatal(err) }
    if _, err := s.LookupStream(service.Generation+1, service.Handle, 4); !errors.Is(err, ErrUnknownService) { t.Fatal(err) }
}
func TestTerminalRemovalReconcilesCountAndBytes(t *testing.T) {
    s, service := streamStore(t); spec := streamSpec(service, 4); before := s.Usage()
    mustInsertStream(t, s, spec)
    if err := s.FinishStream(spec.Generation, spec.Handle, spec.StreamID, TerminalCompleted); err != nil { t.Fatal(err) }
    if err := s.RemoveStream(spec.Generation, spec.Handle, spec.StreamID); err != nil { t.Fatal(err) }
    if s.Usage() != before { t.Fatal("usage mismatch") }
}
~~~

Add duplicate, unknown/closed owner, cross-generation mismatch, lifecycle, cancellation, entry/byte boundaries, exact count, failed-insert atomicity, and isolation.
Name separate TestStreamEntryCapacityBelow/Exact/Above and
TestStreamByteCapacityBelow/Exact/Above tests. Add the 16-contender duplicate
test here: exactly one insertion succeeds, 15 return ErrDuplicateStream, usage
and owner count are one, and ValidateInvariants passes.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run 'Test(Stream|Terminal)' -count=1

Expected RED: StreamTable methods are absent.

- [ ] **Step 3: Implement minimally**

Use map[streamKey]streamEntry. Under one Lock validate owner, duplicate,
capacity, insert, and count increment. Terminal methods update compact enums.
Removal validates terminal state and reconciles count/bytes under the same lock.
Emit one stream event for each successful insert/terminal/remove after unlock.

- [ ] **Step 4: Prove GREEN**

    gofmt -w internal/corestate/stream.go internal/corestate/stream_test.go internal/corestate/service.go internal/corestate/store.go
    go test ./internal/corestate -run 'Test(Stream|Terminal)' -count=1
    go test ./internal/corestate -count=1

Expected: PASS.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/stream.go client/nbsr-go-client/internal/corestate/stream_test.go client/nbsr-go-client/internal/corestate/service.go client/nbsr-go-client/internal/corestate/store.go
    git commit -m "feat(go-client): add bounded stream table"

---

### Task 6: Coordinated teardown and invariant validation

**Files:**
- Create: client/nbsr-go-client/internal/corestate/teardown.go
- Test: client/nbsr-go-client/internal/corestate/teardown_test.go
- Modify: client/nbsr-go-client/internal/corestate/store.go
- Modify: client/nbsr-go-client/internal/corestate/service.go
- Modify: client/nbsr-go-client/internal/corestate/stream.go

**Interfaces:**
- Consumes: all registries, generations, usage, lifecycles.
- Produces: deterministic service/generation teardown and ValidateInvariants.

Service order: close service, reject new streams, caller terminalizes/removes
streams, require count zero, remove service. Generation destruction is not
rotation: under one Lock delete the generation from the open map first, reject
insertion, close services, finish active streams as TerminalFailed, remove
streams and counts, remove services/reverse indexes, reconcile bytes, and delete
allocator state. The scalar highestGeneration rejects stale reopening. Mappings
remain independent.

ValidateInvariants recomputes counts/bytes, reverse-index bijection, counts, generation ownership, handles, owners, and lifecycle consistency under RLock. It reports, never repairs.

CloseGeneration emits one aggregate EventGenerationClosed after unlock. It does
not allocate or emit per-entry teardown events; operators observe exact removed
counts through Usage before/after or the closure review, keeping event work
constant and bounded. Observer panic propagates after commit and cannot resurrect
state. Mapping/service/stream events carry their relevant MappingID, Handle, and
StreamID fields; unused identifier fields are zero.

- [ ] **Step 1: Write failing tests**

~~~go
func TestGenerationTeardownReturnsToMappingOnlyUsage(t *testing.T) {
    s := populatedGeneration(t, 7, 3, 4); want := mappingOnlyUsage(s)
    if err := s.CloseGeneration(7); err != nil { t.Fatal(err) }
    if got := s.Usage(); got != want { t.Fatalf("%#v %#v", got, want) }
    if err := s.ValidateInvariants(); err != nil { t.Fatal(err) }
}
func TestServiceTeardownDoesNotTouchUnrelatedService(t *testing.T) {
    s, a, b := twoServiceStore(t); addStreams(t, s, a, 2); addStreams(t, s, b, 2)
    closeAndRemoveServiceStreams(t, s, a)
    got, err := s.LookupService(b.Generation, b.Handle)
    if err != nil || got.ActiveStreams != 2 { t.Fatalf("%#v %v", got, err) }
}
~~~

Add no resurrection, mapping independence, repeated cycles, stale generation use, failed insertion with no partial state, and deliberate same-package corruption detected by ValidateInvariants.
Add two deterministic service-close/stream-insert order tests using same-package
lock-step seams: insert commits before close and remains owned; close commits
before insert and insertion returns ErrServiceClosed. Add equivalent generation
close/service-insert order tests. Each ordering uses channels, never sleeps, and
asserts exact allowed result plus postcondition. Run these focused tests under
the race detector.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run 'Test(GenerationTeardown|ServiceTeardown|ValidateInvariants|RepeatedLifecycle)' -count=1
    go test -race ./internal/corestate -run 'Test(ServiceCloseOrdering|GenerationCloseOrdering)' -count=20 -timeout=60s

Expected RED: coordinated teardown and complete validation are absent.

- [ ] **Step 3: Implement minimally**

Use private locked helpers called with the one Store lock. Iterate bounded maps directly; create no work queue or goroutine. Tests may sort copied keys; production does not allocate an unbounded list.

- [ ] **Step 4: Prove GREEN**

    gofmt -w internal/corestate/teardown.go internal/corestate/teardown_test.go internal/corestate/store.go internal/corestate/service.go internal/corestate/stream.go
    go test ./internal/corestate -run 'Test(GenerationTeardown|ServiceTeardown|ValidateInvariants|RepeatedLifecycle)' -count=1
    go test ./internal/corestate -count=1

Expected: PASS with exact accounting and isolation.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/teardown.go client/nbsr-go-client/internal/corestate/teardown_test.go client/nbsr-go-client/internal/corestate/store.go client/nbsr-go-client/internal/corestate/service.go client/nbsr-go-client/internal/corestate/stream.go
    git commit -m "feat(go-client): coordinate bounded state teardown"

---

### Task 7: Deterministic property corpus and bounded fuzz target

**Files:**
- Test: client/nbsr-go-client/internal/corestate/fuzz_test.go
- Modify: client/nbsr-go-client/internal/corestate/teardown_test.go

**Interfaces:**
- Consumes: complete Store API and ValidateInvariants.
- Produces: test-only operation decoder, seed corpus, and bounded fuzz target.

Encode operations in bytes. High three bits select mapping/service/stream add, close/finish, remove, or generation close; remaining bits select fixed IDs. Use limits 8 mappings, 8 services, 32 streams. Cap each fuzz input at 256 operations. After each operation validate invariants and usage bounds. Maintain a test-only set of observed handles per generation and fail on reuse. Accept only documented typed rejections.
Also retain every observed MappingID in a test-only set and fail on reuse after
remove/expire. Seeds must exercise mapping acquire/remove/release ordering,
MappingID exhaustion seam, and MaxGenerations below/exact/above rejection.

- [ ] **Step 1: Write failing property tests**

~~~go
func FuzzBoundedLifecycle(f *testing.F) {
    f.Add([]byte{0x00, 0x21, 0x42, 0x63, 0x84, 0xa5, 0xc6})
    f.Add([]byte{0xff, 0xff, 0x00, 0x40, 0x80, 0xc0})
    f.Fuzz(func(t *testing.T, ops []byte) {
        if len(ops) > 256 { ops = ops[:256] }
        s := fuzzStore(t); runOperations(t, s, ops); assertWithinLimits(t, s)
        if err := s.ValidateInvariants(); err != nil { t.Fatal(err) }
    })
}
~~~

Add a deterministic TestPropertyCorpus with 20 named seeds and a 4,096-operation bounded create/terminal/remove cycle.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run 'Test(PropertyCorpus|LargeBoundedPopulation|RepeatedLifecycle)' -count=1

Expected RED: operation runner and assertions are absent.

- [ ] **Step 3: Implement test-only runner**

Keep all decoding in fuzz_test.go. Spawn no goroutine and add no production recovery behavior.

- [ ] **Step 4: Prove GREEN**

    gofmt -w internal/corestate/fuzz_test.go internal/corestate/teardown_test.go
    go test ./internal/corestate -run 'Test(PropertyCorpus|LargeBoundedPopulation|RepeatedLifecycle)' -count=1
    go test ./internal/corestate -run '^$' -fuzz '^FuzzBoundedLifecycle$' -fuzztime=10s

Expected: PASS without panic, underflow, overflow, resurrection, handle reuse, or committed generated corpus. The fuzz command is a bounded developer gate, not normal long-running CI.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/fuzz_test.go client/nbsr-go-client/internal/corestate/teardown_test.go
    git commit -m "test(go-client): add bounded lifecycle properties"

---

### Task 8: Baseline-only microbenchmarks and package documentation

**Files:**
- Test: client/nbsr-go-client/internal/corestate/benchmark_test.go
- Modify: client/nbsr-go-client/internal/corestate/doc.go

**Interfaces:**
- Consumes: complete Store API.
- Produces: lookup/insert/remove baselines and concise package security/lifecycle documentation.

Benchmark names begin BenchmarkBaselineOnly, use fixed bounded fixtures, call ReportAllocs and ResetTimer, and assert no target. Package docs explain local-only ServiceHandle, unchanged channel_id authority identity, three registries, limits, logical-versus-heap bytes, teardown, ephemerality, and exclusions.

- [ ] **Step 1: Write failing documentation test and benchmarks**

~~~go
func BenchmarkBaselineOnlyStreamLookup(b *testing.B) {
    s, service := benchmarkStore(b); spec := streamSpec(service, 4); mustInsertStreamB(b, s, spec)
    b.ReportAllocs(); b.ResetTimer()
    for i := 0; i < b.N; i++ {
        if _, err := s.LookupStream(spec.Generation, spec.Handle, spec.StreamID); err != nil { b.Fatal(err) }
    }
}
~~~

TestPackageDocumentationStatesSecurityBoundaries reads doc.go and requires: local-only ServiceHandle; channel_id remains the wire identity; logical bytes are not heap bytes; no network behavior.

- [ ] **Step 2: Prove RED**

    go test ./internal/corestate -run TestPackageDocumentationStatesSecurityBoundaries -count=1

Expected RED: doc.go lacks the exact boundary statements.

- [ ] **Step 3: Complete docs and benchmarks**

Add mapping/service/stream lookup and insert/remove benchmarks. Prefix their comment exactly BASELINE ONLY — NOT ACCEPTANCE CAPACITY. Add no performance target.

- [ ] **Step 4: Prove GREEN and observe baseline**

    gofmt -w internal/corestate/doc.go internal/corestate/benchmark_test.go
    go test ./internal/corestate -run TestPackageDocumentationStatesSecurityBoundaries -count=1
    go test ./internal/corestate -run '^$' -bench '^BenchmarkBaselineOnly' -benchmem -count=3

Expected: PASS; benchmark output is local observation only.

- [ ] **Step 5: Commit**

    git add client/nbsr-go-client/internal/corestate/doc.go client/nbsr-go-client/internal/corestate/benchmark_test.go
    git commit -m "docs(go-client): document bounded core state"

---

### Task 9: Full Tranche 1 acceptance and closure record

**Files:**
- Create: docs/reviews/production-go-client-tranche1-bounded-core-state.md
- Modify only if a gate exposes a defect: client/nbsr-go-client/internal/corestate files

**Interfaces:**
- Consumes: complete module and repository integrity commands.
- Produces: command/result record with PASS/FAIL/INCONCLUSIVE, commit SHA, protected refs, and changed-path audit.

- [ ] **Step 1: Write literal RED closure**

Create the review with every command below marked FAIL — not yet executed.

- [ ] **Step 2: Prove RED**

    if (rg -n "FAIL — not yet executed" docs/reviews/production-go-client-tranche1-bounded-core-state.md) { exit 1 }; exit 0

Expected RED: prints every pending gate and exits 1.

- [ ] **Step 3: Run exact acceptance commands**

From client/nbsr-go-client:

    gofmt -w internal/corestate/*.go
    go test ./... -count=1
    go test -race ./... -count=1
    go vet ./...
    go test ./internal/corestate -run 'Test.*(Capacity|Bytes|Teardown|Lifecycle|Invariant|Handle|Duplicate|Conflict|Isolation)' -count=1
    go test ./internal/corestate -run '^$' -fuzz '^FuzzBoundedLifecycle$' -fuzztime=10s
    go test ./internal/corestate -run '^$' -bench '^BenchmarkBaselineOnly' -benchmem -count=3

From repository root:

    git diff --check
    git status --short
    $planCommit = git log -1 --format=%H -- docs/superpowers/plans/2026-08-14-production-go-client-tranche1-bounded-core-state.md
    if ([string]::IsNullOrWhiteSpace($planCommit)) { throw "plan baseline is not committed" }
    git diff --name-only $planCommit
    git diff --exit-code $planCommit -- interop/nbsr-go-peer crates/nbsr-transport docs/protocol vectors evidence
    python -m pytest tests/performance/test_session_rotation_model.py tests/test_p2d_stream_credit.py -q
    python -m ruff check .
    git rev-parse main
    git rev-parse origin/main

Expected: Go gates exit 0; benchmark sets no target; the committed plan baseline
is derived from Git and changed paths after it are only client/nbsr-go-client
and the closure review; protected paths have no diff; focused Python and Ruff
pass; local/remote main equal
1938154d498b32d81a3564319969430644e8a688. Update only observed results.

- [ ] **Step 4: Prove GREEN closure**

    if rg -n "FAIL — not yet executed" docs/reviews/production-go-client-tranche1-bounded-core-state.md; then exit 1; else exit 0; fi
    git diff --check
    git status --short

Expected: no pending marker; whitespace passes; status contains only intended Tranche 1 files.

- [ ] **Step 5: Commit closure**

    git add client/nbsr-go-client/go.mod client/nbsr-go-client/internal/corestate docs/reviews/production-go-client-tranche1-bounded-core-state.md
    git diff --cached --name-only
    git diff --cached --stat
    git diff --cached --check
    git commit -m "test(go-client): close bounded core state tranche"

Do not push implementation until human review.

---

## Exact Tranche 1 acceptance gate

- [ ] go test ./... -count=1 passes in client/nbsr-go-client.
- [ ] go test -race ./... -count=1 passes.
- [ ] go vet ./... passes.
- [ ] Entry and logical-byte capacity one-below/exact/one-above tests pass for every registry.
- [ ] Mapping conflict, exact expiry, removal, and accounting pass.
- [ ] ServiceHandle is four-byte uint32, zero-invalid, monotonic, non-reused, generation-independent, and overflow-fail-closed.
- [ ] Stable service/RouteGrant digests are never authority.
- [ ] Streams remain pinned to generation, handle, and opaque StreamID.
- [ ] Duplicate decisions are atomic and typed.
- [ ] Service/generation teardown reconciles counters and bytes without resurrection or unrelated damage.
- [ ] Bounded concurrency tests pass under race detector.
- [ ] Deterministic property corpus and 4,096-operation population pass.
- [ ] Ten-second fuzz check finds no panic, underflow, overflow, reuse, resurrection, or capacity breach.
- [ ] No unbounded registry, queue, slice, worker, retry, or cleanup list exists; production starts no goroutine.
- [ ] Logical bytes are distinguished from heap bytes and reconcile exactly.
- [ ] Benchmarks are BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
- [ ] interop/nbsr-go-peer remains unchanged.
- [ ] P1F/P2D Rust, protocol, vectors, and evidence remain unchanged.
- [ ] No QUIC, TLS, resolver, authority transport, OS interception, proxy, persistence, rotation, revocation feed, enrollment, UDP/IP, or migration code exists.
- [ ] Focused Python safety tests and Ruff pass.
- [ ] git diff --check and changed-path audit pass.
- [ ] Local and remote main remain 1938154d498b32d81a3564319969430644e8a688.

## Explicit exclusions

This plan excludes QUIC, TLS, RouteGrant acquisition, NBSR Authority Control Plane transport, resolver/DNS integration, Synthetic-IP OS allocation, TUN, WFP, eBPF, packet interception, proxy listeners, platform adapters, Transport Session establishment, Service Channel wire admission, Stream Credit framing, P2D changes, rotation, active/standby behavior, revocation-feed transport, key enrollment, live-state persistence, UDP/IP, cross-edge migration, and performance optimization.
