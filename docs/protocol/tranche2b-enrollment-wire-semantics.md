# Tranche 2B Enrollment Wire Semantics (Minimal Profile)

Status: `FROZEN — APPROVED FOR IMPLEMENTATION`  
Tranche: `2B`

Enrollment Human Decision #1: `APPROVED`  
Deployment-specific bootstrap remains outside the generic NBSR enrollment wire.

Enrollment Human Decision #2: `APPROVED`  
Enrollment Profile v1 supports INITIAL ENROLLMENT ONLY with `ENROLL`; REENROLL and all replacement/rotation/recovery behavior are out of scope.

Enrollment Human Decision #3: `APPROVED`  
`ENROLLMENT_RESULT_SIGNING = 16` is the dedicated operator-side purpose for EnrollmentResultPayload.

Scope:

- minimal enrollment-only wire needed so a production Go client can become enrolled with
  its Source Operator ACP and then use the already-frozen Acquire/Renew/Freshness
  profile
- no Runtime implementation
- do not modify frozen ACP Acquire/Renew/Freshness wire or source code
- no QUIC, transport sessions, stream credits, F75, resolver, or synthetic IP changes

Repository anchors preserved:

- Device identity purposes remain exactly:
  - `PurposeDeviceACPRequest`, `PurposeTSProof`, `PurposeLocalStateIntegrity`
- `ACP_RESULT_SIGNING` remains dedicated to frozen ACP authority result envelope
  and must not be reused for enrollment result purposes
- Tranche 2B `status.md` marks Enrollment Profile v1 as frozen for implementation.

## A) Corrected minimal operation set

### Primary operation: `ENROLL`

1. `ENROLL` is the only required enrollment wire operation.
2. v1 is initial-enrollment only; `REENROLL` is not defined.
3. Request/response are not over `/acp/authority`.
4. V1 does not define REENROLL, credential rotation/replacement, lost-device recovery,
   recovery rollover, prior-credential proof, or any prior-credential coexistence semantics.

## B) Corrected minimal request schema

Enrollment request body is the complete COSE Sign1 object encoding the envelope:

- Protected CBOR header:
  - algorithm = `-8`
  - non-empty protected `kid`
  - payload is embedded in the COSE Sign1 payload (no detached payload mode)
  - external AAD is empty (unless existing repository semantics explicitly require otherwise)
- Embedded deterministic payload map `EnrollmentRequestPayload`:

| Key | Field | Notes |
|---:|---|---|
| `0` | `protocol_version` | MUST be `1`; no downgrade |
| `1` | `request_id` | 16-byte opaque request ID |
| `2` | `deadline_unix` | absolute retry/ambiguity bound |
| `3` | `source_operator` | deployment-selected profile owner |
| `4` | `profile` | requested ACP profile |
| `5` | `device_signing_key` (`map`) | proposed DeviceIdentity request key |

`device_signing_key` map:
- `0` `public_key`
- `1` `key_id`
- `2` `purpose`
- `3` `generation`
- `4` `thumbprint`

Notes:

- No `bootstrap_authorization` field in generic NBSR wire.
  Deployment-specific bootstrap context (including any bootstrap token/challenge or mTLS)
  is applied outside this protocol payload before `/acp/enroll` is invoked.
- `EnrollmentRequestPayload` MUST NOT contain:
  - bootstrap token
  - bootstrap challenge
  - QR/login credential
  - bootstrap authorization blob
  - mTLS credential
  - deployment-specific onboarding evidence
  - reenroll fields (including `reenroll = true`)
  - `previous_device_id`
  - `previous_generation`
- No separate `proof_of_possession` field is carried.
  The COSE signature over the complete request payload is the proof of possession.
- Enrollment request signature proves possession of the proposed Device ACP request key only;
  it does not replace deployment/bootstrap authorization.
- TS proof and local-state keys are not present.
- Enrollment request uses `PurposeDeviceACPRequest` only.
- Signature domain:
  `NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00` + `PurposeDeviceACPRequest`.

## C) Corrected minimal response schema

Enrollment response body is the complete COSE Sign1 object encoding the envelope:

`EnrollmentResultPayload`:

| Key | Field | Notes |
|---:|---|---|
| `0` | `protocol_version` | MUST be `1`; no downgrade |
| `1` | `request_id` | echoes the request correlation ID |
| `2` | `request_digest` | SHA-256 over request CBOR bytes |
| `3` | `enrollment_status` | see section I |
| `4` | `device_identity` (`map`) | minimum durable state required by current Go identity model |

`device_identity` map:
- `0` `id`
- `1` `source_operator_id`
- `2` `credential_generation`
- `3` `credential_not_before`
- `4` `credential_expires_at`
- `5` `signing_key` (`map`)

`signing_key` map:
- `0` `key_id`
- `1` `purpose`
- `2` `generation`
- `3` `thumbprint`

There are no parallel unsigned sibling fields; the COSE payload is canonical for all
enrolled identity data.

- `request_digest` is required and binds the result to the exact request body.
- The client MUST verify:
  - response `request_id` matches the sent request.
  - `request_digest` equals `SHA-256(deterministic_CBOR_bytes(EnrollmentRequestPayload))`.
- `device_identity` MUST be present only when `enrollment_status == ENROLLMENT_ACCEPTED`.
  For any non-success status, `device_identity` MUST be absent and no partial enrollment state
  is consumed or persisted.

- The EnrollmentResultPayload COSE Sign1 signature MUST verify using purpose:
  `ENROLLMENT_RESULT_SIGNING` in the operator/federation KeyPurpose trust domain.
- `ENROLLMENT_RESULT_SIGNING = 16`:
  - is distinct from `ACP_RESULT_SIGNING = 15`
  - is distinct from `PurposeDeviceACPRequest`, `PurposeTSProof`, `PurposeLocalStateIntegrity`
  - is distinct from route-grant, freshness, checkpoint, revocation, and federation
    evidence signer purposes.
- The protected non-empty `kid` plus enrolled/operator trust registry resolves the signer key.
- No `signing_purpose`, `signer_id`, `operator_key`, or similar convenience metadata is
  carried in the `EnrollmentResultPayload`.
- Verification MUST require exact purpose: `ENROLLMENT_RESULT_SIGNING` (no `ACP_RESULT_SIGNING`
  reuse).

## D) CBOR field-key assignments

- Request `EnrollmentRequestPayload`: keys `0..5` as listed in section B.
- Response `EnrollmentResultPayload`: keys `0..4` and nested map `4.x` as listed in section C.
- This draft does not assign extra keys for bootstrap token, transport hints,
  authority generation, or checkpoint data.

## E) Bootstrap boundary and transport trust

- Enrollment bootstrap remains deployment-specific and must be established before
  NBSR enrollment message exchange.
- Deployment/bootstrap layer MUST authorize the enrollment attempt before generic NBSR
  enrollment evaluation.
- No universal bootstrap token/challenge/credential/API shape is defined in protocol.
- Do not define a bootstrap protocol API in generic NBSR.
- POST `/acp/enroll` over TLS 1.3, HTTP/2 mandatory.
- No HTTP/1.1 fallback.
- No path-versioning (`/acp/enroll` fixed).
- No security-relevant query parameters.
- No generic NBSR requirement for mTLS in this draft; deployment may require it
  as part of its bootstrap layer before this protocol is invoked.
- Server authentication is mandatory.
- Fail closed on bootstrap/trust/profile failures.

## F) Replay/idempotency model

- Retry uses the signed request payload + `request_id` to produce a deterministic
  request digest.
- Exact same `request_id` and canonical request payload does not create a new
  semantic decision; it replays the same terminal signed result.
- Same `request_id` with a different canonical request payload is rejected as
  conflict with signed status `ENROLLMENT_REQUEST_CONFLICT`.
- If an enrollment would replace or rotate an already-enrolled credential, this is treated as
  an invalid attempt and must fail closed with `ENROLLMENT_REJECTED` (no `REENROLLMENT_UNSUPPORTED` status).
- Unresolved request state is treated as ambiguous and kept fenced until deterministically
  resolved.

## G) Restart and rollback

- Enrollment produces persisted DeviceIdentity state only.
- Enrollment does not seed a durable authority-generation floor.
- Existing Tranche 2B ACP restart rule remains:
  successful Freshness validation is required before Ready.
- `Freshness` response/result establishes current authority-generation state and
  final readiness gates.
- Therefore `authority_generation` and `authority_checkpoint` fields are removed from
  enrollment result payload in this correction pass.

## H) Protocol-facing resource limits

Provisional limits:

- complete signed enrollment request body <= `16 KiB`
- complete signed enrollment response body <= `64 KiB`
- enrollment status deadline horizon <= `30` seconds
- bounded duplicate waiters and bounded concurrent enrollment requests (exact numbers are
  deployment configuration)

## I) Minimal signed semantic statuses

- `ENROLLMENT_ACCEPTED`
- `ENROLLMENT_REJECTED`
- `ENROLLMENT_INVALID`
- `ENROLLMENT_REQUEST_CONFLICT` (same `request_id` + different canonical request)
- `ENROLLMENT_EXPIRED` (request deadline elapsed)

Transport/TLS/timeouts/unavailability are transport failures and remain unsigned.

## J) Remaining exact `HUMAN_DECISION_REQUIRED` items

Human Decisions Required Before Freeze: `none`.
Protocol Gaps: `none`.

## K) Validation/diff summary

- Changes are complete for Task 3 finalization:
  - `docs/protocol/tranche2b-enrollment-wire-semantics.md`
  - `docs/protocol/status.md`
  - `docs/protocol/registries/federation-v0.1-development.json`
  - `docs/protocol/federation-v0.1-development-profile.md`
  - `nbsr/federation/registry.py`
  - `tests/federation/test_registry.py`
  - `client/nbsr-go-client/internal/identity/identity_test.go`
  - `docs/protocol/wp8-federation-v0.1-registry-allocation.md` (regenerated below)
