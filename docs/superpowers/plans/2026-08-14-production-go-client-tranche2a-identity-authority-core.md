# Production Go Client Tranche 2A Identity and Authority Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the bounded, transport-neutral production Go identity and authority engine that independently verifies final RouteGrants, maintains local freshness/generation/rollback safety, and supplies one-use authority to future TS/SC ownership without implementing ACP networking or new wire semantics.

**Architecture:** Add three cohesive packages beside the accepted `internal/corestate`: `internal/identity` owns purpose-separated opaque key references, `internal/authority` owns the verifier, sealed authority, freshness/generation state, cache, coalescing, idempotency, rollback/restart gate, fixture provider, and observer events under one coherent mutex, and `internal/retry` computes finite retry decisions without sleeping. Provider and cryptographic calls occur outside mutation locks; immutable value snapshots cross package boundaries, and only unexported constructors create verified authority/checkpoint values.

**Tech Stack:** Go 1.26.5; standard library only (`context`, `crypto/ed25519`, `crypto/rand`, `crypto/sha256`, `encoding/binary`, `errors`, `fmt`, `io`, `sync`, `time`); existing frozen Core v0.2 RouteGrant CBOR/COSE fixtures; Go testing, race detector, vet, native fuzzing, and baseline-only benchmarks.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`. Never modify, merge, rebase, or force-push `main`.
- Preserve local and remote `main` at `1938154d498b32d81a3564319969430644e8a688`.
- The approved Tranche 2 design baseline is `40eb5dbaa11cee7ae3e8e690b20b1c6c0d6f2485` and is already published on the working branch.
- Preserve every accepted `internal/corestate` API, lifecycle, bound, error, observer, and accounting semantic. Do not move authority code into `corestate`.
- Do not modify `interop/nbsr-go-peer`, `verifiers/federation-go`, Rust transport, protocol registries/vectors, or P1F/P2D evidence.
- The client authenticates only to its enrolled Source Operator ACP. It never discovers federation members, collects quorum, negotiates cross-operator trust, or selects destination issuers.
- TLS/authenticated provider delivery never makes authority usable. Only independent local verification may construct a sealed `VerifiedAuthority`.
- No Application Stream creation performs an ACP freshness call. The hot-path validity check is local, bounded, non-I/O, and allocation-free after caller preparation.
- Persist only the signed ACP authority-generation floor abstraction. Never persist or restore RouteGrants, TSs, SCs, credits, streams, selectors, reservations, pending calls, retry state, or caches.
- Cold start always enters `FreshnessRequired`; new authority-dependent work remains denied until fresh enrolled-ACP validation succeeds.
- TPM/secure monotonic hardware is optional defense-in-depth and has no Tranche 2A implementation.
- Every map, byte total, pending operation, waiter set, retained request, retry budget, event payload, and test operation sequence has an explicit bound.
- Use literal RED, minimal GREEN, focused regression, and one independently reviewable commit per task.
- No callback, signer, verifier dependency, provider call, observer call, or floor-store call while holding an internal authority mutation lock.
- Snapshots and returned byte slices are immutable copies. No raw private-key bytes or mutable parser tree crosses a manager boundary.
- Any need for a new enrollment/ACP request, result, checkpoint, revocation, or idempotency wire field is labeled `TRANCHE 2B — REQUIRES SEPARATE PROTOCOL APPROVAL` and excluded.
- Benchmarks are labeled exactly `BASELINE ONLY — NOT ACCEPTANCE CAPACITY`; they set no throughput or allocation acceptance target.

---

## Planned production package structure

```text
client/nbsr-go-client/
├── go.mod
└── internal/
    ├── corestate/                         # accepted Tranche 1, unchanged
    ├── identity/
    │   ├── doc.go
    │   ├── errors.go
    │   ├── types.go
    │   ├── signer.go
    │   ├── store.go
    │   ├── identity_test.go
    │   └── signer_test.go
    ├── authority/
    │   ├── doc.go
    │   ├── errors.go
    │   ├── types.go
    │   ├── observer.go
    │   ├── provider.go
    │   ├── cbor.go
    │   ├── cose.go
    │   ├── verifier.go
    │   ├── freshness.go
    │   ├── generation.go
    │   ├── cache.go
    │   ├── coalesce.go
    │   ├── idempotency.go
    │   ├── floor.go
    │   ├── restart.go
    │   ├── manager.go
    │   ├── fixture_provider.go
    │   ├── verifier_test.go
    │   ├── freshness_test.go
    │   ├── generation_test.go
    │   ├── cache_test.go
    │   ├── coalesce_test.go
    │   ├── idempotency_test.go
    │   ├── floor_test.go
    │   ├── restart_test.go
    │   ├── manager_test.go
    │   ├── concurrency_test.go
    │   ├── fuzz_test.go
    │   └── benchmark_test.go
    └── retry/
        ├── doc.go
        ├── errors.go
        ├── policy.go
        └── policy_test.go
```

`authority` remains one package because cache mutation, pending acquisition,
freshness publication, generation invalidation, reservation transitions, and
restart readiness require one explicit lock order and sealed unexported fields.
`retry` is independent pure decision logic. `identity` can be replaced by an OS
keystore adapter in a later platform tranche without changing authority state.

## Exact shared interfaces and types

### `internal/identity`

```go
package identity

type Purpose uint8
const (
    PurposeDeviceACPRequest Purpose = iota + 1
    PurposeTSProof
    PurposeLocalStateIntegrity
)

type KeyRef struct {
    ID         [32]byte
    Purpose    Purpose
    Generation uint64
    Thumbprint [32]byte
}

type DeviceIdentity struct {
    ID                  [32]byte
    SourceOperatorID    string
    CredentialGeneration uint64
    CredentialNotBefore uint64
    CredentialExpiresAt uint64
    SigningKey          KeyRef
}

type WorkloadPolicyContext struct {
    SubjectDigest    [32]byte
    PolicyGeneration uint64
    CredentialExpiresAt uint64
    PolicyExpiresAt uint64
}

type TSProofKey struct {
    TSGeneration uint64
    Key          KeyRef
}

type LocalStateIntegrityKey struct { Key KeyRef }

type Signer interface {
    KeyRef() KeyRef
    PublicKey(context.Context) ([]byte, error)
    SignPurposeBound(context.Context, Purpose, []byte) ([]byte, error)
}

type Registry interface {
    Device() (DeviceIdentity, error)
    Workload([32]byte) (WorkloadPolicyContext, error)
    TSProof(uint64) (TSProofKey, error)
    LocalStateIntegrity() (LocalStateIntegrityKey, error)
}
```

All structs contain public metadata only. `Signer` never exports private bytes.
`KeyRef.ID` is an opaque local handle, not a `kid`, credential, bearer token, or
filesystem path. Zero IDs, purposes, and generations are invalid. A
`WorkloadPolicyContext` is optional: absence is represented by a nil pointer in
an immutable request copy; no enterprise IAM object is required.

### `internal/authority`

```go
package authority

type AuthorityGeneration uint64
type TSGeneration uint64
type RequestID [16]byte
type RouteIntentDigest [32]byte
type RouteGrantDigest [32]byte
type ServiceDigest [32]byte
type PolicyDigest [32]byte
type ProofKeyThumbprint [32]byte
type CheckpointDigest [32]byte

type RouteIntent struct {
    Canonical       []byte
    Digest          RouteIntentDigest
    ServiceIdentity string
    SourceOperator  string
    SourceEdge      string
    TargetOperator  string
    TargetEdges     []string
    Transport       string
    Port            uint16
    RecordSequence  uint64
    PolicyHash      PolicyDigest
    RouteID         [16]byte
    LeaseID         [16]byte
    ExpiresAt       uint64
}

type AuthorityKey struct {
    IntentDigest       RouteIntentDigest
    ServiceDigest      ServiceDigest
    SourceOperator     string
    SourceEdge         string
    TargetOperator     string
    TargetEdgeSetDigest [32]byte
    Profile            string
    Transport          string
    Port               uint16
    DeviceID           [32]byte
    DeviceGeneration   uint64
    WorkloadDigest     [32]byte
    WorkloadGeneration uint64
    TSGeneration       TSGeneration
    ProofThumbprint    ProofKeyThumbprint
    PolicyHash         PolicyDigest
    PolicyGeneration   uint64
    AuthorityGeneration AuthorityGeneration
}

type AcquireRequest struct {
    Key            AuthorityKey
    Intent         RouteIntent
    Device         identity.DeviceIdentity
    Workload       *identity.WorkloadPolicyContext
    RequestID      RequestID
    DeadlineUnix   uint64
}

type RenewRequest struct {
    AcquireRequest
    PreviousGrant RouteGrantDigest
}

type FreshnessRequest struct {
    SourceOperator string
    Profile        string
    DeviceID       [32]byte
    DeviceGeneration uint64
    AfterGeneration AuthorityGeneration
    AfterCheckpoint CheckpointDigest
    DeadlineUnix   uint64
}

type ProviderGrant struct {
    ExactRouteGrant []byte
    Profile         string
    AuthorityGeneration AuthorityGeneration
    Checkpoint      CheckpointDigest
}

type ProviderFreshness struct {
    SourceOperator string
    Profile        string
    Evidence       []byte
}

type AuthorityProvider interface {
    Acquire(context.Context, AcquireRequest) (ProviderGrant, error)
    Renew(context.Context, RenewRequest) (ProviderGrant, error)
    Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error)
    Close() error
}
```

`ProviderGrant` and `ProviderFreshness` are untrusted candidates. Their byte
slices are copied at the boundary. No public conversion exists from either type
to `VerifiedAuthority` or `VerifiedCheckpoint`.

```go
type IssuerRecord struct {
    KID          []byte
    PublicKey    [32]byte
    Purpose      uint16
    Profile      string
    SourceOperator string
    Generation   uint64
    NotBefore    uint64
    ExpiresAt    uint64
    Revoked      bool
}

type IssuerResolver interface {
    ResolveRouteGrantIssuer(context.Context, []byte, string, string, uint64) (IssuerRecord, error)
}

type CheckpointClaims struct {
    SourceOperator string
    Profile        string
    Generation     AuthorityGeneration
    IssuedAt       uint64
    FreshUntil     uint64
    Digest         CheckpointDigest
    RevokedGrants  []RouteGrantDigest
}

type CheckpointEvidenceVerifier interface {
    VerifyFreshnessEvidence(context.Context, ProviderFreshness, FreshnessRequest, uint64) (CheckpointClaims, error)
}
```

`CheckpointEvidenceVerifier` is an injected trust boundary because the ACP
checkpoint wrapper has no approved schema. Tranche 2A supplies only a
fixture/in-memory verifier inside `authority`; any production implementation is
`TRANCHE 2B — REQUIRES SEPARATE PROTOCOL APPROVAL`.

```go
type VerificationContext struct {
    Key         AuthorityKey
    Intent      RouteIntent
    Checkpoint  VerifiedCheckpoint
    NowUnix     uint64
}

type Verifier struct { issuers IssuerResolver }
func NewVerifier(IssuerResolver) (*Verifier, error)
func (v *Verifier) VerifyRouteGrant(context.Context, ProviderGrant, VerificationContext) (VerifiedAuthority, error)

type VerifiedAuthority struct { seal verifiedAuthority }
type VerifiedCheckpoint struct { seal verifiedCheckpoint }

type verifiedAuthority struct {
    key AuthorityKey
    grant RouteGrantDigest
    serviceIdentity string
    generation AuthorityGeneration
    expiresAt uint64
    checkpoint CheckpointDigest
}

type verifiedCheckpoint struct {
    sourceOperator string
    profile string
    generation AuthorityGeneration
    issuedAt uint64
    freshUntil uint64
    digest CheckpointDigest
    revoked []RouteGrantDigest
}

func (a VerifiedAuthority) Key() AuthorityKey
func (a VerifiedAuthority) GrantDigest() RouteGrantDigest
func (a VerifiedAuthority) ServiceIdentity() string
func (a VerifiedAuthority) TSGeneration() TSGeneration
func (a VerifiedAuthority) ProofThumbprint() ProofKeyThumbprint
func (a VerifiedAuthority) Generation() AuthorityGeneration
func (a VerifiedAuthority) ExpiresAt() uint64
func (a VerifiedAuthority) CheckpointDigest() CheckpointDigest
func (c VerifiedCheckpoint) Generation() AuthorityGeneration
func (c VerifiedCheckpoint) FreshUntil() uint64
func (c VerifiedCheckpoint) Digest() CheckpointDigest
```

The exported wrappers contain only unexported fields, have no exported literal-
construction path, and expose immutable scalar/copy accessors. Zero values are
invalid and rejected by every consuming method.

### Manager, cache, generation, rollback, and hot-path APIs

```go
type Limits struct {
    MaxCacheEntries, MaxPending, MaxWaitersPerPending, MaxRequestRecords int
    MaxCacheBytes, MaxPendingBytes, MaxRequestBytes uint64
    MaxGrantBytes, MaxCheckpointEvidenceBytes, MaxServiceIdentityBytes int
}

type Clock interface { NowUnix() uint64 }
type RequestIDSource interface { NewRequestID() (RequestID, error) }
func NewCryptoRequestIDSource(io.Reader) (RequestIDSource, error)

type GenerationSnapshot struct { generation AuthorityGeneration }
type Reservation struct { id uint64; key AuthorityKey; grant RouteGrantDigest }
type AuthorityHandle struct { key AuthorityKey; grant RouteGrantDigest; generation AuthorityGeneration; expiresAt uint64; checkpoint CheckpointDigest }
type AdmissionOwner struct { TSGeneration TSGeneration; ChannelID [16]byte }

type Usage struct {
    CacheEntries, PendingCalls, PendingWaiters, RequestRecords int
    CacheBytes, PendingBytes, RequestBytes uint64
}

type RequestStatus uint8
const (
    RequestPending RequestStatus = iota + 1
    RequestComplete
    RequestAmbiguous
)

type RequestSnapshot struct {
    ID RequestID
    RequestDigest [32]byte
    ResultDigest [32]byte
    Status RequestStatus
    AuthorityGeneration AuthorityGeneration
    ExpiresAt uint64
}

type Manager struct { /* one mutex and bounded state; exact fields private */ }
func NewManager(Limits, Clock, AuthorityProvider, *Verifier, CheckpointEvidenceVerifier, GenerationFloorStore, Observer) (*Manager, error)
func (m *Manager) Acquire(context.Context, AcquireRequest) (Reservation, error)
func (m *Manager) Renew(context.Context, RenewRequest) (Reservation, error)
func (m *Manager) PublishFreshness(context.Context, FreshnessRequest, ProviderFreshness) (VerifiedCheckpoint, error)
func (m *Manager) CaptureGeneration() (GenerationSnapshot, error)
func (m *Manager) ValidateForNewWork(Reservation, GenerationSnapshot, uint64) error
func (m *Manager) Consume(Reservation, AdmissionOwner, GenerationSnapshot, uint64) (AuthorityHandle, error)
func (m *Manager) Release(Reservation) error
func (m *Manager) Quarantine(Reservation, RequestID) error
func (m *Manager) InvalidateGrant(RouteGrantDigest) error
func (m *Manager) InvalidateOlderThan(AuthorityGeneration) (int, error)
func (m *Manager) Usage() Usage
func (m *Manager) ValidateInvariants() error
func (m *Manager) Close() error
```

`ValidateForNewWork` and `Consume` are local only: no provider, verifier,
checkpoint parser, floor store, or observer call occurs from their critical
validation path. `Consume` linearizes the final generation/freshness/expiry/
revocation check and one-owner transition. Future TS/SC code converts the
returned scalar generation values into its own accepted types; Tranche 2A does
not import or mutate `corestate`.

```go
type SignedGenerationFloor struct {
    SourceOperator string
    Profile        string
    Generation     AuthorityGeneration
    Checkpoint     CheckpointDigest
    SignedEvidence []byte
}

type GenerationFloorStore interface {
    Load(context.Context, string, string) (SignedGenerationFloor, error)
    StoreHigher(context.Context, SignedGenerationFloor) error
}

type RestartState uint8
const (
    RestartColdStart RestartState = iota + 1
    RestartFreshnessRequired
    RestartReady
    RestartFailClosed
)

func NewRestartGate(GenerationFloorStore, CheckpointEvidenceVerifier, Clock, Observer) (*RestartGate, error)
func (g *RestartGate) Load(context.Context, string, string) error
func (g *RestartGate) AcceptFresh(context.Context, FreshnessRequest, ProviderFreshness) (VerifiedCheckpoint, error)
func (g *RestartGate) State() RestartState
func (g *RestartGate) RequireReady() error
```

The in-memory floor store copies signed evidence, accepts equal identical floors
idempotently, rejects equal conflicting or lower floors, and calls no manager.
No durable-state API accepts a RouteGrant, cache entry, reservation, TS, SC,
credit, stream, or selector type.

### `internal/retry`

```go
package retry

type Class uint8
const (
    Retryable Class = iota + 1
    ConditionallyRetryable
    Terminal
)

type Input struct {
    Class          Class
    Attempt        uint32
    MaxAttempts    uint32
    NowUnixMilli   uint64
    DeadlineUnixMilli uint64
    BaseBackoffMillis uint64
    MaxBackoffMillis  uint64
    JitterPermille uint16
    JitterSample   uint16
    RetryAfterMillis uint64
    ConditionChanged bool
    CircuitOpen    bool
    ApplicationPayloadWritten bool
}

type Decision struct { Retry bool; DelayMillis uint64; TerminalReason Reason }
type Reason uint8
const (
    ReasonNone Reason = iota
    ReasonTerminalClass
    ReasonConditionUnchanged
    ReasonAttemptsExhausted
    ReasonDeadline
    ReasonCircuitOpen
    ReasonPayloadWritten
)
func Decide(Input) (Decision, error)
```

`Decide` is pure and never sleeps. It rejects invalid budgets/overflow, forbids
retry after application payload, clamps exponential backoff and retry hints to
the remaining deadline, and never returns retry for `Terminal`.

## Typed authority errors and observer contract

`identity`, `authority`, and `retry` each follow the accepted Tranche 1
`ErrorCode` plus typed-error/sentinel pattern. Authority sentinels are:

```go
ErrUnknownIdentity, ErrInvalidKeyPurpose, ErrInvalidAuthority,
ErrSignatureFailure, ErrBindingMismatch, ErrExpired, ErrRevoked,
ErrStaleFreshness, ErrStaleGeneration, ErrGenerationRollback,
ErrCacheCapacity, ErrPendingCapacity, ErrWaiterCapacity,
ErrRequestConflict, ErrRequestAmbiguous, ErrProviderUnavailable,
ErrPolicyDenied, ErrTerminalEnrollment, ErrInvalidLimits,
ErrInvalidTransition, ErrClosed, ErrNotReady, ErrAccountingOverflow
```

These are local errors, not protocol numbers. Provider errors are translated by
explicit `errors.Is` classification; strings never control behavior.

```go
type Observer interface { Observe(Event) }
type Event struct {
    Kind EventKind
    AuthorityGeneration AuthorityGeneration
    Grant RouteGrantDigest
    Request RequestID
    Result ErrorCode
}
```

Events cover acquire requested/coalesced/result, renewal requested/result,
freshness accepted/rejected/expired, generation advanced, authority invalidated,
cache hit/miss/full, ambiguous quarantine, rollback-floor update/reject, and
retry decision. Record compact events while locked, emit after unlock, and use
digests/typed results only—never keys, raw grants, service names, or payload.

## Pre-implementation baseline gate

The plan must be human-approved, committed alone, and present on the working
branch before Task 1 begins. The executor derives and records the immutable plan
commit:

```powershell
$planPath = 'docs/superpowers/plans/2026-08-14-production-go-client-tranche2a-identity-authority-core.md'
$planCommit = git log -1 --format=%H -- $planPath
if ([string]::IsNullOrWhiteSpace($planCommit)) { throw 'plan baseline is not committed' }
$paths = git diff-tree --no-commit-id --name-only -r $planCommit
if ($paths.Count -ne 1 -or $paths[0] -ne $planPath) { throw 'plan commit is not isolated' }
git show --no-patch --format=%H $planCommit
```

Expected: one nonempty plan SHA and exactly the plan path. Record it in the
Tranche 2A closure review. Do not rewrite history if the gate fails.

---

### Task 1: Purpose-separated identity and key-reference lifecycle

**Files:**
- Create: `client/nbsr-go-client/internal/identity/doc.go`
- Create: `client/nbsr-go-client/internal/identity/errors.go`
- Create: `client/nbsr-go-client/internal/identity/types.go`
- Create: `client/nbsr-go-client/internal/identity/signer.go`
- Create: `client/nbsr-go-client/internal/identity/store.go`
- Test: `client/nbsr-go-client/internal/identity/identity_test.go`
- Test: `client/nbsr-go-client/internal/identity/signer_test.go`

**Interfaces:**
- Consumes: Go standard library only.
- Produces: every `identity` type, constant, `Signer`, and `Registry` signature defined above; `NewMemoryRegistry(DeviceIdentity, []WorkloadPolicyContext, []TSProofKey, LocalStateIntegrityKey) (*MemoryRegistry, error)` and `NewMemorySigner(KeyRef, ed25519.PrivateKey) (*MemorySigner, error)` for deterministic tests only.

- [ ] **Step 1: Write literal failing tests**

```go
func TestPurposeSeparatedReferencesRejectReuse(t *testing.T) {
    device := keyRef(1, PurposeDeviceACPRequest, 1)
    if _, err := NewMemoryRegistry(deviceIdentity(device), nil,
        []TSProofKey{{TSGeneration: 7, Key: device}}, localKey());
        !errors.Is(err, ErrInvalidKeyPurpose) { t.Fatal(err) }
}

func TestSignerNeverExportsPrivateKey(t *testing.T) {
    typ := reflect.TypeOf((*Signer)(nil)).Elem()
    for i := 0; i < typ.NumMethod(); i++ {
        if strings.Contains(strings.ToLower(typ.Method(i).Name), "private") { t.Fatal(typ.Method(i).Name) }
    }
}
```

Also test zero/missing device, wrong purpose for every role, duplicate TS
generation, mismatched key generation, expired credential validation at exact
boundary, optional workload absence, defensive public-key/signature copies,
wrong purpose passed to `SignPurposeBound`, typed `errors.Is`, and concurrent
read-only registry lookup under `-race`.

- [ ] **Step 2: Prove RED**

Run from `client/nbsr-go-client`:

```powershell
go test ./internal/identity -run 'Test(Purpose|Signer|Identity|Workload|TSProof|LocalState)' -count=1
```

Expected RED: compilation fails because `internal/identity` types do not exist.

- [ ] **Step 3: Implement minimal identity state**

Implement the exact types and interfaces. Validate every input before copying
it into immutable maps. `MemorySigner` keeps an internal private-key copy for
tests, validates its public-key thumbprint against `KeyRef`, domain-separates
signatures as `"NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00" || purpose-byte || message`,
and rejects a requested purpose unequal to its reference. Start no goroutine and
define no global registry or default signer.

- [ ] **Step 4: Prove GREEN and regress**

```powershell
gofmt -w internal/identity/*.go
go test ./internal/identity -count=1
go test -race ./internal/identity -count=1
go vet ./...
```

Expected: all commands exit 0; no private-key accessor exists.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/identity
git commit -m "feat(go-client): add purpose-separated identity state"
```

---

### Task 2: Authority types, errors, limits, observer, and provider boundary

**Files:**
- Create: `client/nbsr-go-client/internal/authority/doc.go`
- Create: `client/nbsr-go-client/internal/authority/errors.go`
- Create: `client/nbsr-go-client/internal/authority/types.go`
- Create: `client/nbsr-go-client/internal/authority/observer.go`
- Create: `client/nbsr-go-client/internal/authority/provider.go`
- Create: `client/nbsr-go-client/internal/authority/manager.go`
- Test: `client/nbsr-go-client/internal/authority/manager_test.go`

**Interfaces:**
- Consumes: `internal/identity` types.
- Produces: exact authority/provider/manager/limits/clock/request-source/observer types above; foundation `NewManager` validation and empty bounded state; `NewCryptoRequestIDSource(io.Reader) (RequestIDSource, error)` using `crypto/rand.Reader` in production and injected readers in tests.

- [ ] **Step 1: Write failing boundary tests**

```go
func TestProviderResultCannotBeUsedAsVerifiedAuthority(t *testing.T) {
    providerType := reflect.TypeOf(ProviderGrant{})
    verifiedType := reflect.TypeOf(VerifiedAuthority{})
    if providerType.AssignableTo(verifiedType) || providerType.ConvertibleTo(verifiedType) { t.Fatal("bypass") }
}

func TestEveryAuthorityLimitRequired(t *testing.T) {
    l := validLimits(); l.MaxPending = 0
    if !errors.Is(l.Validate(), ErrInvalidLimits) { t.Fatal("zero pending accepted") }
}
```

Test 16-byte `RequestID`, zero rejection for every complete-key dimension,
canonical intent digest verification, target-edge digest sorting/copying,
workload nil semantics, string/byte caps, error sentinels, nil dependencies,
provider method signatures, no `Verified` boolean field, and no observer call
while the test holds a lock-step mutation seam.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(Provider|Authority|Limits|RequestID|Observer)' -count=1
```

Expected RED: authority package and types are absent.

- [ ] **Step 3: Implement the minimal foundation**

Create validated value types, defensive-copy helpers, typed errors, limits,
no-op observer, provider interface, request source, and an empty Manager with
one `sync.RWMutex`. Do not implement provider operations or background work.
Manager fields include bounded maps only; its constructor stores dependencies
after validation. Private `notify([]Event)` runs after unlock.

- [ ] **Step 4: Prove GREEN**

```powershell
gofmt -w internal/authority/*.go
go test ./internal/authority -run 'Test(Provider|Authority|Limits|RequestID|Observer)' -count=1
go test ./internal/identity ./internal/authority -count=1
go vet ./...
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority
git commit -m "feat(go-client): define authority provider boundary"
```

---

### Task 3: Frozen RouteGrant CBOR/COSE verification and sealed authority

**Files:**
- Create: `client/nbsr-go-client/internal/authority/cbor.go`
- Create: `client/nbsr-go-client/internal/authority/cose.go`
- Create: `client/nbsr-go-client/internal/authority/verifier.go`
- Test: `client/nbsr-go-client/internal/authority/verifier_test.go`
- Test fixture reads only: `vectors/core-v0.2/artifacts/valid/objects/route-grant-sign1.cose`
- Test fixture reads only: `vectors/core-v0.2/artifacts/invalid/`
- Reference only: `interop/nbsr-go-peer/internal/cbor/cbor.go`
- Reference only: `interop/nbsr-go-peer/internal/authority/authority.go`

**Interfaces:**
- Consumes: `IssuerResolver`, `ProviderGrant`, `VerificationContext`, frozen Core v0.2 RouteGrant fields 0..16.
- Produces: `NewVerifier` and `VerifyRouteGrant` above; `NewStaticIssuerResolver([]IssuerRecord) (*StaticIssuerResolver, error)` for copied, bounded test/profile trust records; private bounded deterministic-CBOR decoder, COSE Sign1 parser, and `verifiedAuthority` constructor.

- [ ] **Step 1: Write failing frozen-fixture and mutation tests**

```go
func TestVerifyRouteGrantSealsFrozenFixture(t *testing.T) {
    candidate, ctx, resolver := validFrozenGrantCase(t)
    got, err := mustVerifier(t, resolver).VerifyRouteGrant(context.Background(), candidate, ctx)
    if err != nil { t.Fatal(err) }
    if got.GrantDigest() != sha256.Sum256(candidate.ExactRouteGrant) { t.Fatal("digest") }
    if got.Key() != ctx.Key { t.Fatal("key") }
}

func TestVerifiedAuthorityZeroValueRejected(t *testing.T) {
    m := bareManager(t)
    if err := m.insertVerifiedForTest(VerifiedAuthority{}); !errors.Is(err, ErrInvalidAuthority) { t.Fatal(err) }
}
```

Add bad signature, wrong/noncanonical `kid`, wrong issuer purpose/profile/source
operator, revoked/expired issuer, wrong service/name/RouteIntent fields, source
and target operator/edge, transport/port, route/lease/record/policy, TS
generation/thumbprint, grant expiry exact boundary, stale authority generation,
wrong checkpoint relation, extra/missing keys, nonpreferred CBOR, trailing data,
oversized/deep input, detached payload, unprotected headers, wrong alg, and
defensive-copy tests. Verify all frozen valid/invalid/mutation vectors that
apply to RouteGrant.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(VerifyRouteGrant|VerifiedAuthority|CBOR|COSE)' -count=1
```

Expected RED: verifier and sealed constructor do not exist.

- [ ] **Step 3: Implement minimal independent verification**

Port only the bounded preferred deterministic-CBOR subset and frozen RouteGrant
COSE Sign1 rules needed by Core v0.2. Keep provenance comments pointing to the
two reference files; do not import their `internal` packages or change them.
Use tag 18, attached payload, empty unprotected map, protected exact `alg=-8`
and opaque `kid` 1..64, empty external AAD, Ed25519, exact keys 0..16, maximum
grant lifetime 600 seconds, and caller-supplied issuer/profile trust. Verify
every expected binding before calling private `sealAuthority`; retain only
normalized immutable fields and the SHA-256 digest, not the parser tree.

- [ ] **Step 4: Prove GREEN and independent parity**

```powershell
gofmt -w internal/authority/cbor.go internal/authority/cose.go internal/authority/verifier.go internal/authority/verifier_test.go
go test ./internal/authority -run 'Test(VerifyRouteGrant|VerifiedAuthority|CBOR|COSE)' -count=1
go test ./internal/authority -count=1
Push-Location ..\..\interop\nbsr-go-peer; go test ./internal/authority ./internal/cbor -count=1; Pop-Location
```

Expected: production and independent-peer fixture suites pass without shared
runtime code. Any semantic disagreement is Outcome C and stops execution.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/cbor.go client/nbsr-go-client/internal/authority/cose.go client/nbsr-go-client/internal/authority/verifier.go client/nbsr-go-client/internal/authority/verifier_test.go
git commit -m "feat(go-client): seal independently verified route grants"
```

---

### Task 4: Freshness checkpoint and monotonic generation barrier

**Files:**
- Create: `client/nbsr-go-client/internal/authority/freshness.go`
- Create: `client/nbsr-go-client/internal/authority/generation.go`
- Test: `client/nbsr-go-client/internal/authority/freshness_test.go`
- Test: `client/nbsr-go-client/internal/authority/generation_test.go`
- Modify: `client/nbsr-go-client/internal/authority/manager.go`

**Interfaces:**
- Consumes: `CheckpointEvidenceVerifier`, `ProviderFreshness`, `FreshnessRequest`, `Clock`, `Observer`.
- Produces: `PublishFreshness`, `CaptureGeneration`, private `sealCheckpoint`, and `ValidateStillCurrent(GenerationSnapshot) error`; checkpoint state scoped by exact enrolled Source Operator/profile.

- [ ] **Step 1: Write failing semantic tests**

```go
func TestFreshnessExpiresAtExactBoundary(t *testing.T) {
    m := freshManager(t, checkpoint(7, 100, 200))
    if err := m.requireFreshLockedForTest(199); err != nil { t.Fatal(err) }
    if err := m.requireFreshLockedForTest(200); !errors.Is(err, ErrStaleFreshness) { t.Fatal(err) }
}

func TestGenerationAdvanceWinsBeforeFinalCheck(t *testing.T) {
    m := freshManager(t, checkpoint(7, 100, 200)); snap, _ := m.CaptureGeneration()
    publishCheckpoint(t, m, checkpoint(8, 110, 210))
    if err := m.ValidateStillCurrent(snap); !errors.Is(err, ErrStaleGeneration) { t.Fatal(err) }
}
```

Test wrong operator/profile, malformed/unverified claims rejection, zero/lower
generation, equal identical idempotence, equal conflicting checkpoint,
generation overflow, issued/fresh ordering, revoked-grant set bound/dedup/order,
credential/policy expiry precedence, expiration event once, immutable copies,
and a counting provider proving 10,000 local freshness/generation checks make
zero provider calls.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(Freshness|Generation|NoProviderCall)' -count=1
```

Expected RED: checkpoint and generation state are absent.

- [ ] **Step 3: Implement minimal freshness/generation state**

Call the evidence verifier outside `Manager.mu`; reacquire the lock, recheck
scope/current generation, reserve invalidation capacity, then atomically publish
the sealed checkpoint and generation. Exact expiry uses `now >= FreshUntil`.
Equal generation accepts only the identical checkpoint digest. Lower or
conflicting state is rollback. Copy/sort the bounded revocation digest set
before commit. Record events under lock and emit after unlock.

- [ ] **Step 4: Prove GREEN including race ordering**

```powershell
gofmt -w internal/authority/freshness.go internal/authority/generation.go internal/authority/freshness_test.go internal/authority/generation_test.go internal/authority/manager.go
go test ./internal/authority -run 'Test(Freshness|Generation|NoProviderCall)' -count=1
go test -race ./internal/authority -run 'TestGenerationAdvanceWinsBeforeFinalCheck' -count=50 -timeout=60s
```

Expected: PASS; no per-check provider call.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/freshness.go client/nbsr-go-client/internal/authority/generation.go client/nbsr-go-client/internal/authority/freshness_test.go client/nbsr-go-client/internal/authority/generation_test.go client/nbsr-go-client/internal/authority/manager.go
git commit -m "feat(go-client): enforce authority freshness generation"
```

---

### Task 5: Bounded grant cache and one-owner consumption lifecycle

**Files:**
- Create: `client/nbsr-go-client/internal/authority/cache.go`
- Test: `client/nbsr-go-client/internal/authority/cache_test.go`
- Modify: `client/nbsr-go-client/internal/authority/manager.go`

**Interfaces:**
- Consumes: sealed `VerifiedAuthority`, current checkpoint/generation, `Limits`.
- Produces: `Reservation`, `AuthorityHandle`, `ValidateForNewWork`, `Consume`, `Release`, `Quarantine`, `InvalidateGrant`, `InvalidateOlderThan`, `Usage`, and invariant validation.

- [ ] **Step 1: Write failing capacity and lifecycle tests**

```go
func TestConsumedGrantNeverReturnsAvailable(t *testing.T) {
    m, r, snap := reservedGrant(t)
    if _, err := m.Consume(r, AdmissionOwner{TSGeneration: r.key.TSGeneration, ChannelID: id16(1)}, snap, 99); err != nil { t.Fatal(err) }
    if err := m.Release(r); !errors.Is(err, ErrInvalidTransition) { t.Fatal(err) }
    if _, err := m.reserveKeyForTest(r.key); !errors.Is(err, ErrInvalidAuthority) { t.Fatal(err) }
}
```

Add below/exact/above entry and logical-byte caps, failed insertion atomicity,
accounting overflow, complete-key dimension table tests (service, canonical
intent, TS generation/thumbprint, operators/edges, profile, policy, device,
workload, generation), exact expiry, revoked/checkpoint invalidation, consumed
and ambiguous non-reuse, reservation ownership, wrong channel/TS, double
consume/release/quarantine, deterministic available-only eviction, immutable
handle, and `ValidateInvariants` deliberate-corruption detection.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(Cache|Grant|Consumed|Ambiguous|AuthorityKey|Invalidation)' -count=1
```

Expected RED: cache lifecycle is absent.

- [ ] **Step 3: Implement minimal bounded cache**

Use private lifecycle enum `available/reserved/consumed/quarantined/invalid` and
maps keyed by exact comparable `AuthorityKey` plus reservation ID. Canonicalize
variable target-edge data into its digest before key construction. Reserve
entry and logical bytes under one lock before insert. Evict only unreserved
available entries by earliest effective expiry then grant digest; never evict
live/reserved authority to hide capacity. `Release` returns a reservation to
available only before any ambiguous/remote-commit seam; `Quarantine` is
terminal. `Consume` performs the final local checkpoint, credential/policy,
generation, expiry, revocation, TS, and owner check in the same critical section.

- [ ] **Step 4: Prove GREEN**

```powershell
gofmt -w internal/authority/cache.go internal/authority/cache_test.go internal/authority/manager.go
go test ./internal/authority -run 'Test(Cache|Grant|Consumed|Ambiguous|AuthorityKey|Invalidation)' -count=1
go test -race ./internal/authority -run 'Test(Consumed|Ambiguous|Invalidation)' -count=20
```

Expected: PASS with exact accounting and no resurrection.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/cache.go client/nbsr-go-client/internal/authority/cache_test.go client/nbsr-go-client/internal/authority/manager.go
git commit -m "feat(go-client): add bounded one-use grant cache"
```

---

### Task 6: Bounded acquisition coalescing and provider orchestration

**Files:**
- Create: `client/nbsr-go-client/internal/authority/coalesce.go`
- Test: `client/nbsr-go-client/internal/authority/coalesce_test.go`
- Modify: `client/nbsr-go-client/internal/authority/manager.go`
- Modify: `client/nbsr-go-client/internal/authority/provider.go`

**Interfaces:**
- Consumes: `AuthorityProvider`, `Verifier`, complete `AcquireRequest`/`RenewRequest`, cache insertion.
- Produces: operational `Manager.Acquire` and `Manager.Renew`; bounded private `pendingCall` with one result channel closed once and waiter reference count.

- [ ] **Step 1: Write failing coalescing tests**

```go
func TestExactAcquisitionCoalescesOneProviderCall(t *testing.T) {
    provider := blockingProvider(); m := managerWith(t, provider)
    results := startCallers(t, 8, func() (Reservation, error) { return m.Acquire(context.Background(), requestA()) })
    provider.Release(validCandidate(t)); assertOneProviderCall(t, provider)
    assertEquivalentSuccessfulReservations(t, results)
}
```

Test every distinct key dimension does not coalesce, pending entry/byte cap,
waiter exact/overflow bound, caller cancellation without canceling remaining
owner, all-callers-cancel cleanup, provider failure wakes all deterministically,
verification failure caches nothing, generation changes during provider call,
manager close wakes waiters, no pending leak, observer-after-lock, and provider
reentrancy proving no provider call occurs under the manager lock.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(ExactAcquisition|Coalesc|Pending|Waiter|Provider)' -count=1
```

Expected RED: Acquire/Renew orchestration is absent.

- [ ] **Step 3: Implement bounded ownership**

Under lock, return a cache reservation or join/create one bounded pending call.
The elected owner unlocks, invokes provider, copies the candidate, resolves
freshness from already-local state, verifies independently, then relocks and
rechecks generation/scope before cache commit. Waiters select on the shared
closed result channel or their own context; no waiter goroutine is created.
The last canceled waiter marks abandonment, but the owner still quarantines any
ambiguous result and removes pending accounting. Renew uses the same machinery
with a distinct operation discriminator and previous-grant digest.

- [ ] **Step 4: Prove GREEN and race safety**

```powershell
gofmt -w internal/authority/coalesce.go internal/authority/coalesce_test.go internal/authority/manager.go internal/authority/provider.go
go test ./internal/authority -run 'Test(ExactAcquisition|Coalesc|Pending|Waiter|Provider)' -count=1
go test -race ./internal/authority -run 'Test(ExactAcquisition|Coalesc|Pending|Waiter|Provider)' -count=20 -timeout=90s
```

Expected: PASS; one provider call for exact concurrent requests and no leaked
pending entry.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/coalesce.go client/nbsr-go-client/internal/authority/coalesce_test.go client/nbsr-go-client/internal/authority/manager.go client/nbsr-go-client/internal/authority/provider.go
git commit -m "feat(go-client): coalesce bounded authority acquisition"
```

---

### Task 7: Bounded request-id and idempotency/ambiguity state

**Files:**
- Create: `client/nbsr-go-client/internal/authority/idempotency.go`
- Test: `client/nbsr-go-client/internal/authority/idempotency_test.go`
- Modify: `client/nbsr-go-client/internal/authority/manager.go`

**Interfaces:**
- Consumes: `RequestIDSource`, request canonical digest, operation discriminator, `Limits`, `Clock`.
- Produces: private `beginRequest`, `finishRequest`, `markAmbiguous`, and `expireRequests`; `RequestRecordSnapshot(RequestID) (RequestSnapshot, error)` for diagnostics with digests/status only.

- [ ] **Step 1: Write failing idempotency tests**

```go
func TestConflictingRequestIDReuseRejected(t *testing.T) {
    m := idempotencyManager(t); id := requestID(1)
    mustBeginRequest(t, m, id, digest(1))
    if err := m.beginRequestForTest(id, digest(2)); !errors.Is(err, ErrRequestConflict) { t.Fatal(err) }
}
```

Test exactly 128 bits, zero ID, injected deterministic generator, production
reader short/error handling, exact duplicate joins same identity, operation
discriminator conflict, bounded entry/byte retention below/exact/above,
deterministic expiry, same-expiry ordering, completed result digest copy,
timeout ambiguity quarantines associated reservation, ambiguous non-reuse,
generation invalidation, and no unbounded history after 4,096 cycles.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(RequestID|Idempot|Conflicting|Ambiguous|RequestRetention)' -count=1
```

Expected RED: request record state is absent.

- [ ] **Step 3: Implement minimal bounded state**

Key records by `(device ID, device generation, operation, RequestID)` and store
only canonical request digest, result/grant digest, compact status, authority
generation, and expiry. Exact duplicate returns the same pending/result
identity; same key with different digest is conflict. Capacity rejects before
provider work. Expiration never makes an old response reusable. Ambiguity marks
the linked grant/reservation quarantined in the same lock transaction.

- [ ] **Step 4: Prove GREEN**

```powershell
gofmt -w internal/authority/idempotency.go internal/authority/idempotency_test.go internal/authority/manager.go
go test ./internal/authority -run 'Test(RequestID|Idempot|Conflicting|Ambiguous|RequestRetention)' -count=1
go test -race ./internal/authority -run 'Test(Idempot|Ambiguous)' -count=20
```

Expected: PASS with exact retention bounds.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/idempotency.go client/nbsr-go-client/internal/authority/idempotency_test.go client/nbsr-go-client/internal/authority/manager.go
git commit -m "feat(go-client): model bounded authority idempotency"
```

---

### Task 8: Rollback floor abstraction and restart fail-closed gate

**Files:**
- Create: `client/nbsr-go-client/internal/authority/floor.go`
- Create: `client/nbsr-go-client/internal/authority/restart.go`
- Test: `client/nbsr-go-client/internal/authority/floor_test.go`
- Test: `client/nbsr-go-client/internal/authority/restart_test.go`

**Interfaces:**
- Consumes: `GenerationFloorStore`, `CheckpointEvidenceVerifier`, `Clock`, `Observer`.
- Produces: `MemoryGenerationFloorStore`, `RestartGate`, exact APIs above, and `ErrFloorNotFound`/`ErrFloorInvalid` typed errors.

- [ ] **Step 1: Write failing rollback/restart tests**

```go
func TestColdStartRequiresFreshness(t *testing.T) {
    gate := newGate(t, storedFloor(7))
    if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil { t.Fatal(err) }
    if gate.State() != RestartFreshnessRequired || !errors.Is(gate.RequireReady(), ErrNotReady) { t.Fatal(gate.State()) }
}

func TestNoDurableAPIAcceptsLiveAuthority(t *testing.T) {
    typ := reflect.TypeOf((*GenerationFloorStore)(nil)).Elem()
    forbidden := []reflect.Type{reflect.TypeOf(ProviderGrant{}), reflect.TypeOf(VerifiedAuthority{}), reflect.TypeOf(Reservation{}), reflect.TypeOf(AuthorityHandle{})}
    assertNoMethodConsumes(t, typ, forbidden)
}
```

Test floor increase, equal byte-identical idempotence, equal conflicting reject,
lower reject, wrong Source Operator/profile, malformed/oversized signed evidence,
defensive copies, store failure, no lock-held store call, missing floor policy,
invalid floor -> `FailClosed`, fresh checkpoint below floor, fresh checkpoint at
or above floor, mandatory post-restart freshness, state transitions, repeated
restart, and no RouteGrant/TS/SC/credit/stream/selectors in durable APIs or
serialized test state.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(Floor|ColdStart|Restart|NoDurableAPI|LiveAuthority)' -count=1
```

Expected RED: floor store and restart gate are absent.

- [ ] **Step 3: Implement minimal rollback model**

`Load` copies and validates the stored semantic floor, then always enters
`FreshnessRequired`; absence is allowed only for first enrollment generation
and still requires freshness. `AcceptFresh` verifies outside the gate lock,
rejects checkpoint generation below the floor, calls `StoreHigher` outside the
lock, then rechecks state and publishes `Ready`. Any corrupt/conflicting/lower
floor enters `FailClosed`. The in-memory store is deterministic test/fixture
code, not a filesystem or production durability claim.

- [ ] **Step 4: Prove GREEN and race safety**

```powershell
gofmt -w internal/authority/floor.go internal/authority/restart.go internal/authority/floor_test.go internal/authority/restart_test.go
go test ./internal/authority -run 'Test(Floor|ColdStart|Restart|NoDurableAPI|LiveAuthority)' -count=1
go test -race ./internal/authority -run 'Test(Floor|Restart)' -count=20
```

Expected: PASS; no live authority restore path exists.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/floor.go client/nbsr-go-client/internal/authority/restart.go client/nbsr-go-client/internal/authority/floor_test.go client/nbsr-go-client/internal/authority/restart_test.go
git commit -m "feat(go-client): enforce restart authority floor"
```

---

### Task 9: Pure finite retry and circuit decision model

**Files:**
- Create: `client/nbsr-go-client/internal/retry/doc.go`
- Create: `client/nbsr-go-client/internal/retry/errors.go`
- Create: `client/nbsr-go-client/internal/retry/policy.go`
- Test: `client/nbsr-go-client/internal/retry/policy_test.go`

**Interfaces:**
- Consumes: no authority package; callers supply the exact `Input` above.
- Produces: `Class`, `Input`, `Decision`, `Reason`, typed errors, and pure `Decide`.

- [ ] **Step 1: Write failing decision-table tests**

```go
func TestApplicationPayloadIsNeverRetried(t *testing.T) {
    in := validInput(); in.ApplicationPayloadWritten = true
    got, err := Decide(in)
    if err != nil || got.Retry || got.TerminalReason != ReasonPayloadWritten { t.Fatalf("%#v %v", got, err) }
}
```

Use a table covering retryable/conditional/terminal, condition unchanged,
attempt zero/exact/exhausted, deadline exact/past, circuit open, retry-after
short/long, zero/max jitter, exponential shift saturation, arithmetic overflow,
maximum delay clamp, cancellation represented as terminal input, and 10,000
decisions with no sleep/goroutine.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/retry -run 'Test(Retry|ApplicationPayload|Deadline|Circuit|Backoff|Jitter)' -count=1
```

Expected RED: retry package is absent.

- [ ] **Step 3: Implement minimal pure policy**

Validate inputs, compute saturating exponential backoff, apply deterministic
signed jitter from `JitterSample` and `JitterPermille`, honor the larger bounded
retry-after hint, clamp strictly below remaining deadline, and return a typed
terminal reason. Import no `time.Sleep`, network package, authority manager, or
application payload type.

- [ ] **Step 4: Prove GREEN**

```powershell
gofmt -w internal/retry/*.go
go test ./internal/retry -count=1
go test -race ./internal/retry -count=1
go vet ./...
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/retry
git commit -m "feat(go-client): add finite retry decisions"
```

---

### Task 10: Fixture provider and full authority-manager integration

**Files:**
- Create: `client/nbsr-go-client/internal/authority/fixture_provider.go`
- Test: `client/nbsr-go-client/internal/authority/manager_test.go`
- Modify: `client/nbsr-go-client/internal/authority/manager.go`
- Modify: `client/nbsr-go-client/internal/authority/observer.go`

**Interfaces:**
- Consumes: all identity/authority/retry primitives, frozen signed RouteGrant fixtures.
- Produces: the fixture types and constructors below, deterministic scripted Acquire/Renew/Freshness/Close behavior, and complete Manager orchestration.

```go
type FixtureProviderLimits struct { MaxEntries int; MaxBytes uint64; MaxCalls uint64 }
type FixtureGrant struct { Operation uint8; RequestDigest [32]byte; Result ProviderGrant; Err error }
type FixtureFreshness struct { RequestDigest [32]byte; Result ProviderFreshness; Claims CheckpointClaims; Err error }
func NewFixtureProvider(FixtureProviderLimits, []FixtureGrant, []FixtureFreshness) (*FixtureProvider, error)
func NewFixtureCheckpointVerifier([]FixtureFreshness) (CheckpointEvidenceVerifier, error)
```

- [ ] **Step 1: Write failing end-to-end local tests**

```go
func TestFixtureAcquireVerifyReserveConsume(t *testing.T) {
    m, req := fixtureManager(t)
    r, err := m.Acquire(context.Background(), req); if err != nil { t.Fatal(err) }
    snap, _ := m.CaptureGeneration()
    if err := m.ValidateForNewWork(r, snap, now(t)); err != nil { t.Fatal(err) }
    if _, err := m.Consume(r, owner(req.Key.TSGeneration), snap, now(t)); err != nil { t.Fatal(err) }
}
```

Test provider never mints/signs grants, unknown fixture request, Acquire/Renew
script separation, copied raw bytes, bounded scripts/calls, closed provider,
freshness then acquire ordering, Source Operator-only trust, federation inputs
absent from public client API, policy denial/provider unavailable translation,
observer event order/cardinality/redaction, close idempotence, provider close
outside lock, no App Stream/provider method, and no changes to `corestate`.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(Fixture|Manager|Observer|SourceOperator|Federation)' -count=1
```

Expected RED: fixture provider and completed orchestration are absent.

- [ ] **Step 3: Implement fixture-only provider and integration**

The provider indexes pre-signed copied fixtures by exact request digest and
operation, enforces entry/byte/call bounds, and returns scripted typed errors.
It has no signer, issuer private key, network import, federation type, HTTP
client, or goroutine. Complete Manager event emission and close behavior. Add
compile-time interface assertions. Keep ACP checkpoint evidence semantic and
fixture-verifier-specific; defining its production encoding is `TRANCHE 2B —
REQUIRES SEPARATE PROTOCOL APPROVAL`.

- [ ] **Step 4: Prove GREEN**

```powershell
gofmt -w internal/authority/fixture_provider.go internal/authority/manager.go internal/authority/observer.go internal/authority/manager_test.go
go test ./internal/authority -run 'Test(Fixture|Manager|Observer|SourceOperator|Federation)' -count=1
go test -race ./internal/authority -count=1
```

Expected: PASS with bounded deterministic events and no networking.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/fixture_provider.go client/nbsr-go-client/internal/authority/manager.go client/nbsr-go-client/internal/authority/observer.go client/nbsr-go-client/internal/authority/manager_test.go
git commit -m "test(go-client): add fixture authority provider"
```

---

### Task 11: Adversarial concurrency, lifecycle fuzzing, and local baselines

**Files:**
- Create: `client/nbsr-go-client/internal/authority/concurrency_test.go`
- Create: `client/nbsr-go-client/internal/authority/fuzz_test.go`
- Create: `client/nbsr-go-client/internal/authority/benchmark_test.go`
- Modify: `client/nbsr-go-client/internal/authority/doc.go`
- Modify: `client/nbsr-go-client/internal/identity/doc.go`
- Modify: `client/nbsr-go-client/internal/retry/doc.go`

**Interfaces:**
- Consumes: complete Tranche 2A API.
- Produces: deterministic lock-step race tests, bounded lifecycle fuzz target, baseline-only benchmarks, and package boundary documentation.

- [ ] **Step 1: Write failing adversarial/documentation tests**

```go
func TestGenerationAdvanceLinearizesBeforeConsume(t *testing.T) {
    m, r, snap, advance := preparedRace(t)
    advance.CommitBeforeFinalCheck()
    if _, err := m.Consume(r, owner(r.key.TSGeneration), snap, 99); !errors.Is(err, ErrStaleGeneration) { t.Fatal(err) }
}

func FuzzAuthorityLifecycle(f *testing.F) {
    f.Add([]byte{0, 1, 2, 3, 4, 5, 6, 7})
    f.Fuzz(func(t *testing.T, ops []byte) {
        if len(ops) > 256 { ops = ops[:256] }
        m := fuzzManager(t); runAuthorityOps(t, m, ops)
        if err := m.ValidateInvariants(); err != nil { t.Fatal(err) }
    })
}
```

Add both deterministic orderings for generation publish vs final check,
invalidate vs reserve, consume vs quarantine, cancel vs provider completion,
close vs acquire, and floor store vs fresh publication. Use channels/barriers,
never sleeps. Fuzz only bounded semantic operations and accept only documented
typed errors. Add documentation tests requiring all exclusions and the exact
baseline label.

- [ ] **Step 2: Prove RED**

```powershell
go test ./internal/authority -run 'Test(GenerationAdvanceLinearizes|Concurrent|PackageDocumentation)' -count=1
```

Expected RED: race seams, fuzz runner, benchmarks, and final docs are absent.

- [ ] **Step 3: Implement test seams, docs, and benchmarks**

Keep lock-step seams in same-package test files. Cap fuzz state at 8 cache
entries, 4 pending calls, 8 request records, 8 waiters, and 256 operations.
Benchmarks named `BenchmarkBaselineOnlyValidityCheck`, `CacheLookup`,
`GenerationCheck`, `FreshnessLookup`, and `RetryDecision` use fixed valid state,
`ReportAllocs`, and no target. Document that measurements are local observations
only and that hot-path checks do no I/O/provider call/wire parsing.

- [ ] **Step 4: Prove GREEN, race, fuzz, and baselines**

```powershell
gofmt -w internal/authority/*.go internal/identity/*.go internal/retry/*.go
go test ./... -count=1
go test -race ./... -count=1
go test ./internal/authority -run '^$' -fuzz '^FuzzAuthorityLifecycle$' -fuzztime=10s
go test ./internal/authority ./internal/retry -run '^$' -bench '^BenchmarkBaselineOnly' -benchmem -count=3
```

Expected: PASS; benchmark output carries no acceptance claim.

- [ ] **Step 5: Commit**

```powershell
git add client/nbsr-go-client/internal/authority/concurrency_test.go client/nbsr-go-client/internal/authority/fuzz_test.go client/nbsr-go-client/internal/authority/benchmark_test.go client/nbsr-go-client/internal/authority/doc.go client/nbsr-go-client/internal/identity/doc.go client/nbsr-go-client/internal/retry/doc.go
git commit -m "test(go-client): add authority adversarial baselines"
```

---

### Task 12: Full Tranche 2A acceptance and closure record

**Files:**
- Create: `docs/reviews/production-go-client-tranche2a-identity-authority-core.md`
- Modify only if a gate reveals a Tranche 2A defect: `client/nbsr-go-client/internal/identity`, `internal/authority`, or `internal/retry` files.

**Interfaces:**
- Consumes: complete implementation and repository integrity gates.
- Produces: evidence record with exact commands, PASS/FAIL/INCONCLUSIVE, counts, plan SHA, final SHA, protected refs, changed-path audit, and explicit non-claims.

- [ ] **Step 1: Write literal RED closure record**

Create the review with every gate below recorded as `FAIL — not yet executed`,
including an expected/observed/result column and no prefilled success count.

- [ ] **Step 2: Prove RED**

```powershell
if (rg -n 'FAIL — not yet executed' docs/reviews/production-go-client-tranche2a-identity-authority-core.md) { exit 1 }
exit 0
```

Expected RED: markers print and command exits 1.

- [ ] **Step 3: Run exact acceptance commands**

From `client/nbsr-go-client`:

```powershell
gofmt -w internal/corestate/*.go internal/identity/*.go internal/authority/*.go internal/retry/*.go
go test ./... -count=1
go test -race ./... -count=1
go vet ./...
go test ./internal/identity -run 'Test(Purpose|Signer|Identity|Workload|TSProof|LocalState)' -count=1
go test ./internal/authority -run 'Test(Verify|Cache|Consumed|Ambiguous|Freshness|Generation|Floor|ColdStart|Coalesc|Pending|Request|NoProviderCall|NoDurableAPI)' -count=1
go test ./internal/authority -run '^$' -fuzz '^FuzzAuthorityLifecycle$' -fuzztime=10s
go test ./internal/authority ./internal/retry -run '^$' -bench '^BenchmarkBaselineOnly' -benchmem -count=3
```

From repository root:

```powershell
git diff --check
$planPath = 'docs/superpowers/plans/2026-08-14-production-go-client-tranche2a-identity-authority-core.md'
$planCommit = git log -1 --format=%H -- $planPath
if ([string]::IsNullOrWhiteSpace($planCommit)) { throw 'plan baseline is not committed' }
git diff --name-only $planCommit
git diff --exit-code $planCommit -- client/nbsr-go-client/internal/corestate interop/nbsr-go-peer verifiers/federation-go crates/nbsr-transport docs/protocol vectors evidence
rg -n 'net/http|http2|quic|tls|windows|registry|tpm|keyring' client/nbsr-go-client/internal/identity client/nbsr-go-client/internal/authority client/nbsr-go-client/internal/retry
rg -n 'TRANCHE 2B — REQUIRES SEPARATE PROTOCOL APPROVAL' client/nbsr-go-client/internal/authority docs/reviews/production-go-client-tranche2a-identity-authority-core.md
python -m pytest tests/performance/test_session_rotation_model.py tests/test_p2d_stream_credit.py -q
python -m ruff check .
git rev-parse main
git rev-parse origin/main
```

Expected: Go gates exit 0; the first `rg` finds only explicit exclusions/test
assertions and no networking/platform implementation imports; the Tranche 2B
marker exists for unapproved checkpoint/wire work; protected-path diff is empty;
focused Python safety tests and Ruff pass; local/remote `main` both equal
`1938154d498b32d81a3564319969430644e8a688`. Record exact observed test counts
and benchmark data without converting baselines into targets.

- [ ] **Step 4: Prove GREEN closure and staged scope**

```powershell
if (rg -n 'FAIL — not yet executed' docs/reviews/production-go-client-tranche2a-identity-authority-core.md) { exit 1 }
git diff --check
git status --short
```

Expected: no pending marker; only intended Tranche 2A packages and closure
review are modified.

- [ ] **Step 5: Commit closure**

```powershell
git add client/nbsr-go-client/internal/identity client/nbsr-go-client/internal/authority client/nbsr-go-client/internal/retry docs/reviews/production-go-client-tranche2a-identity-authority-core.md
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
git commit -m "test(go-client): close identity authority core tranche"
```

Do not push implementation until human review explicitly authorizes publication.

---

## Exact Tranche 2A acceptance gate

- [ ] `go test ./... -count=1` passes in `client/nbsr-go-client` with exact observed counts recorded.
- [ ] `go test -race ./... -count=1` passes.
- [ ] `go vet ./...` passes.
- [ ] Identity purpose separation, wrong generation, missing identity, and no raw private-key export tests pass.
- [ ] Frozen valid RouteGrant fixture passes; bad signature, `kid`, purpose, service, intent, TS, operator/profile, expiry, and stale-generation cases fail closed.
- [ ] No exported API or boolean convention can convert provider candidates into sealed authority.
- [ ] Complete cache key prevents cross-service and cross-TS reuse.
- [ ] Entry and logical-byte cache capacity below/exact/above tests pass.
- [ ] Pending entry/byte and waiter below/exact/above tests pass.
- [ ] Consumed, ambiguous, revoked, expired, stale-checkpoint, and stale-generation grants never return to available.
- [ ] Exact checkpoint expiry (`now == FreshUntil`) fails.
- [ ] Local hot-path validation performs no provider call, I/O, wire parse, or background work.
- [ ] Generation/revocation update ordered before final check rejects stale work under the race detector.
- [ ] Request IDs are exactly 128 bits; conflicting reuse rejects; retention is bounded; ambiguity quarantines authority.
- [ ] Retry decisions have finite attempts/deadline/backoff/jitter/circuit behavior and never retry application payload.
- [ ] Signed generation floor increases monotonically; equal identical is idempotent; equal conflicting/lower rejects.
- [ ] Cold start requires fresh enrolled-ACP validation and cannot restore live authority.
- [ ] Durable APIs accept no RouteGrant, TS, SC, credit, stream, selector, reservation, or cache type.
- [ ] Fixture provider is finite, deterministic, pre-signed-input-only, and cannot mint production authority.
- [ ] Observer events are bounded-cardinality and contain no keys, raw grants, service names, or payload.
- [ ] No provider/verifier/observer/store callback occurs while an authority mutation lock is held.
- [ ] No unbounded map, queue, slice, waiter set, request history, retry loop, goroutine, or cleanup list exists.
- [ ] Ten-second bounded fuzzing finds no panic, capacity breach, resurrection, rollback, or invariant failure.
- [ ] Baselines are labeled `BASELINE ONLY — NOT ACCEPTANCE CAPACITY` and make no throughput claim.
- [ ] `internal/corestate` has no diff from the plan baseline and its full tests remain green.
- [ ] `interop/nbsr-go-peer`, federation verifier, Rust transport, protocol, vectors, and P1F/P2D evidence have no diff.
- [ ] No live ACP/HTTP/HTTP2, enrollment wire, resolver, QUIC/TLS TS, SC wire, credit wire, P2D, rotation, platform, federation negotiation, TPM, or WAN/demo implementation exists.
- [ ] `git diff --check`, changed-path audit, focused Python safety tests, and Ruff pass.
- [ ] Local and remote `main` remain `1938154d498b32d81a3564319969430644e8a688`.

## Tranche 2B and later exclusions

The following are explicitly excluded and, where they need wire semantics, are
`TRANCHE 2B — REQUIRES SEPARATE PROTOCOL APPROVAL`: live HTTP/1.1 or HTTP/2 ACP
transport; enrollment messages; ACP deterministic-CBOR request/result/checkpoint
schemas; message numbers/registries; live checkpoint/response COSE exchange;
server idempotency storage; push transport; live revocation delivery; production
issuer/profile distribution; and ACP authentication wire proof. Also excluded:
resolver/DNS, Synthetic-IP interception, QUIC/TLS TS establishment, SC wire
admission, Stream Credit/P2D changes, rotation, Windows/Linux/router adapters,
client federation negotiation, operator routing, TPM/filesystem/OS keystores,
WAN/demo work, and production performance optimization.

## Plan self-review

- Spec coverage: all eleven Tranche 2A components map to Tasks 1-11; Task 12 owns exact closure evidence.
- Package cohesion: identity and retry are independent; all mutually atomic authority state uses one package and one documented manager lock.
- Type consistency: provider candidates, sealed authority/checkpoint, cache reservation, consumed handle, generation snapshot, and floor types have one definition and matching signatures throughout.
- Scope: no runtime network, ACP/enrollment wire, TS/SC/credit, resolver/platform, federation-client, or TPM implementation is planned.
- Placeholder scan: the plan contains no unresolved placeholder or undefined production ACP wire type; fixture checkpoint verification is an explicit injected seam.
- TDD: every implementation task has literal RED, minimal GREEN, focused regression, and an isolated commit.
