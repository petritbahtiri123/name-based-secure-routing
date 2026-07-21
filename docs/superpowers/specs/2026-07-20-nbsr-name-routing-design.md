# NBSR Name-Routing Design

## Status and scope

This specification defines the first working vertical slice of NBSR as a
name-based replacement for the client-visible DNS routing model. NBSR accepts a
service name, resolves the destination privately at an NBSR gateway, creates a
short-lived route binding, and relays the connection without returning the real
destination address to the client.

The target architecture covers all Internet traffic. The first release supports
HTTP and HTTPS over TCP on a Windows client, with a Linux/Kubernetes-capable
gateway. HTTP/3, arbitrary UDP, raw IP tunneling, and native clients for other
operating systems are later transport adapters over the same core interfaces.

## Product contract

Conventional DNS answers a name query with a destination address. NBSR instead
answers a name-route request with an NBSR-local synthetic address and a signed
route binding. When an application connects to the synthetic address, the NBSR
client sends the connection to the assigned gateway. The gateway resolves the
real destination and relays traffic. The destination address never enters the
application, Windows DNS cache, or client routing table.

For the ISP profile, NBSR is a secure routing primitive rather than an identity,
billing, or content-inspection product. Client identity, JWT authentication,
client mTLS, OPA access rules, and inspection remain optional enterprise/cloud
modules. The ISP profile prohibits TLS interception and application-content
inspection.

## Architecture

The Windows NBSR application contains a shared protocol core and a Windows
adapter. The shared core manages gateway sessions, name-route requests,
synthetic mappings, Ed25519 proof-of-possession, route bindings, connection
relay, recovery, and diagnostics. The Windows adapter integrates name response
and traffic interception with Windows. Later clients reuse the core behind
Linux TUN/resolver, Apple Network Extension, Android VpnService, and router
adapters.

The NBSR edge contains four bounded units:

1. The name-route API validates names and client session keys, creates private
   resolution state, and returns synthetic addresses plus signed bindings.
2. The private resolver resolves names only at the gateway and never serializes
   real addresses into a client response.
3. The relay verifies route binding, port, expiry, and client
   proof-of-possession before resolving and opening the upstream connection.
4. The signing boundary owns the Ed25519 route private key. Relay processes use
   only the public verification key when deployed separately.

Kubernetes runs and scales these units but is not part of the public NBSR wire
protocol. Docker Compose remains the deterministic first integration path.

## Protocol and route flow

The initial name-route request contains:

- protocol version;
- unique request identifier;
- normalized hostname;
- requested transport capability;
- client-session Ed25519 public key;
- client nonce and capability list.

The response contains:

- the matching request identifier;
- synthetic IPv4 and IPv6 addresses;
- assigned gateway identifier;
- signed route binding;
- admission lifetime.

The route binding is an EdDSA JWT with issuer and audience restrictions. It is
bound to the hostname, synthetic addresses, gateway, allowed ports, client
session public-key thumbprint, issue/not-before/expiry times, and unique route
identifier. The initial release allows TCP ports 80 and 443 only.

Before relay admission, the client signs a fresh relay nonce plus the route ID
and requested port with its session private key. The gateway verifies that proof
against the public-key thumbprint in the route binding. This provides anonymous
client-channel binding without requiring an ISP identity system.

The relay bounds the time allowed to receive the complete length-prefixed
handshake. After verification and a successful origin connection it returns a
one-byte accepted result before any application bytes are forwarded; rejection
returns a one-byte denied result and closes. The client tries configured,
server-authenticated gateway endpoints in order until one accepts admission.

The binding has a 60-second admission lifetime. It authorizes starting a new
connection, not the duration of an accepted connection. An established relay
may continue until either endpoint closes it or a separately configured
connection-duration limit is reached. A new connection after admission expiry
requires a new route binding.

## Synthetic addressing

Synthetic addresses are client-local compatibility handles, not destination
addresses. The allocator accepts configurable IPv4 and IPv6 pools, excludes
addresses already in use, keeps forward and reverse mappings, and serializes
allocation, expiry, renewal, and lookup. Reusing a hostname atomically renews
its mapping through the lifetime of the newly issued binding so an address
cannot be reassigned while that binding remains admissible. Exhaustion fails
without falling back to a real address.

The Windows prototype uses loopback-only synthetic addresses so the integration
can run without installing an unsigned kernel driver. The production Windows
adapter will select configurable virtual ranges after checking physical routes,
VPNs, Hyper-V, WSL, and container networks, then use Windows Filtering Platform
for interception. The protocol and mapping interfaces do not depend on the
prototype loopback range.

## HTTP and HTTPS behavior

The Windows stub becomes the name responder for configured traffic and returns
only synthetic addresses. By default the prototype manages both TCP listeners,
HTTP 80 and HTTPS 443, for every registered route. Connections to those
addresses are associated with refreshable hostname state; the client obtains a
fresh route binding before admission and can fail over through its ordered
gateway list.

For HTTPS, the client application retains the original hostname for SNI and
certificate verification. The NBSR client and gateway forward opaque TLS bytes;
they do not substitute certificates or decrypt content. For HTTP, NBSR also
relays bytes without modifying application content. The gateway may use only
the already-authorized route name and port to select the upstream.

HTTP/3 and QUIC are not supported by the first release. Enforced mode denies the
unsupported direct UDP path so conforming clients fall back to HTTPS over TCP.

## Profiles and cryptographic separation

The `isp` profile has no mandatory JWT, client certificate, billing integration,
or user identity. It requires server-authenticated encryption in deployment,
Ed25519-signed route bindings, ephemeral client proof-of-possession, private
gateway resolution, and opaque relay. Enterprise inspection modules cannot be
loaded in this profile.

The existing enterprise demonstration remains intact. It continues to use a
signed workload identity JWT, OPA authorization, and method/path-scoped routing
tickets for `payments.internal`. Identity keys, Internet name-route binding
keys, enterprise route-ticket keys, and TLS certificate keys are separate trust
domains even if local bootstrap tooling creates them together for a demo.

## Failure and recovery

NBSR fails closed for configured name traffic:

- invalid, expired, wrong-host, wrong-port, wrong-gateway, or replayed bindings
  are rejected;
- a missing name returns an NBSR name-resolution error;
- an unavailable upstream returns a gateway connection error;
- an expired mapping is refreshed before a new connection;
- gateway failure triggers another configured NBSR gateway;
- exhaustion or address collision returns an explicit local error;
- public DNS fallback is disabled unless an administrator explicitly enables
  diagnostic bypass.

The Windows adapter records only the settings it owns. Its opt-in IPv6 adapter
persists successfully added addresses in an ownership journal before relying
on them. Mutation is refused without a configured journal; if persistence
fails after an address is added, the adapter immediately removes that address
and surfaces the failure. Shutdown and uninstall surface failed deletions,
while startup retries journaled cleanup after a crash. It never journals or
removes an address that was already present, so recovery does not overwrite
unrelated VPN, DNS, firewall, Hyper-V, WSL, container, or administrator
configuration.

## Privacy and logging

The ISP profile guarantees no TLS interception, no content inspection, no real
destination address returned to clients, encrypted name requests in deployment,
short-lived non-reusable bindings, and minimal operational logs. Secrets,
tokens, proofs, page content, and unnecessary destination history are never
logged.

The gateway necessarily sees requested names and destination addresses because
it resolves and routes them. NBSR documentation must state this limitation and
must not claim anonymity from the gateway operator.

## Verification

Unit tests cover hostname normalization, synthetic allocation/reuse/exhaustion,
route-binding claims, Ed25519 proof-of-possession, expiry, wrong-port,
wrong-host, wrong-gateway, and tampering.

API tests prove that name-route responses contain synthetic addresses and never
contain resolved destination addresses. Resolver tests use deterministic
in-memory mappings rather than public DNS. Relay integration tests use real
local HTTP and TLS origins and prove opaque byte relay, original-hostname SNI
and certificate validation, server-side-only resolution, explicit admission
results, handshake deadlines, admission expiry semantics, active-connection
continuity, and gateway failover.

Windows-focused integration tests prove that a local name lookup returns a
loopback synthetic address, a connection through that address reaches the
hidden deterministic origin, and stopping the agent removes its owned state.
Compose tests prove that the origin is not published to the host and observes
only the relay-side connection. Kubernetes manifests receive static validation
after the focused and Compose paths pass.

## First-release exclusions

The first release does not claim production readiness or implement a signed WFP
kernel driver, arbitrary TCP/UDP/IP tunneling, HTTP/3, mobile or Apple clients,
multi-region anycast, durable distributed mapping or replay-cache state, billing, subscriber
identity, ISP settlement, content inspection, or a production CA/rotation
system. Its purpose is to prove the NBSR protocol and privacy boundary end to
end for HTTP and HTTPS while preserving interfaces required by the full-tunnel
destination architecture.
