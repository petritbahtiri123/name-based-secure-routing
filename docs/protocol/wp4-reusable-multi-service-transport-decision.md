# WP4 reusable multi-service transport decision

**Status:** Complete at the approved origin-free reusable multi-service
same-edge loopback lab scope. This is not production readiness.

## Scope and frozen boundary

WP4 extends the completed origin-free WP3 Rust loopback lab in
`crates/nbsr-transport` so one compatible, mutually authenticated QUIC
Transport Session can carry multiple independently authorized Service Channels.
It does not authorize OriginSet selection, an Origin Endpoint connection,
NameRelay integration, a production claim, 0-RTT, cross-edge resume, or a
frozen Core v0.1 change; it does not select or connect an Origin Endpoint,
integrate NameRelay, claim production readiness, or modify frozen Core v0.1
D1-D6 registries, schemas, states, or wrappers.

The existing native Core v0.2 candidate profile over Quinn remains the basis.
WP4 does not add HTTP/3, QPACK, MASQUE, CONNECT-UDP, Capsules, a second channel
identifier, or a custom transport cryptosystem. The existing 16-byte
`channel_id` is the only Service Channel wire identifier in `ROUTE_*`,
`STREAM_*`, exporter context, audit records, quota state, drain state, resume
state, and UDP framing.

## Transport Session reuse and RouteGrant admission

The exact Transport Session reuse tuple is:

```text
(source_edge_id, destination_edge_id, trust_profile_id, ALPN, protocol_version)
```

A matching tuple is necessary but not sufficient. Reuse is forbidden when the
session is draining, expired, over capacity, on a different authenticated
protocol version, outside reauthentication policy, or incompatible with the
requested service policy. Path and capacity are eligibility state, not tuple
fields. Service Identity and RouteGrant are never Transport Session authority.

A RouteGrant is single-use per Service Channel admission. Its exact signed
bytes, digest, route ID, service, unique nonce, policy, transport, port,
authenticated edges, proof key, and validity bind one `channel_id`. Opening
another channel, including one for the same service, requires a fresh
RouteGrant and nonce. Transport reuse never renews or broadens a grant.

The lab limits are 32 active channels per session and eight active channels for
one service per session. The session idle timeout remains 30 seconds, maximum
session age remains 60 minutes, and keepalive remains disabled.

## Independent channel lifecycle and limits

The authenticated control session has one HELLO exchange and then admits
multiple independent ROUTE exchanges. Its session state owns a bounded map
keyed by `channel_id`; every entry owns its route binding, stream gates,
counters, revocation flag, drain deadline, audit sequence, and exporter
binding.

```text
Candidate -> Active -> Draining -> Closed
                    \-> Revoked -> Closed
```

Malformed or rejected candidate state is not retained. A channel-local error
closes or resets only that channel's streams unless control integrity,
authenticated session identity, audit integrity, or a session-wide resource
invariant cannot be trusted. Unknown channel IDs fail closed without affecting
valid sibling channels. Existing Core v0.2 candidate `ROUTE_*` and `STREAM_*`
numeric-key bodies remain unchanged. Lifecycle controls use existing symbolic
`ROUTE_DRAIN`, `ROUTE_REVOKE`, and `ROUTE_CLOSE` only inside the Core v0.2
candidate profile; their closed bodies require deterministic vectors before
runtime decoding. No new Core v0.1 value is allocated.

| Limit | Value |
|---|---:|
| Active channels per Transport Session | 32 |
| Active channels per service per session | 8 |
| Concurrent reliable streams per channel | 64 |
| Peer-initiated bidirectional streams per Transport Session | 2049 (1 control plus 2048 application streams) |
| Buffered bytes per reliable stream | 1 MiB |
| Buffered reliable bytes per channel | 8 MiB |
| UDP datagram payload | `min(peer QUIC DATAGRAM maximum minus framing, 1200 bytes)` |
| Maximum encoded UDP frame | 1235 bytes |
| Buffered UDP datagrams per channel | 64 |
| UDP rate per channel | 100 datagrams/second with burst 100 |
| Audit queue | 1024 events |
| Replay/tombstone entries per session | 4096 |
| Channel drain maximum | 30 seconds |
| Same-edge resume window | 30 seconds and never beyond grant/session expiry |

Reliable-byte accounting is bidirectional, uses backpressure, and never exceeds
either byte bound. A successful send or returned receive payload retains its
channel reservation until the application explicitly releases that stream's
buffered-payload ownership (or the stream is safely dropped/reset); returning a
raw payload does not release or bypass accounting. Eight simultaneously held
1 MiB payloads exhaust the channel allowance, and another payload is admitted
only after a held reservation is released.
Each channel permits at most 64 concurrent reliable streams per channel.
UDP is drop-on-quota with a channel-scoped audit event. Mandatory audit queue
exhaustion rejects the state-changing operation before mutation. Audit records
contain timestamp, monotonic audit sequence, session ID, channel ID, service
ID, action, outcome, and safe reason code; they contain no secret, exporter
value, grant bytes, payload, Origin Endpoint, or DNS data.

## Exporter-bound channel context

After mutual TLS completes and `ROUTE_ACCEPT` is validated, both peers derive a
32-byte channel binding with the TLS 1.3 exporter. The ASCII label is:

```text
EXPORTER-NBSR-Service-Channel-v2
```

The exporter context is the SHA-256 of the deterministic CBOR encoding of:

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

The value is channel-binding evidence and domain-separated keying material; it
does not replace QUIC packet protection and is never logged. A channel becomes
usable only when the locally derived value matches the expected cross-peer
vector or confirmation input. Positive vectors and one-field mutation,
ordering, type, label, length, and different-handshake vectors are required.
A dependency-independent verifier must reproduce the canonical context bytes,
context hash, and expected 32-byte exporter result.

Every Service Channel independently validates the full WP3 admission chain.
Grant A cannot authorize, resume, drain, revoke, close, stream, or send a
datagram for channel B. Revocation is terminal, installs a tombstone through at
least the later of grant expiry plus 30 seconds or the same-edge resume window,
rejects new streams and datagrams immediately, and resets existing channel
streams. It cannot revive after drain or resume.

## Drain and same-edge resumption

Channel drain stops new streams and datagrams immediately and allows already
accepted reliable streams to finish for at most 30 seconds. At the deadline,
remaining streams reset and the channel closes. Session drain stops new
channels, streams, and datagrams; existing channels receive the same bounded
30-second maximum before the QUIC connection closes. Drain never extends a
grant, session age, authorization, or resume window. Origin Endpoint
replacement and origin drain are not WP4 behavior: drain is session/channel
only.

WP4 resumption is application-state restoration on a newly authenticated
Transport Session to the same exact Source Edge and Destination Edge identities,
trust profile, ALPN, and protocol version. TLS/QUIC resumption alone grants no
Service Channel authority and 0-RTT remains disabled. A resume attempt requires
a fresh RouteGrant, fresh nonces, fresh proof of possession, a new `session_id`,
a new `channel_id`, and a fresh exporter binding. It may correlate to a prior
channel only through an opaque 32-byte single-use resume handle retained for at
most 30 seconds.
The issued record retains the old Transport Session's mandatory monotonic hard
deadline. Its effective expiry is the earliest of issue plus 30 seconds,
remaining RouteGrant validity, any shorter authority deadline, and that old
session hard deadline; equality with an authority deadline is expired.
Issue, preflight, admission, and consume read this authority only from the
sealed `ControlSession` clock. Their public APIs accept no monotonic timestamp,
and all retained-record and session deadlines share one absolute
process-monotonic domain. Each session stores its absolute creation instant and
derives its absolute 60-minute hard deadline from that same snapshot; a newly
created session therefore has age zero without resetting old-session authority.

The prior channel must have closed without revocation, must not be draining,
and all current expiry, policy, service, edge, client-key, replay, capacity,
and audit checks must pass. Reuse consumes the handle atomically; failure
creates no channel. Cross-edge resumption and handover always fail closed and
remain WP6.

## Native QUIC DATAGRAM profile

Native QUIC DATAGRAM was implemented after TCP, exporter, lifecycle, and
resumption passed. It uses Quinn's RFC 9221 QUIC DATAGRAM
support: no HTTP/3, no MASQUE, and no CONNECT-UDP. One QUIC DATAGRAM payload is one
complete application datagram; NBSR does not fragment or reassemble it.

This WP4 integration adds direct exact-pinned `bytes = 1.12.1` beyond WP3's
six-dependency baseline because Quinn's public `Connection::send_datagram`
accepts `bytes::Bytes`. Version 1.12.1 was already present in the lockfile; the
addition does not relax exact pinning or permit other direct dependencies.

The NBSR payload is deterministic CBOR with a closed numeric-key map containing
body version, `channel_id`, monotonically increasing per-direction datagram
sequence, and a byte-string payload. Numeric keys and exact bytes are allocated
only by the approved Core v0.2 WP4 schema/vector task, never in Core v0.1. The
receiver rejects unknown fields, non-canonical encoding, replayed or
non-monotonic sequence, inactive/draining/revoked channels, wrong transport,
oversize payload, and quota exhaustion without delivering payload. A channel's
UDP failure does not terminate sibling channels.

## Completion gate

Every behavior begins with a failing focused test. Deterministic wire and
exporter fixtures require independent verification before their runtime path is
enabled. Completion requires evidence that two services share one session while
authorization, grant nonce, exporter context, stream/byte/datagram quota, audit,
revocation, drain, failure, and resume state remain isolated. The implementation
is complete only at that lab scope.

## Completion evidence and review

Fresh final validation passed 114 executable Rust tests plus 16 doctests (130
total), 332 focused WP4/frozen-protocol Python tests, and 826 passed with 1
skipped in the full Python suite. Rustfmt, Clippy with `-D warnings`, Ruff on
107 formatted files, `pip check`, both Core regeneration checks, and
`git diff --check` passed. The separately owned Core v0.2 exporter subtree
passed canonical CBOR single hash regeneration plus Python and Node checks for
2 valid and 21 invalid/mutation vectors.

The original independent review found Critical and Important authorization
and binding defects; each was fixed with a failing regression first.
Final independent review: PASS with 0 Critical, 0 Important, and 0 Minor findings.
This evidence adds no OriginSet selection, Origin Endpoint forwarding,
NameRelay integration, production claim, cross-edge resume, 0-RTT, WP5+
behavior, or frozen Core v0.1 schema/registry/state/wrapper change.
