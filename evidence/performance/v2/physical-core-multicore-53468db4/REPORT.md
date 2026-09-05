# Physical-core forwarding: current multicore ladders

MEASURED Windows loopback at 53468db421f9e46d49aaa5be2ca9bd0755a2e09a,
clean checkout, release binaries. Both roles share one verified physical-core
pool; one logical processor per physical core, no SMT siblings. Two cores use
mask 0x5 and two independent endpoint groups; four use 0x55 and four groups.
16 KiB request and response payload, one stream per group, 3-second warmup,
30-second measurement, alternating matched Direct/NBSR order. Three valid
repeats per cell, five when either path exceeded 5% CV. All 90 records have
zero errors/timeouts and successful cleanup; unfavorable valid runs remain.

| Cores | Path | Depth | Repeats | Median Gbit/s | p99 ms | CV | Class |
|---|---|---|---|---|---|---|---|
| 2 | direct | 1 | 5 | 1.171785 | 0.814 | 2.94% | STABLE |
| 2 | direct | 2 | 5 | 1.351602 | 2.187 | 7.44% | SATURATED |
| 2 | direct | 3 | 3 | 1.444262 | 2.792 | 1.54% | SATURATED |
| 2 | direct | 4 | 3 | 1.481486 | 3.619 | 0.95% | SATURATED |
| 2 | direct | 8 | 3 | 1.590203 | 7.130 | 1.32% | SATURATED |
| 2 | direct | 16 | 3 | 1.678083 | 36.318 | 1.98% | SATURATED |
| 2 | nbsr | 1 | 5 | 1.534066 | 0.779 | 6.13% | UNRESOLVED |
| 2 | nbsr | 2 | 5 | 1.844830 | 6.561 | 1.23% | SATURATED |
| 2 | nbsr | 3 | 3 | 1.980682 | 2.449 | 1.24% | SATURATED |
| 2 | nbsr | 4 | 3 | 2.218801 | 13.646 | 2.51% | SATURATED |
| 2 | nbsr | 8 | 3 | 2.375082 | 50.737 | 4.87% | SATURATED |
| 2 | nbsr | 16 | 3 | 2.319988 | 55.943 | 2.23% | SATURATED |
| 4 | direct | 1 | 5 | 1.860115 | 1.010 | 7.02% | UNRESOLVED |
| 4 | direct | 2 | 5 | 2.032897 | 2.455 | 2.41% | SATURATED |
| 4 | direct | 4 | 3 | 2.343005 | 4.526 | 1.87% | SATURATED |
| 4 | direct | 8 | 5 | 2.548023 | 8.434 | 4.82% | SATURATED |
| 4 | direct | 16 | 5 | 2.937367 | 15.693 | 6.54% | SATURATED |
| 4 | nbsr | 1 | 5 | 2.306118 | 1.085 | 0.91% | STABLE |
| 4 | nbsr | 2 | 5 | 2.643019 | 10.342 | 24.26% | SATURATED |
| 4 | nbsr | 4 | 3 | 2.976737 | 24.460 | 3.52% | SATURATED |
| 4 | nbsr | 8 | 5 | 3.218905 | 33.224 | 5.33% | SATURATED |
| 4 | nbsr | 16 | 5 | 3.361954 | 43.061 | 7.79% | SATURATED |

Four-core NBSR depth 1 is STRICT-STABLE at 2.306118 Gbit/s, five repeats,
0.908% CV and median p99 1.085 ms. Higher tested depths are SATURATED by the
pre-existing relative latency gates. Peak individual NBSR throughput is
3.666140 Gbit/s and is DIAGNOSTIC ONLY. No intermediate degraded boundary was
resolved by this tested ladder. Two-core NBSR depth 1 remains UNRESOLVED at
6.126% CV; do not substitute its median for a strict-stable claim. Four-core
Direct baseline is also UNRESOLVED; no reliable NBSR-versus-Direct speedup
claim follows from comparing these medians.

Process CPU approaches allocated physical-core capacity in these tested
shapes. This is a measured CPU-resource constraint for the specified workload
and pool, not proof that every cycle is useful, a production hotspot attribution,
a machine-wide optimal forwarding ceiling or a server/WAN capacity result.
Endpoint-group controls and other useful workload shapes remain pending.

CPU ns/op is derived from sampled process CPU over the final measurement
window. It excludes boundary fragments and host interrupt work. Allocations,
context switches, syscalls, effective frequency and temperature are NOT_MEASURED.
Docker Desktop remained open but campaign containers were stopped before these
runs; no concurrent build/test/capture workload was launched during timing.
The external Linux smoke recipe was authored without executing workloads.

The earlier one-core package remains separate. These two multicore ladders
share exact binaries, SHA, sampling code and timing configuration. Do not pool
unlike endpoint counts into one cell or silently treat older single-core binary
hashes as identical. All raw command/resource logs and immutable binaries remain
under the indexed external roots; the package retains their complete indexes.
