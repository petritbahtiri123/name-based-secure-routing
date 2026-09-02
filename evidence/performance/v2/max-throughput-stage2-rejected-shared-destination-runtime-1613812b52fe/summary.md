# Benchmark V2 Task 3 Stage 2: in-process group scaling

Classification: **PASS / HARNESS-LIMITED: destination current-thread echo/event loop**

Independent source groups use distinct OS threads and current-thread Tokio runtimes. Each NBSR group owns a separately authenticated connection and authorized channel. The destination accepts all groups in one current-thread benchmark runtime; this became the measured shared bottleneck. Direct and NBSR both lost throughput and exceeded the strict p99 saturation threshold at two groups while total CPU remained below two effective cores. No host or production NBSR ceiling is claimed.

| Payload/shape | Groups | Direct Gbit/s | NBSR Gbit/s | Delta | NBSR CPU cores | NBSR p99 ms | Region |
|---|---:|---:|---:|---:|---:|---:|---|
| 1024 B / s8 / o8 | 1 | 2.243 | 2.162 | -3.62% | 1.306 | 0.831 | STABLE |
| 1024 B / s8 / o8 | 2 | 2.107 | 2.100 | -0.33% | 1.535 | 1.770 | SATURATED |
| 1024 B / s8 / o8 | 4 | 1.583 | 1.586 | +0.19% | 1.523 | 34.205 | SATURATED |
| 1024 B / s64 / o4 | 1 | 1.923 | 1.881 | -2.20% | 1.300 | 3.380 | STABLE |
| 1024 B / s64 / o4 | 2 | 1.652 | 1.702 | +2.98% | 1.517 | 10.667 | SATURATED |
| 1024 B / s64 / o4 | 4 | 1.462 | 1.559 | +6.66% | 1.547 | 102.400 | SATURATED |
| 16384 B / s4 / o2 | 1 | 2.192 | 2.173 | -0.84% | 1.172 | 1.581 | STABLE |
| 16384 B / s4 / o2 | 2 | 1.960 | 2.056 | +4.91% | 1.489 | 3.708 | SATURATED |
| 16384 B / s4 / o2 | 4 | 1.836 | 1.891 | +3.00% | 1.534 | 48.016 | SATURATED |
| 16384 B / s1 / o4 | 1 | 2.281 | 2.237 | -1.94% | 1.312 | 0.797 | STABLE |
| 16384 B / s1 / o4 | 2 | 2.007 | 2.038 | +1.54% | 1.562 | 1.819 | SATURATED |
| 16384 B / s1 / o4 | 4 | 1.870 | 1.888 | +0.92% | 1.567 | 30.589 | SATURATED |

Process affinity was verified at mask `0x55`, selecting four physical-core-separated logical processors. Per-thread placement inside that allowed set was not independently verified.

All authoritative cells had zero errors/timeouts and process-level cleanup returned every owned NBSR resource and registry to zero.
