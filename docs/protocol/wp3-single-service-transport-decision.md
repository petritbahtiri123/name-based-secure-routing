# WP3 single-service transport decision proposal

**Status: Approved on 2026-07-29; runtime remains gated**

**Date:** 2026-07-29

**Runtime authorization: None.** This proposal does not authorize WP3
implementation, dependency installation, wire allocation, or integration with
the current relay.

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

### A. `aioquic` behind an NBSR transport adapter — recommended for the Python prototype

`aioquic` is a Python asyncio QUIC/TLS 1.3 implementation designed for
embedding and tested for QUIC interoperability. Its documented API exposes
QUIC configuration, ALPN selection, certificates, streams, connection events,
idle timeout, connection migration, and NAT rebinding.

The recommendation is prototype-only:

- pin an reviewed `aioquic` version after dependency approval;
- wrap it behind an NBSR-owned transport interface;
- do not depend on private `aioquic` attributes;
- disable application 0-RTT;
- verify mutual authentication, Retry, stream limits, migration behavior, and
  origin-free errors in local tests; and
- do not make a production-readiness claim from the Python prototype.

### B. Quinn/rustls service — production candidate, not WP3 default

Quinn is a pure-Rust async QUIC implementation with rustls integration and
public exporter support. It is a stronger candidate for a later hardened edge
data plane, but adopting it now creates a second language/runtime, IPC
boundary, packaging work, and a much larger implementation task.

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

## Core v0.2 stream-binding schema proposal prepared

The separately gated
[Core v0.2 stream-binding schema proposal](core-v0.2-stream-binding-schema-proposal.md)
now assigns explicit candidate body keys for `STREAM_OPEN`, `STREAM_ACCEPT`,
and `STREAM_REJECT`, plus bounded control-stream framing and fail-closed
binding rules. The proposal is not frozen and authorizes no runtime.

Its dependency review also confirms that `CLIENT_HELLO`, `EDGE_HELLO`, and the
three `ROUTE_*` message bodies still need separate numeric schemas before WP3
runtime. Approval of the STREAM tables alone does not fill those gaps.

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
| `aioquic` dependency | Prototype implementation choice | Human approval required |
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
