# NBSR legacy compatibility profile

**Status:** WP2/WP3 decision preparation; no runtime authorization

## Purpose

LEGACY_DNS and HYBRID deployments reuse the DNS and Web PKI ecosystems for
temporary origin reachability. NBSR still owns client-visible synthetic
resolution, Service Identity, policy, route authorization, and origin hiding.

## Resolution flow

1. The application requests the Service Name.
2. NBSR performs normal recursive DNS internally, subject to bounded policy.
3. CNAME aliases and A/AAAA answers provide candidate reachability.
4. SVCB/HTTPS records may supply candidate target, priority, port, ALPN, and
   address hints.
5. DNSSEC validation status is recorded when available.
6. NBSR deterministically constructs a bounded internal Derived OriginSet.
7. Policy and candidate validation run before any endpoint is selected.
8. NBSR returns a Synthetic IP to the client.
9. Connection to the Synthetic IP is correlated with a RouteIntent.
10. The Destination Edge connects only to a validated candidate.

The origin IP is never returned to the client, and direct fallback to an origin
endpoint is forbidden.

## DNS mechanism reuse

| Mechanism | Reused behavior | NBSR constraint |
|---|---|---|
| A | Standard IPv4 address RR resolution and TTL | Internal candidate only; reject prohibited ranges unless policy explicitly authorizes the target |
| AAAA | Standard IPv6 address RR resolution and TTL | Internal candidate only; apply equivalent range and scope policy |
| CNAME | Standard alias traversal and TTL behavior | Bound chain depth and loops; the requested Service Name remains the identity |
| SVCB | AliasMode/ServiceMode, priority, target and service parameters | Reject malformed/unsupported mandatory parameters; hints are candidates, not authority |
| HTTPS | SVCB-compatible HTTP endpoint parameters | Preserve the original HTTPS origin name for certificate validation |
| DNSSEC | RRset origin authentication and integrity | Does not create NBSR Service Identity or route authorization |
| Recursive DNS | Existing resolver, cache, and negative-answer behavior | Bound response size, chain depth, query count, TTL, and result count |
| Negative caching | RFC 2308 denial caching | Limits repeated work; never becomes an authorization denial lease |

DNS TTL is not Route Grant expiry. It controls reachability-cache freshness,
not whether a route remains authorized. OriginSet validity, Route Grant
expiry, Transport Session lifetime, Service Channel lifetime, and Application
Stream lifetime are separate clocks.

## Derived OriginSet

A Derived OriginSet is an internal WP2 model, not a Core v0.1 wire object. It
records normalized Service Identity reference, the DNS questions and validation
status, accepted candidate endpoints, ports/transports, priority/weight where
supported, source TTL/expiry, derivation time, and a deterministic content
digest. It must be bounded and reproducible from fixtures.

SVCB/HTTPS `ipv4hint` and `ipv6hint` do not bypass A/AAAA or endpoint policy.
Different-content results under the same local derived version are rejected.
Refreshing origins does not change the Synthetic IP mapping.

## DNSSEC role and downgrade

DNSSEC authenticates DNS data when the full validation chain succeeds. It does
not authenticate an NBSR ServiceRecord owner, grant issuer, Destination Edge,
or connector. Secure, insecure, bogus, and indeterminate results remain
distinct.

Whether LEGACY_DNS may accept securely transported but unsigned DNS, and
whether HYBRID requires DNSSEC for particular metadata, are policy gates.
Bogus data must fail closed; silently treating a previously secure name as
insecure is a DNSSEC downgrade threat.

## Web PKI validation

For HTTPS legacy candidates, reuse normal Web PKI:

- use the requested hostname as the reference identity;
- send the requested hostname as SNI where TLS requires it;
- validate the complete certificate chain against configured trust anchors;
- require SAN matching under RFC 9525;
- enforce certificate validity and configured revocation behavior; and
- never substitute a discovered target name or Origin IP as the service
  reference identity merely because DNS returned it.

Web PKI is useful origin candidate validation for LEGACY_DNS and HYBRID. It is
not sufficient as the only NBSR-native Service Identity mechanism.

In NBSR_NATIVE, ServiceRecord authenticates service identity/policy, OriginSet
authority authenticates reachability publication, Destination Edge admission
authorizes the selected path, and a connector/origin credential authenticates
the final target. Exact OriginSet signing and connector validation remain
human gates.

## Cache and outage behavior

Positive and negative DNS answers follow DNS cache semantics with configured
upper bounds. A Derived OriginSet expires independently according to accepted
source freshness and policy. No DNS refresh may extend a Route Grant.

When DNS is unavailable, NBSR does not expose the last origin to the client.
Whether a bounded, previously validated last-known-good Derived OriginSet may
serve new channels is unresolved. Until approved, new route establishment
fails closed; already-authorized streams follow their independent drain and
expiry policy.

## Security and test requirements

WP2 tests must cover alias loops, mixed or prohibited addresses, CNAME/SVCB
depth, malformed mandatory SVCB parameters, DNSSEC bogus/downgrade behavior,
TTL clamping, negative caching, deterministic Derived OriginSet fixtures,
stable Synthetic IP across refresh, and zero client-visible origin data.
