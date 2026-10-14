# NBSR and related architectures: evidence and comparative experiments

Review date: 2026-10-14. Source snapshot: `ad77d59754651fee449bb1d9c14a946f9f3b2d15`
on `codex/nbsr-v3-wp0-wp1`. This is a documentation review, not a benchmark,
conformance certification, novelty claim, or change to frozen protocol contracts.
The comparison addresses the four technologies raised in the ICNRG feedback.

## Routing boundary

The current NBSR implementation uses existing IP routing. Name resolution,
service selection, synthetic addresses, authenticated edge tunnels, and relay
forwarding form an overlay. A RouteGrant authorizes service access; its name
alone does not establish a network-layer route. No new inter-domain routing
algorithm, autonomous-system path selection, or classic multi-hop routing
protocol is demonstrated. Multiple overlay endpoints or relays do not by
themselves prove such routing. Underlay forwarding, reachability, congestion,
and failures still affect NBSR. Future routing ambitions remain separate from
implemented behavior; see [status](status.md).

## Architectural comparison

| Technology and primary source | Mechanism shared with NBSR | Architectural distinction and evidence limit |
|---|---|---|
| HIP: [RFC 9063](https://www.rfc-editor.org/rfc/rfc9063.html), [HIPv2 RFC 7401](https://www.rfc-editor.org/rfc/rfc7401.html) | Cryptographic identity separate from IP location; authenticated peers and policy checks | HIP introduces host identities/HITs and a base exchange, commonly with ESP protection. NBSR binds a named service and scoped grant to an edge/channel context over QUIC/TLS or prototype relay paths. Service identity is not a HIP HIT; NBSR has not demonstrated HIP-equivalent mobility or multihoming. HIP can use identity ACLs; host authentication alone is not an equivalent service-authorization configuration. |
| SCION: [architecture overview](https://docs.scion.org/en/latest/overview.html) | Explicit trust boundaries and authenticated communication; interest in failure containment | SCION provides inter-domain path discovery and packet-carried forwarding paths. NBSR currently selects/authorizes services and edges over existing IP routes, without SCION path construction or forwarding. A QUIC reconnect or alternate relay is not demonstrated AS-path control. SCION can be used with application authorization; route security and service authorization are different properties. |
| NDN Trust Schemas: [Yu et al., 2015](https://named-data.net/publications/schematizing_trust_ndn/) | Name-constrained signing authority, trust anchors, delegation and least authority | Schemas relate data names to authorized signing-key names and certificate chains, automating data authentication. NBSR admission validates grants for service channels; it does not authenticate every application data object as NDN Data. Data authenticity does not alone establish consumer access control or confidentiality; equivalent encryption/access policy must be specified. |
| Defined-Trust: [DeftT draft-06](https://www.ietf.org/archive/id/draft-nichols-iotops-defined-trust-transport-06.html) | Explicit trust policy, constrained communication and validation across trust boundaries | This comparison uses Defined-Trust communications/DeftT, not unrelated projects also named DEFT. DeftT describes schema-governed signed publications, synchronization and relays in limited domains. NBSR focuses on service admission and stream/datagram channels, including legacy byte forwarding. It has not shown equivalent publication-level policy enforcement. This cited revision is an Internet-Draft, not an approved standard; no claim is made that it is the latest revision. |

These systems overlap but are not interchangeable products. The comparison is
an architectural reading of primary sources, not a finding that any system
lacks an equivalent feature in all implementations. No HIP, SCION, NDN or
Defined-Trust implementation was executed for this review.

## Repository evidence at the reviewed snapshot

Paths below are repository-relative. Tests are inspected coverage, not newly
executed results. Historical counts in status/evidence remain historical.

| Property | Implementation and inspected tests | What the evidence does not establish |
|---|---|---|
| Service-scoped admission | `crates/nbsr-transport/src/admission.rs`, `crates/nbsr-transport/tests/admission.rs` within that crate: service allowlist, grant time, operator/edge, policy hash, record sequence, transport/port, replay and capacity checks before channel allocation | Global trust bootstrap, production authority distribution, or advantage over a correctly configured identity/policy baseline |
| Channel/session binding | `crates/nbsr-transport/src/channel_binding.rs` and crate `crates/nbsr-transport/tests/channel_binding.rs`: TLS exporter context covers service, grant digest, edges, channel, route, nonces, transport, port and policy; tests compare peers and fresh handshakes | Application-object signatures, origin trust, end-to-end security against a compromised enforcing edge |
| Service isolation on shared transport | Crate `crates/nbsr-transport/tests/multi_channel.rs`, including `signed_grant_nonce_replay_cannot_disturb_an_active_sibling`; `crates/nbsr-transport/src/channel_registry.rs`, `crates/nbsr-transport/src/channel_streams.rs`, `crates/nbsr-transport/src/stream_gate.rs` | Isolation from shared congestion, process compromise, shared audit/resource exhaustion or host failure in production |
| Revocation/dependency semantics | `nbsr/federation/revocation.py`, `nbsr/federation/state.py`; `tests/federation/test_revocation.py` checks typed targets, terminal compromise and directional invalidation | Live authenticated revocation delivery, convergence time, crash persistence, or globally bounded stale acceptance |
| Outage behavior | `tests/federation/test_outage.py` checks bounded cached state, no authority expansion, hard expiry/drain, and compromise overriding last-known-good state | Real network partitions, live consensus, independent operator administration, or operational HA |
| Connector lifecycle | `nbsr/connector_control_model.py`, `nbsr/connector_federation_model.py`, crate `crates/nbsr-transport/tests/connector_loopback.rs`; scope is described in `status.md` | Offline decisions or supplied test trust do not prove live bootstrap/revocation, autonomous timers, or production deployment |

The Python federation state machine and Rust transport tests are distinct
boundaries. Passing either does not establish the other is wired into every
runtime. Legacy forwarding and newer origin-free lab exchanges likewise must
not be combined into an unsupported whole-system claim.

## Comparative experiment plan (not executed)

Begin with an equivalent mTLS/QUIC proxy plus per-service policy as the practical
baseline. For HIP and SCION, add the same service policy above their transport
or network boundary rather than testing authentication/routing alone against
NBSR authorization. For NDN/DeftT, express an equivalent two-service workload
as named publications and document the adapter, encryption, consumer policy,
and any semantics that cannot be matched. Report native capabilities separately
from added policy components; an unmappable property is N/A, not a failure.
Pin every implementation/version, trust configuration and policy translation.

| Experiment | Controlled stimulus and observable acceptance criteria | Metrics and claim that could be supported |
|---|---|---|
| Authorization | Same authorized service A and forbidden service B, identities and expiry. Mutate service, key, port/transport, policy version, grant and replay context; test valid traffic too. Observe backend/publication delivery, not only error codes. Forbidden delivery must be zero; valid delivery must meet the predeclared availability target. | False accepts/rejects, admission p50/p95/p99, CPU/memory and policy setup cost. Demonstrates scoped enforcement at a stated cost, not novelty. |
| Service isolation | Place A and B on the same transport/host where supported. Saturate A, exhaust its quotas, replay grants, reset streams and revoke A while B runs. Also test shared session/audit exhaustion. | B loss, throughput, p99 latency, disconnects, wrong-service bytes and retained quotas versus idle and equivalent-policy baselines. Channel-local containment is distinct from shared-resource isolation. |
| Revocation | Revoke key, delegation and service separately during active use. Delay/drop/reorder updates, partition an edge, restart it, roll clocks back and replay stale cache state. Define deny-new, drain and terminate-active semantics separately before running. | Time from authoritative issuance to authenticated receipt, denial and final byte; stale acceptance window, collateral termination, resurrection and recovery. A bound needs a declared delivery/partition assumption; expiry alone is not immediate revocation. |
| Failure behavior | Independently fail authority/resolver, source/destination edge, connector, backend and underlay link; then restore. Verify both existing and new flows, no silent authority expansion and no stale resurrection. | Recovery/blackout time, failed requests, duplicate delivery, resource leaks, policy decisions and availability during safe degradation. Availability gains count only with equivalent security semantics. |
| Routing distinction | In a separately approved multi-host topology, record underlay routes and packet captures while changing IP reachability. For SCION record discovered/selected AS paths too. | Overlay endpoint failover and underlay path recovery reported separately. An NBSR inter-domain routing claim would require an implemented routing/forwarding protocol and independent multi-hop evidence; this experiment cannot create that claim. |

Use paired runs on identical hardware, OS, topology, RTT/loss/MTU, payloads,
concurrency, offered load, crypto strength and logging. Include warm/cold caches,
valid/invalid traffic mixtures and repeated runs with confidence intervals.
Predeclare acceptance thresholds and exclude startup from steady-state only by
an explicit common rule. Keep failed attempts and report security failures
before throughput. Start with bounded 16-client trials under `AGENTS.md` limits;
WAN, partitions and larger capacity runs require their own approved environment.

Retain commit/dirty patch and binary hashes, configs/policies, commands, seeds,
clock assumptions, raw observations, backend delivery logs and cleanup counts.
Use test credentials and redact secrets. A performance benefit requires a
repeatable improvement over an equivalent-policy baseline without weaker
security or hidden adapter cost. Current loopback connection counts or aggregate
throughput do not demonstrate Internet scale, multi-hop routing, production
readiness, or superiority over these architectures.

## Documentation review validation

This change updates documentation only. Source/test references and Markdown
links are checked locally, and the diff is checked for whitespace and scope.
Runtime tests and the comparative experiments above are not run by this change.
No frozen wire allocation, implementation status promotion, email or deployment
is authorized by this document.
