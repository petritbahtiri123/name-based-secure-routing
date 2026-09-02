# Benchmark V2 Task 3 Stage 2: in-process group scaling

Classification: **PASS / HARNESS-LIMITED: shared destination QUIC endpoint driver runtime**

Independent source groups use distinct OS threads and current-thread Tokio runtimes. Each NBSR group owns a separately authenticated connection and authorized channel. Destination application handlers also use dedicated current-thread runtimes, but all accepted connections retain one shared listener/endpoint driver runtime; this is the next harness serialization boundary requiring focused profiling. Direct and NBSR failed to achieve strict stable scaling: NBSR exceeded the strict p99 saturation threshold at two groups while total CPU remained below two effective cores. No host or production NBSR ceiling is claimed.

| Payload/shape | Groups | Direct Gbit/s | NBSR Gbit/s | Delta | NBSR CPU cores | NBSR p99 ms | Region |
|---|---:|---:|---:|---:|---:|---:|---|
| 1024 B / s8 / o8 | 1 | 2.005 | 2.102 | +4.88% | 1.306 | 0.812 | STABLE |
| 1024 B / s8 / o8 | 2 | 2.091 | 2.126 | +1.65% | 1.702 | 1.880 | SATURATED |
| 1024 B / s8 / o8 | 4 | 1.893 | 1.584 | -16.34% | 1.727 | 29.422 | SATURATED |
| 1024 B / s64 / o4 | 1 | 1.454 | 2.154 | +48.13% | 1.290 | 3.142 | DEGRADED |
| 1024 B / s64 / o4 | 2 | 1.511 | 1.602 | +5.99% | 1.704 | 10.444 | SATURATED |
| 1024 B / s64 / o4 | 4 | 1.721 | 1.383 | -19.62% | 1.716 | 70.049 | SATURATED |
| 16384 B / s4 / o2 | 1 | 1.912 | 2.189 | +14.47% | 1.224 | 1.583 | STABLE |
| 16384 B / s4 / o2 | 2 | 2.254 | 1.911 | -15.24% | 1.535 | 3.608 | SATURATED |
| 16384 B / s4 / o2 | 4 | 1.774 | 1.828 | +3.08% | 1.611 | 35.617 | SATURATED |
| 16384 B / s1 / o4 | 1 | 1.971 | 2.658 | +34.85% | 1.323 | 0.651 | STABLE |
| 16384 B / s1 / o4 | 2 | 1.911 | 1.955 | +2.30% | 1.614 | 1.944 | SATURATED |
| 16384 B / s1 / o4 | 4 | 1.730 | 2.142 | +23.76% | 1.666 | 4.800 | SATURATED |

Process affinity was verified at mask `0x55`, selecting four physical-core-separated logical processors. Per-thread placement inside that allowed set was not independently verified.

All authoritative cells had zero errors/timeouts and process-level cleanup returned every owned NBSR resource and registry to zero.
