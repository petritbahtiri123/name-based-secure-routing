# WP7 two-operator ISP lab design

**Status:** Approved on 2026-08-02 under the delegated approval in the WP7 work request. The evidence boundary is a deterministic, storage/configuration-neutral two-domain simulation. It is not a live two-ISP deployment or a federation protocol.

## Selected approach

WP7 adds a Python lab model around existing authority objects. Three approaches were considered: a privileged live multi-network lab, a new cross-operator wire protocol, and an in-process deterministic conformance model. Windows cannot supply credible independent multi-host ISP evidence, and new federation messages belong to WP8, so the approved approach is the smallest deterministic model with separate operator profiles, trust and policy decisions, quotas, audits, topology, and abuse scenarios.

## Ownership, keys, and reused authority

ISP-A owns source admission, subscriber/name limits, source policy, source audit, and source-edge resources. ISP-B owns destination admission, service/route/channel/tunnel limits, destination policy, destination audit, and the connector boundary. Operator identifiers are bounded local configuration labels, not global federation identifiers. Each profile carries separate SHA-256 key fingerprints for identity, policy, and audit purposes; fingerprints must be unique across operators and purposes.

The model consumes caller-verified WP3/WP4 authority as opaque RouteGrant, channel, and exporter-binding digests plus authenticated edge identities. It does not parse, mint, or change Core messages. It consumes the WP5 trusted gateway-profile digest and fail-closed conformance result. It may consume a WP6 `ContinuityPermit`-equivalent snapshot/policy/channel digest context, but only as an additional denial gate; continuity cannot mint route or resume authority.

## Admission and bounded trust

Source admission runs first and authenticates ISP-A, tenant, subscriber pseudonym, name, route, service, source edge, source policy, RouteGrant context, gateway conformance, and current continuity. Destination admission then independently authenticates ISP-B, tenant, service, route, channel, tunnel, destination edge, destination policy, RouteGrant context, and the exact locally configured ISP-A-to-ISP-B trust tuple. Any missing, stale, conflicting, unavailable, replayed, revoked, tombstoned, equivocated, or mismatched context denies before resource allocation.

The only cross-operator trust assumption is a local configuration tuple `(source_operator, source_identity_fingerprint, destination_operator, destination_identity_fingerprint, route_id, service_id, route_grant_digest)`. This is injected trusted lab configuration, not signed ownership, delegation, trust rotation, interoperability, or federation.

## Identity, isolation, and privacy

Subscribers are represented only by an operator-local HMAC-SHA-256 pseudonym supplied by the trusted source boundary. Raw subscriber/client identifiers never enter the lab model. Isolation keys are exact tuples containing the owning operator plus tenant and the relevant subscriber, name, service, route, channel, or tunnel identifier. No quota or authority lookup falls back to a less-specific or foreign key.

The Origin Endpoint exists only inside an `OriginConnector` object owned by ISP-B. It may establish the final simulated connection and returns only a safe receipt digest. No profile, policy, trust record, request, response, audit, report, topology export, scan result, subscriber state, or non-connector component contains or receives the endpoint.

## Limits, clock, fairness, and overload

Limits are independently configured for client, name, route, service, channel, tunnel, and operator scopes. A deterministic integer token bucket uses caller-supplied monotonic milliseconds, positive integer capacity/refill, saturating refill, no fractional arithmetic, no wraparound, rejection of time rollback, and fail-closed unsigned-64-bit bounds. A request consumes all applicable buckets atomically only after every bucket can admit it.

Operator resource ownership uses bounded active allocations. Per-subscriber fair share is `max(1, operator_capacity // active_subscriber_count)` and cannot exceed configured subscriber capacity. A noisy subscriber is denied without consuming a sibling's quota. Collection capacity, counter saturation, audit exhaustion, identifier bounds, and overload all fail closed. There is no direct-origin fallback. Source admission timeout is 5 seconds, destination admission timeout is 5 seconds, and drain is bounded to the existing 30 seconds.

## Audit, topology, scan, persistence, and corruption

Each operator owns an independent bounded append-only in-memory audit ring with a positive uint64 sequence. At capacity or sequence exhaustion, the security decision fails closed rather than dropping or overwriting evidence. Events contain operator, sequence, safe action/reason codes, and safe context digests only. Reports expose aggregate counts and safe codes.

The closed topology schema contains only operator/edge labels, synthetic client prefixes, and opaque connector labels. It is sorted, size-bounded, and rejects unknown fields, duplicate ownership, unsafe routed origin nodes, or direct client-to-origin edges. Raw-scan simulation returns only synthetic and public lab nodes; it proves non-discoverability and non-reachability solely within that model.

WP7 persists no mutable runtime lab state. Therefore file rollback, partial write, symlink, TOCTOU, and corruption risks are avoided rather than delegated to a new format. Existing trusted WP5/WP6 persistence remains independently responsible for its own secure-file checks. Configuration deserialization is closed, bounded, canonical, and side-effect free; planning and verification never mutate live systems.

## Tests and non-claims

RED-GREEN tests cover operator/purpose key separation, both admission stages, spoofing and replay across every context, policy rollback, continuity denials, independent quotas, arithmetic bounds, clock rollback, noisy-neighbor isolation, overload, audit exhaustion, privacy, connector confinement, topology bounds, scan behavior, determinism, and documentation anti-drift.

No production readiness, live two-ISP deployment, independent real administration, real subscriber enforcement, DDoS mitigation/elimination, origin anonymity, global federation, signed ownership/delegation, transparency, trust distribution/rotation, new wire protocol, OriginSet publication interoperability, cross-edge handover/resumption, live consensus, complete partition tolerance, independent interoperability, or raw-scan resistance outside the exact simulated topology is implemented or claimed.
