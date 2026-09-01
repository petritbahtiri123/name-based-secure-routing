# B2-v2 Harness Optimization

Classification: **Evidence PASS / HARNESS-LIMITED: single-thread benchmark runtimes**

The per-operation benchmark SHA-256 interference was removed without changing production NBSR. Full integrity checks run before and after timing and every 1024th timed operation; other operations use eight bounded probes.

| Payload | Stable NBSR Gbit/s | Streams | Outstanding/stream | CV | p99 ms | Effective cores |
|---:|---:|---:|---:|---:|---:|---:|
| 1024 | 1.997 | 64 | 1 | 0.014 | 0.804 | 1.786 |
| 16384 | 2.290 | 1 | 4 | 0.004 | 0.645 | 1.792 |

This result demonstrates removal of benchmark interference only. It does not establish a production speedup or a host hardware ceiling.
