# NBSR Protocol Core v0.1 wire contract

**Status:** normative WP1 contract

**Frozen decisions:** D1–D6, including D6-A1 through D6-A3

**Schema authority:** [Core v0.1 wire schema freeze](core-v0.1-wire-schema.md)

## Normative scope

This document defines the cross-language wire contract implemented by
`nbsr.protocol`: deterministic CBOR, the frozen numeric registries, six
immutable object schemas, the constrained COSE Sign1 wrapper, rejection
behavior, and reproducible test vectors.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
and MAY are to be interpreted as normative requirements. Core v0.1 accepts
only the forms stated here. An implementation MUST fail closed when an input
cannot be interpreted without ambiguity.

## Deterministic CBOR profile

Core v0.1 uses RFC 8949 Core Deterministic Encoding with these additional
profile constraints:

- every integer and length uses its shortest preferred encoding;
- arrays, maps, text strings, and byte strings use definite lengths;
- map keys are strictly ordered by their complete deterministic encoded bytes;
- duplicate or out-of-order map keys are rejected before semantic decoding;
- accepted simple values are `false`, `true`, and `null`;
- integers are bounded to the CBOR 64-bit argument range;
- floats, other simple values, unsupported tags, indefinite-length items, and
  trailing bytes are rejected;
- text must be valid UTF-8 and must satisfy any tighter field alphabet;
- structural scanning and resource checks occur before general CBOR decoding;
- decoding an accepted value and encoding it again MUST reproduce identical
  bytes.

The COSE Sign1 tag 18 is processed by the COSE profile boundary. It is not a
general-purpose tag accepted by the deterministic payload decoder.

### Resource limits

| Limit | Maximum |
|---|---:|
| Complete encoded value | 65536 bytes |
| Nesting depth | 16 |
| Array items | 256 |
| Map pairs | 128 |
| UTF-8 text | 4096 bytes |
| Byte string | 32768 bytes |

Resource-limit failures use `NBSR_E_OVER_CAPACITY`. Other malformed,
non-preferred, or unsupported CBOR forms use
`NBSR_E_PROFILE_UNSUPPORTED`. Encoding MUST apply the total-byte budget while
building the output rather than after unbounded materialization.

## Numeric registries

Protocol version `1` means Core v0.1. No other protocol or object version is
accepted by this contract.

### Message codes

| Code | Symbolic name |
|---:|---|
| 1 | `CLIENT_HELLO` |
| 2 | `EDGE_HELLO` |
| 3 | `ROUTE_OPEN` |
| 4 | `ROUTE_ACCEPT` |
| 5 | `ROUTE_REJECT` |
| 6 | `STREAM_OPEN` |
| 7 | `STREAM_ACCEPT` |
| 8 | `STREAM_REJECT` |
| 9 | `LEASE_RENEW` |
| 10 | `LEASE_RESULT` |
| 11 | `KEY_UPDATE_NOTICE` |
| 12 | `ROUTE_DRAIN` |
| 13 | `ROUTE_REVOKE` |
| 14 | `ROUTE_CLOSE` |
| 15 | `PING` |
| 16 | `PONG` |
| 17 | `ERROR` |

Unknown message codes are rejected.

### Error codes

| Code | Symbolic name |
|---:|---|
| 1 | `NBSR_E_NAME_INVALID` |
| 2 | `NBSR_E_NAME_NOT_FOUND` |
| 3 | `NBSR_E_RECORD_UNTRUSTED` |
| 4 | `NBSR_E_RECORD_STALE` |
| 5 | `NBSR_E_RECORD_REVOKED` |
| 6 | `NBSR_E_CONTEXT_REQUIRED` |
| 7 | `NBSR_E_HANDLE_EXHAUSTED` |
| 8 | `NBSR_E_ROUTE_DENIED` |
| 9 | `NBSR_E_GRANT_INVALID` |
| 10 | `NBSR_E_GRANT_EXPIRED` |
| 11 | `NBSR_E_PROOF_INVALID` |
| 12 | `NBSR_E_REPLAY` |
| 13 | `NBSR_E_PROFILE_UNSUPPORTED` |
| 14 | `NBSR_E_DOWNGRADE` |
| 15 | `NBSR_E_EDGE_UNAVAILABLE` |
| 16 | `NBSR_E_ORIGIN_UNAVAILABLE` |
| 17 | `NBSR_E_REVOKED` |
| 18 | `NBSR_E_OVER_CAPACITY` |
| 19 | `NBSR_E_INTERNAL` |

Unknown error codes are rejected. `NBSR_E_INTERNAL` is only a non-sensitive
fallback when no more specific code applies.

### Revocation codes

| Registry | Code | Meaning |
|---|---:|---|
| Target type | 1 | ServiceRecord |
| Target type | 2 | signing key |
| Target type | 3 | route |
| Target type | 4 | lease |
| Target type | 5 | operator |
| Target type | 6 | edge |
| Target type | 7 | origin connector |
| Mode | 1 | deny new use |
| Mode | 2 | terminate active use |
| Reason | 1 | unspecified |
| Reason | 2 | key compromise |
| Reason | 3 | ownership change |
| Reason | 4 | policy violation |
| Reason | 5 | administrative |
| Reason | 6 | superseded |

### Frozen state machines

The Resolution, Tunnel, Stream, and Connector state names and transitions are
frozen by D3 and implemented by `nbsr.protocol.transition`. States are textual
implementation values, not additional numeric wire codes. Unknown states,
cross-machine transitions, and transitions absent from the frozen transition
tables fail closed.

## Common wire types and bounds

- `uint` is CBOR major type 0. A boolean is never accepted as an integer.
- `tstr` and `bstr` are definite-length text and byte strings.
- Canonical names are lowercase DNS A-label ASCII, 1–253 octets, without a
  trailing dot. Labels are 1–63 octets. Empty labels and IP literals are
  rejected.
- A textual NBSR ID is 1–64 ASCII octets matching
  `[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*`.
- A COSE key identifier is opaque `bstr`, 1–64 bytes, interpreted only inside
  the caller-supplied trust context.
- Request, session, route, lease, revocation IDs and unique nonces are exactly
  16 bytes.
- SHA-256 digests and key thumbprints are exactly 32 bytes.
- Timestamps are unsigned Unix seconds in `0..253402300799`.
- Sequences and generations are unsigned integers in
  `1..18446744073709551615`.
- Ports are unsigned integers in `1..65535`.
- Set-like arrays are strictly ascending by deterministic item bytes and
  contain no duplicates.
- Core v0.1 transport arrays contain only `tcp`; route-profile arrays contain
  only `nbsr-quic-1`.
- Publication mode is exactly one of `legacy`, `dual-published`,
  `nbsr-preferred`, or `nbsr-secure-only`.

ServiceRecord lifetime is at most 604800 seconds, RouteIntent lifetime at most
300 seconds, and RouteGrant lifetime at most 600 seconds. Each end is strictly
greater than its start. Revocation has no universal maximum lifetime and
follows its object-specific optional-expiry rules.

## Object field schemas

Numeric keys are explicit literals. They MUST NOT be inferred from source,
declaration, dataclass, constructor, or table order.

### ServiceRecord

ServiceRecord is a payload without an embedded signature. Every field is
required.

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `record_version` | required | `uint` | 1 | 1 | Must equal Core object version 1 |
| 1 | `canonical_name` | required | ASCII `tstr` | 1 octet | 253 octets | Canonical DNS A-label name; no trailing dot or IP literal |
| 2 | `sequence` | required | `uint` | 1 | 18446744073709551615 | Must be greater than caller-supplied last accepted owner/name sequence |
| 3 | `owner_key_id` | required | opaque `bstr` | 1 byte | 64 bytes | Resolved only in caller trust context; never parsed as text or path |
| 4 | `service_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 5 | `destination_operator_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 6 | `destination_edge_set` | required | array of ASCII `tstr` | 1 item | 16 items | Textual NBSR IDs; strictly ordered and unique |
| 7 | `origin_connector_id` | required | ASCII `tstr` | 1 octet | 64 octets | Textual NBSR ID only; an origin hostname or address is forbidden |
| 8 | `transports` | required | array of ASCII `tstr` | 1 item | 1 item | Exact single value `tcp` |
| 9 | `ports` | required | array of `uint` | 1 item | 32 items | Each port is 1..65535; strictly ascending and unique |
| 10 | `route_profiles` | required | array of ASCII `tstr` | 1 item | 1 item | Exact single value `nbsr-quic-1` |
| 11 | `publication_mode` | required | ASCII `tstr` | 6 octets | 16 octets | Must be one of the four fixed publication-mode values |
| 12 | `not_before` | required | `uint` Unix seconds | 0 | 253402300799 | Start of the ServiceRecord validity window |
| 13 | `not_after` | required | `uint` Unix seconds | 1 | 253402300799 | Greater than `not_before`; lifetime at most 604800 seconds |
| 14 | `revocation_ref` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |

### RouteIntent

RouteIntent is an unsigned, short-lived prepared-route payload.

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `intent_version` | required | `uint` | 1 | 1 | Must equal Core object version 1 |
| 1 | `resolution_context_digest` | required | SHA-256 `bstr` | 32 bytes | 32 bytes | SHA-256 of the deployment-scoped opaque Resolution Context ID bytes |
| 2 | `canonical_name` | required | ASCII `tstr` | 1 octet | 253 octets | Canonical DNS A-label name; no trailing dot or IP literal |
| 3 | `service_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 4 | `source_operator_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 5 | `source_edge_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 6 | `destination_operator_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 7 | `destination_edge_set` | required | array of ASCII `tstr` | 1 item | 16 items | Textual NBSR IDs; strictly ordered and unique |
| 8 | `allowed_transports` | required | array of ASCII `tstr` | 1 item | 1 item | Exact single value `tcp` |
| 9 | `allowed_ports` | required | array of `uint` | 1 item | 32 items | Each port is 1..65535; strictly ascending and unique |
| 10 | `created_at` | required | `uint` Unix seconds | 0 | 253402300799 | Start of the RouteIntent validity window |
| 11 | `expires_at` | required | `uint` Unix seconds | 1 | 253402300799 | Greater than `created_at`; lifetime at most 300 seconds |
| 12 | `record_sequence` | required | `uint` | 1 | 18446744073709551615 | Must equal the accepted ServiceRecord sequence used to create the intent |
| 13 | `policy_hash` | required | SHA-256 `bstr` | 32 bytes | 32 bytes | Opaque policy digest; compared byte-for-byte within caller policy context |
| 14 | `route_id` | required | `bstr` | 16 bytes | 16 bytes | Unique route identifier |
| 15 | `lease_id` | required | `bstr` | 16 bytes | 16 bytes | Unique lease identifier bound to this route |

### RouteGrant

RouteGrant uses only a 32-byte `name_digest` and `allowed_ports`. It is a
payload without an embedded signature.

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `grant_version` | required | `uint` | 1 | 1 | Must equal Core object version 1 |
| 1 | `route_id` | required | `bstr` | 16 bytes | 16 bytes | Must match the RouteIntent route ID |
| 2 | `name_digest` | required | SHA-256 `bstr` | 32 bytes | 32 bytes | SHA-256 of canonical-name ASCII bytes |
| 3 | `service_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern and bound RouteIntent |
| 4 | `source_operator_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 5 | `source_edge_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 6 | `destination_operator_id` | required | ASCII `tstr` | 1 octet | 64 octets | Must match the textual NBSR ID pattern |
| 7 | `destination_edge_set` | required | array of ASCII `tstr` | 1 item | 16 items | Textual NBSR IDs; strictly ordered and unique |
| 8 | `allowed_transports` | required | array of ASCII `tstr` | 1 item | 1 item | Exact single value `tcp` |
| 9 | `allowed_ports` | required | array of `uint` | 1 item | 32 items | Each port is 1..65535; strictly ascending and unique |
| 10 | `client_session_key_thumbprint` | required | SHA-256 `bstr` | 32 bytes | 32 bytes | SHA-256 of the raw 32-byte RFC 8032 Ed25519 public-key encoding |
| 11 | `not_before` | required | `uint` Unix seconds | 0 | 253402300799 | Start of the RouteGrant validity window |
| 12 | `expires_at` | required | `uint` Unix seconds | 1 | 253402300799 | Greater than `not_before`; lifetime at most 600 seconds |
| 13 | `lease_id` | required | `bstr` | 16 bytes | 16 bytes | Must match the RouteIntent lease ID |
| 14 | `record_sequence` | required | `uint` | 1 | 18446744073709551615 | Must equal current accepted ServiceRecord sequence |
| 15 | `policy_hash` | required | SHA-256 `bstr` | 32 bytes | 32 bytes | Must equal the bound RouteIntent policy hash |
| 16 | `unique_nonce` | required | `bstr` | 16 bytes | 16 bytes | Single-use replay identifier within issuer replay state |

### Revocation

Revocation is a payload without an embedded signature.

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `revocation_version` | required | `uint` | 1 | 1 | Must equal Core object version 1 |
| 1 | `revocation_id` | required | `bstr` | 16 bytes | 16 bytes | Unique revocation statement identifier |
| 2 | `issuer_key_id` | required | opaque `bstr` | 1 byte | 64 bytes | Resolved only in caller trust context |
| 3 | `generation` | required | `uint` | 1 | 18446744073709551615 | Must exceed the stored highest accepted issuer generation; update the persistent tombstone before acceptance |
| 4 | `target_type` | required | `uint` | 1 | 7 | Must be a fixed target-type registry code |
| 5 | `target_id` | required | SHA-256 `bstr` | 32 bytes | 32 bytes | Digest formula is selected only by `target_type` as defined above |
| 6 | `mode` | required | `uint` | 1 | 2 | Must be `deny new use` or `terminate active use` |
| 7 | `not_before` | required | `uint` Unix seconds | 0 | 253402300799 | Start of the revocation validity window |
| 8 | `expires_at` | optional | `uint` Unix seconds | 1 | 253402300799 | When absent, the revocation does not expire automatically; when present, greater than `not_before`; MUST be absent for key compromise |
| 9 | `target_sequence` | optional | `uint` | 1 | 18446744073709551615 | Allowed only when `target_type` 1 (service record); rejected for all other target types; when present, binds the targeted record sequence |
| 10 | `reason_code` | required | `uint` | 1 | 6 | Fixed reason registry code; key compromise requires `expires_at` absent; no remote free text |

The highest accepted issuer generation remains a durable tombstone after
expiry or removal. This prevents rollback and resurrection. `target_sequence`
is allowed only for target type 1 and does not replace issuer `generation`.

### ProtocolError

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `error_version` | required | `uint` | 1 | 1 | Must equal Core object version 1 |
| 1 | `error_code` | required | `uint` | 1 | 19 | Must be exactly one frozen D3 ErrorCode value |
| 2 | `request_id` | required | `bstr` | 16 bytes | 16 bytes | Must identify the failed request without exposing session material |
| 3 | `retryable` | required | CBOR boolean | false | true | Exact major-type 7 false or true; integers 0 and 1 are rejected |
| 4 | `retry_after_seconds` | optional | `uint` seconds | 1 | 3600 | Present only when `retryable` is true; absent when false |

### ControlEnvelope

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `protocol_version` | required | `uint` | 1 | 1 | Must equal Core protocol version 1 |
| 1 | `message_type` | required | `uint` | 1 | 17 | Must be exactly one frozen D3 MessageCode value |
| 2 | `request_id` | required | `bstr` | 16 bytes | 16 bytes | Correlation identifier for this request or response |
| 3 | `session_id` | required | `bstr` | 16 bytes | 16 bytes | Identifier of the authenticated control session |
| 4 | `monotonic_sequence` | required | `uint` | 1 | 18446744073709551615 | Must be greater than caller-supplied last accepted session sequence |
| 5 | `body` | required | map with `uint` keys | 0 pairs | 128 pairs | Message-specific schema validates all body keys and values separately |
| 6 | `critical_extension_keys` | optional | array of `uint` | 1 item | 32 items | Extension keys only; strictly ascending, unique, and each key must be present |

## COSE Sign1 profile

ServiceRecord, RouteGrant, and Revocation are the only D6 objects wrapped in
object-level COSE Sign1. RouteIntent, ProtocolError, and ControlEnvelope MUST
NOT receive an object-level COSE wrapper in Core v0.1.

The exact wrapper is:

```text
18([
  protected : bstr,
  unprotected : {},
  payload : bstr,
  signature : bstr .size 64
])
```

The protected byte string is the deterministic encoding of exactly
`{1: -8, 4: kid}`. Header 1 selects EdDSA with an Ed25519 key. Header 4 is an
opaque 1–64-byte `kid`. The unprotected map is empty, the payload is attached,
and external AAD is empty.

The Ed25519 signature covers the deterministic CBOR encoding of:

```text
["Signature1", protected, b"", payload]
```

ServiceRecord `kid` MUST equal `owner_key_id` byte-for-byte. Revocation `kid`
MUST equal `issuer_key_id` byte-for-byte. RouteGrant `kid` is resolved only
inside a caller-supplied authorized RouteGrant-issuer trust context. There is
no global key lookup, algorithm fallback, detached payload, or unprotected
key identifier.

Malformed wrapper structure, unsupported headers, unknown keys, key mismatch,
tampering, and invalid signatures fail before the payload is trusted.
Resource-limit failures retain `NBSR_E_OVER_CAPACITY`; caller-selected
ServiceRecord/Revocation or RouteGrant verification failures use the
appropriate frozen trust error.

## Extensions and unknown fields

Numeric keys `0..999` are reserved to Core. Unknown Core keys fail closed.
Extension keys begin at `1000`.

ServiceRecord, RouteIntent, RouteGrant, Revocation, and ProtocolError are
closed schemas and reject all extensions in Core v0.1. ControlEnvelope alone
may retain unknown non-critical extension keys. Key 6 lists critical extension
keys; every listed key must be present, ordered, and unique. Core v0.1
recognizes no critical extensions, so every non-empty critical list fails
closed. An empty key-6 list is omitted rather than encoded.

Adding a numeric key, registry code, recognized critical extension, wrapper,
state, or transition is not an editorial change.

## Golden vectors

The hash-bound manifest is
`tests/vectors/core-v0.1/manifest.json`. The package contains six valid and 28
invalid vectors and only public test material. Verify exact reproducibility
without writing files:

```bash
python tools/generate_core_v01_vectors.py --check
```

The generator is deterministic and bounded to the owned vector directory.
Invalid privacy vectors may contain documentation-only address literals solely
to prove rejection. No valid vector contains an origin endpoint or secret key.

## Privacy invariant

Core v0.1 payloads, wrappers, valid vectors, client-visible errors, and the
public protocol API MUST NOT disclose an origin address. Canonical-name fields
reject IP literals. No schema carries an origin hostname, reusable credential,
private session key, or direct-origin fallback instruction.

The `origin_connector_id` is a textual NBSR identifier, not network
reachability metadata. Origin discovery and OriginSet are outside these frozen
six schemas.

## Versioning and incompatibility

Any change that alters accepted bytes, emitted bytes, a numeric mapping,
required or optional presence, field type, bound, semantic validation, COSE
binding, extension rule, state, or transition requires compatibility review.
An incompatible change requires a new protocol version, expected to be Core
v0.2 or later, and explicit human approval.

Backward-compatible extensions still require an approved extension definition
and registry decision. V3.6 OriginSet, Service Channel, origin update,
migration, resumption, and handover work MUST NOT be inserted silently into
Core v0.1.

## Non-claims

This contract does not integrate the protocol package into the existing
runtime. It does not implement WP2 Name Node or origin publication, WP3 QUIC
routing, a universal resolver, multi-operator federation, HA, cloud
deployment, or production conformance.

The module is a dependency-light protocol data boundary with deterministic
tests. Application authentication, HTTP semantics, OAuth, database behavior,
and general retry policy remain outside NBSR Protocol Core.
