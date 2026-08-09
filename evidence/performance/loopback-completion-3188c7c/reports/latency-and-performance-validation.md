# NBSR loopback baseline completion report

## 1. Summary

This additive, unoptimized loopback tranche closes the capacity-reproduction and typed-640 evidence blockers. It does not close memory stability. The scientifically justified classification remains `PARTIAL_BASELINE`. Prior evidence under `complete-loopback-db55d18-partial` was not modified.

## 2-8. Classification, provenance, and validation state

- Final classification: `PARTIAL_BASELINE`.
- Branch: `codex/nbsr-v3-wp0-wp1`.
- Initial HEAD: `e4492c4fc4b5124e71e218c56efd16114c147238`.
- Benchmark implementation/evidence HEADs: `3188c7c`, `6f75a10`, and `b59e7fc`; report/evidence assembly continued additively afterward.
- Harness commits are listed in the final handoff and Git history.
- Changed files are limited to benchmark harness/tests, additive evidence, and this report. Frozen protocol/security semantics were not changed.
- Focused performance validation reached 76 passing tests. Full repository validation is recorded in the final handoff after evidence commit.

## 9-12. Capacity

The historical candidates Direct 5,500/s, Rust 2,500/s, and Go 500/s are superseded and are not accepted capacities.

| Path | Fresh passing point | Fresh failing/inconsistent point | Conservative bracket | Three confirmations (p99 ns) | Accepted capacity |
|---|---:|---:|---|---|---:|
| Direct QUIC | 4,750/s | 4,875/s | [4,750, 4,875) | 261,221; 226,763; 213,711 | 4,750/s |
| Rust to Rust | 1,687.5/s | 1,750/s | [1,687.5, 1,750) | 729,944; 487,678; 488,726 | 1,687.5/s |
| Go to Rust | 400/s | 450/s inconsistent across prior/fresh evidence | 400 accepted conservatively; 450 not reproducible | 784,700; 755,100; 696,401 | 400/s |

Every confirmation used 60 seconds warm-up and 600 seconds steady state. All three confirmations passed independently for each accepted point. A failing run was never averaged into acceptance.

## 13-14. Formal load matrix

All values are nanoseconds. Every cell had 100% success. `N/A` means the statistic was not emitted as valid.

| Path | Load | Rate/s | p50 | p95 | p99 | p99.9 | Peak backlog |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct | 25% | 1,187.5 | 123,953 | 160,247 | 256,300 | 843,316 | 8 |
| Direct | 50% | 2,375 | 123,674 | 153,405 | 220,121 | 2,154,763 | 49 |
| Direct | 75% | 3,562.5 | 124,102 | 153,463 | 225,993 | 16,033,405 | 386 |
| Direct | 90% | 4,275 | 124,465 | 151,058 | 235,570 | 1,600,456 | 635 |
| Rust | 25% | 421.875 | 307,844 | 394,478 | 584,489 | 841,963 | 7 |
| Rust | 50% | 843.75 | 306,663 | 400,574 | 579,467 | 8,458,811 | 80 |
| Rust | 75% | 1,265.625 | 306,091 | 370,531 | 544,538 | 8,315,615 | 76 |
| Rust | 90% | 1,518.75 | 307,428 | 376,870 | 711,967 | 41,694,885 | 128 |
| Go | 25% | 100 | 417,200 | 637,700 | 843,500 | N/A | 2 |
| Go | 50% | 200 | 404,100 | 580,200 | 836,700 | 2,355,200 | 22 |
| Go | 75% | 300 | 401,567 | 506,000 | 744,167 | 2,129,034 | 5 |
| Go | 90% | 360 | 400,445 | 602,978 | 905,534 | 16,364,167 | 51 |

The 90% p99 ceilings were Direct 341,680 ns, Rust 808,000 ns, and Go 933,080 ns. All three formal 90% cells passed.

## 15-16. Queue/backlog and open-loop integrity

The former Rust 90% value of 1,231.601 ms is superseded as a formal result but retained historically. At the corrected Rust 90% rate, p99 was 711,967 ns and peak backlog was 128. This supports a load-boundary/scheduling explanation but does not prove a single cause.

Offered arrivals remain scheduled-time based. Start lateness and backlog are explicit, every completed formal request is represented, and overload cannot become healthy merely because work starts late. The long Go memory attempt demonstrated a remaining evidence defect: it drained delayed sequential work until the 3,600-second safety timeout, then the harness lost buffered raw/runtime series and left the child alive. That run is non-authoritative and makes the overall open-loop conclusion `PASS` for completed capacity/formal cells but `INCONCLUSIVE` for long-lived Go evidence retention.

## 17-22. Memory stability

The frozen method excludes the first 60 seconds, uses one-second samples, fits full/second-half/final-quarter least-squares slopes with 95% bounds and R-squared, compares working set and private bytes, and correlates deltas with processed requests. Allocator steps and GC sawtooth are not automatically leaks.

| Path/load | Working set start to end | Overall slope | Request/load observation | Result |
|---|---|---:|---|---|
| Direct 50% | 9.24 to 9.33 MB | 30.8 B/s | 4,272,625 post-warm-up requests; bounded late window | evidence bounded |
| Direct 75% | 8.33 to 8.43 MB | 26.1 B/s | p99 2.423 s; peak backlog 16,588, so load was not stable | `INCONCLUSIVE` |
| Rust 50% | 11.15 to 63.77 MB | 34,081 B/s | final quarter plateaued; allocator-retention explanation remains possible | `INCONCLUSIVE` |
| Rust 75% | 12.56 to 118.31 MB | 61,136 B/s | request-correlated growth continued, but final-quarter fit was noisy | `INCONCLUSIVE` |
| Go 50% | not retained | not valid | timed out at 3,600 s; child cleanup/evidence retention failed | `INCONCLUSIVE` |
| Go 75% | not run after unchanged 50% evidence-loss failure | not valid | repeating unchanged would not improve evidence | `INCONCLUSIVE` |

Direct process memory itself was bounded, but the required stable-load pair was not established. Rust process memory showed approximately 34.4 to 46.5 bytes/request growth across the two loads, yet the frozen repeated sustained-growth rule did not pass at both loads. No Rust allocator-specific instrumentation contaminated these primary runs.

The completed Go formal 90% cell ended with HeapAlloc 62,298,824; HeapSys 83,558,400; HeapIdle 19,841,024; HeapInuse 63,717,376; HeapReleased 4,259,840; NumGC 516; TotalAlloc 18,628,123,512; mallocs 2,139,902,529; frees 2,138,570,207; total GC pause 29,588,100 ns; maximum recent pause 2,008,900 ns. These ten-minute endpoint values cannot substitute for the missing 30-minute runtime series.

## 23-25. Unsupported 640-stream evidence

Rust produced 640/640 typed terminal records with `AuditUnavailable`. Go produced 640/640 typed terminal records with `no-recent-network-activity` timeout. Both were post-admission, expected fail-closed, explicitly marked unsupported, and distinct from protocol-correctness failures.

The supported concurrent-stream result remains 320. The 640 point is beyond the supported benchmark boundary even though the configured transport stream limit is 1,280. Evidence integrity passes without requiring 640 streams to succeed.

## 26. Engineering-budget decision table

| Area | Evidence decision | Engineering decision |
|---|---|---|
| Capacity/formal load | Reproducible and p99-gated for all paths | Accept new conservative capacities for loopback baseline work |
| Typed 640 boundary | Complete fail-closed raw evidence | Retain supported boundary at 320; do not raise limits |
| Direct long-lived memory | Bounded memory but unstable 75% load | Keep unresolved; do not optimize |
| Rust long-lived memory | Mixed plateau and continued noisy growth | Keep unresolved; investigate only in a separately approved tranche |
| Go long-lived memory | Harness timeout/evidence loss | Fix evidence retention before another primary run |
| Demo preparation | Completion criteria not met | Human review may proceed; demo preparation should not |

## 27-30. Evidence, counts, integrity, and harness defects

- Additive evidence: `evidence/performance/loopback-completion-3188c7c`.
- Full external raw root: `C:\codex-evidence\nbsr-loopback-completion-3188c7c`.
- Prior immutable evidence: `evidence/performance/complete-loopback-db55d18-partial` and its external root.
- Repository completion raw records: 1,304 (24 decisions plus 1,280 typed unsupported attempts).
- External attempted/completed request records represented by retained compressed raw files: 64,616,099, including the failed duplicate Rust 75% harness attempt. The failed Go memory attempt retained zero request records and is explicitly a blocker.
- The completion verifier passes and binds the prior checksum file. The external root remains the authority for large compressed request files; repository evidence retains summaries, process time series, logs, and the typed completion raw set.
- Harness defects fixed: single-run capacity acceptance, path-mismatched formal percentages, open-loop lag/backlog visibility, memory sample disappearance checks, post-warm-up trend analysis, typed unsupported failures, request/activity correlation, fractional-rate steady-window counting, and complete additive manifest inventory.
- Harness defect discovered but not fixed in this tranche: timeout cleanup and durable incremental raw/runtime/resource retention for long-lived Go runs.

## 31-35. Defects, opportunities, risks, and readiness

No frozen protocol or security correctness defect was found.

Candidate optimization opportunities — NOT IMPLEMENTED: investigate Rust allocation/retention behavior; Go long-run throughput/GC behavior; Direct long-run scheduler stalls; and queue/backlog behavior near path boundaries. These are observations only. No queue, scheduler, allocator, GC, QUIC, serialization, batching, caching, admission, or concurrency-limit optimization was implemented.

Risks and limitations: Windows loopback only; unoptimized implementations; one host; Direct 75% long-run instability; Rust memory ambiguity; missing Go primary memory series; Go timeout cleanup/evidence-loss defect; p99.9 tail spikes; no cloud, WAN, HTTP/3, or demo claims.

`COMPLETE_LOOPBACK_BASELINE` is **not** scientifically justified because required memory stability remains inconclusive for all three paths and long-lived Go evidence integrity failed. The benchmark is ready for human review as a `PARTIAL_BASELINE`, but it is not ready to serve as the final basis for demo preparation.
