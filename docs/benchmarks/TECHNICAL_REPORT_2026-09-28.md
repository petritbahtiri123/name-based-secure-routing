# NBSR technical evidence report — 28 September 2026

## Decision and scope

**READY FOR TECHNICAL OUTREACH; MORE CLOSURE REQUIRED for production or pilot
readiness.** This report consolidates accepted local evidence through package
commit `21e8e3f85ee2f3ea4f315a5b9106658bc5f67d41`. It closes the reporting step,
not every engineering acceptance gate. No new benchmark or security test was
run for this report. No message has been sent to a prospective partner.

The newest measured engineering source is `fd138398`; older measurements retain
their own source, binaries, shape and environment. MEASURED means an observation
in that scope; DERIVED means arithmetic on observations; HISTORICAL means an
earlier source/workload; DIAGNOSTIC cannot establish stable capacity;
INCONCLUSIVE means insufficient attribution; NOT_PROVEN means no accepted proof.
HISTORICAL and MEASURED can both apply to the same result.

## Architecture and security boundary

The approved PoC route is Client → ISP-A non-frozen adapter → unchanged NBSR
secure path → ISP-B adapter → Origin Connector → isolated private origin.
The demonstrated Docker topology uses an opaque TCP adapter at ISP-A and UDP
adapter at ISP-B, three internal networks and no published origin port.
It uses fixture authority/shared bootstrap material, not independent operator
trust isolation. Authentication, authorization, binding, replay protection,
send completion and fail-closed rules were not relaxed for performance.

## Scoreboard

Each evidence link supplies exact workload, source/binary binding and raw index.
Do not combine rows into a claim about one final binary.

| Result | Observation and classification | Evidence |
| --- | --- | --- |
| Fresh one-core reference | MEASURED: 16 KiB, eight streams, depth one: strict-stable 1.031167 Gbit/s, 3933.590 ops/s, 0.956199 effective cores. p50/p95/p99 1.9296/3.2414/3.9816 ms. DERIVED CPU 239968.103 ns/op. Three repeats, CV 4.294%. | [fd138398 reference](../../evidence/performance/v2/soak-reference-fd138398/summary.md) |
| Fresh degraded boundary | MEASURED: same shape, depth two, 1.159379 Gbit/s, p99 5.9108 ms, CV 0.924%. Individual peak 1.164803 is DIAGNOSTIC. No saturated boundary measured in this short ladder. | [Classification](../../evidence/performance/v2/soak-reference-fd138398/classification.json) |
| Matched Direct control | MEASURED: one-core depth one 1.076719 Gbit/s, p99 3.3386 ms; depth two degraded 1.111379. This is shape-specific, not a universal transport overhead percentage. | [Reference](../../evidence/performance/v2/soak-reference-fd138398/summary.md) |
| Four-core forwarding | HISTORICAL MEASURED at 53468db4: strict-stable 2.306118 Gbit/s, five repeats, CV 0.908%, p99 1.085 ms. Four groups, one stream/group, 16 KiB. | [Multicore](../../evidence/performance/v2/physical-core-multicore-53468db4/REPORT.md) |
| Four-core saturation | HISTORICAL: depths 2/4/8/16 are SATURATED at 2.643019/2.976737/3.218905/3.361954 Gbit/s. Individual 3.666140 peak is DIAGNOSTIC. Intermediate degraded boundary unresolved. | [Multicore](../../evidence/performance/v2/physical-core-multicore-53468db4/REPORT.md) |
| Scaling qualification | Two-core NBSR baseline CV 6.126%; four-core Direct baseline CV 7.02%: UNRESOLVED. Linear scaling and a Direct-relative speedup are NOT_PROVEN. | [Multicore](../../evidence/performance/v2/physical-core-multicore-53468db4/REPORT.md) |
| Finite admission | HISTORICAL MEASURED at 1917b195: 125 offered/s → 119.920 actual/s STABLE; 150 → 138.887 DEGRADED; 200 → 176.182 SATURATED. 512 clients/repeat; 27 repeats, 13,824 admissions, zero errors/timeouts. | [Admission](../../evidence/performance/v2/admission-fresh-1917b195/REPORT.md) |
| Admission latency and limits | At 125 offered/s: handshake p99 10.110 ms, admission p99 28.327 ms. Low-rate 25/50 cells remain degraded by forwarding dispersion. Neither finite admission nor burst behavior proves indefinite sustainable admissions/s. | [Admission](../../evidence/performance/v2/admission-fresh-1917b195/REPORT.md) |
| Native concurrent scale | HISTORICAL MEASURED: 2048 live connections, 3/3 functional trials, 6144 total authenticated round trips; both final eleven-counter reports zero. Observer neutrality NOT_PROVEN. | [2048](../../evidence/performance/v2/native-live2048-memory2-8e0b28a2/summary.md) |
| Larger failed scale | Three 4096 attempts failed before common active hold, zero completed round trips. Destination UDP drops observed; sole cause and production ceiling INCONCLUSIVE. | [4096 failures](../../evidence/performance/v2/native-live4096-530ecac9/summary.md) |
| Memory | At native 2048: source/destination active private-resident medians 806.908203/546.267578 MiB. Resource axes co-vary; isolated bytes/connection/session/channel/stream NOT_PROVEN. Retained RSS is not a leak diagnosis. | [2048](../../evidence/performance/v2/native-live2048-memory2-8e0b28a2/summary.md) |
| Go lifecycle | MEASURED at fd138398: 18/18 cells, 1680 round trips, including 150 same-process cycles. Benchmark-owned source workers joined; destination eight counters zero. Full source QUIC ownership remains INCONCLUSIVE. | [Go scope](../../evidence/performance/v2/go-lifecycle-scope-fd138398/summary.md) |
| Sustained observations | MEASURED: 3 × 3600 s at 75% of fresh one-core reference; 31,139,327 operations, median 0.754762 Gbit/s, CV 0.399%, zero errors/timeouts. Final eleven counters zero at both ends. PARTIAL_B5. | [Soak](../../evidence/performance/v2/soak75-fd138398/summary.md) |
| Packet accounting | HISTORICAL MEASURED: incremental setup IP-byte medians 38,590 (1 KiB/64 streams) and 15,596 (16 KiB/eight streams). Established deltas are signed/variable; no constant NBSR tax established. Physical Ethernet is NOT_MEASURED; L2 estimates are DERIVED. | [Phase accounting](../../evidence/performance/v2/native-phases-6b1095c5/summary.md) |

The soak's achieved/offered ratios were 97.430%, 97.593%, 98.171%. Early-to-late
window-median goodput changes were -0.800%, +0.093%, -0.193%; sampled p99 changes
+1.347%, -7.601%, +2.622%. Existing live drift/private-growth guards passed.
Optional continuous ownership qualification failed during its first enabled
trial; causality is INCONCLUSIVE. Final zeros are not continuous ownership
proof. Three separate hours are not one uninterrupted three-hour test.

## Security and reliability evidence

| Boundary | Accepted observation | Limitation |
| --- | --- | --- |
| Replay, tampering, service/name, port/transport, PoP, expiry, revocation, generation, downgrade, source authorization, malformed input, forged identity, failure/recovery | [Adversarial campaign](../../evidence/security/adversarial-refresh-bf53b8d4/summary.md): 13 PASS, zero FAIL, one direct-origin INCONCLUSIVE at bf53b8d4 | Scenario-bound regressions, not independent certification or a final-SHA full audit |
| Private-origin reachability | [Docker isolation](../../evidence/security/isp-isolation-f831c9bb/REPORT.md): three topology lifecycles, twelve denied probes; authorized path returns exact body; teardown leaves zero owned containers/networks/volumes | Separate f831c9bb evidence; does not relabel the other campaign's INCONCLUSIVE result |
| Federation admission preflight | Same isolation package: 37 Python tests and fixture authorization/drain, zero active allocations | Not live runtime federation; shared bootstrap, independent secret isolation NOT_PROVEN |
| Frozen federation authority | [Boundary register](FEDERATION_OUTREACH_BOUNDARY_2026-09-26.md): current manifest differs from pinned trust digest | BLOCKED_ARCHITECTURAL for this campaign; do not replace the trust anchor to obtain PASS |
| Cancellation and lifecycle | Go worker cancellation/join fix; earlier owned Windows Job Object cleanup and completion ordering fixes | Bounded evidence, not universal no-race/no-leak or complete failure recovery |

## Engineering changes and attribution

Harness corrections removed timed SHA framing interference, fanout/listener
artifacts, synchronous polling, unread-stderr backpressure and source scheduling
pressure. These are not removal of mandatory production cryptographic checks.
Recent changes hardened benchmark worker cleanup, completion ordering, process
ownership and timestamp/resource collection; no new production speedup is
claimed. See the [engineering history](ENGINEERING_CHECKPOINT_2026-09-25.md).

The [Windows receive-buffer optimization](../../evidence/performance/v2/b4b-task4m-217df28e/REPORT.md)
is a production implementation change justified by measured insufficient-buffer
drops, applied symmetrically to Direct/NBSR. Its scoped improvements coexist
with worse p50 and dispersed rate results; it does not establish a general
capacity increase. No frozen wire/security semantics were changed.

## Methodology, environment and reproduction

Release builds; matched Direct/NBSR workload semantics; minimum three valid
repeats, five when CV exceeds 5%; unfavorable valid results retained. Classifiers
and observer thresholds remain those in each package. Timed performance and
packet-accounting captures are separate. The fresh reference uses 20-second
cells after three seconds warmup; multicore uses 30-second cells. Physical-core
selection excludes SMT siblings; both endpoint roles share the selected pool.
The recorded local host topology is four physical/eight logical processors.
Windows loopback and Docker Desktop Linux namespaces are local laptop evidence.
Per-stage environment files bind topology, placement, binaries and tools; no
dedicated server, NIC path, WAN, NUMA or thermal/power qualification is implied.

The measured multicore CPU constraint applies to the tested process pool; it
does not prove an optimal machine-wide ceiling or a production hotspot. An
idle-CPU plateau cannot be called a hardware ceiling. Allocation/op, syscall
and context-switch costs remain unestablished for these headline results.

Use each linked report's exact commands at its named source and fresh output
paths. [The evidence index](TECHNICAL_REPORT_2026-09-28.evidence.json) pins the
canonical checksum indexes and their raw-reference files. Raw data under
`C:/NBSR-build` is not included automatically in a Git clone. Transfer it using
those references and verify hashes before analysis; no off-host backup is claimed.
The [external validation definition](EXTERNAL_LINUX_SERVER_VALIDATION.md)
specifies hardware, builds, telemetry and gates, including remaining portable
matrix work. Actual external results are EXTERNAL_HARDWARE_REQUIRED.

## Claim boundary and remaining work

Safe: local, source-bound throughput and finite admission results; successful
2048-connection trials; three one-hour observations with verified final cleanup;
scoped fail-closed and isolated-origin tests. These justify independent technical
evaluation and pilot scoping.

Unsupported: diagnostic peaks as stable throughput; laptop/loopback as ISP/WAN
capacity; finite/burst admissions as indefinite sustainability; linear scaling;
universal no-leak/security certification; live independent federation; measured
physical-wire cost; fully qualified B5 or complete production readiness.

COMPLETE: this evidence consolidation and previously scoped accepted stages.
PARTIAL/INCONCLUSIVE: continuous ownership observer, full Go internal ownership,
isolated marginal memory costs and handshake attribution. PLATFORM_DIAGNOSTIC_LIMIT:
repeated WPR export/observer failures; [no new manual WPR command is pending](ADMIN_REQUIRED_FINAL_VALIDATION.md).
BLOCKED_DESTRUCTIVE: none required. OPTIONAL_LOW_VALUE: unchanged profiler reruns
without a new defensible method. The outreach brief/message is the next reporting
step; this document does not send or publish it.
