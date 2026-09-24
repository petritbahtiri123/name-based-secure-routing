# Native same-process per-channel stream scale

MEASURED Docker/WSL namespace release b9a29408: three repeats each of16/32/64
concurrent materialized streams within one authenticated session/channel, four
sequential cycles per repeat. 9/9 functional trials,36/36 cycles,1344/1344
1024-byte round-trip operations PASS. All18 owned PIDs absent before container
stop, no forced relay cleanup. Source per-cycle closed and both final eleven
ownership counters zero. Destination per-cycle closed ownership not separately
measured. Exact active stream cardinality and sample identities independently replayed.

Final cooldown RSS ranges (source/destination):16 streams9.125–9.25/6.25–6.5MiB;
32 streams9.5–9.625/6.625–6.875MiB;64 streams10.125–10.375/7.25–7.5MiB.
First-three repeat RSS CV below2.16% in all cells, so three repeats satisfy the
predeclared extension rule. Cooldown FD/thread counts remain6/1 and8/2.
These are diagnostic sampled RSS totals, not qualified incremental bytes/stream,
private memory, allocator attribution or leak freedom. Four cycles are not a
long-run stream-cardinality soak. RTT includes deliberate two-second holds.
No new throughput, latency, sustainable admission or physical-core claim.

14 literal RED cases,208 affected tests and Ruff PASS; focused independent
review clean with37 scoped tests PASS. Rust release hashes unchanged. Only native
harness shape plumbing/replay changed; no production/protocol/security changes.
Build completed before the first coordinator trial. Raw commands/configs,
setup/runner, every valid trial, release manifest and checksums retained.

Safe cleanup of two verified inactive Cargo targets recovered817160192 host
bytes; no evidence/source/Git/private fixtures removed. This is infrastructure
maintenance, not a performance optimization.

Reproduce via docs/benchmarks/NATIVE_SAME_PROCESS_CYCLES.md with streams16/32/64.
Replay: python -B evidence/performance/v2/native-streams-b9a29408/analyze.py
C:/NBSR-build/native-streams-b9a29408 (one command line).
Channel scale, qualified private-memory cost, physical servers and B3/B5 final
acceptance remain open. Classification PASS_FUNCTIONAL_STREAM_CYCLES;
memory DIAGNOSTIC_RSS_ONLY_NO_ALLOCATOR_ATTRIBUTION.
