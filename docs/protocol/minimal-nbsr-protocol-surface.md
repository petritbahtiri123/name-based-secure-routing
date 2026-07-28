# Minimal NBSR protocol surface

**Status:** Architecture boundary; wire details remain gated

NBSR composes DNS, QUIC, TLS, Web PKI, MASQUE-family proxy mechanisms, operating
system capture facilities, and proven replicated stores. It does not replace
them.

## Genuinely new NBSR semantics

The smallest NBSR-specific surface is:

1. **name -> Synthetic IP mapping:** every successful upgraded-network
   resolution returns a scoped Synthetic IP, never an Origin Endpoint.
2. **Synthetic mapping lifecycle:** allocate, scope, refresh, revoke, reclaim,
   and correlate a mapping without changing Service Identity when reachability
   changes.
3. **connection correlation:** translate a connection to a Synthetic IP into a
   bounded RouteIntent in the correct caller and resolution trust context.
4. **RouteGrant semantics:** authorize a specific service route subject to
   service, client/device, gateway, policy, time, sequence, and revocation
   bindings already frozen for Core v0.1.
5. **identity/reachability separation:** Service Identity is independent of
   Origin Endpoint addresses; origin data is mutable internal metadata.
6. **edge admission:** Source Edge and Destination Edge independently
   authenticate and authorize the route and select only validated origins.
7. **layer binding:** bind `Transport Session -> Service Channel ->
   Application Stream` so each application flow is attributable to exactly
   one authorized service context.
8. **session reuse with service-isolated authorization:** multiple services
   may share an eligible transport, but never a grant, revocation state, quota,
   audit identity, or cryptographic/transcript-bound Service Channel context.
9. **no direct fallback:** failure to establish an authorized route fails
   closed; it never reveals or connects the client directly to an origin.
10. **OriginSet authority and publication:** define who can publish, delegate,
    replace, revoke, and recover versioned origin reachability while preventing
    rollback, resurrection, and equivocation.
11. **per-service revocation and audit:** terminate or drain only the affected
    service context when policy permits and retain service-level attribution
    even on shared transport.
12. **federation and trust delegation:** authorize limited inter-operator
    participation without turning transport authentication into universal
    service authorization.

## Explicit exclusions

- NBSR does not define congestion control, loss recovery, packet
  retransmission, or transport pacing; QUIC and its implementation do.
- NBSR does not define TLS cryptography, cipher suites, certificate-path
  algorithms, forward secrecy, or traffic-key updates.
- NBSR does not define DNS record formats, recursive resolution, DNSSEC,
  positive TTL processing, or negative caching.
- NBSR does not define HTTP CONNECT, CONNECT-UDP, CONNECT-IP, Capsule Protocol,
  or QUIC DATAGRAM framing.
- NBSR does not define a custom PMTU discovery algorithm.
- NBSR does not define a distributed database or consensus protocol.
- NBSR does not define TPROXY, nftables, WFP, TUN, eBPF, or local resolver
  platform APIs.
- NBSR does not replace application TLS endpoints, HTTP, OAuth, user login,
  application authorization, transactions, databases, or application recovery.

## Profile rather than invention

NBSR may constrain existing mechanisms: QUIC v1 plus TLS 1.3, mutual edge
authentication, a dedicated ALPN, one control stream, bounded streams,
service-bound exporter contexts, internal-only DNS discovery, strict Web PKI
checks, synthetic-prefix interception, no 0-RTT for route-changing controls,
and fail-closed admission. These are profiles or constraints, not replacements
for the underlying standards.

## Wire-free WP2/WP3 boundary

WP2 can create a deterministic internal Derived OriginSet from DNS and preserve
a stable Synthetic IP without serializing OriginSet. WP3 can establish one
authenticated QUIC/TLS transport and carry one service path without creating a
multi-service channel wire format. Both require their plan gates, but neither
requires changing D1-D6.

Any proposal for a new numeric key, message code, error code, state,
transition, critical extension, or COSE wrapper stops at a human approval gate.
