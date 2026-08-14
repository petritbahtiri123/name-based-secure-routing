# Production Go client subsystem threat model

This document narrows, and does not replace, the authoritative repository-wide
[NBSR threat model](../../threat-model.md). All repository-wide assumptions,
non-claims, future controls, privacy constraints, and severity boundaries remain
in force.

## Overview

The subsystem is a long-lived local Go agent mediating NBSR name resolution and
application flows, acquiring service authority, owning shared QUIC Transport
Sessions, and enforcing Service Channel and Stream Credit isolation. Its most
important failure modes are unauthorized payload forwarding, origin/synthetic
route leakage, authority replay/downgrade/resurrection, cross-service confusion,
and attacker-driven unbounded state.

## Assets, boundaries, and assumptions

Assets: device/workload identity, private-key handles, RouteGrants, RouteIntents,
synthetic mappings, TS authority and selector state, SC bindings, credit epochs
and slots, session-local ServiceHandles, Mapping/Service/Stream registry state,
application payload, local policy, trusted authority/profile config,
revocation/freshness state, and privacy-preserving audit records.

Trust boundaries:

- local application ↔ platform adapter/client;
- OS/kernel/network configuration ↔ privileged adapter/client;
- resolver ↔ Mapping Manager;
- client ↔ source gateway over QUIC/TLS;
- Authority Provider/control plane ↔ RouteGrant Manager;
- persisted state/filesystem ↔ running client;
- administrator/software update ↔ validated configuration/binary;
- Go core ↔ platform adapter.

Network packets, resolver and gateway replies, malformed frames, local
connections, Synthetic-IP traffic, weakly protected config, filesystem
corruption, and stale/replayed authority are attacker-controlled inputs.
Administrators control approved roots, policy, limits, endpoints, and adapter
selection; developers control builds and defaults. Root/kernel, authority-key,
and trusted administrator compromise can defeat the local boundary, but the
client must still avoid accidental cross-service widening and secret logging.

Required invariants:

- no payload before authorization/ACCEPT and no direct-origin fallback;
- no authority downgrade, replay bypass, or resurrection after revocation;
- no credit reuse across service, channel, grant, generation, or TS;
- existing streams never silently migrate between TS generations;
- one compromised application does not inherit another service's authority;
- a Synthetic IP is correlation state, never identity or authority;
- a MappingID or ServiceHandle is correlation/index state, never identity,
  authorization, or a bearer credential;
- malformed/untrusted input cannot crash the long-lived agent;
- all attacker-influenced state, work, retries, logs, and concurrency are bounded;
- rotation and crash recovery cannot restore stale or revoked authority.

## Attack surface, controls, and attacker stories

Priority uses **impact × exploitability × exposure** qualitatively.

| Priority | Threat class / attacker story | Required control and failure rule |
|---|---|---|
| Critical | Spoofing/confused deputy: local app presents another process's Synthetic IP or races mapping reuse | Bind local peer identity + tenant/context + mapping generation + destination; atomic lookup; expired/wrong-context fails closed |
| Critical | Downgrade: gateway/profile error causes legacy STREAM_OPEN or plaintext/direct retry | Pin exact ALPN/P2D profile; reject legacy entrypoints without mutation; never direct fallback |
| Critical | Cross-service/TS confusion: credit or grant for A/TS-A opens B/TS-B | Complete binding keys, actual QUIC stream ID, atomic one-use slot, independent grant/channel admission |
| Critical | Handle alias/stale reuse: freed ServiceHandle or MappingID resolves to a different live service | Never reuse ServiceHandle values within a TS generation, maintain bijective reverse index, remove streams before service teardown, and reject stale references |
| Critical | Digest-as-authority confusion: matching service/grant digest bypasses live grant/channel checks | Treat digests only as integrity/correlation/audit bindings; validate current RouteGrant, SC, generation, revocation, and credit authority |
| Critical | Revocation/rollback: TS-B preparation or restart resurrects revoked grant/channel | Authenticated freshness feed, cross-generation fan-out, monotonic config/revocation state, fresh startup authority |
| High | Route/mapping poisoning by resolver or local config | Resolver provides constrained identity-correlated input only; validate authority/policy; protect config permissions/integrity; collision and bypass tests |
| High | Malicious gateway sends malformed, reordered, slow control/stream data | Bounded decoders, deadlines, ordered control ownership, payload quarantine, independent channel containment, no peer-controlled await under global lock |
| High | Resource exhaustion/slowloris from local apps or network | Global/per-service semaphores, byte/time limits, finite queues/caches/retries, cheap validation first, fair scheduling and rate-limited logs |
| High | Registry flooding/collision degrades O(1)-style lookup or grows memory | Explicit entry/byte capacities, reserved insertion, keyed collision-resistant map implementation, expiry/terminal cleanup, and overload rejection |
| High | Key theft or local privilege abuse | OS keystore/non-exportable keys, purpose separation, least-privilege service/adapter split, no secrets in memory longer than needed or in diagnostics |
| High | Crash-recovery rollback via copied/corrupt state | Persist minimal versioned integrity-protected config and monotonic generation; never persist live TS/SC/credit; quarantine unsafe state |
| High | Malicious/compromised Authority Provider issues or replays stale authority | Pin issuer/profile, verify all grant bindings and validity, freshness/revocation policy, audit opaque digest; authority compromise remains a major residual risk |
| Medium | Network migration treated as authorization | QUIC path validation proves only reachability; revalidate adapter capture and NBSR bindings; cross-edge requires fresh authority |
| Medium | Retry duplicates side effects or application bytes | Typed retry matrix; correlated pre-commit operations only; forbid implicit payload retry after any write |
| Medium | One noisy service starves others on shared TS | Per-service quotas/queues plus aggregate cap and fair scheduler; contain channel failure |
| Medium | SNI/Host inference misroutes non-HTTP, encrypted, or ambiguous traffic | Never use application metadata as generic identity; use per-service mapping or proven adapter FlowContext, then authorize independently |
| Medium | Telemetry correlates user/service/origin or log flood consumes disk | Pseudonymous bounded labels, no origin/payload/keys, rate/size/retention limits, separate security/operations access |
| Medium | Upgrade/admin config widens interception or trusts stale roots | Signed/verified packages, schema and generation checks, staged validation, fail-safe rollback that does not roll back authority |
| Low | Local unprivileged app learns aggregate health/timing | Restrict health endpoint and label detail; coarsen external errors/metrics |

## Mitigation architecture

Authority and forwarding are separate: the adapter cannot grant authority and
the standard Authority Control Plane/AuthorityProvider cannot inject payload or
bypass independent verification. Immutable generation-bearing
handles cross managers. A single selector linearizes new-flow cutover. State
machines validate then commit without holding locks across peer-controlled I/O.
Per-service and global budgets contain noisy neighbors. Permanent security
errors open circuits until relevant authority/config changes rather than retrying.

Fuzz/property testing targets all decoders and lifecycle transitions. Adversarial
tests cover stale mappings, duplicate/old credits, cross-service/TS bindings,
revocation during cutover, crash between prepare/switch/drain, cancellation,
slow peers, queue saturation, and malformed configuration. OS-adapter tests prove
synthetic traffic cannot bypass capture. Registry tests cover capacity,
collision behavior, stale-handle reuse, teardown order, and zero persistence of
ServiceTable/StreamTable state.

## Severity calibration and residual risk

**Critical:** a remotely or locally reachable path that forwards payload without
valid service authority, exposes direct origin reachability, accepts downgrade,
or enables reusable cross-service/TS authority. **High:** key theft, authenticated
authority rollback/resurrection, remotely triggerable durable resource
exhaustion, or a malicious gateway crashing/compromising the agent. **Medium:**
contained service outage, bounded metadata exposure, retry duplication before
application payload, or privilege/config weaknesses needing substantial local
access. **Low:** minor bounded observability leakage or operability defects with
no authority or payload consequence.

Residual production gates include managed enrollment/PKI, authenticated grant
acquisition and revocation freshness, OS-specific least-privilege containment,
independent review, supply-chain assurance, and multi-host failure evidence.
Successful lab interop does not reduce those gates.

## Tranche 2 Authority Control Plane amendment

The detailed ACP threat analysis and mitigations are normative design input in
[the Tranche 2 design](tranche2-identity-authority-control-plane.md). In
particular, DeviceIdentity, TS proof, ACP request, RouteGrant issuer, freshness,
and local-state keys have separate purposes. ACP TLS authentication cannot
replace signed RouteGrant verification, and an `AuthorityProvider` result cannot
reach TS/SC state until Go Core independently verifies it.

An expiring signed checkpoint bounds stale trust. Restart begins with an empty
grant cache and cannot lower the durable accepted generation floor. Exact
service, policy, identity, operator/profile, TS key/generation, and authority
generation bindings prevent response substitution and cross-service/TS reuse.
Per-device/global request, body, idempotency, cache, retry, concurrency, and log
bounds contain amplification and malformed traffic. A compromised device
remains a residual endpoint compromise and requires revocation plus reenrollment.
