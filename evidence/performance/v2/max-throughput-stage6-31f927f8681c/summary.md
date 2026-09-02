# NBSR Maximum Throughput V2 — Stage 6

Classification: **PASS / STRICT-STABLE CEILING ESTABLISHED**.

Command:

```powershell
$env:CARGO_TARGET_DIR='C:\NBSR-build\max-throughput-v2-stage6'
python scripts/run_max_throughput_v2_stage6.py --output evidence\performance\v2\max-throughput-stage6-31f927f8681c --warmup-seconds 3 --duration-seconds 20 --initial-repeats 5 --maximum-repeats 10
```

All cells used NBSR, 16 KiB payloads, one stream per endpoint group, four outstanding operations per stream, and one current-thread Tokio runtime per group. Each cell completed five 20-second measured repeats. No cell exceeded 5% CV, so extension to ten repeats was not triggered.

This is a closed-loop workload. The achieved/offered ratio is the maximum observed outstanding depth divided by configured outstanding depth, capped at 1.0; zero errors and successful cleanup separately establish completion and drain behavior.

| Affinity | Groups | Median Gbit/s | Max Gbit/s | CV | Effective cores | p50 ms | p95 ms | p99 ms | p99/baseline | Classification |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `0x55` | 1 | 2.144 | 2.197 | 2.48% | 1.955 | 0.460 | 0.662 | 0.916 | 1.000x | STRICT_STABLE |
| `0x55` | 2 | 2.942 | 2.956 | 3.48% | 3.623 | 0.626 | 1.053 | 1.699 | 1.856x | REPEATABLE_DEGRADED_LATENCY |
| `0xFF` | 1 | 2.185 | 2.197 | 2.96% | 1.934 | 0.457 | 0.699 | 0.864 | 1.000x | STRICT_STABLE |
| `0xFF` | 2 | 2.775 | 2.836 | 2.31% | 3.903 | 0.661 | 1.134 | 1.334 | 1.545x | REPEATABLE_DEGRADED_LATENCY |

The highest single Stage-6 run was **2.956 Gbit/s** (`0x55`, two groups). The highest repeatable Stage-6 median was **2.942 Gbit/s** at the same shape, but it is not strict-stable because p99 is 1.856x the corresponding one-group baseline.

The highest strict-stable Stage-6 median is **2.185 Gbit/s** (`0xFF`, one group): CV 2.96%, p99 0.864 ms, 1.934 effective cores, zero errors/timeouts, achieved/offered ratio 1.0, and successful cleanup. The `0x55` one-group cell is also strict-stable at 2.144 Gbit/s.

All 20 authoritative runs were valid, reached configured outstanding depth, reported zero errors and zero timeouts, and passed cleanup. Peak combined working set was below 30 MiB. This strict-stable ceiling is limited to this Windows laptop/loopback benchmark topology and workload; it is not generalized to WAN, server-class, NIC, or production deployments.
