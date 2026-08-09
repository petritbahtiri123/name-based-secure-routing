# NBSR unoptimized Windows loopback performance validation

## Classification

`PARTIAL_BASELINE`

This tranche substantially extends the approved partial baseline, but it does **not** satisfy the conditions for `COMPLETE_LOOPBACK_BASELINE`. Capacity candidates were not reproducible at their 90% load cells, and the 640-concurrent-stream boundary did not produce a typed raw failure record. The evidence must not be represented as a complete baseline.

The measured scope is Windows loopback only. It does not establish production, Internet-scale, ISP-scale, cloud-region, WAN, same-region, or cross-region readiness. HTTP/3 remains `NOT SUPPORTED BY CURRENT TEST SURFACE`.

## Provenance and methodology

- Benchmark implementation SHA: `db55d18cb2b5b570430b14b74d6ece73bbe448a4`.
- Previous approved 300,000-sample evidence remains unchanged under `evidence/performance/`.
- New formal headline evidence: 40 independent cells and 2,530,000 successful samples.
- Full external evidence audit: 209 files and 32,672,967 decompressed raw samples; SHA-256, JSON, sample IDs, counts, duration non-negativity, and summaries reconciled.
- Formal warm cells: five runs and 100,000 successes per cell.
- Formal cold cells: five runs and 2,000 genuinely fresh sessions per cell.
- Capacity/load cells: 60-second warm-up plus 600-second steady state with absolute schedules and backlog-visible latency.
- Confidence intervals: deterministic 10,000-resample independent-run bootstrap of the mean per-run percentile, seed 75.
- Timer calibration for open-loop load: scoped Windows 1 ms timer-resolution request; Rust uses `Instant`, Go uses QPC for deadlines and observations.
- All figures are unoptimized implementation measurements.

## Formal headline results

Values are independent-run bootstrap estimates in milliseconds; brackets are 95% confidence intervals. p99.9 is preserved per run in `summaries/analysis.json` and was emitted only for 100,000-sample cells.

| Path / lifecycle | p50 | p95 | p99 |
|---|---:|---:|---:|
| Direct warm request | 0.0984 [0.0968, 0.1007] | 0.1291 [0.1252, 0.1331] | 0.1703 [0.1588, 0.1817] |
| Rust NBSR warm-existing request | 0.1057 [0.1045, 0.1073] | 0.1352 [0.1297, 0.1405] | 0.1833 [0.1648, 0.2011] |
| Go NBSR warm-existing request | 0.1252 [0.1201, 0.1303] | 0.1566 [0.1483, 0.1663] | 0.2141 [0.1951, 0.2308] |
| Rust NBSR warm-new total scenario | 1.9803 [1.9781, 1.9821] | 2.5668 [2.5057, 2.6221] | 12.0024 [11.9860, 12.0165] |
| Go NBSR warm-new total scenario | 1.8368 [1.8314, 1.8432] | 2.4496 [2.3707, 2.5368] | 10.5240 [10.5165, 10.5349] |
| Direct cold total scenario | 4.1936 [3.8620, 4.4319] | 5.0918 [5.0637, 5.1132] | 5.3553 [5.3106, 5.4090] |
| Rust NBSR cold total scenario | 9.3383 [9.0715, 9.6051] | 13.3874 [13.3350, 13.4397] | 13.8488 [13.7992, 13.9272] |
| Go NBSR cold total scenario | 103.4260 [102.7554, 104.0552] | 114.0189 [113.7995, 114.2382] | 116.7062 [115.9856, 117.4327] |

## Matched incremental overhead

| Matched comparison | p50 | p95 | p99 |
|---|---:|---:|---:|
| Rust warm-existing request | +0.0073 [0.0065, 0.0082] | +0.0061 [0.0030, 0.0093] | +0.0131 [0.0057, 0.0217] |
| Go warm-existing request | +0.0268 [0.0204, 0.0332] | +0.0275 [0.0214, 0.0336] | +0.0438 [0.0273, 0.0603] |
| Rust warm-new total | +1.8816 [1.8797, 1.8834] | +2.4373 [2.3798, 2.4929] | +11.8315 [11.8218, 11.8413] |
| Go warm-new total | +1.7381 [1.7335, 1.7448] | +2.3201 [2.2409, 2.4107] | +10.3532 [10.3374, 10.3701] |
| Rust cold total | +5.1447 [4.8603, 5.4023] | +8.2956 [8.2277, 8.3634] | +8.4936 [8.4192, 8.5853] |
| Go cold total | +99.2324 [98.7117, 99.8518] | +108.9271 [108.7167, 109.1374] | +111.3510 [110.5999, 112.1024] |

The cold loopback “one RTT” budget is `INCONCLUSIVE`: loopback does not provide a scientifically meaningful contemporaneous network RTT budget above timer/scheduler noise. Raw matched overhead is reported instead. Negative warm-existing overhead was not interpreted as acceleration.

## Reuse and scaling

- One reusable authenticated Transport Session successfully admitted 20 and 32 independently authorized Service Channels for both Rust and Go sources. Authorization/channel state remained service-specific.
- Sequential 20-service scaling passed at 1, 8, and 64 streams/service (20, 160, and 1,280 requests). At 64 streams/service, request p99 was 0.208 ms Rust and 0.236 ms Go.
- Concurrent scaling passed at 1, 8, and 64 streams for one service and at 20, 160, and 320 streams across 20 services for both sources.
- At 640 concurrent streams across 20 services, Rust failed closed with `AuditUnavailable`; Go timed out for lack of network progress. Because these were not retained as typed raw request failures, this boundary is invalid for formal completion.
- Concurrent Transport Sessions passed at 1, 4, 8, 20, and 32 for all paths. At 32 sessions, observed exploratory establishment rates were 136.8/s direct, 144.7/s Rust, and 102.1/s Go.
- Service Channel scaling passed at 1, 20, and the frozen 32-channel/session limit for both NBSR sources.

## Payload scaling

Secondary exploratory request-latency p50 values (direct / Rust / Go) were:

- 1 byte, 1,000 samples/path: 0.097 / 0.101 / 0.122 ms.
- 1 KiB, 1,000 samples/path: 0.100 / 0.154 / 0.147 ms.
- 16 KiB, 1,000 samples/path: 0.284 / 0.286 / 0.314 ms.
- 256 KiB, 100 samples/path: 2.361 / 2.353 / 3.812 ms.
- 1 MiB, 100 samples/path: 9.996 / 8.720 / 14.829 ms.

The 256 KiB and 1 MiB cells are explicitly secondary exploratory cells and are not equivalent to formal headline cells.

## Capacity and formal load levels

Highest formally tested passing candidates and next failing points:

| Path | Highest passing | Next failing | Decision |
|---|---:|---:|---|
| Direct QUIC | 5,500/s | 6,000/s | `INCONCLUSIVE` reproducibility |
| Rust NBSR | 2,500/s | 3,000/s | `INCONCLUSIVE` reproducibility |
| Go NBSR | 500/s | 750/s | `INCONCLUSIVE` reproducibility |

Every capacity/load cell had 100% request success, zero unexpected protocol rejection, and low destination CPU. Nevertheless, each 90% cell violated the 2× idle-p99 gate: direct p99 22.693 ms, Rust 1,231.601 ms, and Go 1.193 ms. Therefore the candidate capacities are not reproducible enough to be accepted as final sustainable capacities.

Formal 25/50/75/90% p99 results in milliseconds:

| Path | 25% | 50% | 75% | 90% |
|---|---:|---:|---:|---:|
| Direct | 0.250 | 0.198 | 0.180 | 22.693 |
| Rust NBSR | 0.511 | 0.464 | 0.663 | 1,231.601 |
| Go NBSR | 0.748 | 0.665 | 0.729 | 1.193 |

Because the paths use independently determined offered rates, unmatched achieved throughput is not presented as an equivalent matched-throughput comparison. The 90%-of-capacity instability makes the throughput engineering target `INCONCLUSIVE`.

## CPU, memory, and runtime observations

- Destination assigned-capacity CPU remained well below 85% in all formal cells; candidate-cell mean/max examples were 4.58%/7.31% direct at 5,500/s, 4.85%/7.54% Rust at 2,500/s, and 1.08%/2.12% Go-path destination at 500/s.
- Direct destination memory consistently plateaued; at 5,500/s its second-half slope was 2.4 B/s with a 95% CI spanning zero.
- Rust/Go-path destination memory grew in allocator-sized steps before often plateauing in the final quarter. Some load cells showed significant late-window growth. The aggregate conclusion is `INCONCLUSIVE`, not “memory leak” and not PASS.
- Go at 500/s recorded 25.81 GB allocated, 2.965 billion mallocs, 2.962 billion frees, 516 GC cycles, 24.56 ms total GC pause, and 1.024 ms maximum recent GC pause. These are implementation/path observations, not language-wide Go-versus-Rust claims.
- Rust allocation instrumentation was not injected into authoritative latency. Windows process memory is authoritative; allocation-specific work remains absent rather than contaminating latency.

## Decision table

| Criterion | Decision |
|---|---|
| Warm-existing p50 budget | PASS |
| Warm-existing p95 budget | PASS |
| Warm-existing p99 budget | PASS |
| Warm-new p50 budget | PASS |
| Warm-new p95 budget | PASS |
| Warm-new p99 budget | PASS |
| Cold overhead budget interpretation | INCONCLUSIVE |
| Throughput target | INCONCLUSIVE |
| Failure rate under valid supported load | PASS |
| Memory stability | INCONCLUSIVE |
| 20-service Transport Session reuse | PASS |
| Concurrent stream correctness through 320 | PASS |
| Capacity methodology validity/reproducibility | FAIL |
| Five-run reproducibility | PASS |
| Evidence integrity/checksums | PASS |

## Harness defects discovered and fixed

- Lifecycle server completion acknowledgement race.
- Deterministic authority writer idempotence.
- Stale readiness/result/ack files.
- Concurrent stream visibility/deadlock before STREAM_OPEN exchange.
- Concurrent session accept-order assumptions.
- Shared endpoint closure during concurrent sessions.
- Windows 15.6 ms timer quantization; scoped timer resolution plus calibrated absolute waits.
- Go wall-clock/QPC clock-domain mismatch that produced negative latency; the invalid run is retained externally and excluded.
- Formal sample buffering ceiling; load output now streams to disk.

## Protocol/security defects

No frozen protocol/security correctness defect was discovered. Audit capacity failed closed at the 640-stream probe. Its benchmark failure representation is insufficient and is a harness completion issue.

## Candidate optimization opportunities — NOT IMPLEMENTED

- Investigate high-load tail bursts and backlog sensitivity.
- Investigate destination allocator/retention step behavior across long-lived streams.
- Investigate Go source allocation volume and GC activity.
- Add a typed, raw-evidence representation for audit-capacity rejection.
- Determine whether supported concurrency can be increased without weakening audit/security semantics.

No optimization was implemented in this tranche.

## Recommendation

The evidence is ready for human review as a substantial unoptimized loopback-validation tranche, but it is **not** ready to be promoted to `COMPLETE_LOOPBACK_BASELINE` or used as the final performance basis for demo preparation. A narrow follow-on should fix typed concurrency-limit evidence, repeat capacity discovery until 90% levels reproduce, and resolve memory stability to PASS/FAIL. Same-region and cross-region work require separate human approval and must not begin from this tranche.
