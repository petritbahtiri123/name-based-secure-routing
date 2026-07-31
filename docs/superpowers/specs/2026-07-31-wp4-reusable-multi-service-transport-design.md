# WP4 Reusable Multi-Service Transport Design

**Status:** Approved for implementation on 2026-07-31

## Scope

WP4 extends the completed origin-free WP3 Rust loopback lab so one compatible,
mutually authenticated QUIC Transport Session can carry multiple independently
authorized Service Channels. Work remains confined to `crates/nbsr-transport`.
It does not select or connect an Origin Endpoint, integrate NameRelay, modify
frozen Core v0.1 D1-D6 registries/schemas/states/wrappers, claim production
readiness, or implement cross-edge continuity.

The implementation is one cohesive plan executed in ordered TDD tasks:

1. multi-channel control and reliable TCP streams;
2. exporter-bound channel context and independent vectors;
3. authorization, revocation, quotas, audit, and failure containment;
4. bounded channel/session drain;
5. same-edge resumption;
6. native QUIC DATAGRAM UDP channels; and
7. complete validation, independent review, and evidence documentation.

## Selected approach

Use the existing native Core v0.2 candidate profile over Quinn. Do not add
HTTP/3, QPACK, MASQUE, CONNECT-UDP, Capsules, a second channel identifier, or a
custom transport cryptosystem. The existing 16-byte `channel_id` is the
Service Channel wire identifier in `ROUTE_*`, `STREAM_*`, exporter context,
audit records, quota state, drain state, resume state, and UDP framing.

## Transport Session reuse

The exact reuse key is:

```text
(source_edge_id, destination_edge_id, trust_profile_id, ALPN, protocol_version)
```

A matching key is necessary but not sufficient. Reuse is forbidden when the
session is draining, expired, over capacity, on a different authenticated
protocol version, outside reauthentication policy, or incompatible with the
requested service policy. Path and capacity are eligibility state, not key
fields. A Service Identity and RouteGrant are never transport authority.

The WP4 lab profile permits at most 32 active channels per session and eight
active channels for one service. The session idle timeout remains 30 seconds,
maximum session age is 60 minutes, and keepalive remains disabled.

## RouteGrant policy

A RouteGrant is single-use for Service Channel admission. Its exact signed
bytes, digest, route ID, service, unique nonce, policy, transport, port,
authenticated edges, proof key, and validity remain bound to one `channel_id`.
Opening another channel—including another channel for the same service—needs a
fresh RouteGrant and nonce. Transport reuse never renews or broadens a grant.

## Control and channel lifecycle

The authenticated control session has one HELLO exchange and then admits
multiple independent ROUTE exchanges. Its session state no longer stores one
global accepted route. Instead it owns a bounded map keyed by `channel_id`.
Each entry has its own route binding, stream gates, counters, revocation flag,
drain deadline, audit sequence, and exporter binding.

The channel lifecycle is:

```text
Candidate -> Active -> Draining -> Closed
                    \-> Revoked -> Closed
```

Malformed or rejected candidate state is not retained. A channel-local error
closes or resets only that channel's streams unless control integrity,
authenticated session identity, audit integrity, or a session-wide resource
invariant can no longer be trusted. Unknown channel IDs fail closed without
affecting valid siblings.

The existing Core v0.2 candidate `ROUTE_*` and `STREAM_*` numeric-key bodies
remain unchanged. No new Core v0.1 value is allocated. WP4 lifecycle controls
reuse the existing symbolic `ROUTE_DRAIN`, `ROUTE_REVOKE`, and `ROUTE_CLOSE`
only inside the Core v0.2 candidate profile; their exact closed bodies must be
documented and covered by deterministic vectors before runtime decoding.

## Exporter-bound channel context

After mutual TLS completes and ROUTE_ACCEPT is validated, both peers derive a
32-byte channel binding with the TLS 1.3 exporter. The ASCII label is:

```text
EXPORTER-NBSR-Service-Channel-v2
```

The exporter context is SHA-256 of the deterministic CBOR encoding of:

```text
[
  "NBSR-SERVICE-CHANNEL-CONTEXT-v2",
  2,
  session_id,
  source_edge_id,
  destination_edge_id,
  channel_id,
  route_id,
  route_grant_digest,
  service_id,
  transport,
  port,
  policy_hash,
  client_nonce,
  edge_nonce
]
```

The value is channel-binding evidence and domain-separated keying material;
it does not replace QUIC packet protection and is never logged. A channel may
become usable only when the locally derived value matches the expected
cross-peer vector or confirmation input. Positive vectors plus one-field
mutation, ordering, type, label, length, and different-handshake vectors are
required. A dependency-independent verifier must reproduce the canonical
context bytes, context hash, and expected 32-byte exporter result.

## Authorization, revocation, quotas, audit, and containment

Every Service Channel independently validates the full WP3 admission chain.
Grant A cannot authorize, resume, drain, revoke, close, stream, or send a
datagram for channel B.

The lab limits are exact:

| Limit | Value |
|---|---:|
| Active channels per Transport Session | 32 |
| Active channels per service per session | 8 |
| Concurrent reliable streams per channel | 64 |
| Buffered bytes per reliable stream | 1 MiB |
| Buffered reliable bytes per channel | 8 MiB |
| UDP datagram payload | min(peer QUIC DATAGRAM maximum minus framing, 1200 bytes) |
| Buffered UDP datagrams per channel | 64 |
| UDP rate per channel | 100 datagrams/second with burst 200 |
| Audit queue | 1024 events |
| Replay/tombstone entries per session | 4096 |
| Channel drain maximum | 30 seconds |
| Same-edge resume window | 30 seconds and never beyond grant/session expiry |

Reliable-byte accounting uses backpressure; it never buffers above either
bound. UDP is drop-on-quota with a channel-scoped audit event. Mandatory audit
queue exhaustion rejects the state-changing operation before mutation. Audit
records contain timestamp, monotonic audit sequence, session ID, channel ID,
service ID, action, outcome, and safe reason code; they contain no secret,
exporter value, grant bytes, payload, Origin Endpoint, or DNS data.

Revocation is terminal for the channel and installs a tombstone through at
least the later of grant expiry plus 30 seconds or the same-edge resume window.
It rejects new streams/datagrams immediately and resets existing channel
streams. It does not revive after drain or resume.

## Drain

Channel drain stops new streams and datagrams immediately and permits already
accepted reliable streams to finish for at most 30 seconds. At the deadline,
remaining streams are reset and the channel closes. Session drain stops new
channels, streams, and datagrams; existing channels receive the same bounded
30-second maximum before the QUIC connection closes. Drain never extends a
grant, session age, authorization, or resume window.

Origin Endpoint replacement and origin drain are not WP4 behavior.

## Same-edge resumption

WP4 resumption is application-state restoration on a newly authenticated
Transport Session to the same exact Source Edge and Destination Edge identities,
trust profile, ALPN, and protocol version. TLS/QUIC resumption alone confers no
Service Channel authority and 0-RTT remains disabled.

A resume attempt requires a fresh RouteGrant, fresh nonces, fresh proof of
possession, a new `session_id`, a new `channel_id`, and a fresh exporter
binding. It may correlate to a prior channel only through an opaque 32-byte
single-use resume handle retained for at most 30 seconds. The prior channel
must have closed without revocation, must not be draining, and all current
expiry, policy, service, edge, client-key, replay, capacity, and audit checks
must pass. Reuse consumes the handle atomically. Failure creates no channel.

Cross-edge resumption and handover always fail closed and remain WP6.

## UDP framing

UDP is implemented only after the TCP, exporter, lifecycle, and resumption
tasks pass. It uses Quinn's RFC 9221 QUIC DATAGRAM support, not HTTP/3 or
CONNECT-UDP. One QUIC DATAGRAM payload is one complete application datagram;
NBSR does not fragment or reassemble it.

The NBSR payload is deterministic CBOR with a closed numeric-key map containing
body version, `channel_id`, monotonically increasing per-direction datagram
sequence, and a byte-string payload. Numeric keys and their exact bytes are
allocated only in the approved Core v0.2 WP4 schema/vector task, never in Core
v0.1. The receiver rejects unknown fields, non-canonical encoding, replayed or
non-monotonic sequence, inactive/draining/revoked channels, wrong transport,
oversize payload, and quota exhaustion without delivering payload. A channel's
UDP failure does not terminate sibling channels.

## Testing and evidence

Every behavior starts with a failing focused test. Deterministic wire and
exporter fixtures must be independently verified before their runtime path is
enabled. Tests must prove two services share one session while authorization,
grant nonce, exporter context, stream/byte/datagram quota, audit, revocation,
drain, failure, and resume state remain isolated.

After focused tests pass, run the complete Rust suite, Rustfmt, Clippy with
`-D warnings`, focused frozen-protocol Python tests, full Python tests, Ruff,
`pip check`, both regeneration checks, and `git diff --check`. Documentation
records only freshly observed results. Code and evidence remain separate
commits. Independent review must report Critical and Important findings and
all such findings must be fixed with regression tests before completion.

