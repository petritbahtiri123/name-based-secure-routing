# WP2A Name Node core evidence

**Status:** Implemented at bounded loopback lab scope on 2026-07-30.

**Authority:** NBSR Protocol Vision V3.6, frozen Core v0.1 decisions D1-D6,
and approved OriginSet decision D7.

This document records the completed WP2A implementation boundary. It is
evidence for a local deterministic prototype, not a production or
interoperability claim.

## Security invariants

- Synthetic IP for every successful resolution.
- For both configured NBSR and legacy names, origin endpoints remain internal.
- Direct client fallback to an origin endpoint is forbidden.
- An invalid NBSR state never downgrades to legacy.
- DNS TTL is not RouteIntent or RouteGrant lifetime.
- Service identity is independent from mutable reachability metadata.
- Client-visible results, errors, metrics, and normal events do not disclose
  origin endpoints.

## Implemented boundary

WP2A composes these bounded local components:

- `SignedServiceRegistry` verifies owner-bound Service Records, preserves
  record-sequence and revocation-generation tombstones, and fails closed.
- `ResolutionContextStore` correlates a Synthetic IP with bounded internal
  RouteIntent and resolution state.
- `NameNode` classifies only explicitly configured names and returns a stable
  synthetic IPv4/IPv6 pair.
- `NameNodeDnsAdapter` converts supported DNS questions into synthetic-only
  responses without returning internal reachability data.
- `NameNodeLabServer` provides loopback-only UDP and TCP DNS with bounded
  framing, concurrency, timeout, and shutdown behavior.
- `BoundedNameNodeMetrics` records low-cardinality counters and
  privacy-preserving events without raw names or origin endpoints.

The legacy adapter may construct and refresh an internal Derived OriginSet.
Accepted refreshes preserve the Synthetic IP mapping. Temporary failure may
use bounded last-known-good internal state under D7; authenticated negative,
invalid, stale, equivocated, or policy-denied state fails closed.

## Frozen protocol impact

WP2A adds no wire registry or schema allocation:

- 17 message codes remain unchanged.
- 19 error codes remain unchanged.
- D1-D7 remain unchanged.
- No Core v0.1 numeric key, state, transition, critical extension, or COSE
  wrapper changed.

`RouteIntent` is created as internal state using the existing frozen model.
The loopback DNS boundary is a lab adapter and does not define a new NBSR wire
message.

## Explicit non-claims

WP2A provides:

- no real recursive DNS;
- no production DNSSEC or Web PKI validation;
- no signed NBSR-native OriginSet publication;
- no runtime relay or tunnel integration;
- no HA or federation;
- no transparent operating-system interception;
- no independent interoperability result;
- not production ready.

WP3 remains gated. In particular, WP2A does not create a Transport Session,
authorize a Service Channel, open an Application Stream, select a live origin
connector, or integrate with the existing relay.

## Verification evidence

The completed change is covered by deterministic examples and five Hypothesis
properties configured with 300 examples each. Those properties cover valid
configured-name presentation, arbitrary malformed signed input, arbitrary
record update order, accepted legacy refresh, and arbitrary legacy failure
ordering.

The final verification baseline is:

- focused WP2A suite: 207 passed;
- full Python suite: 815 passed, 1 skipped;
- frozen registry/schema/state/vector/CBOR/COSE suite: 167 passed;
- Ruff check and format check: clean;
- dependency check: no broken requirements;
- Core v0.1 and Core v0.2 vector regeneration checks: verified;
- Compose configuration: valid, with a local Docker configuration access
  warning;
- OPA refresh: unavailable because no executable `opa` command was present;
  no replacement result is claimed.

The tests also scan the WP2A boundary for sensitive credential markers and
origin-field naming that could accidentally enter a client-visible surface.
