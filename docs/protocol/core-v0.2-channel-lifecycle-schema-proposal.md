# Core v0.2 channel lifecycle schema proposal

**Status:** approved on 2026-08-01; frozen as a Core v0.2 candidate

**Date:** 2026-08-01

## Scope

This profile freezes closed deterministic CBOR bodies for the existing symbolic
codes `ROUTE_DRAIN` 12, `ROUTE_REVOKE` 13, and `ROUTE_CLOSE` 14 only when the
enclosing `ControlEnvelope.protocol_version` is 2. It allocates no message code,
error code, critical extension, or COSE wrapper and changes no Core v0.1
registry, schema, vector, state, or transition.

These controls apply to one active Service Channel on the same authenticated
Transport Session. They do not drain or replace an Origin, disclose an Origin
Endpoint, authorize resume, UDP, 0-RTT, or cross-edge continuity, or grant new
route authority.

## `ROUTE_DRAIN` body

| Key | Field | Presence | Exact CBOR wire type | Bound | Semantic validation |
|---:|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | exactly 1 | Exactly 1 |
| 1 | `channel_id` | required | byte string | exactly 16 bytes | Nonzero and equal to the active channel |
| 2 | `route_id` | required | byte string | exactly 16 bytes | Nonzero and equal to the active Route Context |
| 3 | `route_grant_digest` | required | byte string | exactly 32 bytes | Equal to the digest of the grant authorizing the active channel |
| 4 | `requested_at` | required | unsigned integer | 0 through 253402300799 | Unix seconds; never extends grant or session authority |
| 5 | `drain_seconds` | required | unsigned integer | 0 through 30 | Values above 30 are rejected, not clamped |

## `ROUTE_REVOKE` body

| Key | Field | Presence | Exact CBOR wire type | Bound | Semantic validation |
|---:|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | exactly 1 | Exactly 1 |
| 1 | `channel_id` | required | byte string | exactly 16 bytes | Nonzero and equal to the active or draining channel |
| 2 | `route_id` | required | byte string | exactly 16 bytes | Nonzero and equal to the active Route Context |
| 3 | `route_grant_digest` | required | byte string | exactly 32 bytes | Equal to the channel's verified grant digest |
| 4 | `revoked_at` | required | unsigned integer | 0 through 253402300799 | Unix seconds used by terminal revocation and tombstone retention |

## `ROUTE_CLOSE` body

| Key | Field | Presence | Exact CBOR wire type | Bound | Semantic validation |
|---:|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | exactly 1 | Exactly 1 |
| 1 | `channel_id` | required | byte string | exactly 16 bytes | Nonzero and equal to the live channel |
| 2 | `route_id` | required | byte string | exactly 16 bytes | Nonzero and equal to the active Route Context |
| 3 | `route_grant_digest` | required | byte string | exactly 32 bytes | Equal to the channel's verified grant digest |
| 4 | `closed_at` | required | unsigned integer | 0 through 253402300799 | Unix seconds; close retains replay and tombstone state |

## Closed deterministic decoding

The three bodies are closed numeric-key maps. Missing, duplicate, or unknown
keys; booleans used as integers; indefinite-length items; floats; tags;
non-preferred integer or length encodings; wrong fixed lengths; trailing bytes;
and any enclosing protocol version other than 2 fail closed. The enclosing
`request_id` must be nonzero and unique, `session_id` must equal the established
Transport Session, and `monotonic_sequence` must strictly advance. A wrong
channel, sibling route, or grant digest consumes neither request nor sequence.

The reviewed deterministic fixture sizes are 124 bytes for `ROUTE_DRAIN` and
121 bytes each for `ROUTE_REVOKE` and `ROUTE_CLOSE`, using 16-byte request,
session, channel, and route identifiers and a 32-byte grant digest.

## Bounded drain semantics

A receiver creates `DrainDeadline` from injected monotonic seconds with
saturating addition. The effective channel deadline is the earliest of the
requested duration (at most 30 seconds), remaining grant lifetime, and the
Transport Session authority deadline. A drain never extends grant expiry,
session age, revocation, authorization, replay, tombstone, or resume lifetime.

Channel drain audits before `Active -> Draining`, then rejects new route/stream
controls, Application Streams, byte reservations, future datagrams, and binding
installation. Already accepted reliable streams may finish and release
accounting before the effective deadline. At the exact deadline the receiver
audits, retains replay/tombstone state, closes the channel, and uses Quinn reset
and stop-sending only inside the transport adapter. Revocation during drain is
immediate and terminal.

Transport Session drain is local state and has no lifecycle wire message or
all-zero `channel_id` sentinel. It audits before mutation, denies new routes and
streams immediately, and gives existing reliable streams no more than 30
seconds, subject to earlier authority. The safe start API accepts trusted
injected Unix and monotonic seconds so every active channel snapshots the
earliest grant, existing channel-drain, and session deadline. The adapter resets
each channel at that earlier deadline even while the session remains draining;
at the session deadline it resets all remaining tracked streams and closes only
that Quinn connection. Unrelated sessions are not affected.

Received `ROUTE_REVOKE` and `ROUTE_CLOSE` controls enter through the exact
authenticated connection adapter. Only after connection binding, control
validation, audit, and logical commit succeed does the adapter reset that
channel's tracked streams. The underlying session transitions are crate-private
so public callers cannot bypass transport teardown.

Audit exhaustion before a start or deadline commit leaves lifecycle state
unchanged. At a deadline, authorization stays denied and the adapter still
resets or closes for safety; the typed enforcement result reports failed audit
integrity without reopening work.

## Compatibility classification

| Surface | Classification | Effect |
|---|---|---|
| Codes 12 through 14 | Versioned reuse | Legal only in a version-2 envelope |
| Quinn reset, stop-sending, connection close | Standard transport reuse | Confined to `quinn_adapter.rs` |
| Service Channel drain state | Core v0.2 runtime state | Scoped to one channel and its streams |
| Transport Session drain | Local runtime state | No wire sentinel or new message code |
| Frozen Core v0.1 D1-D6 | Preserved | No registry, schema, state, or vector change |

The 17 frozen message codes, 19 frozen error codes, six D6 schemas, and Core
v0.1 expectations remain unchanged.
