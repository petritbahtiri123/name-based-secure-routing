# B4b-v2 Task 4j — Admission lifecycle backlog attribution

## Classification

`HARNESS-LIMITED:admission-source-current-thread-runtime`

This is an offline analysis of the accepted Task 4i measurements at commit
`8d0fd5699d56929c9192b947a5b7d3351ea8ca5f`. It adds no timed-path
instrumentation and therefore requires no observer-overhead gate. The result is
limited to this Windows loopback benchmark harness and is not an NBSR production
capacity claim.

## Results

| Offered/s | Completed/s | Achieved | Source cores | Destination cores | Host CPU | Median peak stage occupancy (transport/control/activation/close) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 125 | 119.813 | 95.85% | 0.771 | 0.442 | 23.67% | 1 / 0 / 0 / 0 |
| 150 | 139.511 | 93.01% | 0.951 | 0.545 | 22.90% | 0 / 1 / 1 / 1 |
| 200 | 138.958 | 69.48% | 0.881 | 0.531 | 23.27% | 12 / 21 / 24 / 27 |

Completion changes by only -0.40% from 150/s to 200/s while the admission
source reaches 0.951 effective cores at 150/s. The admission destination peaks
at 0.545 effective cores and whole-host CPU remains about 23%, excluding a
whole-host CPU ceiling and destination CPU saturation.

At 200/s, median peak live occupancy spreads across all successive stages.
This is accumulated in-flight lifecycle work, not a route-validation queue:
`pending_routes_current_entries` has median peak 0 at 200/s and the audit queue
has median peak 5. All repeats finish with zero live connections, sessions,
channels, and streams.

## Service-time change

| Stage p99 | 125/s | 150/s | 200/s |
| --- | ---: | ---: | ---: |
| Transport handshake | 10.439 ms | 11.727 ms | 222.002 ms |
| Control hello RTT | 6.415 ms | 7.315 ms | 216.484 ms |
| Route-open RTT | 6.373 ms | 6.474 ms | 212.470 ms |
| Stream-open RTT | 5.853 ms | 7.586 ms | 219.978 ms |
| Source admission computation | 0.597 ms | 0.594 ms | 0.628 ms |
| Destination admission computation | 0.574 ms | 0.599 ms | 0.620 ms |
| Total lifecycle | 32.229 ms | 45.521 ms | 883.101 ms |

The local source and destination admission computations remain bounded (the
destination p99 grows only 1.08x), while every network-progress RTT inflates by
roughly two orders of magnitude (control hello grows 33.74x). Together with the
source's single-core occupancy and the completion plateau, this attributes the
backlog to scheduling/progress capacity in the benchmark-only admission-source
current-thread runtime. The evidence does not identify a production NBSR
protocol or validation bottleneck.

## Resource and cleanup observations

Median peak private bytes rise from 40.4 MiB at 125/s to 43.5 MiB at 150/s and
139.6 MiB at 200/s; median peak handles rise 346 → 351 → 547. These track the
larger in-flight connection/session population. They return to zero ownership
at the end of every repeat, so this evidence does not show a leak.

## Smallest justified next change

If optimization is approved, use a bounded **HARNESS-ONLY** split of admission
source scheduling across two independently owned current-thread driver shards,
while retaining one independent connection/session lifecycle per logical
client and identical deadlines/accounting. Re-run the rate sweep and stop if
the destination or another measured stage becomes limiting. This report does
not implement that change.

## Reproduction

```powershell
python -m pytest tests/performance/test_task4j_backlog_attribution.py -q
python scripts/analyze_b4b_task4j.py `
  --source evidence/performance/v2/b4b-task4i-fa46af05db79 `
  --output evidence/performance/v2/b4b-task4j-8d0fd5699d56
```

`source-checksums.sha256` pins every Task 4i raw input used. `analysis.json`
contains per-repeat measurements and derived medians; `stage-summary.csv` is a
compact machine-readable table.
