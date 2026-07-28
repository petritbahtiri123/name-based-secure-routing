# Origin publication and migration

**Status:** Approved V3.6 architecture; OriginSet wire form and signing
authority pending human approval

**Runtime status:** Not implemented

## Purpose

Service Identity is stable authorization state. Origin Endpoint data is mutable
internal reachability. NBSR must update reachability without changing the
client-visible Service Name or Synthetic IP and without treating an IP address
as identity.

The migration direction is:

`LEGACY_DNS -> HYBRID -> NBSR_NATIVE`

## Publication modes

### LEGACY_DNS

- Conventional A, AAAA, HTTPS, or SVCB lookup provides temporary internal
  reachability metadata.
- NBSR provides identity, policy, synthetic resolution, and secure routing.
- DNS TTL is not an authorization lease.
- The client always receives a Synthetic IP; the origin IP is never returned.
- Direct client fallback to a discovered origin is forbidden.

The adapter converts a bounded, policy-valid discovery result into a temporary
internal OriginSet. It must reject ambiguous, disallowed, excessive, stale, or
unsafe results. It must not create owner or route authority.

### HYBRID

- Signed NBSR Service Identity and policy records exist.
- Origin Endpoints may still come from a delegated discovery name, Destination
  Edge, connector, or compatibility adapter.
- The Synthetic IP and Service Identity remain stable while the internal
  OriginSet changes.
- Delegation must identify who may publish reachability; mere DNS control does
  not grant broader NBSR authorization.

### NBSR_NATIVE

- Authorized service owners, Destination Edges, or connectors publish signed
  origin updates through an approved NBSR mechanism.
- Legacy DNS is no longer needed for origin reachability publication.
- Issuer authorization, generation, sequence, validity, rollback protection,
  revocation, and split-brain behavior are validated before use.

## OriginSet logical model

OriginSet is a logical model only. It is not inserted into the frozen Core v0.1
D6 schemas and has no approved numeric keys or object-level COSE wrapper.

At minimum it contains:

| Logical field | Required semantic |
|---|---|
| service identifier | Stable Service Identity reference; never an Origin Endpoint |
| service-record generation | Binds the set to an accepted ServiceRecord generation |
| origin generation | Monotonic publisher generation or equivalent epoch |
| monotonic sequence | Strict update ordering inside the generation |
| endpoint set | Bounded eligible Origin Endpoints |
| priorities and weights | Optional ordered selection hints with bounded values |
| transport and port | Exact allowed final-segment transport/port |
| region or locality | Optional bounded routing metadata |
| publication mode | LEGACY_DNS, HYBRID, or NBSR_NATIVE conceptual lifecycle mode |
| validity interval | Start/end or approved non-expiring semantics |
| issuer identity | Authority resolved in an approved trust context |
| rollback protection | Previous digest, generation binding, transparency checkpoint, or equivalent |
| signature or authenticated wrapper | Required whenever the object carries authoritative routing power |

Endpoint forms may include an IP address, discovery hostname, connector ID, or
controlled-egress ID, but they remain inside authorized routing
infrastructure. Endpoint count, encoded size, address family, priorities,
weights, ports, metadata, and validity must be bounded before expensive work.

## Source precedence

Implementations evaluate sources in this order:

1. valid signed NBSR-native OriginSet;
2. valid delegated Destination Edge or connector metadata;
3. constrained legacy DNS discovery bound to accepted identity/policy; and
4. otherwise fail closed.

A higher-precedence source wins only when it is current, authorized, valid,
unrevoked, and not rolled back. Invalid native data does not automatically
downgrade to legacy DNS. The policy for last-known-good data and legacy
unavailability is pending approval.

## Cache and lifetime separation

Maintain distinct state for:

- legacy DNS discovery and DNS TTL;
- OriginSet validity and accepted generation/sequence/digest;
- Synthetic IP mapping lifetime;
- RouteIntent and Route Grant validity;
- Route Context lease;
- Service Channel lifetime;
- Application Stream lifetime; and
- Transport Session lifetime.

DNS TTL refreshes reachability only. It never expires or grants route
authorization. An OriginSet refresh should preserve the Synthetic IP mapping
while the Service Identity and local resolution context remain valid.

## Safe origin update

The required replacement sequence is:

1. receive candidate update;
2. authenticate issuer and validate service-record generation, origin
   generation, monotonic sequence, validity, bounds, revocation, and rollback
   binding;
3. reject stale sequence, lower generation, invalid issuer, duplicate sequence
   with different content, or unauthorized publication mode;
4. validate and health-check new endpoints through an approved trust model;
5. activate valid new endpoints for new channels and Application Streams;
6. preserve or gracefully drain existing streams according to policy; and
7. remove old endpoints only after bounded drain, explicit invalidation,
   revocation, or expiry.

Blind delete-and-replace is forbidden because it can disrupt all existing
traffic before replacements are usable.

If validation fails, keep a still-valid previous set only when policy permits.
Otherwise fail closed. Never disclose or return an Origin Endpoint as a
fallback.

## Rollback and equivocation

An implementation must retain enough durable accepted state to reject:

- lower service-record or origin generation;
- lower sequence in the same generation;
- resurrection after revocation or tombstone;
- same-sequence different-content equivocation;
- replay of an expired or superseded OriginSet; and
- split-brain publishers without an approved precedence/recovery rule.

The exact previous-digest/transparency mechanism and publisher conflict policy
remain pending human approval.

## Health-check boundary

Health is routing evidence, not identity or authority. Health checks must:

- run only against already authorized candidate endpoints;
- use bounded concurrency, time, response size, and retry budgets;
- avoid attacker-controlled redirects or hostname widening;
- bind results to the exact candidate generation/digest; and
- prevent a poisoned checker from silently authorizing another endpoint.

The authoritative checker, attestation format, and quorum policy are not yet
approved.

## Operational examples

### Legacy origin rotation

`service.example` keeps its Service Identity and Synthetic IP. The constrained
DNS adapter observes a new authorized A/AAAA set, constructs a candidate
temporary OriginSet, validates it, directs new channels to healthy new
endpoints, and drains streams using old endpoints.

### Hybrid connector migration

A signed ServiceRecord remains stable while a delegated connector publishes a
new locality. The Destination Edge validates delegation and generation,
activates the new connector for new streams, and removes the old connector
after bounded drain.

### Native emergency invalidation

An authorized native publisher or revocation authority invalidates a
compromised endpoint. Policy may require immediate termination instead of
graceful drain. The action never changes client-visible resolution or reveals
the invalid endpoint.

## Core-version boundary

The logical model may be implemented internally in WP2/WP3 only after that
phase's approval. Native serialization, signing wrapper, issuer model, message
codes, critical extensions, and normative state transitions require a separate
approved extension or Core v0.2 decision.
