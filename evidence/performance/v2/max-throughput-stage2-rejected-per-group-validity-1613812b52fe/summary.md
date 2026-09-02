# Benchmark V2 Task 3 Stage 2: in-process group scaling

Classification: **PASS / HARNESS-LIMITED: shared destination QUIC endpoint driver runtime**

Independent source groups use distinct OS threads and current-thread Tokio runtimes. Each NBSR group owns a separately authenticated connection and authorized channel. Destination application handlers also use dedicated current-thread runtimes, but all accepted connections retain one shared listener/endpoint driver runtime; this is the next measured harness serialization boundary. Direct and NBSR both lost throughput and exceeded the strict p99 saturation threshold at two groups while total CPU remained below two effective cores. No host or production NBSR ceiling is claimed.

| Payload/shape | Groups | Direct Gbit/s | NBSR Gbit/s | Delta | NBSR CPU cores | NBSR p99 ms | Region |
|---|---:|---:|---:|---:|---:|---:|---|
| 1024 B / s8 / o8 | 1 | 1.805 | 2.147 | +18.95% | 1.316 | 0.804 | STABLE |
| 1024 B / s8 / o8 | 2 | 1.890 | 2.131 | +12.78% | 1.686 | 1.904 | SATURATED |
| 1024 B / s8 / o8 | 4 | 1.535 | 1.543 | +0.53% | 1.696 | 8.790 | SATURATED |
| 1024 B / s64 / o4 | 1 | 1.747 | 1.992 | +14.03% | 1.285 | 3.870 | STABLE |
| 1024 B / s64 / o4 | 2 | 1.635 | 1.846 | +12.87% | 1.746 | 7.944 | SATURATED |
| 1024 B / s64 / o4 | 4 | 1.278 | 1.366 | +6.90% | 1.732 | 74.812 | SATURATED |
| 16384 B / s4 / o2 | 1 | 2.591 | 2.098 | -19.02% | 1.224 | 1.579 | STABLE |
| 16384 B / s4 / o2 | 2 | 1.866 | 2.285 | +22.44% | 1.510 | 3.191 | SATURATED |
| 16384 B / s4 / o2 | 4 | 1.732 | 1.796 | +3.72% | 1.591 | 36.063 | SATURATED |
| 16384 B / s1 / o4 | 1 | 2.278 | 2.603 | +14.30% | 1.312 | 0.670 | STABLE |
| 16384 B / s1 / o4 | 2 | 1.788 | 1.976 | +10.55% | 1.562 | 2.120 | SATURATED |
| 16384 B / s1 / o4 | 4 | 1.597 | 1.587 | -0.63% | 1.514 | 31.380 | SATURATED |

Process affinity was verified at mask `0x55`, selecting four physical-core-separated logical processors. Per-thread placement inside that allowed set was not independently verified.

All authoritative cells had zero errors/timeouts and process-level cleanup returned every owned NBSR resource and registry to zero.
