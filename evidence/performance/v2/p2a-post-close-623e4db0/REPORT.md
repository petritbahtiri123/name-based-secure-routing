# Physical-core 1 KiB ladder and ownership evidence repair

MEASURED: 48 valid retained 30-second records from clean 623e4db0, 3-second
warmup, 64 streams per group, shared verified physical-core pool without SMT.
All 321 raw forwarding artifacts verified. The repair's 53 artifacts also verify.

| Physical cores / groups | Path | Depth | Median Gbit/s | Timing ladder class |
|---|---|---|---|---|
| 1 / 1 | Direct | 1 | 0.866196 | STABLE |
| 1 / 1 | Direct | 2 | 0.877617 | SATURATED |
| 1 / 1 | Direct | 4 | 0.929625 | SATURATED |
| 1 / 1 | NBSR | 1 | 0.866384 | STABLE |
| 1 / 1 | NBSR | 2 | 0.934488 | DEGRADED |
| 1 / 1 | NBSR | 4 | 0.958148 | SATURATED |
| 2 / 2 | Direct | 1 | 0.792623 | UNRESOLVED |
| 2 / 2 | Direct | 2 | 0.9064 | SATURATED |
| 2 / 2 | Direct | 4 | 0.9558 | SATURATED |
| 2 / 2 | NBSR | 1 | 1.735490 | UNRESOLVED |
| 2 / 2 | NBSR | 2 | 1.7540 | DEGRADED |
| 2 / 2 | NBSR | 4 | 1.7040 | SATURATED |

Exact values, repeat variation and p99 are in the preserved summaries/records.
Classes use the existing per-shape lowest-depth latency reference and process
cleanup gate. They are NOT two-sided ownership qualification or a universal
production ceiling. The two-core baseline remains unresolved after five repeats.
Endpoint groups and total streams increase with cores; this is increasing total
concurrency, not fixed-concurrency strong scaling. Group p99 aggregation is a
maximum of group quantiles, not a reconstructed global latency distribution.

One-core NBSR depth one: 52,879.882 ops/s, sampled CPU estimate 18,348.613 ns/op,
0.970417 effective cores, median p99 2.6121 ms. This is measured allocated-core
utilization for this workload, not proof of a globally optimal implementation.
Allocations/context switches/syscalls remain NOT_MEASURED.

Fresh source inspection found that pre-repair one-group `cleanup_pass` uses
measured-window creation/replay deltas rather than post-close ownership. Grouped
source has a post-runtime-join snapshot; destinations had no post-close gauges.
All prior raw results remain retained. Process drain/exit is supported; two-sided
zero residual ownership is NOT_PROVEN by those raw forwarding runs.

The benchmark-only repair adds optional PID-bound post-close evidence and a
fail-closed eleven-gauge validator. Live RED lacked the destination report.
Diagnostic GREEN with one and four groups proves all requested gauges zero on
the source and every destination. Source grouped evidence is explicitly after
runtime joins. These smokes do not establish a long-run or repeated capacity
claim. Observer comparison and current-SHA qualification remain PENDING.

See `docs/benchmarks/P2A_POST_CLOSE_OWNERSHIP.md` for the repair, tests and commands.
External roots and raw-index hashes are in external-inputs.json; canonical copied
indexes use LF while external-inputs binds the original raw index bytes.
