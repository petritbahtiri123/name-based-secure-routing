# Fresh finite-batch admission progression

MEASURED on clean source `1917b1950a4ff94e18445da513f31848850c81fc`, release Windows loopback,
two source shards, inherited affinity. Every repeat offers 512 clients alongside
30 seconds of established forwarding with two seconds of warmup. This is a finite
admission batch, **not sustained admission-soak or production/server capacity**.

| Offered/s | Repeats | Actual admissions/s | Achieved/offered | Max rate/goodput CV | Handshake p99 ms | Admission p99 ms | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 25 | 5 | 24.746 | 98.98% | 6.73% | 4.066 | 11.472 | DEGRADED |
| 50 | 5 | 49.118 | 98.24% | 6.77% | 4.486 | 11.595 | DEGRADED |
| 75 | 3 | 72.976 | 97.30% | 1.71% | 6.081 | 15.038 | STABLE |
| 100 | 5 | 95.989 | 95.99% | 4.05% | 10.502 | 24.598 | STABLE |
| 125 | 3 | 119.920 | 95.94% | 1.61% | 10.110 | 28.327 | STABLE |
| 150 | 3 | 138.887 | 92.59% | 2.74% | 12.940 | 37.362 | DEGRADED |
| 200 | 3 | 176.182 | 88.09% | 4.84% | 26.089 | 103.373 | SATURATED |

All 27 repeats are valid and retained: 13,824 successful admissions, zero errors
and timeouts. All 512 terminal client records reconcile per repeat; all processes
exit. Eight tracked counters are zero on each of the two destinations. This
runner does not establish a source-global 11-counter post-close ownership result.

The highest tested STABLE offered rate is 125/s (119.920 actual/s). At 150/s the
median achieved/offered ratio is below 95%; at 200/s it is below 90%, which is
SATURATED under the declared classifier despite every client eventually succeeding.
Progression therefore stops at 200/s after preceding stable cells; configured
250/s was not executed. The 25/s and 50/s cells remain DEGRADED by forwarding CV,
with no attempt to remove unfavorable repeats or replace the original reference.
The classifier uses the 25/s cell's median forwarding reference, whose CV remains
above 5%; low-rate dispersion remains a qualification, not a proven causal limit.

Median sampled process CPU is approximately 1.32–1.52 effective cores across these
cells (whole observed lifetime). No physical-core affinity was imposed and no
hardware ceiling or production bottleneck is established. Handshake progress
remains UNRESOLVED / PLATFORM_DIAGNOSTIC_LIMIT under the earlier rejected observer
comparisons. These fresh outcomes cannot prove a cause for historical differences.

Historical 119.813 admissions/s and Task 4k's saturated outcomes remain separate
source/workload-stage evidence. This fresh cohort preserves the same broad
125/150/200 classification sequence; it is not an exact before/after optimization
comparison. No new production optimization accompanies this package.

`analysis.json` is the original runner output, independently rebuilt exactly from
all repeat records. `raw-checksums.sha256` binds all 254 retained raw artifacts
under `C:/NBSR-build/task4i-fresh-1917b195`; `environment.json` binds commands,
binary/source hashes and host identity. `validation.json` records integrity and
ownership scope. The package helper verifies raw data before writing this report.

Reproduce from the source SHA with a fresh output path:

```powershell
$env:CARGO_TARGET_DIR='C:/NBSR-build/b4b-task4k'
python scripts/run_b4b_task4i.py --output C:/NBSR-build/task4i-fresh-UNIQUE --source-shards 2 --offered-rates 25 50 75 100 125 150 200 250
```

No Administrator action, push, main modification or evidence deletion was needed.
Current benchmark forwarding/soak and complete external validation remain pending.
