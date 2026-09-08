# Five-minute preparation comparison: no soak qualification

Source/binaries 0124f8ad, Linux Docker/WSL loopback, one allocated guest CPU,
16KiB/eight streams/depth1. The rational offered rate is fixed from the earlier
40b277fb 70% reference; it is not relabelled a current-source calibration.
Three counterbalanced pairs vary only premeasurement warmup: 3 versus 60 seconds.
Requested measurement is 300 seconds with unchanged live guards.

| Warmup | Repeat | Result |
| --- | --- | --- |
| 3s | 1 | FAIL: live p99 drift, seven steady windows retained |
| 60s | 1 | Completes 300s: 2.234392 Gbit/s, 98.650% achieved/offered |
| 60s | 2 | FAIL: live p99 drift, six steady windows retained |
| 3s | 2 | FAIL: source private growth, nine steady windows retained |
| 3s | 3 | Completes 300s: 2.236824 Gbit/s, 98.757% achieved/offered |
| 60s | 3 | Completes 300s: 2.239248 Gbit/s, 98.864% achieved/offered |

All three completed diagnostic runs report zero errors/timeouts and all eleven
final ownership counters zero on both endpoints. Continuous ownership is
NOT_MEASURED in these diagnostics. Neither arm supplies three successful repeats;
the completed subset is not a stable-capacity cohort. All failed prefixes remain.

Longer warmup is not established as a reliable fix and was not adopted as a
production or benchmark-default optimization. No qualified 60/120-minute soak
follows from these results. Further causal attribution and source-compatible
reference/observer/soak qualification remain open; no hardware ceiling is proven.
