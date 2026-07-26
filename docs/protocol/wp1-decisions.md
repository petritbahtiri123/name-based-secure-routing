# WP1 protocol decisions for approval

**Status:** approved implementation freeze with amendments A1-A4; no WP1 production code exists
**Scope:** Protocol Core v0.1 data model and deterministic vectors only
**Decision:** approved for WP1 implementation on 2026-07-26 by Petrit Bahtiri
with amendments A1-A4 recorded in this document.

## D1 - CBOR profile

Use RFC 8949 Core Deterministic Encoding for every signed payload and native
control message.

- definite-length arrays, maps, byte strings, and text strings only;
- preferred shortest integer and length encodings;
- RFC 8949 Core Deterministic map-key ordering by bytewise lexicographic
  comparison of each key's deterministic encoded bytes;
- duplicate map keys rejected before semantic decoding;
- tags, floating point, undefined values, and application-specific simple
  values rejected in Core v0.1 structures;
- decoded bytes must equal deterministic re-encoding;
- maximum depth, item count, string length, byte-string length, and total
  message length enforced before object construction.

**Recommended Python dependency:** `cbor2` for standards-compatible primitive
decoding, wrapped by an NBSR structural validator and re-encoder. The NBSR
implementation, not `cbor2` canonical mode or another library default, owns
encoding, bytewise map-key ordering, canonicality, duplicate-key, size, and
type policy. Acceptance requires equality with the NBSR deterministic
re-encoder; `cbor2.dumps(..., canonical=True)` is not part of the profile.

## D2 - COSE Sign1 profile

Implement only the COSE Sign1 subset required by RFC 9052/9053 with the
existing `cryptography` Ed25519 primitives.

- COSE tag 18 required;
- protected header must contain `alg=-8` and a `kid` encoded as an opaque CBOR
  byte string of 1-64 bytes;
- algorithm and key identifier must not be accepted from unprotected headers;
- `kid` has meaning only within the caller-supplied trust context used for key
  lookup; it is not parsed as a global name, operator ID, path, or text value;
- external AAD is the empty byte string in Core v0.1;
- detached payloads are prohibited;
- only Ed25519 public/private key objects are accepted;
- all other algorithms, curves, critical headers, and header duplication fail
  closed.

Do not add a broad COSE dependency in WP1. This minimizes accepted surface and
makes algorithm confusion testable. Reconsider a maintained general-purpose
COSE library only after cross-language vectors exist.

## D3 - Numeric registries

- Protocol version `1` means Core v0.1.
- Message codes `1..17` are frozen exactly as Vision V3 section 10.4.
- Field keys `0..999` are reserved for the Core specification.
- Extension keys start at `1000`.
- Unknown Core keys fail closed.
- Unknown extension keys are accepted only when they are not listed as
  critical and the schema explicitly permits extensions.
- Error codes are frozen to the complete Vision V3 section 25 mapping:

| Symbolic name | Integer |
|---|---:|
| `NBSR_E_NAME_INVALID` | 1 |
| `NBSR_E_NAME_NOT_FOUND` | 2 |
| `NBSR_E_RECORD_UNTRUSTED` | 3 |
| `NBSR_E_RECORD_STALE` | 4 |
| `NBSR_E_RECORD_REVOKED` | 5 |
| `NBSR_E_CONTEXT_REQUIRED` | 6 |
| `NBSR_E_HANDLE_EXHAUSTED` | 7 |
| `NBSR_E_ROUTE_DENIED` | 8 |
| `NBSR_E_GRANT_INVALID` | 9 |
| `NBSR_E_GRANT_EXPIRED` | 10 |
| `NBSR_E_PROOF_INVALID` | 11 |
| `NBSR_E_REPLAY` | 12 |
| `NBSR_E_PROFILE_UNSUPPORTED` | 13 |
| `NBSR_E_DOWNGRADE` | 14 |
| `NBSR_E_EDGE_UNAVAILABLE` | 15 |
| `NBSR_E_ORIGIN_UNAVAILABLE` | 16 |
| `NBSR_E_REVOKED` | 17 |
| `NBSR_E_OVER_CAPACITY` | 18 |
| `NBSR_E_INTERNAL` | 19 |

`NBSR_E_INTERNAL` is a non-sensitive fallback used only when no more specific
error code applies.

## D4 - Identifiers and time

- `request_id`, `session_id`, `route_id`, `lease_id`, and `unique_nonce` are
  byte strings of exactly 16 bytes in wire structures.
- operator IDs, edge IDs, service IDs, and connector IDs are canonical
  lowercase ASCII text with explicit per-field length bounds;
- COSE `kid` follows D2 and remains an opaque 1-64 byte string scoped to the
  caller's trust context;
- times are unsigned integer Unix seconds in UTC.
- digests and key thumbprints are 32-byte SHA-256 byte strings.
- canonical names use lowercase DNS A-label form with no trailing dot.
- IP literals and origin addresses are prohibited in signed NBSR service
  records, RouteIntents, Route Grants, revocations, errors, and every valid
  golden vector.

## D5 - Golden vectors

Committed vectors contain only public test material:

- a fixed, clearly labeled test-only Ed25519 seed used by the deterministic
  vector generator;
- public key, protected headers, payload, signature, and complete COSE Sign1
  bytes;
- valid and invalid vectors with expected symbolic error codes;
- no production key, token, hostname, subscriber identity, or origin address;
- RFC 5737 IPv4 and RFC 3849 IPv6 documentation literals may appear only as
  inputs in explicitly invalid rejection vectors whose expected result proves
  that IP-shaped origin data is rejected.

The generator must reproduce every checked-in byte exactly. Tests must fail if
regeneration changes a vector without an explicit protocol review.

## Approval gate

Before WP1 code begins, approve or amend D1-D5. Approval freezes the first
cross-language wire contract; changing these decisions later requires new
vectors and an explicit versioning decision.
