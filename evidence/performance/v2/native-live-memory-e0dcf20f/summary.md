# Native live-bundle private-memory diagnostic

MEASURED release e0dcf20f: 6/6 trials and 4608/4608 authenticated connections/1024-byte round trips. Separate live-bundles scenario uses existing benchmark-only standard QUIC keepalive1s,100offered/s,two source shards,one advertised guest core/role,Docker/WSL namespaces. No idle/controller/transport timeout increase. This does not convert the c5b53c66 idle1024 failure into a pass.

Median process private-resident totals across repeats (MiB):

|Live bundles|Repeats|Source active|Destination active|Destination cooldown|
|---:|---:|---:|---:|---:|
|512|3|207.847656|157.095703|157.087891|
|1024|3|403.306641|307.234375|307.261719|

Private-memory repeat CV maximum0.590%; at least3 repeats,5 when first-three active/destination-cooldown CV exceeds5%. All12 owned PIDs absent, both final eleven ownership counters zero, no forced relay. Source cooldown NOT_MEASURED: source exits after ACK. Destination cooldown uses the unchanged report gate. PSS/RSS/FD/thread ranges, all repetitions and phase-contained samples retained.

Maximum individual memory capture60.263850ms is diagnostic, not total observer cost or neutrality proof. No throughput/admission/latency claim. Connections,sessions,channels and streams co-vary: derived bundled slopes include QUIC/runtime/allocator/fixture cost and cannot identify isolated object sizes or predict other scales.

13 literal RED tests;321 affected tests/Ruff PASS; independent focused review53 tests PASS. Exact mode/config/controller/environment/argv/replay binding, legacy idle compatibility and sequential-cycle rejection checked. All Rust binary hashes unchanged; no production/security/protocol change.

Reproduce EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md with bundle_mode:live-bundles and memory_observer:true; retain commands/build/config/run.py/setup.py. Replay: python -B evidence/performance/v2/native-live-memory-e0dcf20f/analyze.py C:/NBSR-build/native-live-memory-e0dcf20f

Classification MEASURED_DIAGNOSTIC_LIVE_BUNDLE_MEMORY. Observer-neutral timing, isolated resource costs, allocator/retention attribution, physical-server execution and full B3/B5 acceptance remain unproven.

Scoped evidence review clean; actual historical idle-memory16 cell replay PASS. Documented inactive Go build cache cleaned through go clean -cache after path/reparse/process checks, recovering388472832host bytes. Source,module cache,fuzz data and authoritative evidence untouched.
