# Native2048 source allocation diagnostic

MEASURED3/3FAIL_RETAINED at release8945c77a. Only allocation changes from the
preceding MIB diagnostic:sourceCPU0+4 instead ofCPU0, for existing two shards;
destinationCPU2 unchanged. Three distinct advertised guest cores, no physical
host proof. Same2048livebundles,100offered/s,private observerOFF,1skeepalive,
failure-only MIB and unchanged buffers/timeouts/binaries.

|Trial|Materialized source rows|HandshakeTimeout|Destination drops=RcvbufErrors|Last5s source/destination effective guest cores|
|---|---:|---:|---:|---|
|n2048-r1|1490|19|2274|1.152/0.916|
|n2048-r2|906|15|0|1.504/0.904|
|n2048-r3|1167|13|1116|1.13/0.888|

No completed roundtrips; partial observations are not terminal admission counts.
All6ownedPIDs absent after forced group cancellation. Final ownership unmeasured.
Source socket/MIB errors zero in trials1/3; trial2 source observation UNAVAILABLE.
Destination namespace UDP InErrors equal RcvbufErrors2274/0/1116; other error
fields zero. One failed trial has zero observed receive-buffer errors, so buffer
loss does not explain every failure. No packet/event-time causal attribution.

Giving the existing source shards a second guest core did not resolve this
workload in any attempted repeat. This is not an unbiased scaling-efficiency
estimate; cohorts are sequential, and host checksum verification overlaps.
No sustainable/strict-stable2048, physical-host ceiling or production limit claim.
The current destination benchmark runtime still defaults to one worker; affinity
alone does not change it. Next justified experiment separately exposes the
existing destination runtime knob with exact replay/config binding before trying
two destination workers. No source worker knob claim: source lifecycle uses its
own fixed shard runtimes.

Replay: `python -B evidence/performance/v2/native-live2048-source2-8945c77a/analyze.py C:/NBSR-build/native-live2048-source2-8945c77a`.
Sealed raw trial/config/build/commands and failed cleanup retained. Actual replay
verifies three-core placement, binary hashes, every failure and CPU/drop totals.
