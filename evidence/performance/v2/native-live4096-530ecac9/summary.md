# Native 4096 live-bundle diagnostic

MEASURED release530ecac9: three attempts, all FAIL_RETAINED before the common
active hold. Zero completed application round trips. Requested4096,100offered/s,
two source shards on guestCPU0+4, destination two runtimeworkers on guestCPU2+6;
one-Hz private-memory observer ON, existing1skeepalive, unchanged timers/buffers.

|Attempt|Materialized observations|HandshakeTimeout|Destination cumulative socket drops|Last5s source/destination effective-core estimate|
|---|---:|---:|---:|---:|
|n4096-r1|2031|1|111|1.586/1.402|
|n4096-r2|3605|8|4061|1.256/1.702|
|n4096-r3|2500|39|5336|1.612/1.746|

Materialized observations are not accepted successful application connections.
Every destination socket-drop sum equals its namespace UDP RcvbufErrors/InErrors
counter at the failure snapshot. Source socket accounting is UNAVAILABLE where
its strict duplicate-inode validation fails; never substitute zero. These are
cumulative snapshots without packet timing or per-timeout causal attribution.
CPU is DERIVED from contained tick samples, not physical-core utilization proof.
No host-wide resource ceiling or specific production hotspot is established.

All six owned PIDs absent before container stop. Forced owned-child cancellation
was required; final runtime ownership is NOT_MEASURED, not zero. No forced local
management relay cleanup. Every raw failure, memory/resource sample and marker
is retained. Initial failure was followed by two explicitly declared unchanged
attempts; no unfavorable result was discarded. No CV-qualified timing/memory
statistic is claimed from this failed cohort. Host read-only integrity work
and fixture cleanup overlapped trials, so this is not isolated causal profiling.

The harness now permits4096 live bundles and a source-only20000-entry archive
bound; the512MiB byte limit and all archive path/link protections remain intact.
The failing workloads did not reach the full16384-marker success inventory;
that complete real collection path remains NOT_PROVEN despite focused tests.
Idle mode still rejects4096. Rust release hashes are unchanged.

Accepted native memory-observed scale remains2048 at8e0b28a2,three functional
passes. Neither stage establishes sustainable admissions/s, strict-stable
throughput, a production connection ceiling or a qualified long soak.
Residual transport progress remains UNRESOLVED / PLATFORM_DIAGNOSTIC_LIMIT;
no speculative production change is justified by these snapshots.

Replay:
`python -B evidence/performance/v2/native-live4096-530ecac9/analyze.py C:/NBSR-build/native-live4096-memory2-530ecac9 C:/NBSR-build/native-live4096-followup-530ecac9`.

Safe maintenance:12 verified exited2048 fixtures removed only after raw checksums
and PID absence were verified.1092550656 logical Docker writable bytes removed;
host free space decreased during concurrent work, so no host SSD recovery claim.
Images, bind-mounted evidence/private fixtures, source and Git remained intact.
