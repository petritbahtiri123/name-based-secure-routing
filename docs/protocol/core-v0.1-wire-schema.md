# NBSR Core v0.1 wire schema freeze

**Status:** proposed with D6-A1 through D6-A3; pending human approval

**Scope:** deterministic CBOR payload schemas and wrapper requirements only; no production implementation

**Authority after approval:** D6 in `docs/protocol/wp1-decisions.md`

This document is the sole numeric-field source for WP1 Task 4. Every key is
assigned explicitly. Implementations MUST NOT derive keys from declaration
order, table order, dataclass order, or the field order in Vision V3.

## Common scalar and collection rules

- `uint` means a CBOR major-type 0 integer. A CBOR boolean is never an integer.
- `tstr` means definite-length, valid UTF-8 CBOR text. Fields restricted to
  ASCII reject every non-ASCII code point.
- `bstr` means a definite-length CBOR byte string.
- Canonical names are lowercase DNS A-label ASCII without a trailing dot:
  each label is 1 to 63 octets, the whole name is 1 to 253 octets, empty
  labels and IP literals are rejected.
- A textual NBSR ID is 1 to 64 ASCII octets and matches
  `[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*`. It has no whitespace, slash,
  backslash, control byte, repeated separator, or uppercase character.
- A key ID is an opaque `bstr` of 1 to 64 bytes. It is interpreted only in a
  caller-supplied trust context.
- A UUID-sized protocol ID or nonce is a `bstr` of exactly 16 bytes. No UUID
  textual form is accepted on the wire.
- A digest or thumbprint is a `bstr` of exactly 32 bytes.
- A timestamp is an unsigned Unix second in the inclusive range
  `0..253402300799`. Time comparisons use integer seconds in UTC.
- A sequence or generation is a `uint` in `1..18446744073709551615`.
- A port is a `uint` in `1..65535`.
- Set-like arrays are non-empty unless the field is explicitly optional,
  contain exact item types, are strictly ascending by their deterministic
  CBOR item bytes, and reject duplicate values.
- All structures remain subject to the bounded deterministic-CBOR limits in
  D1. A field-specific maximum below can only reduce those limits.
- No schema permits an origin hostname, origin IP address, IP-literal name,
  session key, or reusable bearer credential.

## Time-window limits

| Object | Maximum inclusive lifetime |
|---|---:|
| ServiceRecord | 604800 seconds |
| RouteIntent | 300 seconds |
| RouteGrant | 600 seconds |

For each object listed above, the end timestamp MUST be greater than the start
timestamp and the difference MUST NOT exceed the listed maximum. Construction
validates the shape of the window. A caller that supplies `now` additionally
rejects a not-yet-valid or expired object.

Revocation has no universal maximum lifetime. Its optional `expires_at`
follows the D6-A1 rules in the Revocation table.

## Fixed semantic registries

Publication modes are the exact text values `legacy`, `dual-published`,
`nbsr-preferred`, and `nbsr-secure-only`. Core v0.1 transport arrays contain
only `tcp`. Core v0.1 route-profile arrays contain only `nbsr-quic-1`.

Revocation numeric values are frozen as follows:

| Registry | Code | Meaning |
|---|---:|---|
| target type | 1 | service record |
| target type | 2 | signing key |
| target type | 3 | route |
| target type | 4 | lease |
| target type | 5 | operator |
| target type | 6 | edge |
| target type | 7 | origin connector |
| mode | 1 | deny new use |
| mode | 2 | terminate active use |
| reason | 1 | unspecified |
| reason | 2 | key compromise |
| reason | 3 | ownership change |
| reason | 4 | policy violation |
| reason | 5 | administrative |
| reason | 6 | superseded |

A revocation `target_id` is SHA-256 over the target's canonical identifier
bytes: canonical-name ASCII for a service record, opaque key-ID bytes for a
signing key, raw 16-byte ID for a route or lease, and textual-ID ASCII for an
operator, edge, or origin connector.

## COSE Sign1 wrapper matrix

Vision V3 section 10.3 makes COSE Sign1 the only object-level signature
wrapper in Core v0.1. The signed objects are deterministic-CBOR payload maps
without an embedded signature field.

| Object | Object-level COSE Sign1 | Protected `kid` binding |
|---|---|---|
| ServiceRecord | required | `kid` equals `owner_key_id` byte-for-byte |
| RouteGrant | required | `kid` resolves only in caller-supplied authorized issuer trust context |
| Revocation | required | `kid` equals `issuer_key_id` byte-for-byte |
| RouteIntent | prohibited | No object-level COSE wrapper |
| ProtocolError | prohibited | No object-level COSE wrapper |
| ControlEnvelope | prohibited | No object-level COSE wrapper |

For ServiceRecord and Revocation, signature verification succeeds only when
the protected-header `kid` exactly matches the corresponding payload byte
string. RouteGrant has no issuer field: its protected `kid` is opaque and may
select a key only from the caller-supplied authorized RouteGrant issuer trust
context. No fallback to a global key namespace, payload-derived lookup, or
unprotected-header key identifier is permitted.

## ServiceRecord

ServiceRecord is the payload carried by the required COSE Sign1 wrapper. It
has no embedded signature field, and the protected `kid` must equal
`owner_key_id` byte-for-byte. Every listed field is required.

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

## RouteIntent

RouteIntent is short-lived prepared route state. It binds the non-exported
resolution context to a canonical name before a RouteGrant exists.

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

## RouteGrant

Core v0.1 uses only `name_digest`, never a canonical-name-or-digest union.
`name_digest` is SHA-256 over the canonical-name ASCII bytes. Core v0.1 uses
only `allowed_ports`; service-capability encoding is deferred to a later
version. RouteGrant is a payload without an embedded signature and uses the
required COSE Sign1 RouteGrant issuer trust-context rule above.

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

## Revocation

Revocation has one fixed target representation: a target-type code plus a
32-byte target digest. It contains no polymorphic text-or-bytes target field.
It is a payload without an embedded signature, and its required COSE Sign1
protected `kid` must equal `issuer_key_id` byte-for-byte.

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

Acceptance stores the highest accepted issuer generation as a durable
tombstone even after a revocation expires or is administratively removed.
An object at or below that generation is rejected, preventing revocation
rollback and resurrection. `target_sequence` is not the issuer monotonicity
mechanism; it only scopes a service-record target. Issuer monotonicity always
uses `generation`.

## ProtocolError

ProtocolError carries only a stable code and retry guidance. It never carries
free-form remote detail, origin information, trust internals, keys, or tokens.

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `error_version` | required | `uint` | 1 | 1 | Must equal Core object version 1 |
| 1 | `error_code` | required | `uint` | 1 | 19 | Must be exactly one frozen D3 ErrorCode value |
| 2 | `request_id` | required | `bstr` | 16 bytes | 16 bytes | Must identify the failed request without exposing session material |
| 3 | `retryable` | required | CBOR boolean | false | true | Exact major-type 7 false or true; integers 0 and 1 are rejected |
| 4 | `retry_after_seconds` | optional | `uint` seconds | 1 | 3600 | Present only when `retryable` is true; absent when false |

## ControlEnvelope

ControlEnvelope key 6 is the critical-extension-key list. Its `body` is the
numeric-key map required by the selected `message_type`; Task 4 models only
the bounded envelope map and does not invent message-specific body fields.

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---:|---|---|---|---|---|---|
| 0 | `protocol_version` | required | `uint` | 1 | 1 | Must equal Core protocol version 1 |
| 1 | `message_type` | required | `uint` | 1 | 17 | Must be exactly one frozen D3 MessageCode value |
| 2 | `request_id` | required | `bstr` | 16 bytes | 16 bytes | Correlation identifier for this request or response |
| 3 | `session_id` | required | `bstr` | 16 bytes | 16 bytes | Identifier of the authenticated control session |
| 4 | `monotonic_sequence` | required | `uint` | 1 | 18446744073709551615 | Must be greater than caller-supplied last accepted session sequence |
| 5 | `body` | required | map with `uint` keys | 0 pairs | 128 pairs | Message-specific schema validates all body keys and values separately |
| 6 | `critical_extension_keys` | optional | array of `uint` | 1 item | 32 items | Extension keys only; strictly ascending, unique, and each key must be present |

## Unknown-field and extension rules

1. Keys `0..999` are the reserved Core range. Any unlisted Core key in any
   schema is rejected.
2. ServiceRecord, RouteIntent, RouteGrant, Revocation, and ProtocolError are
   closed schemas in Core v0.1. They reject every key `>=1000`.
3. ControlEnvelope alone permits extension keys `1000..18446744073709551615`.
4. An extension key absent from key 6 is non-critical. Its value may use only
   the deterministic Core CBOR value types accepted by D1, remains subject to
   all resource limits, is preserved as an immutable numeric-key/value pair,
   and has no authorization semantics in Core v0.1.
5. Every key listed in key 6 MUST be `>=1000`, MUST occur exactly once in the
   same envelope, and MUST be strictly ascending with no duplicate.
6. Core v0.1 defines no recognized critical extension. Therefore every
   non-empty key-6 list is rejected with `NBSR_E_PROFILE_UNSUPPORTED`.
7. Listing a Core key, an absent extension key, a duplicate key, or an
   unsupported critical key is always a fail-closed error.

## Approval consequences

Approval freezes every table, registry, bound, and rule in this document as
D6. Task 4 tests and code may then copy these mappings as explicit literals.
Any change after approval requires human review, updated documentation tests,
and a versioning decision if encoded bytes or accepted values change.
