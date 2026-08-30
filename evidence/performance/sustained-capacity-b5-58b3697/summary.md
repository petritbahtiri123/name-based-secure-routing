# B5 Sustained Capacity

Evidence Status: **PASS**
System Result: **STABLE**

| Duration s | Payload B | Streams | Operations | Median Gbit/s | Goodput drift | p95 ns | p99 ns | Peak working set | Steady private slope | Errors | Timeouts | Cleanup | Classification |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|---:|---:|:---|:---|
| 3600 | 1024 | 64 | 156167149 | 0.734 | -3.168% | 2490550 | 3249250 | 10.3 MiB | destination=80.0 B/s, source=130.7 B/s | 0 | 0 | PASS | PASS / STABLE |
| 1800 | 16384 | 8 | 5678257 | 0.853 | 1.599% | 3921000 | 4784850 | 9.9 MiB | destination=21.8 B/s, source=30.0 B/s | 0 | 0 | PASS | PASS / STABLE |

Latency percentiles use deterministic 1-in-64 samples; operation and goodput counts are exact. Early/late comparisons exclude warm-up by construction.
Resource phase alignment uses monotonic progress arrival timestamps; packet capture was not enabled to avoid observer overhead.

Base Git SHA: `58b369752dd86811f10c1f52551879a1a861403f`
Host: Windows-11-10.0.26200-SP0 / Intel64 Family 6 Model 142 Stepping 12, GenuineIntel
Command: `scripts/run_b5_sustained_capacity.py --output 'evidence\performance\sustained-capacity-b5-58b3697' --run primary-60m-1k64:3600:1024:64 --run secondary-30m-16k8:1800:16384:8 --warmup-seconds 10 --cooldown-seconds 30 --sample-seconds 5`
