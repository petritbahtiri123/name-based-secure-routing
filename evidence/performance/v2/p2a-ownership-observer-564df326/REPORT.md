# Optional post-close ownership observer qualification

MEASURED: clean564df326, retained release binaries, five alternating on/off
NBSR pairs per shape, three-second warmup and30-second measurement. Both roles
share verified physical-core representatives without SMT. All20 records valid;
all222 raw artifact hashes verified. No concurrent builds/tests/captures/Docker
workloads were launched. Direct was not part of this observer-only comparison.

| Shape | Observer | Median Gbit/s | Median p99 ms | Throughput CV | Timing class |
|---|---|---|---|---|---|
| 1core/1group,1KiB,64streams,depth1 | off |0.854389|2.6773|1.99%|STABLE|
| same | on |0.874694|2.2681|1.22%|STABLE|
| 4cores/4groups,16KiB,1stream/group,depth1 | off |2.349727|1.0616|10.74%|UNRESOLVED|
| same | on |2.343236|1.0405|0.81%|STABLE|

The one-core observer gate FAILS: absolute median p99 change15.28% exceeds5%,
despite throughput change2.38%. The improvement in p99 does not make the
observer non-distorting. Use its ownership results separately from unobserved
timing; do not pool or use this comparison for causal performance attribution.

The four-core median observer gate PASSES: throughput change-0.276%,
p99 change-1.988%. The off-mode CV10.74% is explicitly not strict-stable even
with five repeats. Passing this median observer gate does not establish stable
unobserved capacity or rule out distribution/scheduler effects.

All five on-mode repeats per shape have zero in all11 required ownership gauges
on the source and every destination. One-group source/destination reports occur
while the enclosing runtime remains alive. Four-group source reports follow
all group runtime joins; they are not runtime-alive source-group evidence.
Off-mode ownership remains NOT_MEASURED. There is no claim of long-run cleanup,
server/WAN performance or globally optimal production capacity.

Timing classes use each fixed shape/mode lowest-depth p99 and existing common
repeat rules. This is a single-point qualification, not a renewed full ceiling
ladder. All earlier unfavorable valid records remain retained. New grouped/paced
soak changes still require their own same-SHA calibration and load binding.
