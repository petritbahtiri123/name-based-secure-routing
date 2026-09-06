# First live bounded-controller diagnostic

MEASURED diagnostic at clean 3644c324: shared four-physical-core mask 85,
four endpoint groups, 16 KiB, one stream/group, depth one, 2,000 offered ops/s,
three-second warmup, ten-second issue duration, one-second progress cadence.
This is one integration attempt, not a repeated capacity or authoritative soak cell.

Direct completed 19,998/20,000 offered operations, zero errors/timeouts, accounting
and process cleanup PASS. Runtime ownership is NOT_MEASURED for Direct.
NBSR was aborted by the unchanged live p99 drift guard at seven seconds, with
14,040 completed operations observed in its final retained progress record.
It has no successful final or owned-resource cleanup proof. Overall attempt FAIL;
the controller retained the unfavorable measurements and partial evidence.

NBSR early/late-third median sampled p99 ratio was 1.252585, above the existing
1.20 drift threshold. Each one-second window held only 31–32 globally sampled
latencies, so the reported p99 is effectively its maximum. This does not prove
sustained drift, a transport defect or a production ceiling. It is not discarded.
Direct's corresponding ratio was 0.979149 across nine steady windows.

Before long-soak qualification, choose and declare a cadence with enough samples
for tail comparison and run matched repeats. A longer aggregation interval changes
the measurement window, not offered rate, security, issue deadline, or drift
threshold; do not retroactively reclassify this attempt as passing.

All 41 raw manifest entries were verified. Retained outputs include bounded
stdout/resource histories and process cleanup results. No replacement repeat,
timeout increase, security change or implementation optimization followed this run.
