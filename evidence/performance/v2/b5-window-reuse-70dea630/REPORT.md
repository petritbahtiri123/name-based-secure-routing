# B5 latency-buffer allocation correction

**Benchmark-only measured allocation improvement. Long soak NOT_PROVEN.**

Clean source 70dea630 has 18 valid one-core reference repeats with ownership
reports: Direct/NBSR baseline 0.862068/0.873913 Gbit/s STABLE; depth2 DEGRADED,
depth4 SATURATED. NBSR sampled CPU is approximately 18,369.65 ns/op and 0.980
effective cores. These are finite Windows loopback results, not server maxima.
Three separate after-hold fixed-load diagnostics passed at approximately
0.585 Gbit/s, CV 0.066%, achieved/offered 95.70-95.81%, both final reports zero.

The new counterbalanced observer comparison passed its first off/on pair,
then on-r2 failed the existing private-memory growth guard. No replacement.
Source private bytes rose 2,883,584 to 3,325,952 (432 KiB), while all eleven
live ownership gauges stayed constant. This is not a proven leak; the observer
prefix cannot qualify. All failed raw evidence remains retained.

Source inspection and literal allocation-counter RED tests identified a full
replacement latency vector per publication and a copy for percentile sorting.
RED measured one large serializer allocation and three replacement allocations
in three empty publications. The test-only thread-local counter counts blocks
at least 32 KiB, excluding setup.

The sole publisher now owns a second prepared vector, swaps it with the
collector, sorts the completed window outside coordinator locks, serializes
through the existing immutable callback, clears and reuses the storage.
Both Direct and NBSR share this benchmark code. Two buffers are prepared before
timing, replacing transient replacement/copy allocations. No samples, counts,
stride, capacity limits, percentiles, deadlines, publication ACK semantics,
security checks or memory-growth thresholds were weakened. Production code
is unchanged. Small group/formatting allocations remain; this is not zero
allocations/op.

GREEN: zero large allocations in serialization and three full publications
of 8,192 reverse-ordered samples each; exact counts and p50/p95/p99 retained.
Invalid replacement storage latches failure without erasing samples.
Release tests: Direct 7 PASS; source 88 PASS/1 pre-existing ignored timer
experiment. Python 101 focused PASS; actual release lifecycle/sampling 2 PASS.
Release build, rustfmt, release Clippy including tests with -D warnings and
diff checks PASS. One focused parent review found no Important issue in buffer
ownership, lock ordering, sink failure, overflow or final publication.

All 276 indexed artifacts in raw-evidence.json were freshly verified. Tested
working source and release binaries are retained in
C:/NBSR-build/b5-window-reuse-70dea630. Raw logs retain original line endings.
No authoritative data was deleted.

The process memory effect still needs live reruns; these allocation tests do
not attribute every private byte. No production speedup, leak fix, neutral
observer or sustained-capacity claim follows. Next: same-load live rerun,
then matched reference/observer/long-soak qualification. Do not pool failed
cohorts with replacements.
