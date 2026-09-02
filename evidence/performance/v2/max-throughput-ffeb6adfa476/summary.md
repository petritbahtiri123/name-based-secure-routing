# Benchmark V2 Task 3: maximum-throughput sweep

Classification: **PARTIAL / HARNESS-LIMITED: single-thread peer event loops**

The full single-channel geometric matrix completed with no correctness, timeout, or cleanup failures. Throughput plateaued while the matched source and destination used about 1.3 effective CPU cores in total; therefore this is not a measured host or hardware ceiling. The current in-process P2A mode owns one authorized NBSR channel and one single-thread runtime per peer. Multi-channel scaling remains required before a funding-grade stable host ceiling can be claimed.

| Payload | NBSR peak | Shape | Matched Direct | Delta | CPU cores | p50/p95/p99 ms |
|---:|---:|---|---:|---:|---:|---|
| 1024 | 1.910 Gbit/s | 1 conn / 1 channel / 8 streams / 8 outstanding | 1.884 Gbit/s | +1.36% | 1.311 | 0.535/0.701/0.806 |
| 16384 | 2.278 Gbit/s | 1 conn / 1 channel / 4 streams / 2 outstanding | 2.174 Gbit/s | +4.76% | 1.307 | 0.867/1.322/1.648 |

All raw valid degraded/saturated cells are retained. The strict common p99 rules classify most high-load cells as degraded or saturated even when their throughput is repeatable; peak above means highest valid repeatable throughput, not a new stable ceiling.

No production NBSR, protocol, transport, security, frozen-authority, or resource-limit code changed.
