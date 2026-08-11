# P2B Stream-Establishment Profile

## Executive summary

P2B is accepted. Classification **A — NBSR control/admission path dominated**. No optimization was implemented.

## 50% load

| Path | ops/s | mean ns/op | p50 | p95 | p99 | CPU ns/op | errors | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct | 2375.004 | 119111.2 | 103716 | 146084 | 199537 | 447770.5 | 0 | 0.0000% |
| nbsr | 843.748 | 289816.7 | 267470 | 395870 | 487667 | 1188271.6 | 0 | 0.0004% |

Incremental mean NBSR cost: 170705.4 ns/op. Source admission wait/read alone: 82.9% of that delta; measured source phases explain 107.1% (overlap/noise may make this exceed 100%).

## 90% load

| Path | ops/s | mean ns/op | p50 | p95 | p99 | CPU ns/op | errors | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct | 4275.003 | 186767.8 | 103227 | 130173 | 181242 | 259462.3 | 0 | 0.0000% |
| nbsr | 1518.616 | 256235.7 | 243433 | 327947 | 419625 | 683584.8 | 0 | 0.0008% |

Incremental mean NBSR cost: 69467.9 ns/op. Source admission wait/read alone: 180.0% of that delta; measured source phases explain 219.9% (overlap/noise may make this exceed 100%).

## Interpretation

The destination uses one sequential control-stream read/authorize/respond loop. Source `open_bi` follows the admission response. The admission wait/read is the largest NBSR-specific source phase at both loads; StreamGate/replay/audit/state work inside destination authorization is much smaller. Destination control-read and accept timers include inter-arrival/dependency wait and are not CPU attribution.

No safe allocation-count profiler or usable stack-sampling analysis tool was available. Allocation counts/bytes, allocator stacks, lock wait/hold, and Tokio wakeup counts are therefore unavailable; process CPU and fixed-cardinality wall timers are reported instead.

## Recommended first optimization

Remove the per-stream serialized STREAM_OPEN admission round trip from the critical path while preserving authorization, replay, sequencing, audit, and fail-closed semantics.
