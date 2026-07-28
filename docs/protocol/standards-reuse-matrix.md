# NBSR standards reuse matrix

**Status:** Architecture decision preparation; no runtime authorization

**Date:** 2026-07-28

**Authority:** NBSR Protocol Vision V3.6 and frozen Core v0.1 D1-D6

## Classification rule

- **REUSE EXISTING STANDARD:** use the standard's protocol, state, security,
  or operational mechanism without defining an NBSR substitute.
- **NBSR PROFILE OR CONSTRAINT:** select, bind, limit, or forbid behavior while
  retaining the standard mechanism.
- **NEW NBSR PROTOCOL SEMANTIC:** behavior that the reused standards do not
  express, and that is necessary for name-based secure routing.

One row can contain all three layers. A blank "New NBSR semantic" cell means
NBSR does not need a new semantic for that problem.

## Repository evidence

The current implementation has `cbor2`, `cryptography`, `dnslib`, Python
`ssl`, and `httpx`. It has no QUIC, HTTP/3, MASQUE, CONNECT-UDP, CONNECT-IP,
or broad COSE dependency. Therefore references to those standards below are
architecture choices and dependency-selection inputs, not implementation
claims. Existing Core v0.1 code and tests retain exactly 17 message codes, 19
error codes, the frozen state machines, and the six frozen Core v0.1 wire
schemas. No frozen registry or schema change is made by this package.

## Matrix

| Problem area | Existing standard/mechanism | What is reused | NBSR profile/constraint | New NBSR semantic | Wire impact | Human approval required | Planned work package |
|---|---|---|---|---|---|---|---|
| Secure edge transport | QUIC v1, RFC 9000 | Connection IDs, authenticated packets, multiplexed reliable streams, stream and connection flow control | `nbsr-quic-1`; authenticated Source Edge to Destination Edge scope; bounded stream limits | Transport Session identity and allowed reuse scope | Profile only until an NBSR binding is encoded | Yes: transport scope and reuse key | WP3, WP4 |
| Loss and congestion | QUIC loss recovery and congestion control, RFC 9002 | RTT estimation, loss detection, recovery, congestion control, pacing guidance | Library implementation must be standards-conformant; NBSR does not replace the controller | None | None | No for WP3 library reuse | WP3 |
| Path continuity | QUIC v1 path validation and connection migration | PATH_CHALLENGE/RESPONSE, NAT rebinding, client migration, Connection IDs | Same authenticated edge pair only by default; recheck all NBSR bindings | Authorization continuity across a validated path change | No Core v0.1 change; future continuity profile | Yes: cross-edge resume | WP4, WP6 |
| Connection lifecycle | QUIC v1 idle timeout, graceful application close, CONNECTION_CLOSE, draining, stateless reset | Transport liveness and termination machinery | NBSR maximum age, reauthentication, channel drain, and failure-containment policy remain separate | Per-Service-Channel revoke and drain behavior | No Core v0.1 change | Yes: timeout values and channel lifecycle | WP3, WP4 |
| Address validation | QUIC v1 Retry, validation tokens, anti-amplification | Source-address validation and the three-times anti-amplification limit | Deploy Retry under load or policy; tokens are scoped, integrity-protected, short-lived, and not authorization | Admission ordering before route/channel allocation | None unless an NBSR token is later defined | No for using QUIC Retry; yes for any NBSR token | WP3, WP5 |
| Transport encryption | TLS 1.3 over QUIC, RFC 8446 and RFC 9001 | Confidentiality, integrity, forward secrecy, transcript binding, traffic-key update | TLS 1.3 only; mutual edge authentication; validated trust anchors and peer role | Binding an authenticated edge transport to NBSR session policy | Profile only | Yes: trust and certificate profile | WP3 |
| Service-channel context | TLS exporters, RFC 8446 section 7.5; TLS 1.3 channel binding, RFC 9266 | Exporter primitive and transcript-bound keying material | Dedicated label and canonical service/channel context inputs; domain separation; no secret reuse | Independent cryptographic or transcript-bound Service Channel context | Future profile or Core v0.2; no D1-D6 change | Yes: exact derivation and vectors | WP4 |
| Early data | TLS 1.3 and QUIC 0-RTT | Standard replay-prone early-data mechanism for explicitly safe data | No 0-RTT for route-changing control messages, grants, revocation, migration, resume, handover, or OriginSet updates | Classification of NBSR messages as replay-safe or replay-unsafe | No allocation implied | Yes before any NBSR 0-RTT use | WP4, WP6 |
| Legacy address discovery | DNS A and AAAA, RFC 1035 and RFC 3596 | Address RR lookup and normal recursive resolution | Internal reachability input only; filter addresses and bound answers; never client-visible origins | Deterministic Derived OriginSet construction | Internal model only | WP2 design approval | WP2 |
| DNS aliasing | DNS CNAME, RFC 1034 and RFC 1035 | Standard alias processing, loop handling, TTLs, and cache behavior | Bound chain depth; retain requested Service Name as identity; target is reachability metadata | Association of alias result with Service Identity and policy | Internal model only | No new wire approval for WP2 | WP2 |
| Rich service discovery | DNS SVCB and HTTPS, RFC 9460 | Endpoint priority, target, port, ALPN and supported hints | Treat hints as candidates; validate mandatory parameters and final A/AAAA; preserve original service name | Deterministic conversion into a Derived OriginSet | Internal model only | WP2 design approval | WP2 |
| DNS data authentication | DNSSEC, RFC 4033 through RFC 4035 | DNS RRset origin authentication and integrity where a validated chain exists | Never equate DNSSEC with NBSR Service Identity or authorization; define downgrade handling | Recording discovery assurance separately from NBSR identity | Internal metadata only | Yes: required/optional policy by mode | WP2, WP5 |
| DNS caching | DNS TTL and negative caching, RFC 2308 | Positive and negative reachability-cache lifetimes | DNS TTL is not Route Grant expiry or authorization; clamp resource-abusive values | Stable synthetic mapping independent of origin refresh | None | Yes: outage and last-known-good policy | WP2 |
| TCP proxying | QUIC reliable byte streams; HTTP CONNECT, RFC 9110 where an HTTP proxy profile is selected | Ordered reliable byte transport; standardized CONNECT authority tunneling when applicable | Initial native profile uses one QUIC application stream per proxied TCP flow; HTTP CONNECT is optional and does not replace NBSR control | Stream-to-Service-Channel and Route Context binding | Transport profile; no new Core code allocated | Yes: final application-stream preface or CONNECT choice | WP3 |
| UDP proxying | MASQUE CONNECT-UDP, RFC 9298; HTTP Datagrams and Capsule Protocol, RFC 9297; QUIC DATAGRAM, RFC 9221 | Standard UDP flow framing, datagram carriage, and capsule fallback | Future profile only; bind every flow to an authorized Service Channel; no 0-RTT route changes | UDP flow authorization and service binding | Future approved extension or Core v0.2 | Yes: exact UDP framing | WP4 or later |
| IP proxying | MASQUE CONNECT-IP, RFC 9484; Capsule Protocol; QUIC DATAGRAM | Standard IP proxy tunnel framing and MTU/error conventions | Future explicit IP profile; narrow selectors, no universal VPN-like authorization | Per-service or policy-scoped IP-route authorization | Future Core v0.2 profile | Yes: IP profile and authorization scope | Later than WP4 |
| Packet sizing | QUIC v1 datagram sizing and DPLPMTUD; RFC 8899 | QUIC minimum Initial size, PMTU discovery, probing, and loss integration | Account for NBSR and proxy overhead; bound inner payload; do not invent PMTU | Service-aware oversized-payload error and policy | Profile only unless an NBSR error is needed | Yes if a new error or wire signal is needed | WP3, WP4 |
| Legacy certificate checks | TLS, PKIX RFC 5280, service identity RFC 9525, SNI RFC 6066 | Certificate path validation, validity, SAN matching to requested hostname, SNI | Web PKI validates a legacy origin candidate; it is not the only NBSR-native Service Identity | Relationship between accepted candidate and ServiceRecord/OriginSet authority | Internal policy first | Yes: Web PKI requirement level | WP2, WP3 |
| Native origin authority | COSE Sign1 profile concepts, ServiceRecord authority, delegated edge/connector metadata | Existing signature and trust primitives where approved | Do not add an OriginSet wrapper, key, or message under D1-D6 | OriginSet issuer authority, publication, rollback, equivocation, and revocation | New wire design or internal-only model | Yes: OriginSet compatibility and authority gate | WP2, WP6 |
| Synthetic IPv4 | RFC 1918, RFC 6598 Shared Address Space, loopback, operator-assigned routes | Existing address semantics and host routing | Prefix is configurable and collision-checked; 100.64.0.0/10 is not universally safe; prevent leakage | Scoped name-to-Synthetic-IP allocation and lifecycle | Local API/state only | Yes: production allocation | WP2, WP5 |
| Synthetic IPv6 | RFC 4193 ULA or operator-assigned prefixes | Local IPv6 routing and high-probability unique ULA generation | Per-operator generated prefix; collision detection; border rejection; no universal constant | Scoped name-to-Synthetic-IP allocation and lifecycle | Local API/state only | Yes: production allocation | WP2, WP5 |
| Capture on Linux/OpenWrt | nftables, TPROXY, policy routing, TUN, eBPF, local DNS interception | Proven OS packet classification, redirection, and virtual-interface mechanisms | Least privilege; explicit synthetic-prefix capture; bypass detection; reversible configuration | Correlation of intercepted synthetic destination with RouteIntent | Outside Core wire | Yes per deployment profile | WP5 |
| Capture on Windows | Windows Filtering Platform, local resolver/DNS policy, signed service or driver | Platform filtering, callout, policy, and resolver integration | Signed production components; synthetic-prefix-only capture; fail closed on bypass | Correlation of intercepted synthetic destination with RouteIntent | Outside Core wire | Yes per Windows deployment | WP5 |
| Per-service capacity | QUIC stream limits and flow control plus operator token buckets/schedulers | Transport-level bounds, backpressure, and congestion response | Independent channel/stream/byte quotas, fair scheduling, priority policy, starvation prevention | Service-level quota and audit attribution on shared transport | Internal policy; future channel profile | Yes: default bounds and scheduling policy | WP4, WP5 |
| Admission and DDoS | QUIC Retry and anti-amplification; bounded CBOR scanner; caches and token buckets | Cheap address/framing checks and bounded parsing | Validate cheaply before replay, signatures, policy, route state, or channel allocation | NBSR admission order and service-scoped capacity decisions | No new wire impact by default | No for ordering; yes for any new challenge | WP3, WP5 |
| Time and replay | UTC timestamps, monotonic generation/sequence, replay caches, tombstones | Common freshness and rollback-control practices | Separate DNS TTL, OriginSet validity, grant, session, channel, and stream lifetimes | Cross-object rules preventing stale acceptance and resurrection | Existing D6 semantics preserved; future OriginSet rules gated | Yes for OriginSet/resume windows | WP2, WP4, WP6 |
| Logging and privacy | Structured logging, pseudonymous identifiers, access controls, retention policy | Proven operator observability practices | No client-visible origin; no origin in normal client telemetry; separate security and operations access | Per-service audit attribution across a shared session | No wire impact unless audit fields are standardized | Yes: shared-transport audit identity | WP4, WP5 |
| HA and replication | etcd/Raft, PostgreSQL replication, signed snapshots, replicated logs | Proven consensus, storage, and replication systems | Protocol defines correctness and bounded staleness, not a database protocol | Fail-closed generation, sequence, tombstone, replay, revocation, and OriginSet convergence | No storage wire; future federation may have wire impact | Yes: staleness and failover bounds | WP6 |
| Federation | PKI/delegation mechanisms and authenticated inter-operator transport | Existing cryptographic identities and secure transport | Least-authority delegation, explicit trust contexts, revocation, audit boundaries | NBSR Service Identity delegation and inter-operator route authority | New NBSR semantics; likely Core v0.2 | Yes | WP6 or later |

## Safe defaults that do not require new wire allocations

WP2 may reuse ordinary recursive DNS, A/AAAA/CNAME processing, SVCB/HTTPS
parsing, negative caching, and Web PKI libraries to build a bounded internal
Derived OriginSet. It must return only the stable Synthetic IP.

WP3 may select a mature QUIC v1/TLS 1.3 library for one authenticated
edge-to-edge Transport Session and one reliable QUIC stream per proxied TCP
flow. QUIC owns loss, congestion, flow control, path validation, and key
updates. NBSR owns admission and service binding. These defaults do not
approve runtime work, an ALPN registration, a channel wire form, or changes to
frozen Core v0.1.

## Human gates left open

Reuse does not settle the exact Service Channel exporter derivation, production
synthetic prefix, UDP or IP proxy profile, Web PKI requirement level, cross-edge
resume, resource/time defaults, HA staleness, platform interception profile,
or any OriginSet wire/authority decision. Those remain explicit human gates.
