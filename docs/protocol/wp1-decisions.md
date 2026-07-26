# WP1 protocol decisions for approval

**Status:** proposed implementation freeze; no WP1 production code exists  
**Scope:** Protocol Core v0.1 data model and deterministic vectors only

## D1 - CBOR profile

Use RFC 8949 Core Deterministic Encoding for every signed payload and native
control message.

- definite-length arrays, maps, byte strings, and text strings only;
- preferred shortest integer and length encodings;
- deterministic map-key ordering;
- duplicate map keys rejected before semantic decoding;
- tags, floating point, undefined values, and application-specific simple
  values rejected in Core v0.1 structures;
- decoded bytes must equal deterministic re-encoding;
- maximum depth, item count, string length, byte-string length, and total
  message length enforced before object construction.

**Recommended Python dependency:** `cbor2` for standards-compatible primitive
encoding/decoding, wrapped by an NBSR structural validator. The wrapper, not
the library default, owns canonicality, duplicate-key, size, and type policy.

## D2 - COSE Sign1 profile

Implement only the COSE Sign1 subset required by RFC 9052/9053 with the
existing `cryptography` Ed25519 primitives.

- COSE tag 18 required;
- protected header must contain `alg=-8` and a non-empty `kid`;
- algorithm and key identifier must not be accepted from unprotected headers;
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
- Error codes receive stable integers in the same order as Vision V3 section
  25; symbolic names remain the public diagnostic contract.

## D4 - Identifiers and time

- `request_id`, `session_id`, `route_id`, `lease_id`, and `unique_nonce` are
  byte strings of exactly 16 bytes in wire structures.
- key identifiers, operator IDs, edge IDs, service IDs, and connector IDs are
  canonical lowercase ASCII text with explicit per-field length bounds.
- times are unsigned integer Unix seconds in UTC.
- digests and key thumbprints are 32-byte SHA-256 byte strings.
- canonical names use lowercase DNS A-label form with no trailing dot.
- IP literals and origin addresses are prohibited in signed NBSR service
  records, RouteIntents, Route Grants, revocations, errors, and golden vectors.

## D5 - Golden vectors

Committed vectors contain only public test material:

- a fixed, clearly labeled test-only Ed25519 seed used by the deterministic
  vector generator;
- public key, protected headers, payload, signature, and complete COSE Sign1
  bytes;
- valid and invalid vectors with expected symbolic error codes;
- no production key, token, hostname, subscriber identity, or origin address.

The generator must reproduce every checked-in byte exactly. Tests must fail if
regeneration changes a vector without an explicit protocol review.

## Approval gate

Before WP1 code begins, approve or amend D1-D5. Approval freezes the first
cross-language wire contract; changing these decisions later requires new
vectors and an explicit versioning decision.
