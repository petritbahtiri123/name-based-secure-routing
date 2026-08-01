# Core v0.2 session and route schema proposal

**Status:** approved on 2026-07-29; frozen as a Core v0.2 candidate

**Date:** 2026-07-29

**Runtime authorization:** none. This document proposes five numeric
message-body mappings and exact proof-of-possession input for review. It does
not allocate protocol version 2, change a frozen registry, authorize a QUIC
dependency, or permit WP3 runtime implementation.

## Purpose

Complete the two prerequisites discovered during stream-binding review:

1. bind an NBSR control session to the mutually authenticated QUIC Transport
   Session and a source-held proof-of-possession key; and
2. create one independently authorized Route Context / Service Channel before
   any Application Stream can be accepted.

The proposal reuses QUIC v1 and mutual TLS 1.3 for transport security, the
frozen D6 RouteGrant and ProtocolError objects, and the existing symbolic
message codes `CLIENT_HELLO` 1, `EDGE_HELLO` 2, `ROUTE_OPEN` 3,
`ROUTE_ACCEPT` 4, and `ROUTE_REJECT` 5. The new body mappings are candidates
only for a separately approved protocol version 2 profile.

All five bodies are closed numeric-key maps carried in the `body` of a
`ControlEnvelope`. Numeric keys are assigned explicitly and never inferred
from implementation field order.

## CLIENT_HELLO body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `source_operator_id` | required | ASCII text string | 1 octet | 64 octets | Matches the frozen textual NBSR identifier pattern and authenticated source certificate policy |
| 2 | `source_edge_id` | required | ASCII text string | 1 octet | 64 octets | Matches the frozen textual NBSR identifier pattern and exact source edge certificate SAN binding |
| 3 | `destination_operator_id` | required | ASCII text string | 1 octet | 64 octets | Matches the configured destination trust context |
| 4 | `destination_edge_id` | required | ASCII text string | 1 octet | 64 octets | Matches the frozen textual NBSR identifier pattern and the connected destination certificate SAN |
| 5 | `client_nonce` | required | byte string | exactly 32 bytes | exactly 32 bytes | Cryptographically unpredictable; not all zero; unique within the destination replay-retention window |
| 6 | `client_session_public_key` | required | byte string | exactly 32 bytes | exactly 32 bytes | Raw 32-byte RFC 8032 Ed25519 public key for RouteGrant proof of possession; distinct from the TLS certificate key |
| 7 | `sent_at` | required | unsigned integer Unix seconds | 0 | 253402300799 | Accepted only within caller-configured bounded clock-skew policy; never defines grant or route lifetime |

The envelope uses a source-chosen unpredictable 16-byte `session_id` generated
with a CSPRNG. It must not be all zero and must not repeat for the same
Destination Edge within retained replay state. The first outbound control
sequence is 1. The hello is carried only after the QUIC/TLS handshake
completes. No 0-RTT is permitted for HELLO or ROUTE messages.

## EDGE_HELLO body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `source_edge_id` | required | ASCII text string | 1 octet | 64 octets | Echoes the source edge identity accepted from the certificate-bound CLIENT_HELLO |
| 2 | `destination_edge_id` | required | ASCII text string | 1 octet | 64 octets | Equals the authenticated destination edge certificate SAN binding |
| 3 | `client_nonce` | required | byte string | exactly 32 bytes | exactly 32 bytes | Echoes the CLIENT_HELLO nonce byte-for-byte |
| 4 | `edge_nonce` | required | byte string | exactly 32 bytes | exactly 32 bytes | Destination-generated cryptographically unpredictable challenge; not all zero; single-use for route admission |
| 5 | `client_session_key_thumbprint` | required | SHA-256 byte string | exactly 32 bytes | exactly 32 bytes | SHA-256 of the raw CLIENT_HELLO 32-byte RFC 8032 Ed25519 public key |
| 6 | `accepted_at` | required | unsigned integer Unix seconds | 0 | 253402300799 | Created after identity, replay, capacity, and bounded clock-skew checks pass |

The client nonce and edge nonce are independent single-use challenges. The
`EDGE_HELLO` enclosing `request_id` and `session_id` exactly echo the
`CLIENT_HELLO` envelope. Control sequences are monotonic independently in each
sending direction. Both messages belong to the same authenticated QUIC
Transport Session; they cannot be copied to another connection or edge.

TLS certificate validation authenticates the Source Edge and Destination Edge.
The Ed25519 session key proves possession for RouteGrants and does not replace
mutual TLS 1.3, certificate-chain validation, certificate SAN role binding, or
caller-supplied operator trust policy.

## ROUTE_OPEN body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `channel_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Source-generated unpredictable identifier; not all zero; unique within this Transport Session |
| 2 | `route_grant` | required | byte string containing one deterministic COSE Sign1 RouteGrant | 1 byte | 32768 bytes | Complete frozen RouteGrant wrapper; verified only in caller-supplied authorized issuer trust context; no trailing bytes |
| 3 | `edge_nonce` | required | byte string | exactly 32 bytes | exactly 32 bytes | Exact unused challenge from the accepted EDGE_HELLO on this Transport Session |
| 4 | `requested_transport` | required | ASCII text string | exactly 3 octets | exactly 3 octets | Exactly `tcp` or `udp` and present in the verified RouteGrant `allowed_transports`; UDP uses the separately approved Core v0.2 DATAGRAM profile |
| 5 | `requested_port` | required | unsigned integer | 1 | 65535 | Present in the verified RouteGrant `allowed_ports` and current destination policy |
| 6 | `opened_at` | required | unsigned integer Unix seconds | 0 | 253402300799 | Within bounded clock skew and the verified RouteGrant validity interval |
| 7 | `proof_signature` | required | Ed25519 signature byte string | exactly 64 bytes | exactly 64 bytes | Valid RFC 8032 signature by the CLIENT_HELLO session public key over the exact transcript below |

`route_grant_digest` is SHA-256 over the complete verified deterministic COSE
Sign1 RouteGrant bytes carried at key 2. The digest binds the exact signed
object, including its protected headers, payload, and signature.

### Exact proof-of-possession transcript

The signed object is a deterministic CBOR array. The signed bytes are the NBSR
deterministic CBOR encoding of this exact array in this exact order:

```text
[
  "NBSR-ROUTE-OPEN-v2",
  2,
  ControlEnvelope.session_id,
  ControlEnvelope.request_id,
  channel_id,
  RouteGrant.route_id,
  RouteGrant.service_id,
  authenticated_destination_edge_id,
  edge_nonce,
  requested_transport,
  requested_port,
  route_grant_digest,
  opened_at
]
```

The first item is the literal ASCII domain-separation label
`NBSR-ROUTE-OPEN-v2`. Item 2 is unsigned integer protocol version 2. IDs,
nonce, digest, strings, port, and timestamp retain the exact wire types and
bounds defined in their schemas. The `proof_signature` is the RFC 8032
Ed25519 signature over those deterministic CBOR bytes without an extra
prehash.

The SHA-256 thumbprint of the verifying public key must equal the frozen
RouteGrant `client_session_key_thumbprint`. The RouteGrant `route_id`,
`service_id`, source identities, destination membership, transport, port,
policy hash, record sequence, validity, unique nonce, lease, revocation state,
and issuer signature must all validate independently of the proof signature.

## ROUTE_ACCEPT body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `channel_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the independently admitted Service Channel identifier |
| 2 | `route_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Equals the verified RouteGrant route ID |
| 3 | `route_grant_digest` | required | SHA-256 byte string | exactly 32 bytes | exactly 32 bytes | Echoes the digest of the exact RouteGrant accepted by destination admission |
| 4 | `accepted_at` | required | unsigned integer Unix seconds | 0 | 253402300799 | Created only after all admission and bounded capacity checks succeed |

The enclosing `request_id` and `session_id` match the `ROUTE_OPEN`. Acceptance
creates exactly one Route Context / Service Channel on this Transport Session.
It does not authorize a different service, grant, channel, session, edge,
transport, or port. It does not create an Application Stream.

## ROUTE_REJECT body

| Key | Field | Presence | Exact CBOR wire type | Minimum | Maximum | Semantic validation |
|---|---|---|---|---|---|---|
| 0 | `body_version` | required | unsigned integer | 1 | 1 | Exactly 1 for this proposal |
| 1 | `channel_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the candidate channel without accepting or allocating it |
| 2 | `route_id` | required | byte string | exactly 16 bytes | exactly 16 bytes | Echoes the parsed candidate RouteGrant route ID without accepting it |
| 3 | `route_grant_digest` | required | SHA-256 byte string | exactly 32 bytes | exactly 32 bytes | Identifies the rejected exact RouteGrant without exposing it |
| 4 | `protocol_error` | required | numeric-key map | exactly the frozen D6 ProtocolError schema | exactly the frozen D6 ProtocolError schema | Carries the most specific safe frozen error and matches the enclosing request ID |

A structurally malformed `ROUTE_OPEN` for which the route ID or grant digest
cannot be safely computed receives the existing generic `ERROR` envelope, not
a partial `ROUTE_REJECT`.

## Admission and error rules

The lab's bounded AuditLog retains the Task 6 total of exactly 1024 queued
events and adds a containment partition of exactly 24 queued channel-scoped
events per `channel_id`. The 32-channel lab maximum therefore permits at most
768 channel-scoped records and preserves at least 256 total slots for
session/security lifecycle records whose `channel_id` is absent. The partition
applies uniformly to route admission, binding, stream, UDP, quota, channel
lifecycle, and channel-scoped resume audit reservations. Reaching channel A's
24-event cap rejects A's next audited mutation before channel or global audit
state changes; it does not consume channel B's budget or the session reserve.
Popping an event releases its exact channel slot. The global 1024-event limit
continues to fail closed before mutation.

Source and destination admission are independent. A valid Source Edge
decision never compels Destination Edge acceptance. Destination admission
occurs in this order:

1. validate bounded control framing and the closed numeric body;
2. verify session ID, request ID, monotonic sequence, time, and nonce replay;
3. parse bounded deterministic COSE without allocating route state;
4. verify RouteGrant signature in caller-supplied authorized issuer trust
   context;
5. verify proof of possession and every grant, certificate, edge, service,
   transport, port, record, policy, expiry, and revocation binding;
6. reserve bounded channel capacity; and
7. emit `ROUTE_ACCEPT`.

The most specific frozen ProtocolError is used:

- malformed or unknown fields use `NBSR_E_PROFILE_UNSUPPORTED`;
- invalid grant structure, signature, issuer, or binding uses
  `NBSR_E_GRANT_INVALID`;
- an expired grant uses `NBSR_E_GRANT_EXPIRED`;
- a bad proof uses `NBSR_E_PROOF_INVALID`;
- reused session ID, request ID, nonce, challenge, grant nonce, or stale
  monotonic sequence uses `NBSR_E_REPLAY`;
- denied policy uses `NBSR_E_ROUTE_DENIED`;
- unavailable authorized destination uses `NBSR_E_EDGE_UNAVAILABLE`; and
- bounded resource exhaustion uses `NBSR_E_OVER_CAPACITY`.

`NBSR_E_INTERNAL` remains only a non-sensitive fallback when no more specific
code applies. Unknown numeric keys, booleans used as integers, duplicates,
indefinite lengths, non-preferred encodings, unsupported tags, floats, or
trailing bytes fail closed.

## Privacy and forwarding boundary

An Origin Endpoint, origin hostname, DNS answer, connector address, health
result, or internal destination selection must not appear in any HELLO or
ROUTE body, client-visible error, or normal client telemetry. Route acceptance
does not expose or confer direct origin reachability.

No Application Stream may be opened or carry bytes before both independent
admissions complete, `ROUTE_ACCEPT` is validated, and the separately approved
`STREAM_OPEN` exchange succeeds. Failure affects only the candidate channel
unless the authenticated Transport Session itself is invalid.

## Replay, lifetime, and storage

- CLIENT and EDGE nonces are single-use within bounded replay state.
- A session ID is accepted once for the authenticated destination and retained
  for at least the maximum session/resumption replay window.
- A RouteGrant `unique_nonce` is single-use according to issuer and federation
  replay policy.
- Channel ID reuse is rejected even with a different grant.
- DNS TTL, OriginSet validity, RouteGrant expiry, Transport Session lifetime,
  Service Channel lifetime, and Application Stream lifetime remain distinct.
- Exact production replay retention and clock-skew values remain resource
  profile decisions; implementations must configure finite bounds and fail
  closed when required replay state is unavailable.
- No HELLO or ROUTE message is permitted in 0-RTT.

## Compatibility classification

| Surface | Classification | Effect |
|---|---|---|
| QUIC v1 and mutual TLS 1.3 | Reuse existing standards | No custom transport or handshake |
| Ed25519 session proof | Profile of RFC 8032 plus deterministic NBSR transcript | New versioned proof bytes |
| Existing RouteGrant and ProtocolError | Reuse frozen D6 objects | No object-schema change |
| Five message-body mappings | New Core v0.2 wire semantic | Human schema approval required |
| Existing HELLO and ROUTE symbolic codes | Versioned reuse candidate | Requires protocol version 2 approval |

The 17 message codes remain unchanged. The 19 error codes remain unchanged.
The six D6 schemas remain unchanged. Frozen state registries and transitions
remain unchanged. This proposal creates no new critical extension and no new
COSE wrapper. The `route_grant` field carries the already-frozen RouteGrant
COSE Sign1 wrapper.

Protocol version 2 is not allocated by this document. Core v0.1
`ControlEnvelope.protocol_version` remains exactly 1, and a Core v0.1 peer
must never interpret these candidate bodies. Negotiation and downgrade
behavior require separate approval.

## Remaining runtime gate

After approval, cross-language deterministic vectors must freeze:

- all five valid bodies and their enclosing envelopes;
- the exact proof transcript and Ed25519 signature;
- RouteGrant digest computation;
- wrong-key, wrong-edge, wrong-service, wrong-port, replay, expiry, and
  malformed rejection cases; and
- interaction with the approved STREAM bodies.

The missing vectors and still-unallocated protocol version 2 each blocks WP3
runtime. No Python model, serializer, QUIC dependency, or transport integration
may be created from this proposal alone.

## Approved ballot

The human protocol owner approved these nine candidate decisions on
2026-07-29:

1. every numeric key, required field, exact type, and bound in all five tables;
2. source-chosen session ID and per-direction control sequencing;
3. raw Ed25519 session public key in CLIENT_HELLO;
4. EDGE_HELLO nonce and session-key-thumbprint confirmation;
5. complete RouteGrant COSE bytes in ROUTE_OPEN;
6. exact deterministic proof transcript and domain-separation label;
7. closed-map and frozen-error behavior;
8. ROUTE acceptance before any STREAM exchange; and
9. preparation of deterministic vectors as the final pre-runtime wire gate.

This approval freezes the candidate mapping. D8 separately approves the
future protocol version value and downgrade behavior. Neither approval
authorizes production code, dependency installation, or runtime integration.
