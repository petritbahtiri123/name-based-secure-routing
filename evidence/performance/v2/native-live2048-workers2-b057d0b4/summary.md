# Native2048 destination runtime/allocation diagnostic

MEASURED releaseb057d0b4: 3 PASS_FUNCTIONAL / 0 FAIL_RETAINED across3fixed trials;
6144 completed authenticated connections/1024-byte roundtrips in passed trials.
Existing source two shards retainCPU0+4. Destination expandsCPU2 toCPU2+6 and
explicitly selects2existing benchmark runtimeworkers. Same2048livebundles,
100offered/s,1skeepalive,memoryobserverOFF and unchanged buffers/timeouts.
Rust binary hashes unchanged; no production/security/wire modification.

All passed trials have both final eleven ownership counters zero, owned source
and destination PID absence before container shutdown, and no forced relay.
Any failed trial is separately retained in analysis. Private/PSS memory unmeasured.
No UDP snapshot on success: absence of failure-only data does not mean zero drops.

|Passed trial|Source effective cores before active|Destination effective cores before active|
|---|---:|---:|
|n2048-r1|0.901|1.187|
|n2048-r2|0.842|1.08|
|n2048-r3|0.96|1.273|

CPU values are tick-quantized contained-sample estimates over10seconds before
the earlier active marker, not strict lower bounds or physical-core proof.
This sequential allocation+worker experiment is not a counterbalanced causal
measurement or scaling-efficiency result. It must not turn functional completion
into sustainable admissions/throughput or long-run stability. Prior failures,
including zero-drop failures and incomplete destination cardinality, remain valid.

Destination-only control is bound config/CLI/controller/environment/exactargv/
requested-actual replay. Omission preserves old evidence. Source lifecycle ignores
the outer worker flag, so explicit source workers are rejected; fixed source
shards remain unchanged. Sequential cycles reject this bundle-only setting.
Validation:4initialRED,1cycleRED,1reviewRED;121affectedtests/RuffPASS;scopedreview
finding fixed;actualhistoricale0dcf20f512pair replayPASS. Current release built
successfully; replayed all outcomes/indexes and per-role identity/placement.

Replay: `python -B evidence/performance/v2/native-live2048-workers2-b057d0b4/analyze.py C:/NBSR-build/native-live2048-workers2-b057d0b4`.
Scope: Docker/WSL four advertised guest cores, not external physical/server/NIC
validation. No new strict-stable Gbit/s, sustainable admissions, qualified observer,
soak, or global maximum connection claim. Next: same configuration private-memory
observer cohort, preserving any failure and applying resource CV repeat rule.

Scoped evidence review corrected unconditional UDP-measured wording: no failure snapshots in this all-pass cohort. No calculation or workload change.
