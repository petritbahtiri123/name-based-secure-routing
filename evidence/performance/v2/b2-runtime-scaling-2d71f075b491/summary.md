# B2-v2 Task 2b Runtime Scaling

Classification: **PASS / HARNESS-LIMITED: multi-thread runtime overhead**

Increasing benchmark workers from 1 to 2 or 4 increased CPU consumption and reduced throughput in both Direct and NBSR. This identifies a benchmark-runtime scheduling/synchronization cost; it is not a production NBSR result.

| Workload | Path | Workers | Gbit/s | Ops/s | Effective cores | CPU ns/op | p99 ms | CV |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| p1024-s64-o1 | direct | 1 | 1.828 | 111568 | 1.781 | 15869 | 0.859 | 0.061 |
| p1024-s64-o1 | direct | 2 | 0.854 | 52113 | 2.455 | 47284 | 2.629 | 0.035 |
| p1024-s64-o1 | direct | 4 | 0.886 | 54049 | 2.725 | 50422 | 2.548 | 0.032 |
| p1024-s64-o1 | nbsr | 1 | 1.797 | 109652 | 1.789 | 16325 | 0.923 | 0.042 |
| p1024-s64-o1 | nbsr | 2 | 0.750 | 45804 | 2.416 | 52921 | 3.076 | 0.075 |
| p1024-s64-o1 | nbsr | 4 | 0.809 | 49389 | 2.616 | 52461 | 2.722 | 0.059 |
| p16384-s1-o4 | direct | 1 | 2.148 | 8195 | 1.775 | 215822 | 0.833 | 0.090 |
| p16384-s1-o4 | direct | 2 | 1.810 | 6903 | 2.409 | 354497 | 0.927 | 0.059 |
| p16384-s1-o4 | direct | 4 | 1.673 | 6383 | 2.475 | 392143 | 1.072 | 0.022 |
| p16384-s1-o4 | nbsr | 1 | 2.248 | 8577 | 1.773 | 203069 | 0.715 | 0.027 |
| p16384-s1-o4 | nbsr | 2 | 1.652 | 6300 | 2.326 | 373169 | 1.098 | 0.061 |
| p16384-s1-o4 | nbsr | 4 | 1.340 | 5112 | 2.240 | 438264 | 1.773 | 0.430 |

No production runtime, protocol, transport, security, or frozen-authority code changed.
