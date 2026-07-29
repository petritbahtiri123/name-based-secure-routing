# Legacy DNS-backed Derived OriginSet Design

**Status:** Approved design for Phase D implementation planning

**Date:** 2026-07-29

**Scope:** WP2 legacy DNS discovery boundary, bounded cache, and deterministic
conversion into the internal `DerivedOriginSet` model

## Goal

Convert normalized legacy DNS reachability into bounded internal
`DerivedOriginSet` values while preserving stable Synthetic IP mappings,
keeping origin addresses hidden, and continuing safe synchronization through
short transient DNS failures.

## Non-goals

This phase does not:

- change Core v0.1 registries, schemas, state machines, or error codes;
- create an OriginSet wire format, message, CBOR encoding, or COSE wrapper;
- query public DNS during tests;
- integrate origin selection into `NameRelay`;
- implement Web PKI network handshakes or active health checks;
- implement Service Channels, QUIC, WP3, or native origin publication; or
- return an Origin Endpoint through DNS, an API response, or a client-visible
  error.

## Chosen approach

Phase D uses a small adapter between an injected DNS discovery boundary and the
approved internal OriginSet model.

The DNS boundary returns normalized, bounded discovery snapshots. The adapter
validates their policy metadata, converts accepted endpoints into a
`DerivedOriginSet`, and stores the accepted set in an independent cache.
Existing DNS libraries or a future recursive resolver own DNS transport,
packet parsing, CNAME/SVCB processing, and RFC 2308 negative caching. The
adapter does not invent replacements for those standards.

The adapter exposes explicit refresh operations. It does not start threads or
own an event loop. A later Name Node scheduler may call the refresh API at the
returned refresh deadline.

## Components

### `LegacyDnsSnapshot`

An immutable normalized result from the injected DNS boundary:

- requested Service Name;
- origin discovery name;
- endpoint IP literals and ports;
- source TTL in seconds;
- DNSSEC status;
- observation timestamp; and
- a result classification: positive, temporary failure, authenticated
  negative, or invalid.

The snapshot contains no authorization claim. DNS reachability and DNSSEC
status cannot create Service Identity, RouteGrant authority, or native
publication authority.

### `LegacyOriginRequest`

An immutable caller-supplied trust and policy context:

- `service_id`;
- accepted ServiceRecord generation;
- local derivation issuer ID;
- permitted ports;
- permitted address ranges; and
- maximum accepted endpoint count, from 1 through 32.

This request keeps service identity and policy outside DNS data. The Phase D
adapter does not infer a Service Identity from an origin name or IP address.

### `LegacyOriginAdapter`

The adapter:

1. accepts a request and normalized snapshot;
2. rejects mismatched names, timestamps, ports, address ranges, endpoint
   counts, and DNSSEC-bogus data;
3. normalizes and deterministically orders accepted endpoints;
4. increments the local monotonic sequence only for a newly accepted refresh;
5. chains `previous_digest` to the highest retained accepted state;
6. calls `accept_originset` before replacing cache state; and
7. returns internal status and deadlines without exposing endpoint data to a
   client model.

Origin generation starts at 1 for the local derivation authority. A higher
ServiceRecord generation never permits a lower origin generation or sequence.
Generation-reset behavior requires a separate decision and is not introduced
here.

### `LegacyOriginCache`

The cache is keyed by `(service_id, issuer_id)` and stores:

- highest accepted `DerivedOriginSet`;
- DNS freshness deadline;
- bounded last-known-good deadline;
- next refresh/retry deadline;
- consecutive temporary-failure count; and
- tombstone or hard-invalidated state where applicable.

The prototype cache has a configurable maximum entry count with a default of
1,024. When full, insertion fails closed. It does not silently evict accepted
security state or tombstones.

## Time profile

These values are configurable prototype defaults, not Core wire constants:

- maximum accepted source DNS TTL: 300 seconds;
- last-known-good grace: 300 seconds;
- proactive refresh: 80 percent of the accepted source TTL, with a minimum of
  1 second before expiry;
- temporary-failure retry delays: 1, 2, 4, 8, 16, then 30 seconds;
- maximum retry delay: 30 seconds.

DNS freshness and OriginSet validity remain separate:

- `dns_fresh_until` is the observation time plus the clamped source TTL;
- `last_known_good_until` is `dns_fresh_until` plus the configured grace;
- the Derived OriginSet validity ends at `last_known_good_until`;
- DNS TTL never extends a RouteGrant, Transport Session, Service Channel, or
  Application Stream lifetime.

## Refresh and outage behavior

### Successful refresh

1. Validate the snapshot and caller policy.
2. Build the candidate OriginSet.
3. Validate monotonic sequence and digest continuity.
4. Store the candidate atomically.
5. Mark it fresh and reset temporary-failure backoff.
6. Preserve all Synthetic IP mappings.

The adapter never deletes the accepted set before the replacement passes all
validation.

### Temporary DNS failure

Timeout and SERVFAIL are temporary failures:

- retain the last accepted set;
- return it only while the bounded last-known-good deadline remains valid;
- mark it as last-known-good rather than fresh;
- schedule another refresh using the bounded retry sequence; and
- fail closed for new use after the grace deadline.

Existing Application Streams are outside this cache decision and follow their
own authorization and drain policy.

### Hard failure

The following invalidate new use immediately:

- authenticated NXDOMAIN or authenticated NODATA for the required endpoint;
- DNSSEC bogus or a prohibited secure-to-insecure downgrade;
- caller policy or ServiceRecord generation mismatch;
- revocation or tombstone state;
- endpoint outside the permitted ranges or ports;
- endpoint count above the request or model limit;
- stale generation or sequence;
- same-version different-content equivocation; or
- invalid candidate validation result.

Hard failure retains the highest security state or tombstone required to
prevent rollback. It never falls back directly to an origin address.

## Candidate-validation boundary

The Phase D adapter accepts only endpoints approved by an injected,
fail-closed candidate validator. Deterministic tests use a local validator.

The later production validator must enforce address policy and, where
applicable, Web PKI validation and health checks before new channels use an
endpoint. This design does not claim that DNS or DNSSEC alone performs those
checks.

## Data flow

```text
registered Service Name and caller policy
    -> injected legacy DNS discovery
    -> normalized LegacyDnsSnapshot
    -> policy and candidate validation
    -> deterministic DerivedOriginSet candidate
    -> rollback/equivocation/tombstone validation
    -> independent LegacyOriginCache
    -> internal validated OriginSet consumer

application DNS query
    -> existing NBSR synthetic mapping
    -> Synthetic IP only
```

The two flows remain separated. Origin refresh never changes the
client-visible Synthetic IP mapping.

## Error handling

Phase D uses local internal exceptions and result states. It does not allocate
or repurpose a Core v0.1 protocol error code.

Errors and ordinary logs must identify the service and failure class without
including origin IP literals. Detailed endpoint evidence belongs only in a
separately controlled security log boundary, which is outside this
implementation.

## TDD acceptance criteria

Focused tests must prove:

- deterministic A/AAAA snapshot conversion;
- one through 32 accepted endpoints and rejection above the configured bound;
- strict port, address-range, timestamp, and exact-type validation;
- stable Synthetic IP mapping across successful refreshes;
- DNS TTL and RouteGrant lifetime remain independent;
- proactive refresh and exact bounded retry deadlines;
- last-known-good is allowed only through its 300-second prototype grace;
- timeout/SERVFAIL never exposes or directly returns an origin;
- authenticated negative and DNSSEC-bogus results invalidate immediately;
- new state is accepted before old state is replaced;
- stale, rollback, same-version equivocation, and broken digest chains fail
  closed;
- hard invalidation retains resurrection-prevention state;
- cache capacity fails closed without silent security-state eviction;
- no client response, ordinary error, or ordinary log contains an origin IP;
  and
- existing Core v0.1 registry, schema, state, CBOR, and COSE tests remain
  unchanged and passing.

## Approval boundary

Approval of this design authorizes a TDD implementation of the isolated WP2
adapter and cache only. Integration into `NameRelay`, production recursive DNS,
Web PKI network validation, active health checks, native OriginSet
publication, or WP3 requires a later human gate.
