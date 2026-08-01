# NBSR resource and timeout profile

**Status:** Bounded implementation requirements plus non-normative lab values

This profile separates transport settings from authorization semantics. Values
marked **frozen** come from D6. Values marked **lab recommendation** are safe
starting points for deterministic WP2/WP3 tests, not universal production
defaults. Values marked **pending** require human approval before production.

## Initial bounds

| Resource or timer | Initial value/status | Enforcement and rationale |
|---|---|---|
| Route Grant lifetime | **Frozen:** maximum 600 seconds | D6 RouteGrant rule; cannot be extended by DNS refresh or transport reuse |
| RouteIntent lifetime | **Frozen:** maximum 300 seconds | D6 RouteIntent rule |
| Clock skew | **Lab recommendation:** 30 seconds; production pending | Apply symmetrically to time validation but never extend a tombstone or monotonic generation |
| QUIC idle timeout | **Lab recommendation:** 30 seconds; production pending | Negotiated QUIC transport liveness; closing an idle session grants no authorization |
| Keepalive interval | **Lab recommendation:** disabled unless middlebox policy requires it; if enabled, less than half the negotiated idle timeout | Transport liveness only; keepalive does not renew grants or channels |
| Maximum Transport Session age | **Lab recommendation:** 60 minutes; production pending | Force fresh peer authentication; independent of active grants |
| Reauthentication interval | **Lab recommendation:** no longer than maximum session age; production pending | Revalidate peer role/trust and all continuing channel bindings |
| Graceful drain timeout | **Lab recommendation:** 30 seconds; production pending | Stop new streams immediately; bound completion before forced close |
| Reconnect backoff | **Lab recommendation:** exponential from 250 ms to 30 seconds with jitter | Bound retry load; authorization rechecks on every new session |
| Same-edge resume | **Pending** | Resume transport only after expiry, revocation, replay, gateway, service, device/client, and policy checks |
| Cross-edge resume | **Pending and disabled** | Requires explicit reauthorization and approved proof |
| Transport Sessions per authenticated peer | **Lab recommendation:** 8; production pending | Reject excess before expensive route allocation |
| Service Channels per Transport Session | **Lab recommendation:** 32; production pending | Independent authorization and quota per channel |
| Service Channels per service per session | **Lab recommendation:** 8; production pending | Prevent one service consuming the shared session |
| Application Streams per Service Channel | **Lab recommendation:** 64 concurrent; production pending | Enforce below the QUIC connection stream limit |
| Buffered bytes per stream | **Lab recommendation:** 1 MiB; production pending | Backpressure rather than unbounded buffering |
| Buffered bytes per Service Channel | **Lab recommendation:** 8 MiB; production pending | Independent accounting; throttle only the offending channel when possible |
| Replay cache | **Bound required; exact entries pending** | Cover accepted proof lifetime plus clock skew and tombstone requirements; reject on capacity uncertainty |
| DNS/Derived OriginSet cache | **Prototype profile:** 1,024 entries; production pending | Reject insertion at capacity; never silently evict accepted security state or tombstones |
| Legacy OriginSet source TTL | **Prototype profile:** clamp to 300 seconds; production pending | Reachability freshness only; proactive refresh begins at 80 percent |
| Legacy OriginSet outage grace | **Prototype profile:** 300-second last-known-good grace; production pending | Temporary timeout/SERVFAIL only; authenticated negative, DNSSEC bogus/downgrade, policy failure, rollback, and equivocation invalidate immediately |
| Legacy OriginSet retry | **Prototype profile:** 1, 2, 4, 8, 16, then 30 seconds | Retry work is bounded and never extends grant or OriginSet validity |
| Signature-result cache | **Bound required; exact entries pending** | Key by exact signed bytes, trust context, key generation, and policy state; never cache a broad success |
| Audit queue | **Bound required; exact entries pending** | Apply backpressure or fail closed for mandatory security audit events |
| WP4 peer-initiated bidirectional streams per Transport Session | **Lab profile: 2,049 total** | One control stream plus at most 2,048 simultaneous application streams (32 channels times 64); channel limits remain independently enforced |

Every limit is configurable within an operator-approved safe range. Raising a
transport limit must not implicitly raise a per-service quota.

## Distinct lifetimes

- **DNS TTL:** lifetime of cached DNS reachability data.
- **OriginSet validity:** publisher/derivation interval during which an
  OriginSet may be selected, subject to sequence, generation, health, and
  revocation.
- **Route Grant expiry:** last instant the named authorization can be used or
  renewed under its rules.
- **Transport Session lifetime:** authenticated QUIC/TLS relationship age.
- **Service Channel lifetime:** independently authorized service context,
  bounded by its grant, policy, revocation, session, and reauthentication.
- **Application Stream lifetime:** one application flow; completion or drain
  never extends the parent authorization.

DNS TTL does not authorize a route. None of these clocks silently extends
another.

## Time, sequence, and replay rules

- Validate `not_before` and `expires_at` against a bounded configured skew.
- Use wall-clock time for validity intervals and monotonic process time for
  local duration measurement.
- Persist highest accepted issuer generation and tombstones where D6 requires
  them.
- For OriginSet, retain highest generation/sequence and content digest so
  stale and same-sequence-different-content updates fail closed; exact native
  rules remain gated.
- Replay cache keys include trust context, message/proof type, issuer, service,
  gateway/client bindings, and unique proof identifier.
- Cache exhaustion must not become fail open.

## Flow control, fairness, and noisy neighbors

QUIC connection/stream flow control, stream limits, and congestion control are
reused. NBSR additionally accounts for active channels, streams, queued bytes,
processed bytes, admission work, and audit volume per service. Scheduling must
prevent starvation and may use weighted fair queuing or another reviewed
scheduler; no universal priority algorithm is frozen.

Revoking or throttling service A must not revive, authorize, or unnecessarily
terminate service B. Transport-wide overload may close the session only when
bounded containment cannot preserve security.

## MTU and datagram bounds

Use QUIC packet sizing and DPLPMTUD. For a future QUIC DATAGRAM profile, the
usable inner datagram is no larger than the peer-advertised limit and current
path capacity after all encapsulation overhead. Oversized UDP payloads are
rejected or handled by the chosen standard proxy profile; QUIC DATAGRAM frames
are not fragmented. Future CONNECT-IP fragmentation/ICMP policy remains gated.

## Admission resource order

Perform cheap packet/framing checks, QUIC address validation where applicable,
bounded CBOR scanning, replay/sequence checks, signature verification, and
policy evaluation before allocating route or channel state. Apply token
buckets to unauthenticated packets, validated peers, services, and expensive
cryptographic work. Proof-of-work is not justified for the initial profile.

## Approval gate

Human approval is required for production timer values, resource ceilings,
fairness policy, retry behavior, replay/cache sizes, drain lifetime, and
same-edge/cross-edge resume. Lab values must be load-tested and replaced by
deployment-class profiles before production claims.
