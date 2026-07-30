# WP3 QUIC Handshake Spike Design

**Status:** approved in principle on 2026-07-30; written specification pending
human review

**Scope:** the smallest Phase E runtime slice: an isolated Rust transport crate
proving an authenticated QUIC v1 / TLS 1.3 handshake between a Source Edge and
a Destination Edge

**Runtime authorization:** none. This design does not authorize implementation.
Implementation remains blocked until a separate TDD plan is reviewed and
approved.

## Objective

Prove that the approved WP3 transport profile can be expressed behind a small
NBSR-owned interface without coupling protocol semantics to a QUIC library.

The spike proves only:

- Source Edge as QUIC client and Destination Edge as QUIC server;
- QUIC v1 with TLS 1.3;
- exact ALPN `nbsr-quic-1`;
- mutual authentication under a private test CA;
- exact configured peer-identity matching;
- disabled application 0-RTT;
- bounded connection setup and close; and
- origin-free, bounded failure reporting.

It does not send Core control messages, create Route Contexts or Service
Channels, open application streams, select an Origin Endpoint, or integrate
with the existing relay.

## Selected approach

Use pinned Quinn and rustls releases behind an NBSR-owned asynchronous
transport adapter.

This replaces the original Python recommendation after dependency review found
that `aioquic 1.3.0` can request a client certificate only through the private
`_request_client_certificate` field, marked by that library as test-only. That
fails this design's public-API and mutual-authentication abort criterion.

Quinn with rustls exposes public client- and server-certificate configuration,
including a mandatory `WebPkiClientVerifier`. It can therefore prove real
mutual TLS without a fork, private-library access, or new NBSR authentication
semantics. The crate remains isolated so this choice neither migrates the
existing Python runtime nor commits the full NBSR implementation to Rust.

The approved direct dependency set is Quinn `0.11.11`, rustls `0.23.43`, and
Tokio `1.53.1`, using rustls's `ring` provider and TLS 1.3 only. `rcgen 0.14.8`
is permitted as a development dependency solely to generate ephemeral test
certificates. `Cargo.lock` freezes the complete resolved dependency graph.

### Alternatives not selected

1. **Use `aioquic 1.3.0`.** Rejected because server-side client-certificate
   requests require a private, explicitly test-only TLS field. One-way TLS
   would not satisfy the approved mutual edge authentication profile.
2. **Integrate QUIC directly into `NameRelay`.** Rejected for the spike because
   it would mix a historical signed-JSON TCP prototype with the future Core
   v0.2 transport boundary and make rollback difficult.
3. **Fork `aioquic` or access private fields.** Rejected because the spike must
   use reviewed public APIs and remain maintainable across dependency updates.
4. **Build a custom QUIC or TLS stack.** Rejected because packet protection,
   loss recovery, congestion control, path validation, and TLS are reused
   standards, not new NBSR semantics.

## Architectural boundary

The spike introduces a transport-neutral boundary under a new module namespace,
expected to be shaped as:

```text
crates/
  nbsr-transport/
    Cargo.toml
    Cargo.lock
    src/
      lib.rs
      config.rs
      error.rs
      quinn_adapter.rs
    tests/
      handshake.rs
      support/
        mod.rs
```

These filenames are planning targets, not frozen public APIs.

`lib.rs` exposes the minimum NBSR-owned connection contract. Protocol, route,
service, origin, and application-stream types are deliberately absent.
`quinn_adapter.rs` is the only module permitted to import Quinn-specific
connection types. Existing Python runtime modules do not import or invoke the
crate.

The initial interface exposes only lifecycle behavior equivalent to:

```text
connect(config: ClientConfig, endpoint: SocketAddr) -> AuthenticatedConnection
accept(config: ServerConfig, bind: SocketAddr) -> (listener, accepted connection)
AuthenticatedConnection.authenticated_peer() -> EdgeIdentity
AuthenticatedConnection.close()
```

The concrete spelling is finalized by the TDD plan. The interface must not
accept a Service Identity, RouteGrant, OriginSet, Origin Endpoint, synthetic
mapping, route ID, Service Channel ID, or application payload.

## Identity and trust profile

The private-lab trust profile contains:

- local certificate and private-key references;
- trust-anchor references;
- the configured local edge identity and role;
- the exact expected peer edge identity and role;
- ALPN `nbsr-quic-1`;
- handshake timeout;
- idle timeout for the bounded test connection; and
- TLS 1.3-only rustls configuration;
- disabled session resumption for the spike;
- a connection API that never invokes Quinn's `into_0rtt`; and
- a bounded close timeout.

The spike uses certificates generated only for tests. Private keys are never
committed, logged, returned in errors, or embedded in fixtures intended for
production use.

Authentication succeeds only when:

1. the certificate chain validates to the configured test trust anchor;
2. the certificate validity interval is current under rustls validation;
3. the peer identity exactly matches the configured certificate SAN;
4. the peer role is allowed by local configuration;
5. ALPN is exactly `nbsr-quic-1`; and
6. the handshake completes within the configured bound.

Certificate subject text or possession of any certificate is insufficient.
The authenticated edge identity does not become Service Identity and grants no
service authorization.

The exact SAN encoding and production federation trust model remain outside
this spike and require separate approval.

## Connection lifecycle

The successful test lifecycle is:

1. create an isolated Destination Edge listener on a loopback address and
   ephemeral UDP port;
2. configure both peers with the private test CA and exact expected peer
   identities;
3. initiate a Source Edge QUIC connection;
4. complete address validation as handled by the QUIC implementation;
5. complete TLS 1.3 mutual authentication and exact ALPN selection;
6. expose the authenticated peer identity through the transport-neutral
   connection object;
7. exchange no NBSR control or application data; and
8. close both sides gracefully within a bounded timeout.

Tests must not require public network access, public DNS, fixed ports, cloud
services, or machine-installed certificates.

The spike does not promise connection migration, NAT rebinding, Retry-token
policy, resumption, multi-edge failover, or production keepalive behavior.
Those capabilities remain profiled architecture and future gated work.

## Failure behavior

All failures are fail-closed and occur before route or service state exists.

The adapter returns typed internal transport failures for:

- untrusted certificate chain;
- expired or not-yet-valid certificate;
- peer SAN mismatch;
- disallowed peer role;
- ALPN mismatch;
- handshake timeout;
- peer close during setup; and
- bounded unexpected transport failure.

The exact internal exception names are implementation details to be fixed in
the TDD plan. They are not Core error-code allocations and must not alter the
frozen 19-code registry.

Failure details may identify the local operation and a bounded symbolic reason.
They must not expose private keys, certificate bytes, Origin Endpoints,
RouteGrants, raw packets, or unbounded third-party exception text.

No fallback to TCP, direct origin, a weaker TLS mode, an unverified
certificate, another ALPN, or 0-RTT is permitted.

## Test design

Implementation follows TDD with the smallest test first.

### Configuration and identity tests

- Source Edge and Destination Edge roles are distinct and closed.
- Missing trust anchors, identities, or certificate references fail before
  socket creation.
- ALPN is fixed to `nbsr-quic-1`.
- Application 0-RTT cannot be enabled by the spike configuration.
- Service, route, origin, and application fields are absent from the adapter
  contract.

### Loopback handshake tests

- valid Source Edge and Destination Edge certificates complete mutual
  authentication;
- each side observes the exact configured peer identity;
- the negotiated ALPN is exactly `nbsr-quic-1`;
- no control or application stream is opened;
- graceful close completes; and
- the test uses loopback plus an ephemeral UDP port.

### Negative handshake tests

- unknown CA;
- wrong Source Edge SAN;
- wrong Destination Edge SAN;
- expired certificate;
- role mismatch;
- ALPN mismatch;
- missing client certificate;
- handshake timeout; and
- peer close during setup.

Every negative case must prove that no route, Service Channel, application
stream, OriginSet selection, origin connection, or existing relay mutation
occurred.

### Isolation and anti-drift tests

- only the concrete adapter exposes Quinn-specific connection handling;
- rustls client-certificate verification is mandatory on the server;
- the client configuration provides its certificate and validates the server;
- TLS 1.2 and session resumption are not enabled;
- no code path invokes Quinn's `into_0rtt`;
- the existing `NameRelay` remains unchanged and does not import the adapter;
- frozen Core v0.1 registry, schemas, states, CBOR, and COSE surfaces remain
  unchanged;
- checked-in Core v0.2 vectors remain byte-identical;
- no new numeric key, message code, error code, state, transition, critical
  extension, or COSE wrapper appears; and
- no client-visible or test output contains an Origin Endpoint.

## Validation strategy

The future implementation must run, in this order:

1. focused configuration and identity tests;
2. the smallest successful loopback-handshake test;
3. focused negative handshake tests;
4. transport isolation and anti-drift tests;
5. existing Core v0.1 and Core v0.2 protocol tests;
6. `cargo test`, `cargo fmt --check`, and `cargo clippy -- -D warnings`;
7. the full Python suite;
8. Ruff check and format check;
9. `pip check`;
10. deterministic Core v0.2 vector regeneration and byte comparison; and
11. `git diff --check`.

The implementation plan must record exact commands. A passing loopback
handshake proves only the prototype adapter boundary, not internet
interoperability, production PKI, production security, or deployment
readiness.

## Explicit exclusions

This spike does not:

- implement HELLO, ROUTE, STREAM, or ERROR messages;
- parse or emit Core v0.2 control frames;
- allocate Route Contexts or Service Channels;
- create Application Streams or proxy TCP;
- evaluate RouteGrant, policy, revocation, replay, quota, or audit state;
- consume or select from OriginSet;
- reveal or connect to an Origin Endpoint;
- integrate with `NameRelay`, the Windows agent, DNS interception, synthetic
  mapping, or cloud infrastructure;
- implement Retry-token policy, migration, resumption, handover, or failover;
- add multi-service session reuse or per-channel cryptographic derivation;
- modify frozen Core v0.1 D1-D6 decisions;
- change Core v0.2 candidate schemas, vectors, or outcomes; or
- make a production-readiness claim.

## Acceptance criteria

The later implementation is acceptable only when:

- Quinn `0.11.11`, rustls `0.23.43`, Tokio `1.53.1`, and rcgen `0.14.8`
  are pinned and resolved in the checked-in `Cargo.lock`;
- all QUIC-specific code is confined to the standalone Rust crate;
- a loopback QUIC v1 / TLS 1.3 handshake mutually authenticates exact Source
  Edge and Destination Edge identities;
- ALPN is exactly `nbsr-quic-1`;
- application 0-RTT is disabled;
- every negative authentication case fails before route or service allocation;
- shutdown and timeouts are bounded and leave no background task or socket;
- the existing relay and protocol runtime remain unchanged;
- frozen registries, schemas, states, and vector bytes remain unchanged; and
- focused and full validation passes.

## Abort criteria

Stop implementation and return for human review if:

- Quinn/rustls cannot enforce mutual client-certificate validation and exact
  peer identity through public APIs;
- the adapter requires a new wire message, numeric key, error code, state,
  transition, critical extension, or COSE wrapper;
- disabling 0-RTT cannot be demonstrated;
- a service or RouteGrant must be attached to the Transport Session to make the
  spike work;
- test certificates cannot remain isolated and reproducible;
- the existing relay or OriginSet runtime must change;
- cleanup leaves live sockets or tasks after a bounded timeout; or
- Core v0.1 or the reviewed Core v0.2 vector package changes.

## Next gate

After human approval of this written specification, prepare a task-by-task TDD
implementation plan. The plan must begin with dependency review and failing
tests, identify exact files and commands, and keep the first successful
handshake independent of route and service behavior.

No code, dependency, certificate fixture, socket, or runtime integration is
authorized until that plan is separately approved.
