# NBSR Benchmark Budgets v0.1

These are engineering targets, not wire-validity or protocol requirements.
Failure is recorded and is not optimized in the baseline task.

| Target | Budget |
|---|---|
| Warm existing Service Channel | p50 <= direct + 5 ms; p95 <= direct + 10 ms; p99 <= direct + 20 ms |
| Warm new service | p50 <= direct + 10 ms; p95 <= direct + 20 ms; p99 <= direct + 40 ms |
| Cold | p95 incremental overhead <= one contemporaneously measured RTT |
| Throughput | >=90% of matched direct at <=75% independently sustainable load |
| Correctness | zero protocol correctness errors |
| Benchmark failures | transport/application failures <0.1% |
| Memory | no sustained post-warm-up unbounded heap growth |

Sustainable capacity is the highest offered rate that, after a 60-second
warm-up and during a 10-minute steady-state window, has at least 99.9% success,
no unexpected rejection or exceeded protocol/resource limit, destination CPU
at most 85% of assigned capacity, no sustained unbounded memory growth, and
p99 no more than twice the path's idle p99.

