# NBSR project direction and evidence guide

## Purpose and authority

NBSR aims to make a service name the entry point to an authenticated, authorized
route while keeping service identity independent of mutable origin reachability.
Security, useful performance and reliable operation must advance together. A fast
path that bypasses authorization, or a reliable connection to the wrong service,
does not satisfy that goal.

This is the durable navigation guide for that direction, not a second protocol
specification or an execution plan. [Protocol Vision V3.6](NBSR_Protocol_Vision_V3.6.md)
remains the architectural source of truth; its precedence rules, approved protocol
decisions and frozen contracts govern. [Implementation status](../protocol/status.md)
and scoped evidence establish what has actually been demonstrated. Dates and
completion labels always belong to a particular boundary, not the entire product.

The milestone snapshot below was checked against source and retained records at
`2ccb5d89d168eae9192a7968e32154a1800dd33d` (2026-11-14). This is a documentation
reconciliation, not a new test, deployment or benchmark result.

## The intended system

The V3.6 path is: **name request -> scoped Synthetic IP -> source-edge correlation
and admission -> authenticated Transport Session -> independently authorized
Service Channel -> Application Stream -> destination admission -> validated
origin or connector**. See the [architecture flow](NBSR_Protocol_Vision_V3.6.md#end-to-end-architecture-flow).

A Synthetic IP is a client-facing compatibility handle, not the service identity
or origin address. The source edge must correlate the connection to the intended
name and authorization context; an IP/port alone cannot identify a service when
handles are shared. The destination independently admits the requested service
and controls the final private reachability segment. Origin addresses stay out of
client-visible answers and direct-origin fallback is forbidden.

The central rule is **session reuse, service isolation**. Multiple services can
reuse compatible encrypted transport without sharing authority, quotas,
revocation or lifecycle ownership. See [session/channel architecture](session-channel-model.md)
and the [Go resolution and secure-routing boundary](production-go-client/tranche6-resolution-secure-routing.md).

Identity, ownership, delegation and policy authorize use; discovering an endpoint
does not. Legacy DNS can supply constrained internal reachability, but its TTL is
not an authorization lease. The intended migration is legacy DNS to hybrid to
NBSR-native origin publication, without changing the client-facing synthetic
contract. See [origin publication and migration](origin-publication-migration.md).

Applications retain their own login, authorization, transactions, TLS semantics
and recovery responsibilities. NBSR does not promise anonymity from operators,
DDoS elimination, arbitrary transparent mobility or production readiness.

## Qualities that must remain visible

| Goal | Required direction | Evidence needed before a broader claim |
| --- | --- | --- |
| Security | Exact identity/name/service bindings; independent admission; fail-closed expiry, revocation and replay handling; origin privacy | Authenticated trust and currentness, negative cases, cross-service isolation and review at the actual runtime boundary |
| Performance | Reuse compatible sessions, multiplex service-isolated work, keep queues and resources bounded | Valid comparable workload, source/binary provenance, issuance and completion accounting, latency/throughput and resource measurements |
| Reliability | Explicit ownership and cleanup, bounded drain, safe renewal/restart and non-resurrection of revoked state | Fault and restart evidence with retained uncertainty, trusted monotonic state and the relevant live topology |
| Operability | Truthful readiness, explicit provisioning, reproducible startup/shutdown and rollback | Non-fixture installation and operational acceptance; configuration or UI success alone is insufficient |

These are acceptance concerns, not new numeric promises or replacements for the
[resource/timeout profile](../protocol/resource-timeout-profile.md). Reuse reviewed
transport, cryptographic and storage mechanisms; do not invent wire semantics or
relax a contract to move a progress counter.

## Milestones and current boundaries

The [single-instance plan](../superpowers/plans/2026-10-10-single-instance-operator-package.md)
is the local operator delivery sequence. The [V3.6 roadmap](../superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md)
provides the broader work-package direction and decision gates. Their historical
entries are not a substitute for later scoped evidence or current task authority.

| Area | Retained boundary | What still separates it from the intended system |
| --- | --- | --- |
| Local end-to-end path | A scoped explicit HTTP CONNECT demo composes client authority, real QUIC, service isolation and a private backend response | Transparent DNS/platform interception, non-fixture deployment and general service support are separate gates; see [demo scope](../demo/nbsr-end-to-end-demo.md) |
| Local P1 relay telemetry (2026-11-28 successor) | [Two Python gateway subprocesses](../demo/p1-cross-gateway-telemetry.md) compose real loopback TLS, independent signed admission, B policy denial and B unavailability with service-side counts and gateway-local traces joined by the test | Local trust/DNS fixtures with distinct gateway process identities and reaped exits; separate from the Go/Rust Core/Federation path, production source-edge packaging and cross-host evidence |
| Single-instance Stages 1-2 | Ownership/contract and offline one-service configuration accepted: 2/10 at their defined scope | [Preflight](../../deploy/single-instance/README.md) reports offline validity, not authenticated references or READY |
| Stage 3 connector | Development Go/Rust control, TLS/exporter loopback, fixture authority and negative enforcement exist | Persistent authenticated registration with real authority/currentness, event delivery and timers remains partial |
| Signed native prerequisites | Retained genesis signatures and bounded request/evidence joins are checked in a Rust integration-test helper | Supplied signer contexts and a three-object fixture inventory are not complete governing closure, runtime authority or admission |
| Local composition and pilot | Later stages specify relay, origin validation, composition, packaging, acceptance, real provisioning and installation | They require their own acceptance and final security-audit gate; earlier fixture success does not close them |
| DNS, HA and federation expansion | Resolver models, simulated continuity and scoped federation/interoperability evidence exist | Production DNS trust, transparent routing, live durable HA, global federation and WAN capacity remain distinct work; local pilot completion would not establish them |

For connector scope, start with the [runtime decision gate](../reviews/2026-11-14-authenticated-registration-runtime-gate.md),
then the [native genesis review](../reviews/2026-11-14-native-signed-genesis-evidence.md)
and [request/evidence binding review](../reviews/2026-11-14-native-request-evidence-binding.md).
The source confirms `registration_ready()` remains false in
`crates/nbsr-transport/src/connector_authority.rs`; the genesis helper is under
`crates/nbsr-transport/tests/support/connector_genesis.rs`. Do not turn successful
signature verification into a registration permit.

The critical connector gate is authenticated provisioning and currentness of the
complete governing dependencies, safe nonregressing restart state, and an approved
clock/serialization boundary. Preserve all applicable controller, normal 3/5 and
emergency 2/5 obligations. The existing client ACP transport/startup mechanisms
are reuse candidates, not an approved mapping to connector governance. Client
readiness and connector READY are separate claims.

The status file and roadmap retain older checkpoints alongside later updates.
For example, older entries describe independent interoperability as pending while
later status records report scoped Task 10B evidence; older KAR notes lack the
subsequently retained signed positives. Read the linked successor review and
source for that exact question. Preserve the older evidence rather than treating
either a historical negative or a later narrow positive as a whole-system result.

## How to read performance and reliability evidence

Use the [paced methodology](../benchmarks/SPHERE_PACED_2026-10-19.md) and the
relevant [area guidance](../agents/AREA_GUIDANCE.md). Retain the original validator
outcome. `INVALID_PARTIAL` remains an invalid/partial attempt even if useful source
counters were collected; counters do not repair missing capture, validation or
cleanup evidence. The capture failure paths in
`scripts/performance/linux_native_capture.py` explicitly preserve that status.

Keep planned opportunities, issued requests, transport packets/ACKs and unique
completions separate. Only matched cohorts, windows and drain boundaries support
an issued-to-completed comparison. Unissued work is not packet loss; missing
counters and unconfirmed cleanup are not zero. A pass at one client count, host,
fixture or topology does not establish larger capacity, WAN behavior or production
readiness. This guide assigns no status to an active run and authorizes no run.

## Deferred delivery direction

The [future Linux appliance and container record](future-linux-appliance.md)
preserves the owner's 2026-11-18 idea for minimal VM/device images and pullable
container images for Kubernetes. It reuses the existing operator packaging stages;
it does not change completion counts or authorize implementation or publication.
Start with a supported standard Linux kernel. Alpine is an evaluation candidate,
not a selected base; kernel-specific changes require measured justification.

## Navigation and maintenance

- For architecture or scope decisions, read this guide and the relevant V3.6
  section, then the [architecture index](README.md) for supporting contracts.
- For implementation, use [status](../protocol/status.md), the applicable approved
  decision/plan, nearby source/tests and the latest scoped review. Read the
  matching [area guidance](../agents/AREA_GUIDANCE.md) before changing that area.
- For delivery milestones, use the single-instance plan's current alignment and
  acceptance gates. Keep publication, infrastructure activation and execution
  authorization separate from documentation and local code preparation.
- When a milestone changes, update its status/evidence record and this guide's
  affected boundary or pointer in the same change. Record what changed, source
  identity, validation scope, remaining gates and the successor evidence link.
  Preserve historical pins, failures and approved contracts.
- Reuse context already verified in the task. Do not reread the whole document
  set for every small edit. Recheck when the affected contract, milestone,
  authority or evidence changes, and use the [handoff template](../agents/HANDOFF.md)
  when transferring work.
