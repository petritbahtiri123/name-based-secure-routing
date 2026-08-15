# Tranche 2B ACP Wire Semantics (Acquire / Renew / Freshness) — Draft

Status: DRAFT — HUMAN DECISIONS PENDING  
Tranche: 2B

Scope:

- only RouteGrant **Acquire**, **Renew**, and **Freshness**
- HTTP/2 over TLS 1.3 transport assumption only
- no enrollment wire design
- no protocol/schema changes beyond this ACP wire contract

Assumptions preserved from existing implementation:

- client talks only to its enrolled Source Operator ACP
- `AuthorityProvider` remains transport-neutral
- deterministic CBOR and COSE Sign1 are the canonical authority encodings
- protected `kid`, Ed25519, SHA-256, and existing key-purpose separation stay unchanged
- 128-bit request IDs stay unchanged
- no ACP call per Application Stream
- freshness/generation/rollback decisions remain unchanged

## 1) Acquire RouteGrant

### Request fields (wire-level)

- `device_identity`: current `identity.DeviceIdentity` values
  - `id`, `source_operator_id`, `credential_generation`, `credential_not_before`,
    `credential_expires_at`, `signing_key` (`id`, `purpose`, `generation`,
    `thumbprint`)
- `workload` (optional): `WorkloadPolicyContext` fields
  - `subject_digest`, `policy_generation`, `policy_expires_at`
  - included only when workload mode is enabled
- `authority_key` fields from `AuthorityKey`
  - `intent_digest`, `service_digest`, `source_operator`, `source_edge`,
    `target_operator`, `target_edge_set_digest`, `profile`, `transport`,
    `port`, `device_id`, `device_generation`, `ts_generation`,
    `proof_thumbprint`, `policy_hash`, `policy_generation`,
    `authority_generation`
- `route_intent` fields from `RouteIntent`
  - `canonical`, `digest`, `service_identity`, `source_operator`, `source_edge`,
    `target_operator`, `target_edges`, `transport`, `port`, `record_sequence`,
    `policy_hash`, `route_id`, `lease_id`, `expires_at`
- `request_id` (16-byte)
- `deadline_unix`

### Response fields

- `cose_sign1` (enveloped RouteGrant result, signed bytes)
- `cose_profile` (ACP profile string used to resolve route grant issuer)
- `authority_generation`
- `checkpoint_digest`

### Signed fields

- Signed authority content must remain the same canonical RouteGrant bytes (`cose_sign1`).
- `AuthorityProvider`-level metadata (`authority_generation`, `checkpoint_digest`) is
  carried separately as binding/routing context and is **not** a new signature target.
- Signature verification is still done by existing Go verifier against the CBOR/COSE
  RouteGrant semantics.

### Binding requirements

- Request fields are bound to local request context before provider call:
  - `request.Intent.Digest == request.Key.IntentDigest`
  - `request.Workload`/`request.Key.Workload_*` consistent when workload is present
  - `request.Key.Profile` matches the request profile context selected by enrollment
  - canonical `target_edges` set ordering and digest must match
  - request signature/authenticator ties this exact request payload to the caller
- Response binding checks (client-side verifier) require:
  - RouteGrant payload bindings match the exact request key/intent
  - `response.authority_generation == request.key.authority_generation`
  - `response.profile == request.key.profile`
  - `response.checkpoint_digest == current_freshness_checkpoint.digest`

### Idempotency semantics

- Client continues 128-bit `RequestID` exactly once for retries of the same request
  intent.
- Duplicate request key with identical computed request digest must be treated as
  equivalent and may be reused from request cache/response coalescing.
- Same key + different digest is `ErrRequestConflict`.
- If transport deadline/cancel happens after a provider operation has committed in
  memory, the request becomes **ambiguous** and may not be reused as live grant
  authority; ambiguity is quarantined.

### Timeout / ambiguity behavior

- `DeadlineUnix` is the operation boundary at request-level.
- Context cancellation before completion returns client context error or `ErrExpired`
  (never converts to grant).
- Cancellation after provider call may only yield `ErrRequestAmbiguous` until local
  cache/commit state is deterministic.
- Ambiguous result paths never permit silent reuse of returned signed bytes.

### Semantic errors

- transport failures are separate (timeouts/TLS/unreachable/unauthenticated)
- semantic failures return explicit local/authority errors:
  - policy/validation deny
  - stale generation/freshness
  - unknown identity / invalid binding
  - issuer/signature failures
- any semantic denial must remain explicit and non-fallback.

### Maximum / bounded resources

- Request/response are bounded by existing authority limits and request validation:
  - `Limits.MaxRequestBytes`, `Limits.MaxServiceIdentityBytes`
  - `Limits.MaxGrantBytes`, `Limits.MaxCacheEntries`, `Limits.MaxPending`,
    `Limits.MaxWaitersPerPending`, `Limits.MaxRequestRecords`
- all serialized request/response blobs are copied before verifier use and bounded
  before state mutation.

### Version / downgrade behavior

- protocol/version/profile mismatch must fail closed, with no downgrade/fallback.
- exact ACP profile/version values are required here but intentionally not invented
  by this draft.

## 2) Renew RouteGrant

### Request fields (wire-level)

- all Acquire fields above
- plus `previous_grant_digest` (the currently consumed grant being replaced)

### Response fields

- same response envelope fields as Acquire
- `previous_grant` is not expected to repeat in response; only confirmation fields
  above are returned

### Signed fields

- renewed authority remains only the signed RouteGrant bytes (`cose_sign1`)
- renew is always a fresh request and freshly signed response; no local extension
  of prior bytes

### Binding requirements

- Must carry the exact same `authority_key`/`route_intent` context as the replaced
  flow and a matching `previous_grant` claim.
- verifier checks full RouteGrant binding against the same local request key and
  current checkpoint before replacement.
- replacement must consume and retire predecessor atomically.

### Idempotency semantics

- same 128-bit idempotency model as Acquire, but keyed by `previous_grant_digest`
  as part of the operation namespace.
- exact retries can reuse the same cached terminal response/result; conflict
  differs by namespace or digest.
- ambiguous renew completion must be treated as unresolved authority until the local
  cache confirms final outcome.

### Timeout / ambiguity behavior

- uses same `DeadlineUnix` and ambiguity/quarantine behavior as Acquire
- if renew response ambiguity occurs after provider action, local cache state owns
  the fail-closed rule and prevents accidental reuse

### Semantic errors

- same transport/auth categories as Acquire
- additional semantic outcomes for renew path:
  - predecessor mismatch / replay conflict
  - stale generation / stale checkpoint / no-longer-valid predecessor
  - policy deny on reauthorization context

### Maximum / bounded resources

- same bounded transport/request/response limits as Acquire
- pending renewal scope is also bounded by existing `MaxPending` and `MaxPendingBytes`

### Version / downgrade behavior

- same fail-closed version policy as Acquire
- renew must not be treated as an exception to version/profile mismatch rules

## 3) Freshness

### Request fields (wire-level)

- `source_operator`
- `profile`
- `device_id`
- `device_generation`
- `after_generation` (optional query cursor for server-side delta behavior)
- `after_checkpoint` (optional cursor)
- `deadline_unix`

### Response fields

- `cose_checkpoint_evidence` (signed checkpoint evidence / envelope bytes)
- response binding context:
  - `source_operator`, `profile`

### Signed fields

- freshness evidence content must remain signed by existing freshness checkpoint
  signer semantics in the existing verifier stack (COSE/CBOR canonical input).
- RouteGrant content is not signed by freshness response.

### Binding requirements

- `source_operator` + `profile` must match current enrollment target
- evidence must be independently verified and then sealed:
  - strict freshness time window
  - strictly increasing generation unless same generation and identical digest
  - monotonic rollback rejection
- stale freshness must block authority-using flows (`ErrStaleFreshness`).

### Idempotency semantics

- freshness is not 128-bit idempotent in the same sense as grant operations; it is
  bounded polling + local replay gating.
- repeated unchanged freshness payloads are optional cache-friendly on the freshness
  side; duplicates that regress generation must be rejected.

### Timeout / ambiguity behavior

- deadline is transport-level bound and does not create grant authority on failure
- ambiguous freshness RPC responses do not grant authority and keep local state fail-closed

### Semantic errors

- transport errors are distinct from freshness semantic failures
- semantic freshness failures include stale/revoked/rollback/expiry conditions
- any freshness soft-failure is not equivalent to a successful checkpoint advance

### Maximum / bounded resources

- `Limits.MaxCheckpointEvidenceBytes` bounds signed freshness evidence blob.
- checkpoint revoked-digest set length is bounded by `Limits.MaxCacheEntries`.
- no per-Application-Stream freshness call in steady state.

### Version / downgrade behavior

- freshness failure, downgrade, and out-of-band fallback behavior remains fail-closed.
- no implicit fallback to stale/legacy freshness when version/context checks fail.

## Human Decisions Required Before Freeze

- **HUMAN_DECISION_REQUIRED:** response signature envelope fields (exact envelope
  field names and additional metadata) are not yet frozen.
- **HUMAN_DECISION_REQUIRED:** freshness response metadata (minimal required fields and
  inclusion set, especially checkpoint sequence/timestamp fields).
- **HUMAN_DECISION_REQUIRED:** version/downgrade exact values, registry labels, and
  failure codes.
- **HUMAN_DECISION_REQUIRED:** idempotency namespace and retry contract beyond the
  current client-local model (replay horizon, same-request reuse, duplicate policy for
  transient transport vs app-layer retries).
- **HUMAN_DECISION_REQUIRED:** request-auth challenge/signature details (challenge
  shape, signing input, and verifier binding policy).
- **HUMAN_DECISION_REQUIRED:** concrete budget numbers for all transport/resource budgets.
- **HUMAN_DECISION_REQUIRED:** endpoint/path mapping from operations to concrete
  HTTP/2 routes and whether path/versioned URI is part of protocol negotiation.

B — this draft preserves existing Go-core semantics and keeps the seven unresolved items
above explicit for human approval.
