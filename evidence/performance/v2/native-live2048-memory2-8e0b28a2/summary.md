# Native2048 two-worker private-memory diagnostic

MEASURED release8e0b28a2:3/3 trials PASS_FUNCTIONAL,
6144/6144 authenticated connections/1024-byte roundtrips.
2048livebundles,100offered/s,two source shards onguestCPU0+4,two destination
runtimeworkers onguestCPU2+6. Existing1skeepalive,buffers/timeouts unchanged.
Optional private/PSS memory observer enabled at most1Hz; neutrality UNPROVEN.

Across-repeat medians of phase-contained process private resident totals:

|Phase|MiB|
|---|---:|
|Source active|806.908203|
|Destination active|546.267578|
|Destination cooldown|546.917969|

Maximum private-memory repeat CV0.2010%. Minimum3validrepeats,5ifanyfirst-three
resource CV>5%. All outcomes retained. All6ownedPIDs absent before
container shutdown; both final eleven ownership counters zero; no forced relays.
Source cooldown NOT_MEASURED: source exits afterACK. PSS,RSS,FD/thread ranges and
all repeats remain in analysis/raw. Maximum individual memory capture379.937470ms
is diagnostic, not total observer overhead or neutrality proof.

Connection/session/channel/stream counts co-vary: these are process totals,
not isolated bytes/resource, allocator/leak attribution, or extrapolation to
4096. No throughput/sustainable-admission/latency/soak/physical-server claim.
This does not erase older single-worker failures or qualify observer effect;
cohorts are sequential and host checksum verification overlaps runtime.

Replay: `python -B evidence/performance/v2/native-live2048-memory2-8e0b28a2/analyze.py C:/NBSR-build/native-live2048-memory2-8e0b28a2`.
Exact cohort labels/SHA/config/runtime/allocation, raw outcomes, ownership,
phase-contained samples and CV repeat policy independently replayed. Rust release
hashes unchanged; no production/security/wirechange. Broader B3 isolated-resource
attribution, qualified B5 soak, 4096 native measurement and final freeze remain open.
The earlier b057d0b4 cohort remains 2 PASS / 1 observer-invalid outcome; the
owned-exit memory observer fix at 8e0b28a2 leaves unavailable memory unmeasured
and preserves strict identity, live permission errors and terminal continuity.
