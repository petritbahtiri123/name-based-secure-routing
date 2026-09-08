# Linux admission repair verification and active-bundle diagnostics

Source2a30272e, release Docker/WSL loopback. All four mixed-workload peers share one selected guest CPU. These are finite512-client batches alongside established traffic, not sustained admissions/s or a server ceiling.

| Offered/s | Actual admissions/s | Classification | Repeats |
| ---: | ---: | --- | ---: |
| 25 | 24.789482 | STABLE | 3 |
| 50 | 49.217779 | STABLE | 3 |
| 75 | 72.892233 | STABLE | 3 |
| 100 | 97.378629 | STABLE | 3 |
| 125 | 119.313320 | STABLE | 3 |
| 150 | 142.418287 | DEGRADED | 3 |
| 200 | 111.350407 | SATURATED | 5 |

All23 records are valid with zero reported errors/timeouts and successful cleanup. The200/s cohort has6.11% dispersion after five repeats and remains SATURATED. Its handshake p99 median is343.282ms and admission p99 is1276.066ms; the125/s values are13.817ms and35.677ms. All unfavorable valid repeats are retained.

One actual admission-destination PF_EXITING transition at200/s repeat4 is retained and followed by owned exit code0. This verifies the2a30272e observer repair in the real NBSR workload. Sampled effective cores are approximately0.954-0.958 for the whole co-resident workload. The unpaced established stream also consumes this allocation; aggregate busy CPU does not alone attribute admission stalls or establish global hardware/NBSR capacity.

Three independent1024 live-bundle diagnostics pass; all three2048 attempts fail. Namespace UDP receive-buffer drop deltas are118/41/151 versus6425/13055/21244. Source2048 failures contain424/387/206 HandshakeTimeout outcomes; repeat1 also has one client_task_failed. These counters do not identify a socket or exact drop timing. No buffer optimization follows from correlation alone;132a3b82 adds failure-only owned-socket snapshots for subsequent attribution.

Raw:C:/NBSR-build/linux-followup-2a30272e. Build:C:/NBSR-build/linux-current-2a30272e. No simultaneous benchmark/build workload. Largest accepted active-bundle count remains1024; sustained near-ceiling soak remains NOT_PROVEN.
