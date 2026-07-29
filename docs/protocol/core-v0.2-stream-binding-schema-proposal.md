# Core v0.2 stream-binding schema proposal

**Status:** human approval required; not frozen

**Date:** 2026-07-29

**Runtime authorization:** none. This document proposes numeric body keys for
review. It does not allocate them, approve protocol version 2, authorize a
dependency, or permit WP3 runtime implementation.

## Purpose

Bind one QUIC Application Stream to exactly one independently authorized
Service Channel and Route Context without making the whole Transport Session
an authorization context. The proposal reuses the frozen symbolic message
codes `STREAM_OPEN` 6, `STREAM_ACCEPT` 7, and `STREAM_REJECT` 8 only under a
separately approved protocol version 2 profile.

The three bodies below are closed numeric-key maps carried as the `body` of a
frozen D6 `ControlEnvelope`. Numeric keys are assigned individually in this
proposal and are never derived from source-code field order.

## STREAM_OPEN body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `quic_stream_id` | required | unsigned integer | 4 | 4611686018427387903 | Source-initiated bidirectional QUIC stream; divisible by 4; stream 0 is reserved for control |
| 2 | `channel_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Identifies one active independently authorized Service Channel on the same authenticated Transport Session |
| 3 | `route_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Equals the active Route Context and the verified RouteGrant `route_id` |
| 4 | `route_grant_digest` | required | byte string | exactly 32 bytes | exactly 32 bytes | SHA-256 over the complete verified deterministic COSE Sign1 RouteGrant bytes; must match the grant authorizing this channel |
| 5 | `transport` | required | text string | exactly 3 UTF-8 bytes | exactly 3 UTF-8 bytes | Exactly `tcp`; future transports require a separately approved versioned profile |
| 6 | `port` | required | unsigned integer | 1 | 65535 | Destination application port permitted by the RouteGrant and current policy; not an exposed Origin Endpoint |

## STREAM_ACCEPT body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `quic_stream_id` | required | unsigned integer | 4 | 4611686018427387903 | Echoes the accepted `STREAM_OPEN` stream ID on the same authenticated Transport Session |
| 2 | `channel_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the independently authorized Service Channel identifier |
| 3 | `route_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the accepted active Route Context identifier |
| 4 | `accepted_at` | required | unsigned integer | 0 | 253402300799 | UTC Unix seconds when admission completed; must not exceed the receiving implementation clock plus approved skew |

## STREAM_REJECT body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `quic_stream_id` | required | unsigned integer | 4 | 4611686018427387903 | Echoes the rejected `STREAM_OPEN` stream ID on the same authenticated Transport Session |
| 2 | `channel_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the candidate Service Channel identifier without accepting or allocating it |
| 3 | `route_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the candidate Route Context identifier without accepting it |
| 4 | `protocol_error` | required | numeric-key map | exactly the frozen D6 ProtocolError schema | exactly the frozen D6 ProtocolError schema | Carries the most specific safe frozen error; its `request_id` equals the enclosing `ControlEnvelope.request_id` and it contains no Origin Endpoint |

Structurally malformed messages that cannot supply all required echo fields
are rejected with the existing generic `ERROR` envelope rather than a partial
`STREAM_REJECT`. Booleans are not integers. Duplicate keys, indefinite
lengths, non-preferred encodings, unsupported tags, floats, trailing bytes,
and unknown numeric keys are rejected. An unknown numeric key maps to
`NBSR_E_PROFILE_UNSUPPORTED`; resource-limit failures remain
`NBSR_E_OVER_CAPACITY`.

## Control-stream framing

The first Source Edge-initiated bidirectional QUIC stream is stream 0 and is
the only control stream in this profile. Each control frame is:

```text
shortest-form QUIC variable-length integer frame_length
deterministic CBOR ControlEnvelope bytes
```

`frame_length` is from 1 through 65,536 bytes inclusive and counts only the
following CBOR bytes. The prefix must use the shortest-form QUIC
variable-length integer. The CBOR item must consume the complete frame with no
trailing bytes. More frames may follow sequentially on stream 0. Existing
bounded CBOR limits continue to apply inside the frame.

Application streams are later Source Edge-initiated bidirectional QUIC
streams: 4, 8, 12, and so on. `STREAM_OPEN` is sent on stream 0 and references
one such stream. The Source Edge sends no application bytes on the referenced
stream before a matching `STREAM_ACCEPT`. On rejection, peers use standard
QUIC stream reset and stop-sending behavior; NBSR defines no custom data-stream
preface. No 0-RTT is permitted for route-changing controls, including
`STREAM_OPEN`.

## Binding and validation

Acceptance requires all of the following:

1. The enclosing `ControlEnvelope.session_id` belongs to the same authenticated
   Transport Session carrying stream 0 and the referenced Application Stream.
2. `request_id` is unique within that session and `monotonic_sequence` strictly
   increases under the frozen ControlEnvelope rules.
3. One `quic_stream_id` is opened at most once per Transport Session.
4. One `channel_id` identifies an active Service Channel independently
   authorized for exactly one service.
5. One `route_id` identifies the active Route Context named by the verified
   RouteGrant, and the supplied grant digest matches byte-for-byte.
6. The service, source edge, destination edge, transport, port, policy,
   sequence, expiry, revocation, nonce, and client-session-key bindings remain
   valid at admission time.
7. Capacity is reserved only after bounded framing, replay, grant, revocation,
   and policy checks succeed.

A `STREAM_ACCEPT` or `STREAM_REJECT` is a response only when the enclosing
`request_id` and `session_id` match the original `STREAM_OPEN`, and its echoed
stream, channel, and route fields match exactly. A mismatched or replayed
response fails closed.

## Privacy and failure behavior

An Origin Endpoint, delegated origin hostname, DNS answer, connector address,
or internal health-check result must not appear in any of these bodies,
client-visible errors, or normal client telemetry. The `port` is an authorized
service port, not proof or disclosure of a selected origin. Rejections use the
most specific frozen ProtocolError code that is safe to expose.

Failure of this Service Channel resets only its bound Application Stream unless
transport integrity or authenticated peer state is invalid. It does not
authorize, revive, or unnecessarily terminate an unrelated channel.

## Unresolved dependencies that block runtime

This proposal assumes, but does not define, two prerequisite exchanges:

- `CLIENT_HELLO` and `EDGE_HELLO` bodies that establish and bind the
  `ControlEnvelope.session_id`; and
- `ROUTE_OPEN`, `ROUTE_ACCEPT`, and `ROUTE_REJECT` bodies that create the
  independently authorized Route Context and Service Channel.

Both exchanges need explicit numeric schemas, exact validation, deterministic
vectors, and separate human approval. Their absence blocks WP3 runtime even if
the three STREAM body tables are approved. This document does not infer those
schemas from opaque maps or allocate new message codes.

The exact per-Service-Channel TLS exporter derivation also remains a separate
WP4 gate. WP3 may prove single-service binding without claiming that the future
multi-service cryptographic separation formula is frozen.

## Compatibility classification

| Surface | Classification | Effect |
|---|---|---|
| QUIC stream identifiers and reset behavior | Reuse existing standard | No custom transport primitive |
| Control-frame length prefix | NBSR profile of QUIC variable-length integer | New versioned framing rule |
| Three STREAM body mappings | New Core v0.2 wire semantic | Human schema approval required |
| Existing STREAM symbolic codes | Versioned reuse candidate | Legal only after protocol version 2 approval |
| Frozen D1-D6 objects and registries | Preserved | No Core v0.1 change |

The 17 message codes remain unchanged. The 19 error codes remain unchanged.
The six D6 schemas remain unchanged. Frozen state registries and transitions
remain unchanged. This proposal creates no new critical extension and no new
COSE wrapper.

Protocol version 2 is not yet allocated. Reusing codes 6 through 8 with these
new bodies requires separate approval of protocol version 2 negotiation and
downgrade behavior. A Core v0.1 peer must never interpret these proposed
bodies.

## Approval ballot

Human approval is required for:

1. the exact numeric mappings in all three body tables;
2. stream 0 as the sole control stream and the length-prefixed framing;
3. Source Edge-initiated bidirectional Application Streams starting at ID 4;
4. the RouteGrant COSE Sign1 digest definition;
5. mandatory wait for `STREAM_ACCEPT` before application bytes;
6. closed maps and the stated error mapping;
7. reuse of existing STREAM codes only under a future protocol version 2; and
8. preparation, but not implementation, of the prerequisite HELLO and ROUTE
   body schemas.

Approval freezes only this documentation proposal after its status is amended.
It does not authorize runtime until every dependency above has passed its own
gate and an implementation plan is approved.
