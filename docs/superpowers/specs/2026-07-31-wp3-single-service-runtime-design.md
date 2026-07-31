# WP3 single-service runtime design

**Status:** approved design direction on 2026-07-31; implementation requires a
separately reviewed TDD plan.

**Authority:** Vision V3.6, D7, D8, the approved Core v0.2 candidate schemas,
and the completed isolated Quinn/rustls handshake boundary.

## Objective

Build the smallest loopback-only WP3 runtime slice that proves a mutually
authenticated Transport Session can admit exactly one Service Channel and one
TCP Application Stream through the approved Core v0.2 control sequence. It
must prove admission and isolation, not provide an origin relay, a client
agent, multi-service reuse, production deployment, or a new wire protocol.

## Selected approach

Extend the isolated Rust `crates/nbsr-transport` boundary rather than adapting
the historical Python `NameRelay`. Quinn/rustls continues to own QUIC v1 and
TLS 1.3. A new NBSR-owned control layer owns only bounded frame handling,
version-locked dispatch, validation against the reviewed Core v0.2 fixtures,
and single-service admission state.

The initial lab path is:

```text
Source Edge -- QUIC/TLS 1.3 --> Destination Edge
  stream 0: CLIENT_HELLO -> EDGE_HELLO -> ROUTE_OPEN -> ROUTE_ACCEPT
  stream 4: STREAM_OPEN -> STREAM_ACCEPT -> bounded test payload exchange
```

The Destination Edge accepts an internal validated-route target supplied by a
test-only in-memory policy adapter. The target proves that admission has a
separate internal destination-selection boundary; it contains no real origin
address and opens no origin connection. A later approved task may connect that
boundary to the existing Python Derived OriginSet model or a reviewed shared
model.

## Why this boundary

1. Extending the Rust transport crate retains the proven public Quinn/rustls
   mutual-authentication boundary and keeps QUIC-specific types in one place.
2. Adding raw streams without Core v0.2 controls is rejected: it would make a
   Transport Session act as universal service authorization.
3. Integrating the historical TCP relay is rejected: its JSON preface and
   fixed-origin behavior are prototype evidence, not the versioned V3.6
   control plane.

## Runtime components

### Transport adapter

`quinn_adapter.rs` remains the sole owner of Quinn connection and stream
types. It enables one source-initiated bidirectional control stream and a
bounded source-initiated application stream only after TLS 1.3, exact ALPN,
and exact Source/Destination Edge identity checks succeed. It does not expose
raw connection authority to policy code.

### Versioned control framing

The control stream uses the approved shortest-form QUIC variable-length
length prefix followed by one complete deterministic Core v0.2
`ControlEnvelope`. The first accepted frame is `CLIENT_HELLO` with version 2.
The session remains version-locked; unknown, mixed, malformed, oversized, or
trailing data fails closed. A failed v0.2 attempt never retries as v0.1.

The runtime codec and COSE implementation must be selected only after a
dependency review proves it against the checked-in deterministic vector
package. No library-specific canonicalization mode, private API, or
best-effort parsing is acceptable.

### Admission state

The Destination Edge keeps bounded, in-memory state keyed by authenticated
Transport Session and exact Core version. It tracks session/request IDs,
monotonic sequences, CLIENT/EDGE nonces, admitted channel ID, RouteGrant
digest, Route ID, service identity, expiry, and replay state. It admits one
service and one channel for this lab slice. A RouteGrant is verified in its
caller-supplied authorized issuer trust context; its proof of possession,
edge, service, transport, port, policy, expiry, and revocation bindings are
all checked before channel allocation.

### Application-stream gate

`STREAM_OPEN` can refer only to a source-initiated bidirectional QUIC stream
with an ID divisible by four and greater than zero. No application byte is
read or written before the matching `STREAM_ACCEPT`. Rejection resets only the
candidate stream and leaves the authenticated Transport Session usable for
safe closure; it does not create another authorization context.

The accepted test stream terminates at an in-memory bounded echo fixture. It
does not select, reveal, or connect to an Origin Endpoint. This proves the
stream gate without falsely claiming final-segment forwarding.

## State and failure rules

- TLS and edge identity failure occur before a control or route state exists.
- Structural framing and schema failures occur before signature verification
  or channel allocation.
- Replay, expired grant, invalid proof, policy denial, destination denial, and
  capacity exhaustion use the most-specific already frozen ProtocolError
  behavior from the approved candidate schemas.
- Malformed bytes that cannot safely correlate a request use generic
  transport close; no partial reject is manufactured.
- The implementation retains no origin endpoint, raw RouteGrant, proof
  signature, private key, or unbounded peer exception in public results or
  normal logs.
- Closing a session drops its bounded lab state. Cross-edge resume, migration,
  handover, HA replication, long-lived tombstones, and production replay
  retention remain later work packages.

## Explicit exclusions

This design does not authorize:

- changes to D1-D6, 17 message codes, 19 error codes, Core v0.1 schemas,
  state registries, deterministic CBOR, or COSE wrappers;
- a Core v0.1-to-v0.2 fallback, new ALPN, new application close code, or
  numeric allocation beyond approved Core v0.2 candidates;
- multi-service Transport Session reuse, per-channel exporter derivation,
  UDP/IP profiles, migration, resumption, handover, HA, or federation;
- a real OriginSet publisher, origin connector, legacy DNS recursion,
  production DNSSEC/Web PKI policy, NameRelay integration, Windows agent work,
  cloud resources, or production claims.

## Test and approval strategy

The future TDD plan must begin with failing tests for each externally visible
gate and must include these groups:

1. deterministic Core v0.2 vector conformance before any socket test;
2. valid and invalid control-frame parsing, version locking, and no-downgrade;
3. independent RouteGrant and proof-of-possession admission tests;
4. replay, expiry, revocation, service/edge/port mismatch, and capacity tests;
5. a loopback QUIC test proving no application byte precedes `STREAM_ACCEPT`;
6. a bounded accepted in-memory application-stream exchange with no origin;
7. isolation tests proving the Python relay and WP2 Name Node are unchanged;
8. frozen Core v0.1/vector anti-drift tests, Rust formatting/Clippy, and the
   full Python suite.

The TDD plan must declare the exact Rust codec/COSE dependencies after its
dependency review. If no public API can satisfy every checked-in vector and
the bounded scanner requirements, implementation stops for human review.

## Next human gate

Review this design, then approve a task-by-task TDD plan limited to the
single-service loopback admission and stream-gate laboratory. That approval
does not authorize production forwarding or any later WP4-WP8 behavior.
