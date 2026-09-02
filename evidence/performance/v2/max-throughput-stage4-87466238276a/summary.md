# Benchmark V2 Task 3 Stage 4: independent destination endpoints

Classification: **PASS / AFFINITY-CPU-SATURATED**. This classification applies only to the four selected physical-core representative logical processors on this Windows loopback host.

Each connection/channel group used an independently bound destination QUIC endpoint in a separate current-thread runtime process. Endpoint processes were pinned to verified physical-core representative masks: `0x1`, `0x4`, `0x10`, and `0x40`. The source process was constrained to `0x55`; individual source group-thread placement was not enforceable or verified. Direct and NBSR used identical endpoint topology, stream count, outstanding depth, runtime flavor, affinity policy, warmup, duration, and repetition policy.

| Path | Endpoint groups | Repeats | Median Gbit/s | Ops/s | CV | Effective cores | p99 ms | Peak working set MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct | 1 | 3 | 1.386 | 5,288 | 1.29% | 1.703 | 1.232 | 16.8 |
| Direct | 2 | 5 | 1.983 | 7,563 | 9.91% | 3.437 | 2.500 | 26.0 |
| Direct | 4 | 5 | 1.984 | 7,569 | 11.74% | 3.716 | 10.381 | 43.9 |
| NBSR | 1 | 5 | 2.397 | 9,144 | 14.42% | 1.885 | 0.863 | 18.1 |
| NBSR | 2 | 5 | 3.014 | 11,498 | 6.23% | 3.749 | 2.060 | 27.9 |
| NBSR | 4 | 5 | 2.333 | 8,899 | 16.45% | 3.731 | 5.644 | 46.4 |

The primary question is answered **YES**: removing the shared destination endpoint driver produced clear NBSR scaling from one to two endpoint groups. Median throughput increased 25.75%, and every valid two-group repeat exceeded every valid one-group repeat. Four groups did not scale: median throughput fell 22.60% from two groups while p99 increased from 2.060 ms to 5.644 ms.

At two and four NBSR groups, tracked source plus destination processes consumed approximately 3.75 and 3.73 effective cores within the four-logical-processor `0x55` affinity pool. Memory stayed small relative to host RAM, with 46.4 MiB peak combined working set at four groups. There were zero errors, zero timeouts, and cleanup passed for every run. The next measured limit is therefore the affinity-constrained CPU pool, not the previous shared endpoint driver. This does not establish a whole-host, SMT, NIC, server-class, or production NBSR hardware ceiling.

Median NBSR source CPU was 0.945, 1.890, and 1.848 effective cores for one, two, and four groups. Median destination endpoint CPU was 0.941 at one group; 0.891 and 0.965 at two groups; and 0.396, 0.533, 0.432, and 0.539 at four groups. The fall in per-endpoint CPU at four groups is consistent with contention for the already saturated four-processor affinity pool. Direct displayed the same aggregate pattern.

No NBSR cell satisfied the pre-existing strict repeatability gate of CV <=5%, even after automatic extension to five repeats. Consequently, **highest strict-stable NBSR throughput is NOT ESTABLISHED** and **highest repeatable NBSR throughput under that gate is NOT ESTABLISHED**. The highest measured median is 3.014 Gbit/s at two endpoint groups; the highest valid single repeat is retained in raw evidence and is not presented as a stable ceiling.

Measured NBSR-minus-Direct deltas were +72.92%, +52.02%, and +17.57% for one, two, and four groups. They are retained but not generalized because several matched cells remained above the repeatability gate. Raw per-run data, per-group throughput, process CPU, affinity verification, memory, latency, cleanup, executable hashes, and host metadata are preserved in this directory.
