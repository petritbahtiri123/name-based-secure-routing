# Native concurrent-bundle private-memory scale

MEASURED diagnostic release c5b53c66: 18/18 functional trials; 3024/3024 connections and authenticated1024-byte round trips. Successful counts16..512;1024 first attempt failed and retained separately.100offered/s,two source shards,one advertised guest core per role,Docker/WSL namespaces. Existing120-second controller and transport timeouts unchanged.

Median across repeats of active/cooldown private-resident process totals (MiB):

|Concurrent bundles|Repeats|Source active|Destination active|Destination cooldown|
|---:|---:|---:|---:|---:|
|16|3|11.160156|8.591797|8.556641|
|32|3|17.511719|13.341797|13.400391|
|64|3|30.179688|22.357422|22.375000|
|128|3|55.714844|41.525391|41.419922|
|256|3|106.531250|79.798828|79.871094|
|512|3|206.111328|156.322266|156.144531|

Final private-memory repeat CV maximum 1.079%. At least3 repeats/cell; five required when any first-three active or destination-cooldown private CV exceeds5%. Every attempt retained. All36 owned PIDs absent before stopping fixtures; no forced relays. Both final eleven ownership counters zero in every successful trial. Active/cooldown PSS,RSS,FD/thread ranges and all repetitions retained in analysis.

All memory samples used for phase totals are wholly within endpoint-local phase intervals and bind process identity,affinity,lifetime and CPU bounds. Maximum individual capture 68.086894ms is not total observer cost or neutrality proof. Source cooldown is NOT_MEASURED because source exits after ACK; destination cooldown uses the existing two-second report gate.

Retained1024-r1 failure: active markers were reached, then source control EOF after failed markers. Source276 timed_out close diagnostics held11.984048827..15.483579284seconds ready-to-release; destination554 timed_out and5other_closed. The pinned Quinn idle-expiry attribution already retained in B3_IDLE_ATTRIBUTION.md applies to timed_out only. Source terminal outcomes are incomplete:3 success,117 failure,904 missing after cancellation. Both children required owned-group kill; process absence was verified, but final resource ownership is NOT_MEASURED. This is a failed partial diagnostic, not a valid capacity/memory point or a general1024 ceiling. No timeout increased or result discarded. No remaining1024 repeats were launched after failure.

DIAGNOSTIC only: private totals include allocator/runtime/fixture retention. Connection/session/channel/stream counts co-vary, so this is bundled resource scale, not independently qualified bytes/resource. No sustainable admission, throughput, latency, allocator cause, leak freedom, long soak or physical-server claim. Nonzero destination retained pages are preserved despite zero owned-resource counters.

10 literal RED tests;308 affected tests and Ruff PASS; focused independent review53 tests PASS. Evidence review found duplicate-cell/mixed-SHA replay gaps;2 literal RED thenGREEN, exact unique labels/fixed full cohort SHA, scoped re-review PASS. Existing default-off512/1024 evidence replays with the current verifier. Rust binary hashes unchanged: no production/protocol/security change. Five verified inactive reproducible Cargo targets recovered1189752832 measured host bytes; no source/Git/authoritative evidence deleted.

Reproduce using EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md with memory_observer:true and the retained run.py/setup.py/configs/exact build manifest. Replay: python -B evidence/performance/v2/native-bundle-memory-c5b53c66/analyze.py C:/NBSR-build/native-bundle-memory-c5b53c66

Classification: PARTIAL_DIAGNOSTIC_MEMORY_SCALE_1024_FAILED. Observer qualification, marginal resource cost/retention attribution, Go-to-Rust coverage, physical-host execution and full B3/B5 acceptance remain open.
