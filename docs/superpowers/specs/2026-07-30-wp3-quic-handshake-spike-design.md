# WP3 QUIC Handshake Spike Design

**Status:** approved in principle on 2026-07-30; written specification pending
human review

**Scope:** the smallest Phase E runtime slice: an isolated Python transport
adapter proving an authenticated QUIC v1 / TLS 1.3 handshake between a Source
Edge and a Destination Edge

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

Use a reviewed, pinned `aioquic` release behind an NBSR-owned asynchronous
transport adapter.

This is the smallest approved path because the current prototype is Python and
asyncio-based, `aioquic` reuses QUIC v1 and TLS 1.3 rather than recreating
transport or cryptography, and the adapter preserves the option to replace the
prototype data plane later.

The dependency is not added by this design commit. The implementation plan must
identify the exact reviewed version and record the dependency validation before
any package file changes.

### Alternatives not selected

1. **Integrate QUIC directly into `NameRelay`.** Rejected for the spike because
   it would mix a historical signed-JSON TCP prototype with the future Core
   v0.2 transport boundary and make rollback difficult.
2. **Implement the first spike in Rust with Quinn/rustls.** Deferred because it
   adds a second runtime, IPC, packaging, and deployment boundary before the
   protocol-facing adapter has been proven.
3. **Build a custom QUIC or TLS stack.** Rejected because packet protection,
   loss recovery, congestion control, path validation, and TLS are reused
   standards, not new NBSR semantics.

## Architectural boundary

The spike introduces a transport-neutral boundary under a new module namespace,
expected to be shaped as:

```text
nbsr/
  transport/
    __init__.py
    interface.py
    identity.py
    aioquic_adapter.py

tests/
  transport/
    test_identity.py
    test_aioquic_handshake.py
    test_aioquic_failures.py
```

These filenames are planning targets, not frozen public APIs.

`interface.py` defines the minimum NBSR-owned connection contract. Protocol,
route, service, origin, and application-stream types are deliberately absent.
`aioquic_adapter.py` is the only module permitted to import `aioquic`.
Existing runtime modules must not import `aioquic` directly.

The initial interface exposes only lifecycle behavior equivalent to:

```text
connect(local_edge, expected_peer, endpoint, trust_profile) -> connection
accept(local_edge, expected_peer_policy, trust_profile) -> connection
connection.authenticated_peer
connection.close()
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
- a flag that keeps application 0-RTT disabled.

The spike uses certificates generated only for tests. Private keys are never
committed, logged, returned in errors, or embedded in fixtures intended for
production use.

Authentication succeeds only when:

1. the certificate chain validates to the configured test trust anchor;
2. the certificate validity interval is current under the injected test clock
   or the library's validated clock boundary;
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

- only the concrete adapter imports `aioquic`;
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
6. the full Python suite;
7. Ruff check and format check;
8. `pip check`;
9. deterministic Core v0.2 vector regeneration and byte comparison; and
10. `git diff --check`.

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

- `aioquic` is pinned to a separately reviewed version;
- all QUIC-specific code is confined behind the NBSR adapter;
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

- the selected `aioquic` public API cannot enforce mutual client certificate
  validation and exact peer identity without private-library access;
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
