# Native2048 observer-off diagnostic

MEASURED:3/3 fixed attempted trials FAIL_RETAINED before the full active gate.
Release1c103518,2048 live bundles,100offered/s,two shards,source guestCPU0,
destination guestCPU2,existing1s keepalive and unchanged timeouts. Optional
private-memory observer OFF; ordinary resource observation remains enabled.

|Trial|Materialized source observations|HandshakeTimeout outcomes|Destination cumulative socket drops|Last5s source/destination effective guest cores|
|---|---:|---:|---:|---|
|n2048-r1|1355|56|33|0.888/0.952|
|n2048-r2|1032|4|0|0.92/0.922|
|n2048-r3|1496|9|752|0.876/0.948|

Zero completed roundtrips recorded; materialized rows are partial observations,
not all terminal admissions. Both owned process groups were cancelled/killed
on each failed trial and all6PIDs absent before container shutdown. Final
ownership counters NOT_MEASURED. Source UDP snapshots UNAVAILABLE, not zero.
Private/PSS memory unmeasured. All failures and partial telemetry preserved.

The failure occurs without the optional private-memory observer; removing it
is not a demonstrated fix. This sequential off cohort is not counterbalanced
with the earlier on cohort and overlaps host checksum verification. Lower VM
monotonic timestamps suggest a changed boot epoch; a restart is inferred, not
independently verified. It does NOT qualify observer neutrality or quantify its
causal effect. Destination zero-drop failed repeat also prevents treating live
socket drops as a necessary observed symptom across all failures; snapshots do
not measure closed sockets or full event history.

Last5s tick-quantized CPU estimates show both allocated guest roles busy;
physical host placement and per-timeout causation remain unproven. No stable
capacity, useful throughput, sustainable admission, buffer-size fix, hardware
ceiling or production bottleneck claim. Next failure-only namespace MIB capture
can distinguish aggregate RcvbufErrors from other UDP errors without sampling
normal workload or changing buffers/timeouts.

Replay: `python -B evidence/performance/v2/native-live2048-split-off-1c103518/analyze.py C:/NBSR-build/native-live2048-split-off-1c103518`.
Raw driver/config/release/environment/telemetry/cleanup and exact outcomes sealed.

Scoped read-only evidence review found no further important issue after limiting the boot-epoch statement to an inference.
