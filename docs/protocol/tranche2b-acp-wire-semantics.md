# Tranche 2B ACP Wire Semantics (Acquire / Renew / Freshness)

Status: FROZEN — APPROVED FOR IMPLEMENTATION
Tranche: 2B

Scope:

- only RouteGrant **Acquire**, **Renew**, and **Freshness**
- HTTP/2 over TLS 1.3 transport only
- no enrollment wire design
- no implementation/runtime changes in this task
- client uses only its enrolled Source Operator ACP
- existing `AuthorityProvider` boundary, RouteIntent/AuthorityKey/DeviceIdentity/WorkloadPolicyContext semantics, RouteGrant/Freshness verification, RequestID/idempotency, and generation/floor semantics are preserved and treated as fixed inputs

This document reflects approved decisions #1–#7 and expresses the ACP wire profile in an implementation-ready, minimal form.

## 0) Decision status

- Decision #1: **APPROVED** — mandatory minimal signed ACP result envelope
- Decision #2: **APPROVED** — minimal metadata only; no duplicated authority/routing semantics in result envelope
- Decision #3: **APPROVED** — protocol_version=1, profile bound, no fallback downgrade
- Decision #4: **APPROVED** — deadline-scoped server-side idempotency
- Decision #5: **APPROVED** — DeviceIdentity request authentication + TLS 1.3 + no challenge flow
- Decision #6: **APPROVED** — fixed profile ceilings and quotas
- Decision #7: **APPROVED** — single endpoint `/acp/authority`, operation from signed canonical payload

## 1) Repository alignment check against implementation-facing models

The wire payloads below are derived from existing internal types:

- `AcquireRequest` and `RenewRequest` define authority key, route intent, device identity, optional workload, request ID, and deadline.
- `FreshnessRequest` defines source/profile/device identity scope, continuity cursor fields, and deadline.
- `AuthorityProvider` already exposes exactly `Acquire()`, `Renew()`, and `Freshness()` call points.
- `RouteIntent`, `AuthorityKey`, `RouteGrant`, `CheckpointClaims`, `VerifiedCheckpoint` define the existing verification and binding surface.
- `RequestID` and request-idempotency logic are already defined in local Core.
- `GenerationFloor` behavior (restart/rollback) remains unchanged.

## 2) HTTP/2 transport profile

- `POST /acp/authority` is the only route for all three operations.
- Operation is selected by the authenticated canonical `operation` field in the request envelope.
- Request path/method are transport-only; no security semantics in URL path/query.
- No operation-specific paths.
- No URL protocol/version/fallback/profile/identity/challenge parameters.
- One unary HTTP/2 request/response per RPC-style call:
  - request body bounded by operation limits
  - response body bounded by operation limits
  - no unbounded request-body streaming
  - no unbounded response streaming
- TLS 1.3 is mandatory. No cleartext ACP.
- DeviceIdentity challenge/preflight is not used in normal operations.

## 3) Canonical message model and signing boundary

### 3.1 Canonical request payload and boundary

`ACPRequestPayload` is the canonical payload object for an ACP operation.

- It is an operation payload map containing common envelope fields and operation-specific fields.
- It is encoded as **deterministic CBOR** according to the same bounded decoding/encoding rules already used in this repository.
- Encoding rules are applied before COSE signing and before request digest computation.
- No indefinite-length items.

The HTTP request body MUST be the full COSE Sign1 byte string over that exact canonical payload.

`request_digest` is `SHA-256` over the exact canonical `ACPRequestPayload` bytes (not over the COSE wrapper).

ACP request/response map keys are fixed unsigned integers. Integer-key
assignment is documented in the final ACP schemas; no textual map keys are
allowed in release-grade wire objects.
Integer keys are scoped to each specific ACP schema map; reusing small integer
values in one map does not imply global semantic reuse across other maps.

### 3.2 Request authentication boundary (Decision #5)

- Request identity is authenticated by application-layer DeviceIdentity purpose `PurposeDeviceACPRequest`.
- TLS 1.3 transport is mandatory and server-authenticated.
- mTLS MAY be deployment hardening only; it never replaces application-layer `PurposeDeviceACPRequest` authentication.
- TS proof remains separate from DeviceIdentity ACP request authentication and retains its independent purpose and semantics.
- DeviceIdentity key proves request possession by signing the exact canonical `ACPRequestPayload` bytes with COSE Sign1.
- COSE Sign1 protected header requirements:
  - `alg = -8` (Ed25519 signature)
  - non-empty protected `kid` (1..64 bytes), opaque to protocol
- The signature-domain must include the DeviceIdentity purpose binding (current signer behavior binds `Purpose...` in the signed input before Ed25519 signing).
- Transport headers (including TLS metadata) are transport-only and never part of the signed/hashed payload.

`request_signature` MUST NOT be a field inside `ACPRequestPayload`; the COSE envelope is the HTTP body.

### 3.3 Signed result boundary

`ACPResultPayload` is the canonical response payload object.

- It is encoded as deterministic CBOR with the same repository rules.
- The HTTP response body is COSE Sign1 over the exact canonical `ACPResultPayload`.
- The outer signature therefore binds both the canonical result envelope and the
  embedded `artifact` bytes for whichever terminal decision is encoded there.
- Inner RouteGrant/freshness artifact signatures remain independently verified
  using their existing trust paths and semantics.

### 3.4 ACP result signer purpose

Use a dedicated operator trust purpose for the outer ACP Result Envelope only.

- `PurposeDeviceACPRequest` remains request-only and is unchanged.
- The ACP result COSE envelope is signed by the Source Operator with a dedicated
  federation/operator trust purpose:
  - `nbsr/federation/registry.py` `KeyPurpose.ACP_RESULT_SIGNING`
  - applied registry value: `15` (`FEDERATION_TRANSPORT` remains `14`)
- This purpose signs only the **outer** ACP result envelope and does **not**
  replace or alter inner artifact semantics:
  - RouteGrant inner artifact verification stays on existing route-grant issuer/purpose behavior.
  - Freshness/checkpoint evidence verification stays on existing freshness evidence trust paths.
  - revocation/federation evidence remain in their existing trust domains.
- This purpose is operator-side (`federation` domain); do not add `PurposeACPResult`
  to `client/nbsr-go-client/internal/identity`.

This keeps minimal domain separation while preserving all existing Ed25519/CBOR/COSE semantics and `identity.Purpose` checks.

## 4) ACP request envelope and integer keys

Common request fields are present for all operations:

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Inside signed boundary |
|---|---|---|---|---|---|---|
| `0` | `protocol_version` | `uint` | yes | fixed protocol binding; must equal `1` | exact `1` | yes |
| `1` | `operation` | `text` | yes | one of `acquire_route_grant` \| `renew_route_grant` \| `freshness` | fixed set | yes |
| `2` | `request_id` | `bytes16` | yes | 128-bit replay-bounded actor request identity | exactly 16 bytes | yes |
| `3` | `deadline_unix` | `uint` | yes | request validity window | must satisfy per-operation bounded-request policy | yes |
| `4` | `source_operator` | `text` | yes | scope binding; must match authority envelope | textual-ID constraints | yes |
| `5` | `profile` | `text` | yes | profile binding; no fallback | existing text constraints | yes |
| `6` | `request_payload` | `map[uint]any` | yes | operation-specific envelope for the selected operation | bounded by operation policy ceilings | yes |

### 4.1 Acquire request payload (selected by `operation = acquire_route_grant`)

`request_payload` is a map for Acquire:

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Inside signed boundary |
|---|---|---|---|---|---|---|
| `0` | `key` | map | yes | authority key scope for this request | per-field constraints from `AuthorityKey` | yes |
| `1` | `intent` | map | yes | route intent and route-grant binding payload | bounded by request body policy | yes |
| `2` | `device` | map | yes | request device/auth context | per-field constraints from `DeviceIdentity` | yes |
| `3` | `workload` | map | optional | policy workload binding; must match `key.workload_*` when present | required as a set if present | yes |

#### 4.1.1 AuthorityKey payload map (`request_payload[0]`)

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Signed |
|---|---|---|---|---|---|---|
| `0` | `intent_digest` | `bytes32` | yes | `sha256(intent.canonical)` | 32 bytes | yes |
| `1` | `service_digest` | `bytes32` | yes | service binding digest | 32 bytes | yes |
| `2` | `source_operator` | `text` | yes | must equal top-level `source_operator` | existing text constraints | yes |
| `3` | `source_edge` | `text` | yes | route ownership binding | existing text constraints | yes |
| `4` | `target_operator` | `text` | yes | destination/operator binding | existing text constraints | yes |
| `5` | `target_edge_set_digest` | `bytes32` | yes | sorted edge set digest over target edge set | 32 bytes | yes |
| `6` | `profile` | `text` | yes | must equal top-level `profile` | existing text constraints | yes |
| `7` | `transport` | `text` | yes | must match `intent.transport` | existing text constraints | yes |
| `8` | `port` | `uint16` | yes | must match `intent.port`; >0 | `1..65535` | yes |
| `9` | `device_id` | `bytes32` | yes | must equal `device.id` | 32 bytes | yes |
| `10` | `device_generation` | `uint` | yes | must equal `device.credential_generation` and non-zero | >0 | yes |
| `11` | `workload_digest` | `bytes32` | optional/present | must match `workload.subject_digest` if workload present | 32 bytes if workload present | yes |
| `12` | `workload_generation` | `uint` | optional/present | must match `workload.policy_generation` if workload present | >0 if workload present | yes |
| `13` | `ts_generation` | `uint` | yes | TS proof-generation binding | >0 | yes |
| `14` | `proof_thumbprint` | `bytes32` | yes | proof key binding | 32 bytes | yes |
| `15` | `policy_hash` | `bytes32` | yes | route policy semantic binding | 32 bytes | yes |
| `16` | `policy_generation` | `uint` | yes | policy continuity binding | >0 | yes |
| `17` | `authority_generation` | `uint` | yes | request/result generation binding for this authority scope | >0 | yes |

#### 4.1.2 RouteIntent payload map (`request_payload[1]`)

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Signed |
|---|---|---|---|---|---|---|
| `0` | `canonical` | `bytes` | yes | canonical request intent bytes; used for exact digest binding | bounded by policy | yes |
| `1` | `digest` | `bytes32` | yes | must equal `sha256(canonical)` | 32 bytes | yes |
| `2` | `service_identity` | `text` | yes | service binding | existing constraints | yes |
| `3` | `source_operator` | `text` | yes | must match `key.source_operator` | existing constraints | yes |
| `4` | `source_edge` | `text` | yes | must match `key.source_edge` | existing constraints | yes |
| `5` | `target_operator` | `text` | yes | destination binding | existing constraints | yes |
| `6` | `target_edges` | `[]text` | yes | sorted and unique list | routeintent validation | yes |
| `7` | `transport` | `text` | yes | must match `key.transport` | existing text constraints | yes |
| `8` | `port` | `uint16` | yes | must match `key.port` and non-zero | `1..65535` | yes |
| `9` | `record_sequence` | `uint` | yes | route sequence binding | >0 | yes |
| `10` | `policy_hash` | `bytes32` | yes | route policy binding and matching `key.policy_hash` | 32 bytes | yes |
| `11` | `route_id` | `bytes16` | yes | route identity | 16 bytes | yes |
| `12` | `lease_id` | `bytes16` | yes | lease identity | 16 bytes | yes |
| `13` | `expires_at` | `uint` | yes | route-expiry binding | non-zero and valid range | yes |

#### 4.1.3 Device payload map (`request_payload[2]`)

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Signed |
|---|---|---|---|---|---|---|
| `0` | `id` | `bytes32` | yes | request actor identifier | 32 bytes | yes |
| `1` | `source_operator_id` | `text` | yes | must equal `key.source_operator` | existing text constraints | yes |
| `2` | `credential_generation` | `uint` | yes | non-zero credential epoch | >0 | yes |
| `3` | `credential_not_before` | `uint` | yes | credential lifetime floor | valid timestamp | yes |
| `4` | `credential_expires_at` | `uint` | yes | credential lifetime ceiling | >0 and valid range | yes |
| `5` | `signing_key` | map | yes | key used for request authentication | required fields below | yes |

##### 4.1.3.1 Device signing key payload map (`request_payload[2][5]`)

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Signed |
|---|---|---|---|---|---|---|
| `0` | `id` | `bytes32` | yes | key identifier used by protected `kid` | 32 bytes | yes |
| `1` | `purpose` | `uint8` | yes | must be `PurposeDeviceACPRequest` | exact enum value | yes |
| `2` | `generation` | `uint` | yes | key generation epoch | >0 | yes |
| `3` | `thumbprint` | `bytes32` | yes | key fingerprint | 32 bytes | yes |

#### 4.1.4 Optional workload payload map (`request_payload[3]`)

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Signed |
|---|---|---|---|---|---|---|
| `0` | `subject_digest` | `bytes32` | optional | must match `key.workload_digest` when workload is present | 32 bytes | yes |
| `1` | `policy_generation` | `uint` | optional | must match `key.workload_generation` when workload is present | >0 | yes |
| `2` | `credential_expires_at` | `uint` | optional | workload credential lifetime floor/ceiling | valid timestamp | yes |
| `3` | `policy_expires_at` | `uint` | optional | workload policy binding lifetime | valid timestamp | yes |

### 4.2 Renew RouteGrant payload extension

For `operation = renew_route_grant`, `request_payload` is the Acquire payload
plus one additional required field:

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Inside signed boundary |
|---|---|---|---|---|---|---|
| `4` | `previous_grant` | `bytes32` | yes | exact predecessor RouteGrant digest being replaced | 32 bytes | yes |

### 4.3 Freshness request payload

For `operation = freshness`, `request_payload` is:

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Inside signed boundary |
|---|---|---|---|---|---|---|
| `0` | `device_id` | `bytes32` | yes | request actor scope | 32 bytes | yes |
| `1` | `device_generation` | `uint` | yes | request caller generation context | >0 | yes |
| `2` | `after_generation` | `uint` | yes | checkpoint continuity lower bound | full range (`AuthorityGeneration`) | yes |
| `3` | `after_checkpoint` | `bytes32` | yes | checkpoint continuity cursor | 32 bytes (`CheckpointDigest`) | yes |

## 5) ACP result payload and integer keys

ACP responses use the same COSE-signing boundary and map key layout for all
operations:

| CBOR key | Field | Type | Req.? | Source/binding | Size constraint | Signed |
|---|---|---|---|---|---|---|
| `0` | `protocol_version` | `uint` | yes | must match request | exact `1` | yes |
| `1` | `operation` | `text` | yes | must match request operation | fixed set | yes |
| `2` | `request_id` | `bytes16` | yes | must match request | exactly 16 bytes | yes |
| `3` | `request_digest` | `bytes32` | yes | must equal request canonical digest | 32 bytes | yes |
| `4` | `source_operator` | `text` | yes | request scope | existing text constraints | yes |
| `5` | `profile` | `text` | yes | request scope | existing text constraints | yes |
| `6` | `authority_generation` | `uint` | yes | result authority generation for the successful or denied decision context | >0 for all terminal authority states | yes |
| `7` | `result_status` | `text` | yes | semantic status | fixed set | yes |
| `8` | `artifact` | `bytes` | conditional | exact signed ACP artifact bytes for `success`; absent on non-success | request-dependent body ceilings above | yes |

## 8) Semantic status model (envelope-only)

Minimal status set for ACP results:

- `success`
- `invalid_request`
- `unsupported_version`
- `unsupported_profile`
- `request_id_conflict`
- `request_expired`
- `resource_exhausted`
- `stale_generation`
- `stale_freshness`
- `policy_denied`
- `revoked`
- `binding_error`
- `signature_error`
- `internal_error`

Rules:

- `success` means a new artifact is present and independently verifiable.
- Any transport failure (`TLS`, HTTP/2 stream error, timeout, etc.) is a transport outcome, not an ACP semantic status.
- Failures remain fail-closed; absence of an artifact on non-success status is terminal and non-retriable without a new explicit request.

## 9) Idempotency model (Decision #4)

- Idempotency key: authenticated actor tuple + operation + `request_id`:
  - device identity
  - credential generation
  - operation
  - `request_id`
- The request identity also carries `request_digest`:
  - same key + same digest → same decision path may be replayed from exact terminal state
  - same key + different digest → `request_id_conflict` only; no state overwrite
- Replay/ambiguity horizon: bounded by `deadline_unix`, with per-profile cap 30 seconds from acceptance.
- Post-deadline retention: may be retained for cleanup only, max 60 seconds after `deadline_unix`, never extending request authority.
- Server must preserve idempotency state over process restart.
- Replica-consistent state across ACP replicas for same authority scope is required for correctness of exact-key semantics (storage choice is out of scope).
- Exact duplicate concurrent requests MUST NOT trigger a second authority evaluation.
- Minimum retained fields for in-flight/terminal replay:
  - operation
  - `request_id`
  - `request_digest`
  - deadline
  - terminal result state
  - terminal result bytes (when terminal)

## 10) Timeout, ambiguity, and retry behavior

- If `now >= deadline_unix` before evaluation completes: return signed semantic failure (`request_expired`).
- If transport times out/aborts before terminal decision: the client has ambiguity only; it may retry same exact request until deadline.
- A retry after deadline requires a new request identity; replay with same request identity and expired deadline is rejected.
- Concurrency and budgets are enforced before/at admission; on overload return `resource_exhausted`.

## 11) Binding and downgrade behavior (Decision #3)

- `protocol_version` and `profile` are mandatory in every request and are inside signature/request hash.
- Server MUST accept only exact `protocol_version`/`profile` pairs it supports.
- If unsupported version or profile: signed status `unsupported_version` / `unsupported_profile` (no transport-level remap).
- No automatic downgrade and no fallback to older behavior.
- No probing/fallback loops in client or server.

## 12) Version/resource/capacity envelope

Per-profile limits are implementation-bound:

| Complete COSE message | Max size |
|---|---|
| Acquire request COSE body | 64 KiB |
| Renew request COSE body | 64 KiB |
| Freshness request COSE body | 16 KiB |
| Acquire response COSE body | 128 KiB |
| Renew response COSE body | 128 KiB |
| Freshness response COSE body | 1 MiB |

The signed `artifact` bytes are included within those complete COSE-body ceilings; no separate artifact allowance is added.

Per-connection/request-shaping profile limits:

- max 16 concurrent ACP operations per client/device connection
- max 4 duplicate waiters per pending exact request
- request deadline horizon max 30 seconds
- idempotency cleanup grace max 60 seconds after deadline
- unmatched/oversized input and capacity rejects are fail-closed

## 13) End-to-end field boundary summary

For each operation, exactly these request/response envelopes are in-scope:

- Acquire: common envelope + Acquire payload + Acquire result envelope
- Renew: common envelope + Acquire payload + `previous_grant` + Renew result envelope
- Freshness: common envelope + Freshness payload + Freshness result envelope

No additional route/grant/credential fields are duplicated in signed result envelopes.

## 14) Implementation status and protocol gaps

Protocol Gaps: `none`.

The approved wire contract is complete. The following work remains for 3R-C implementation and is not a protocol gap:

- implement deterministic CBOR serializers and complete COSE Sign1 request/result composition exactly as defined above
- map the frozen semantic `result_status` set to existing local `AuthorityError` behavior without adding protocol statuses

`ACP_RESULT_SIGNING = 15` is already applied in the operator/federation `KeyPurpose` registry. It authenticates only the outer ACP Result Envelope. No client `identity.Purpose` alias exists or is required.

## Human Decisions Required Before Freeze

Human Decisions Required Before Freeze: `none`.
