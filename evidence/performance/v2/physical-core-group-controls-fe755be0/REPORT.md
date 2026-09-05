# Physical-core endpoint-group controls

MEASURED: Windows loopback, release, clean fe755be0 source state. Same 16 KiB
request/response and one stream per endpoint as the prior multicore package.
Three-second warmup and 30-second measurement; both roles share each verified
physical-core pool with no SMT siblings. Every one of 56 retained records is
valid, has zero errors/timeouts and passes cleanup. All 374 raw hashes verified.
Five repeats are retained whenever either matched path exceeded 5% throughput CV.

| Cores | Groups | Path | Depth | Repeats | Median Gbit/s | p99 ms | CV | Class |
|---|---|---|---|---|---|---|---|---|
| 2 | 1 | direct | 1 | 3 | 0.896091 | 0.410 | 0.74% | STABLE |
| 2 | 1 | direct | 2 | 3 | 1.341436 | 0.578 | 2.62% | DEGRADED |
| 2 | 1 | direct | 4 | 3 | 1.470175 | 1.024 | 4.39% | SATURATED |
| 2 | 1 | direct | 8 | 3 | 1.520739 | 1.953 | 2.36% | SATURATED |
| 2 | 1 | nbsr | 1 | 3 | 0.978598 | 0.354 | 2.49% | UNRESOLVED |
| 2 | 1 | nbsr | 2 | 3 | 2.037745 | 0.475 | 1.14% | DEGRADED |
| 2 | 1 | nbsr | 4 | 3 | 2.430334 | 0.730 | 3.10% | SATURATED |
| 2 | 1 | nbsr | 8 | 3 | 2.702661 | 1.274 | 2.95% | SATURATED |
| 4 | 2 | direct | 1 | 5 | 1.342245 | 0.544 | 7.09% | UNRESOLVED |
| 4 | 2 | direct | 2 | 3 | 2.194479 | 0.872 | 3.49% | DEGRADED |
| 4 | 2 | direct | 4 | 3 | 2.664842 | 1.407 | 0.74% | SATURATED |
| 4 | 2 | direct | 8 | 5 | 2.603195 | 2.753 | 3.35% | SATURATED |
| 4 | 2 | nbsr | 1 | 5 | 1.549058 | 0.463 | 2.12% | STABLE |
| 4 | 2 | nbsr | 2 | 3 | 2.920480 | 0.650 | 3.85% | DEGRADED |
| 4 | 2 | nbsr | 4 | 3 | 3.258713 | 1.231 | 4.46% | SATURATED |
| 4 | 2 | nbsr | 8 | 5 | 3.312443 | 2.304 | 4.83% | SATURATED |

The four-core/two-group NBSR ladder resolves STABLE 1.549058 Gbit/s,
DEGRADED 2.920480 Gbit/s (see exact JSON), then SATURATED higher depths.
The two-core/one-group NBSR baseline remains UNRESOLVED because its p99 repeat
variation fails the all-repeat latency gate despite low throughput CV. Its
2.0377 Gbit/s point is DEGRADED, not strict-stable.

Each classification uses that fixed group's lowest-depth p99 baseline.
Consequently a DEGRADED point in one group configuration can have lower absolute
p99 than a STABLE point in another. These are qualified workload ladders, not one
pooled latency SLA or a universal production capacity. Always report absolute
p99 and configuration with the classification. The four-group 2.306118 Gbit/s
result remains a separate fixed-shape qualification; no baseline is silently
replaced by a more favorable group. Soak inputs must bind the exact chosen
workload and its reference artifact.

More outstanding work raises CPU utilization in the one-group control, but
also raises latency. This is configuration evidence, not a production code
optimization or attribution of a production hotspot. No protocol, security,
timeout or assertion change was made. Both Direct and NBSR use equivalent
workload parameters. CPU accounting remains sampled process CPU, excluding
boundary fragments and interrupt work; allocations, context switches, syscalls,
effective frequency and temperature remain unmeasured. No competing test/build
or capture workload was launched during timing. All unfavorable valid results
are retained in the records and indexed external raw roots.
