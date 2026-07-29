# Core v0.2 version selection and downgrade decision

**Status:** approved on 2026-07-29

**Decision:** D8

**Scope:** documentation and future wire allocation only

**Runtime authorization:** none. This decision does not modify the current
`ProtocolVersion` enum, install a QUIC dependency, create serializers, or
authorize WP3 runtime implementation.

## Problem

Core v0.1 freezes `ControlEnvelope.protocol_version` to unsigned integer 1.
The approved Core v0.2 HELLO, ROUTE, and STREAM candidate bodies require an
unambiguous version boundary without changing how a v0.1 peer interprets its
existing envelope or allowing a failed v0.2 connection to fall back silently.

The transport profile already freezes `nbsr-quic-1` as the proposed ALPN and
ServiceRecord route-profile value. The `1` in that token identifies the
transport profile, not the Core object version. Creating another ALPN merely
to select Core v0.2 would add a second discovery and certificate-policy
surface without removing the envelope version field.

## D8 decision

### D8-1 — one transport ALPN

Core v0.1 and Core v0.2 use the exact ALPN `nbsr-quic-1`. No
`nbsr-quic-2` token is created by D8.

ALPN authenticates and selects the NBSR QUIC transport family. It does not
negotiate RouteGrant authority, Service Identity, publication mode, or
application protocol.

### D8-2 — exact Core version value

The future Core v0.2 registry value is:

| Symbolic name | Integer | Meaning |
|---|---:|---|
| `CORE_0_2` | 2 | Core v0.2 envelopes and approved v0.2 message-body schemas |

This is a new versioned value, not a modification or alias of `CORE_0_1 = 1`.
The current production registry continues to contain only `CORE_0_1` until a
separately approved implementation task adds v0.2 support.

The Core v0.2 `ControlEnvelope` retains numeric keys 0 through 6 from D6, but
key 0 is exactly unsigned integer 2. This is a new v0.2 envelope schema. It
does not widen the accepted value of the frozen Core v0.1 schema.

### D8-3 — version selection, not in-band negotiation

Before opening a Transport Session, the Source Edge selects one exact Core
version from authenticated local/operator policy or signed NBSR metadata in
the caller-supplied trust context. Legacy DNS, an Origin Endpoint, an
unauthenticated peer hint, or a previous connection failure cannot lower that
selection.

There is no version-list field, highest-common-version exchange, or new
negotiation message. The first NBSR control frame is the selected version's
`CLIENT_HELLO` envelope. For Core v0.2 its `protocol_version` is 2.

### D8-4 — session version lock

The Destination Edge performs bounded deterministic CBOR structural
validation and reads key 0 before dispatching to the exact version-specific
envelope and body decoder. Once the first `CLIENT_HELLO` is accepted:

- every envelope on that QUIC Transport Session uses the same Core version;
- `EDGE_HELLO` uses and confirms that same version;
- the Transport Session reuse key includes `protocol_version`;
- Core v0.1 and Core v0.2 Service Channels never share one Transport Session;
- QUIC path migration does not change the version; and
- resumption may reuse state only when the authenticated version is identical.

A version change requires a new Transport Session and a fresh authorization
flow.

### D8-5 — no automatic fallback

An attempted Core v0.2 session never retries as Core v0.1 merely because:

- the peer rejects or closes the connection;
- a timeout occurs;
- the v0.2 decoder rejects a body;
- a v0.2 feature is unsupported;
- an intermediary interferes with the connection; or
- legacy discovery data advertises only older behavior.

Core v0.1 may be used only when authenticated policy explicitly selected
Core v0.1 before the connection attempt and the service's minimum-version
policy permits it. A user or operator may initiate a separately authorized
v0.1 attempt; the protocol does not perform that downgrade automatically.

### D8-6 — mismatch and unsupported-version failure

If both peers understand the selected Core version and a response carries a
different version, the receiver sends the existing `ERROR` message with
`NBSR_E_DOWNGRADE` when it can do so safely, then closes the Transport
Session.

If the received version is unknown and no safe version-specific envelope can
be encoded, the peer closes the QUIC connection with non-sensitive generic
application failure. D8 does not allocate a QUIC application error code.
Client-visible text must not expose supported-version inventory, trust
internals, Origin Endpoints, or policy details.

The same generic-close rule applies when structural parsing cannot safely
recover and authenticate the Core version, session ID, and request ID. No
version-specific `ERROR` envelope is synthesized from partial or
unauthenticated bytes. A future Core v0.2 `ERROR` body schema requires its own
explicit review; D8 does not create one.

An unknown version is never interpreted as the nearest known version. A Core
v0.1 decoder never accepts a version-2 envelope, and a Core v0.2 decoder never
accepts a version-1 envelope on a session selected as v0.2.

## Message and schema dispatch

Under Core v0.2:

- codes 1 through 5 use the approved candidate HELLO and ROUTE body mappings;
- codes 6 through 8 use the approved candidate STREAM body mappings;
- codes 9 through 17 retain their frozen symbolic meanings but do not gain
  v0.2 body schemas until separately reviewed; and
- the complete 17-message and 19-error numeric mappings remain unchanged.

A message code existing in both versions does not imply that its body bytes
are interchangeable. Dispatch is the ordered pair
`(protocol_version, message_type)`.

Unknown numeric body keys remain fail-closed. Core v0.2 does not inherit an
extension, COSE wrapper, state, transition, or message-body schema merely
because Core v0.1 permits the surrounding symbolic code.

## Replay, cache, and audit partitioning

Replay keys, request IDs, session IDs, cached accept/reject results, and
resumption state are partitioned by exact Core version in addition to their
existing issuer, peer, session, and service bindings. A cached v0.1 result
cannot satisfy a v0.2 request or vice versa.

Privacy-safe security audit records include the exact Core version and ALPN.
They do not include origin addresses, raw RouteGrants, proof signatures,
session keys, or unauthorised service names.

## Compatibility impact

| Surface | Classification | Result |
|---|---|---|
| ALPN `nbsr-quic-1` | Existing approved transport profile | Unchanged |
| `CORE_0_1 = 1` | Frozen Core v0.1 registry | Unchanged |
| `CORE_0_2 = 2` | New Core v0.2 version value | Approved future allocation; runtime registry remains unchanged |
| Envelope keys 0 through 6 | Reused numeric layout in a new versioned schema | Core v0.1 acceptance rules remain unchanged |
| Automatic version fallback | Prohibited NBSR behavior | Downgrade attempts fail closed |
| Version-list negotiation message | Not created | No new message code |
| QUIC application close code | Still unresolved | No allocation in D8 |

D8 changes no Core v0.1 numeric key, message code, error code, state, state
transition, critical extension, or COSE wrapper. The six D6 object schemas
remain byte-for-byte unchanged.

## Rejected alternatives

### A new ALPN for every Core version

Rejected for Core v0.2. It would couple the transport-profile token to object
schema evolution, require new route-profile discovery values, and duplicate
the existing envelope version discriminator.

### In-band supported-version lists

Rejected for Core v0.2. A list and selection response would require new body
keys or messages, downgrade-proof transcript binding, preference rules, and
additional state before the first version-specific envelope can be trusted.

### Try newest, then reconnect with an older version

Rejected. Connection failure is attacker-influenceable and cannot authorize a
weaker protocol.

## Required conformance plan

Future deterministic tests must prove:

1. Core v0.1 accepts only version 1 and its frozen schema.
2. Core v0.2 accepts only version 2 and the selected v0.2 body mapping.
3. The first accepted message is version-matching `CLIENT_HELLO`.
4. A mixed-version envelope on one session fails with downgrade handling.
5. Failure of a v0.2 attempt never starts an automatic v0.1 attempt.
6. A v0.1 cached result, replay entry, or resume state cannot authorize v0.2.
7. QUIC migration and same-edge resumption preserve the exact version.
8. Unknown versions fail closed without revealing supported versions or
   Origin Endpoints.
9. Versions 1 and 2 use the same exact ALPN `nbsr-quic-1`.
10. No frozen Core v0.1 registry or schema bytes change.

These tests belong to the cross-language deterministic-vector gate. D8 does
not authorize their runtime implementation today.

## Remaining gates

Before WP3 runtime:

1. produce and independently verify deterministic envelope, HELLO, ROUTE,
   STREAM, proof, mismatch, and downgrade vectors;
2. write a TDD implementation plan for a version-dispatch boundary that keeps
   the Core v0.1 decoder unchanged; and
3. separately approve any QUIC application close code if interoperability
   requires one.

No runtime implementation begins from D8 alone.
