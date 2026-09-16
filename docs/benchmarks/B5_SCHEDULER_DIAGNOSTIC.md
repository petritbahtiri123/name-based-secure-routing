# B5 external scheduler diagnostic

Status: collection/analysis COMPLETE; memory/p99 root cause remains UNRESOLVED.
No production optimization, capacity increase or gate change was made.

## Method and observer limits

Three counterbalanced off/on pairs, each 300 seconds, on exact release build
`f8925b25`, Linux Docker/WSL loopback. Fixed historical rate
`64804600000000 / 7500349701` ops/s, 16 KiB, eight streams, depth one, three-second
warmup, 30-second progress. Both peers share one selected guest CPU. This is
not verified host physical-core isolation or current-SHA ceiling calibration.
Ownership sampling remains enabled in both arms; no allocator library is used.

The external Python observer reads owned benchmark process/thread `schedstat`
and cgroup CPU counters every second. It matches exact executable paths and
verifies process/thread start identities around reads. It does not write to
peers, change affinity or add threads inside them. The observer runs separately
with its recorded default guest affinity; its cost is part of the on arm.

| Metric | Off median | On median | Delta |
|---|---:|---:|---:|
| Gbit/s | 2.233926 | 2.237221 | +0.1475% |
| Median window p99, ms | 1.280960 | 1.272156 | -0.6873% |
| Approximate summed peer CPU cores | 0.764018 | 0.754665 | -1.2242% |

Goodput CV: 0.175% off / 0.081% on. Window-p99 CV: 2.417% / 2.670%; no extension
to five was required. Paired p99 deltas: +2.803%, **-6.193%**, -0.259%.
The absolute change above 5% is retained even though latency improved.
Observer qualification remains **NOT_QUALIFIED_FOR_CAUSAL_PERFORMANCE_ATTRIBUTION**.
Small cohort medians cannot establish negligible observer effect.

All six completed traffic with zero errors/timeouts, no sustained sampled
ownership growth and all eleven final counters zero at both peers. Three runs
retained private-memory growth failures: on r2 source, off r3 destination,
on r3 source/destination. Other three had no diagnostic gate violations.
Independent five-minute runs do not form a sustained 30-minute soak.

## Measured scheduler accounting

Each instrumented role had 300 in-phase samples, stable thread identities,
nondecreasing window-endpoint counters and sample gaps below two seconds. Each
30-second traffic window had at least 25 scheduler samples. All failures and
the full window-level data are retained.

| Repeat | Source runtime cores | Destination runtime cores | Source runqueue thread-s/s | Destination runqueue thread-s/s |
|---|---:|---:|---:|---:|
| 1 | 0.390695 | 0.365428 | 0.208062 | 0.202074 |
| 2 | 0.385881 | 0.366973 | 0.209602 | 0.203204 |
| 3 | 0.386935 | 0.367794 | 0.210200 | 0.203515 |

Summed peer runtime was approximately 0.753--0.756 guest cores. The main source
and destination threads account for almost all runqueue wait, approximately
60--61 seconds each over the observed 299-second intervals. These are measured
guest scheduler counters, not an inferred hardware ceiling. Cgroup deltas for
`nr_throttled` and `throttled_usec` were zero in all three runs.

The [Linux kernel scheduler statistics documentation](https://docs.kernel.org/scheduler/sched-stats.html)
defines these counters as CPU time, runnable queue wait and timeslices. Queue
wait is not network/IO blocking; summing waiting thread-seconds does not produce
CPU utilization. The remaining wall time cannot simply be assigned to network
wait. Guest counters do not rule out Windows/WSL host scheduling effects.

**Supported hypothesis for a controlled next experiment:** sharing one guest
CPU creates meaningful runnable waiting between peers. The data do not prove
that this causes the observed p99 drift, and no p99 gate failed in this cohort.
Do not translate this into a production scheduler defect or a core ceiling.

## Next bounded experiment

Compare shared versus separate explicitly selected guest CPUs for source and
destination, keeping rate, traffic semantics, runtime workers and all gates
unchanged. Declare the increased total CPU allocation; do not report it as a
single-core efficiency improvement. Validate each peer's exact affinity and
preserve source/binary provenance. Guest CPUs are not verified physical cores.
Use at least three counterbalanced pairs, extending to five for CV above 5%.

First use uninstrumented performance arms. A reduction in latency would support
a placement effect, not automatically a software fix. A separately qualified
observer is required to attribute the queue reduction. If the effect is noise
or remains unattributable, record the platform diagnostic limit and move to
native Linux/host profiling rather than adding increasingly invasive hooks.
This experiment is specified, not implemented or measured by this package.

## Evidence and verification

Canonical: `evidence/performance/v2/b5-scheduler-2c6b3aaa`.
Raw: `C:/NBSR-build/b5-scheduler-2c6b3aaa`; exact release-build index is also bound.
Literal RED: two parser/validation failures. GREEN/final: three focused tests,
including identity reuse rejection; non-root live preflight passed discovery,
sampling and bounded shutdown. Relevant existing Python tests: 75 PASS.
Observer/analyzer Ruff checks passed. No production Rust/Go changes required
new compilation or security acceptance; existing security claims are unchanged.

Sampler source, executed runner, all raw traces, analysis, commands and checksum
indexes are preserved. Reproduce in a fresh directory and keep unavailable
samples/failures visible. The analyzer rejects inadequate steady coverage.
