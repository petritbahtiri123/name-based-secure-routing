# WP3 single-service transport decision proposal

**Status: Approved on 2026-07-29; origin-free lab implementation complete on 2026-07-31**

**Date:** 2026-07-29

**Further runtime authorization: None.** The approved origin-free Rust lab
slice is complete. This record does not authorize OriginSet selection, an
Origin Endpoint connection, relay integration, new wire allocation,
multi-service reuse, or production deployment.

**Verified implementation update (2026-07-31):** the approved Rust-only slice
binds the authenticated Quinn peer through HELLO/ROUTE control sequencing,
decodes RouteOpen, validates the caller-trusted signed RouteGrant and RouteOpen
proof, and admits one service/transport/port-bound logical channel. A matching
ROUTE_ACCEPT is mandatory before that admitted channel creates the StreamGate
for actual Quinn stream ID 4. The real loopback stream has a bounded 4 KiB
in-memory echo and pre-accept reset. It adds no Origin Endpoint connection or
forwarding, OriginSet selection, NameRelay integration, multi-service reuse,
or production claim.

## Purpose

Define the smallest standards-based transport profile that can carry one
independently authorized NBSR service path without designing a custom
transport or silently changing frozen Core v0.1.

The initial vertical slice is:

```text
Source Edge
  -> authenticated QUIC v1 / mutual TLS 1.3 Transport Session
      -> one independently authorized Service Channel / Route Context
          -> one or more reliable QUIC Application Streams
              -> Destination Edge
                  -> validated Derived OriginSet endpoint
```

This is intentionally single-service for WP3, but the Transport Session
interface must not encode a one-service-per-session restriction.

## Repository evidence

- The Python project currently has no QUIC, HTTP/3, MASQUE, CONNECT-UDP, or
  CONNECT-IP dependency.
- The current `NameRelay` is an asyncio TCP relay with a signed JSON
  admission preface. It is historical prototype behavior, not the V3.6 QUIC
  transport.
- Core v0.1 freezes the `ROUTE_*` and `STREAM_*` message codes, but it does not
  freeze their message-body field schemas.
- `RouteGrant`, `RouteIntent`, and `ControlEnvelope` schemas are frozen; none
  contains a QUIC stream ID or Service Channel wire identifier.
- Phase D now supplies a validated internal Derived OriginSet, but it is not a
  wire object.

## Reused standards

WP3 reuses:

- QUIC v1 from [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000);
- TLS 1.3 over QUIC from
  [RFC 9001](https://www.rfc-editor.org/rfc/rfc9001);
- QUIC streams, Connection IDs, flow control, loss recovery, congestion
  control, path validation, Retry, anti-amplification, close, and key update;
  and
- PKIX certificate validation for the prototype private trust domain.

NBSR does not implement a congestion controller, loss-recovery algorithm,
packet protection scheme, custom TLS handshake, or custom QUIC stack.

## Library decision

### A. `aioquic` behind an NBSR transport adapter — superseded spike choice

`aioquic` is a Python asyncio QUIC/TLS 1.3 implementation designed for
embedding and tested for QUIC interoperability. Its documented API exposes
QUIC configuration, ALPN selection, certificates, streams, connection events,
idle timeout, connection migration, and NAT rebinding.

This was the approved prototype recommendation on 2026-07-29. During the
pre-implementation API review on 2026-07-30, `aioquic` 1.3.0 exposed mandatory
client-certificate requests only through the private, test-only
`_request_client_certificate` attribute. That conflicts with the approved
public-API-only boundary. The choice is therefore **superseded for this
handshake spike**, without changing any protocol decision or rejecting
`aioquic` for unrelated future experiments.

No private `aioquic` attribute was used and no Python runtime dependency was
added.

### B. Quinn/rustls isolated handshake crate — approved spike choice

Quinn is a pure-Rust async QUIC implementation with rustls integration and
public mutual-certificate-verifier and authenticated peer-identity APIs. The
2026-07-30 amendment approved Quinn/rustls only for the isolated WP3 handshake
boundary. It does not approve a Rust migration, IPC boundary, packaged edge
service, or production data plane. Quinn/rustls remains a **production
candidate** requiring separate architecture, packaging, operational, and
security review.

The completed WP3 slice's direct-dependency baseline is exactly six packages:
ed25519-dalek 2.2.0, Quinn 0.11.11, rustls 0.23.43, SHA-2 0.11.0, Tokio
1.53.1, and x509-parser 0.18.1. They are exact-pinned and locked under
`crates/nbsr-transport`. WP4's later direct `bytes` addition is not part of
this WP3 baseline and is justified in the WP4 decision record.

### C. Custom QUIC implementation — rejected

A custom QUIC implementation would unnecessarily recreate packet protection,
loss recovery, congestion control, migration, and interoperability behavior.
It is outside NBSR's minimal protocol surface.

## Proposed transport profile

### Connection role

- Source Edge is the QUIC client.
- Destination Edge is the QUIC server.
- QUIC v1 and TLS 1.3 are mandatory.
- The proposed ALPN is exactly `nbsr-quic-1`, matching the already-used route
  profile name. This is a proposed ALPN, not an approved registration or wire
  freeze.
- There is no 0-RTT in the WP3 profile. Route-changing controls are never sent in
  early data.

### Prototype mutual authentication

The Python prototype uses mutual TLS 1.3 under a private lab CA:

- each peer validates the complete certificate chain and validity interval;
- each configured edge identity matches an exact certificate SAN;
- local configuration binds the SAN to the expected Source Edge or
  Destination Edge role;
- hostname/SAN checks are not replaced by certificate possession alone;
- certificate errors fail before route or stream allocation; and
- certificate subject strings do not become Service Identity.

The production federation CA, SAN type, role encoding, revocation mechanism,
and cross-operator trust model remain separate approvals.

### Transport reuse key

The proposed reusable Transport Session key is:

`(source_edge_id, destination_edge_id, trust_profile_id, ALPN, protocol_version)`

Path state and capacity are eligibility checks, not key components. Service
Identity is not part of transport authentication. A RouteGrant is not reusable
transport authority. Every Service Channel must still perform independent
authorization even when this key matches.

WP3 carries only one active service per session while proving the boundary.
WP4 may permit multiple channels only after the channel wire and exporter
gates pass.

## Control and application streams

The proposed native profile reserves the first Source-Edge-initiated
bidirectional QUIC stream as the control stream. Later bidirectional streams
carry proxied TCP Application Streams.

HTTP CONNECT remains a valid optional deployment profile, but it is not the
native WP3 control protocol. Replacing NBSR control with HTTP would not remove
RouteGrant, Service Channel, revocation, or audit semantics.

## Blocking wire gap

The frozen registry contains `STREAM_OPEN`, `STREAM_ACCEPT`, and
`STREAM_REJECT`, but there is no frozen message-body schema that binds:

- QUIC stream ID;
- route ID;
- Service Identity or digest;
- Service Channel identity;
- RouteGrant or authorization digest;
- allowed transport and port;
- policy digest/version; and
- replay/nonce state.

Using the opaque `ControlEnvelope.body` without a reviewed numeric mapping
would invent new numeric body keys silently. A connection-bound single-service
shortcut would avoid a preface only by attaching service authorization to the
entire Transport Session, which conflicts with session reuse and service
isolation.

The recommended resolution is a separately reviewed Core v0.2 stream-binding
body schema that reuses the existing `STREAM_OPEN`, `STREAM_ACCEPT`, and
`STREAM_REJECT` symbolic semantics where compatible. The review must assign
every numeric key individually, define exact types/bounds, bind the QUIC
stream ID and authorized service context, and add cross-language deterministic
CBOR vectors. It may determine that versioned message codes are safer.

This proposal allocates no new numeric body keys, message code, state, or
transition.

## Observed isolated handshake evidence

The approved TDD spike completed on 2026-07-30 as a standalone Rust crate:

- 8 configuration tests and 11 handshake tests pass on loopback;
- the positive test mutually authenticates exact
  `source-edge.test`/`destination-edge.test` DNS SAN identities and exact ALPN
  `nbsr-quic-1`;
- negative tests reject unknown client/server CAs, missing or expired
  certificates, Source/Destination SAN mismatch, ALPN mismatch, timeout, and
  peer refusal during setup;
- TLS 1.3 is the only enabled TLS version; resumption and early data are
  disabled;
- the authenticated connection exposes no stream API and exchanges no NBSR
  control or application data; and
- Quinn endpoint and connection operations remain confined to the adapter.

This is a **handshake boundary**, not a completed Transport Session, Service
Channel, route, final-origin segment, runtime integration, interoperability,
or production-readiness result. WP3 runtime remains separately gated.

## Core v0.2 stream-binding schema proposal prepared

The separately gated
[Core v0.2 stream-binding schema proposal](core-v0.2-stream-binding-schema-proposal.md)
now assigns explicit candidate body keys for `STREAM_OPEN`, `STREAM_ACCEPT`,
and `STREAM_REJECT`, plus bounded control-stream framing and fail-closed
binding rules. The candidate was approved on 2026-07-29 but does not allocate
protocol version 2 or authorize runtime.

The dependency is now covered by the separately gated
[Core v0.2 session and route schema proposal](core-v0.2-session-route-schema-proposal.md).
That proposal and cross-language deterministic vectors still require separate
approval before WP3 runtime.

## Origin and application boundary

The Destination Edge selects a final endpoint only from the accepted internal
Derived OriginSet. QUIC peers and client-visible errors never receive the
Origin Endpoint unless the Destination Edge is the authorized internal
consumer.

The Application Stream is an ordered byte stream. HTTP, TLS at the application
endpoint, OAuth, cookies, user login, and transaction semantics remain owned
by the application.

## Admission order

1. Perform QUIC address validation and preserve anti-amplification.
2. Complete TLS 1.3 and mutual edge authentication.
3. Validate bounded deterministic control framing.
4. Validate replay/sequence state and RouteGrant.
5. Evaluate service, route, edge, port, expiry, revocation, and policy
   bindings.
6. Reserve bounded Service Channel capacity.
7. Accept the Application Stream.

No origin connection or expensive route state is allocated before admission
succeeds.

## Compatibility impact

| Surface | Classification | Result |
|---|---|---|
| QUIC/TLS transport | Reuse existing standard | No custom transport |
| `aioquic` dependency | Superseded spike implementation choice | No dependency added |
| Quinn/rustls crate | Isolated implementation evidence | Approved for handshake spike only |
| ALPN `nbsr-quic-1` | NBSR profile/wire behavior | Human approval required |
| Lab mTLS profile | NBSR constraint | Human approval required |
| Transport reuse key | New internal NBSR semantic | Human approval required |
| Service Channel internal model | New internal NBSR semantic | Separate Phase E model approval |
| Application-stream binding | New NBSR wire semantic | Core v0.2 schema approval required |
| Existing Core registries | Frozen | Unchanged |

The 17 message codes remain unchanged. The 19 error codes remain unchanged.
The six D6 schemas remain unchanged. Frozen state transitions remain
unchanged. There is no new critical extension and no new COSE wrapper.

## Approved ballot

The human protocol owner approved these nine decisions on 2026-07-29:

1. `aioquic` as the Python prototype dependency only;
2. Source Edge client and Destination Edge server roles;
3. exact proposed ALPN `nbsr-quic-1`;
4. the private-lab-CA mutual TLS 1.3 profile;
5. the Transport Session reuse key;
6. first bidirectional stream as the control stream;
7. native QUIC streams rather than HTTP CONNECT for the initial TCP profile;
8. Core v0.2 stream-binding schema work before WP3 runtime; and
9. continued prohibition of 0-RTT for all route-changing controls.

Approval of items 1 through 7 permits dependency pinning and a transport
handshake spike only after a written TDD plan. Item 8 authorized preparation
of the distinct wire schema proposal, not its freeze. No Phase E runtime
implementation begins from this approval alone.

On 2026-07-30, the protocol owner approved the public-API review result and
the minimal switch from ballot item 1 to the isolated Quinn/rustls handshake
crate. The remaining ballot decisions and all runtime gates are unchanged.
