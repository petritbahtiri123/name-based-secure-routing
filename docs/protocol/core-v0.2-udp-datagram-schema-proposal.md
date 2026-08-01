# Core v0.2 UDP DATAGRAM profile proposal

## Status and scope

This document proposes the bounded UDP profile for an already authenticated
NBSR Core v0.2 Transport Session. It carries one complete application datagram
in one RFC 9221 QUIC DATAGRAM. It does not allocate a message code or change a
frozen Core v0.1 registry.

The profile does not define HTTP/3, MASQUE, CONNECT-UDP, Capsules,
fragmentation, reassembly, retransmission, ordering, reliable delivery, origin
forwarding, or cross-edge state. QUIC DATAGRAM loss and reordering remain
possible and must not be described as reliable delivery.

## Admission

A UDP Service Channel uses the existing Core v0.2 candidate `ROUTE_OPEN` and
correlated `ROUTE_ACCEPT` flow. `ROUTE_OPEN.body[4]` is the three-octet ASCII
text string `udp`. The complete signed RouteGrant must list `udp` in
`allowed_transports`; service, destination, port, record sequence, policy,
validity, nonce, proof-of-possession, and exporter binding checks remain
independent. A grant that permits only `tcp` cannot authorize UDP.

No DATAGRAM operation is admitted for a candidate, unbound, TCP, draining,
revoked, or closed channel. A live exporter binding is specific to the exact
authenticated Quinn connection and exact `channel_id`.

## Exact DATAGRAM payload

The QUIC DATAGRAM payload is the preferred deterministic CBOR encoding of this
closed numeric-key map:

| Key | Field | Exact type and bound |
|---:|---|---|
| 0 | `body_version` | unsigned integer exactly 1 |
| 1 | `channel_id` | byte string exactly 16 bytes and not all zero |
| 2 | `sequence` | unsigned integer 1..18446744073709551615 |
| 3 | `payload` | byte string 0..1200 bytes, also bounded by the negotiated peer maximum |

For `channel_id = h'11111111111111111111111111111111'`, sequence 1, and an
empty payload, the exact 25 bytes are:

```text
a4 00 01 01 50 11111111111111111111111111111111 02 01 03 40
```

The map header is `a4`; keys are encoded in numeric order. Unknown, missing, or
duplicate keys; non-unsigned integers; bool-as-int; tags; floats; indefinite
items; non-preferred integer or length encodings; wrong lengths or types; zero
channel or sequence; trailing bytes; and payloads over 1200 bytes are rejected.

The effective payload cap is computed from the exact next-sequence encoding:

```text
min(1200, greatest payload length whose complete encoded frame <= peer maximum)
```

The CBOR byte-string header and sequence width are therefore part of the
calculation; there is no fixed framing-overhead assumption. A 1200-byte payload
at sequence 1 encodes to 1227 bytes. If even the 25-byte empty-payload frame
does not fit, no application datagram is allowed.

## Per-channel gate

Each live exporter-bound UDP channel has independent inbound and outbound
state:

- outbound sequences start at 1, increase strictly, are reserved only after
  validation and mandatory audit reservation, and never wrap;
- inbound sequences must be greater than the retained high-water mark;
- the receive queue contains at most 64 complete payloads; the 65th is dropped
  with a typed quota audit and cannot be replayed into the queue;
- each direction has an independent token bucket of 100 datagrams per second
  and burst 200, starts with 200 tokens, retains fractional refill in integer
  sub-token units, and rejects backwards monotonic milliseconds without state
  mutation; and
- an audit reservation failure fails closed before sequence, token, or queue
  mutation.

Popping or lifecycle-clearing a payload does not lower the inbound replay
high-water mark. Drain stops new DATAGRAM operations immediately. Deadline,
revoke, close, and session drain clear only the affected queued payload and
gate state while retaining the replay tombstone. Malformed, oversize, replay,
quota, audit, and non-connection transport failures do not mutate sibling
channels. Only a Quinn connection-level error is session-wide.

## Quinn adapter boundary

Quinn DATAGRAM buffer configuration, negotiated maximum queries, native send,
and native receive remain in the transport adapter. Framing, sequencing,
quotas, and queues remain Quinn-free. One native send receives one complete
encoded frame; there is no fragmentation or retry layer.

The implementation uses bounded 262144-byte Quinn send and receive DATAGRAM
buffers. Application queues remain separately bounded to 64 payloads per UDP
channel.

## Validation requirements

Deterministic tests freeze the 25-byte empty fixture, the 1227-byte
sequence-1/1200-byte fixture, canonical rejection matrix, exact negotiated cap,
sequence exhaustion, 64/65 queue behavior, 200/201 burst, 10-millisecond refill
after exhaustion, backwards time, audit exhaustion, lifecycle denial, and
sibling isolation. A bounded real loopback uses two separately signed and
exporter-bound UDP services plus an authorized TCP sibling on one Transport
Session. Receive waits are bounded and are evidence of loopback behavior only,
not a reliability claim.
