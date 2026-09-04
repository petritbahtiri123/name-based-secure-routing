# B4b-v2 Task 4k — Fixed two-shard admission-source scheduler

## Classification

- Evidence: `FAIL` (the approved PASS gate was not met)
- System: `SATURATED`
- Next measured stage: `UNRESOLVED:transport-handshake-progress`

The change is benchmark-only. It does not modify the destination, deadlines,
protocol, wire format, security behavior, production runtime, or frozen
authority. Results apply only to this Windows loopback harness.

## Boundary result

| Source shards | Highest stable | First degraded | First saturated |
| ---: | ---: | ---: | ---: |
| 1 | 125/s | 150/s | 200/s |
| 2 | 125/s | 150/s | 200/s |

Two shards therefore did not move the stable/degraded/saturated boundary.

## Matched measurements

| Shards | Offered/s | Status | Actual/s | Achieved | Admission p99 | Handshake p99 | Established | Forwarding p99 |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 125 | BASELINE | 119.402 | 95.52% | 33.23 ms | 10.99 ms | 0.626 Gbit/s | 0.422 ms |
| 1 | 150 | DEGRADED | 138.682 | 92.45% | 46.31 ms | 13.01 ms | 0.629 Gbit/s | 0.447 ms |
| 1 | 200 | SATURATED | 139.510 | 69.76% | 795.64 ms | 196.10 ms | 0.630 Gbit/s | 0.454 ms |
| 1 | 250 | SATURATED | 118.746 | 47.50% | 1499.40 ms | 356.44 ms | 0.630 Gbit/s | 0.441 ms |
| 1 | 300 | SATURATED | 101.772 | 33.92% | 1864.56 ms | 484.69 ms | 0.629 Gbit/s | 0.448 ms |
| 1 | 400 | SATURATED | 94.349 | 23.59% | 2309.52 ms | 836.96 ms | 0.628 Gbit/s | 0.447 ms |
| 2 | 125 | BASELINE | 118.642 | 94.91% | 29.05 ms | 9.93 ms | 0.622 Gbit/s | 0.445 ms |
| 2 | 150 | DEGRADED | 140.781 | 93.85% | 35.47 ms | 12.47 ms | 0.620 Gbit/s | 0.459 ms |
| 2 | 200 | SATURATED | 161.029 | 80.51% | 138.84 ms | 34.63 ms | 0.633 Gbit/s | 0.477 ms |
| 2 | 250 | SATURATED | 61.862 | 24.74% | 3010.36 ms | 1046.12 ms | 0.623 Gbit/s | 0.473 ms |
| 2 | 300 | SATURATED | 64.869 | 21.62% | 3027.42 ms | 3015.00 ms | 0.625 Gbit/s | 0.473 ms |
| 2 | 400 | SATURATED | 63.361 | 15.84% | 6179.75 ms | 3020.41 ms | 0.623 Gbit/s | 0.483 ms |

All runs admitted 512/512 eventually, had zero terminal ownership residue, and
preserved established forwarding. Capacity classification uses arrival-rate
achievement and latency gates, not eventual success alone.

## CPU and resources

At 200/s, the two shard threads consumed median 0.524 and 0.517 effective
cores. At 250/s they fell to 0.218 and 0.303 while admission throughput and
handshake latency collapsed. Total measured process CPU remained about 1.52
effective cores and host CPU remained about 22%. This excludes source-shard or
whole-host CPU saturation.

At 250/s with two shards, median peak private memory was 119.0 MiB and handles
were 530. Both rose with in-flight connections and returned to zero ownership
during cleanup. No leak is claimed.

## Interpretation

Two shards materially improve the already-saturated 200/s cell (+15.42%
actual admissions/s and much lower p99), proving that the original source
runtime contributed to the plateau. The improvement is insufficient for PASS
because neither classification boundary moves.

At 250/s and above, delay first becomes dominant in transport handshake
progress: handshake p99 rises from 34.63 ms at 200/s to 1046.12 ms at 250/s,
then reaches approximately 3 seconds at 300/s. Source shard CPU, total CPU, and
host CPU all retain headroom; destination pending-route high-water remains one.
These measurements locate the next delayed stage but do not distinguish Quinn
timer/runtime interaction from Windows UDP/network scheduling. Exact ownership
therefore remains unresolved.

## Smallest justified next step

Run profiling only, matched at two shards / 200 and 250 offered/s, using
low-overhead external ETW plus Npcap packet timing. Correlate first outbound UDP,
first reply, retry-like patterns, runtime ready/wait time, and destination
accept progress. Do not add shards, change deadlines, or optimize until that
attribution is measured.

## Reproduction

```powershell
$env:CARGO_TARGET_DIR='C:\NBSR-build\b4b-task4k'
python scripts/run_b4b_task4k.py `
  --output evidence/performance/v2/b4b-task4k-c8df2156efe1 `
  --duration-seconds 30 --warmup-seconds 2
python scripts/run_b4b_task4k.py `
  --output evidence/performance/v2/b4b-task4k-c8df2156efe1 `
  --analyze-existing
```
