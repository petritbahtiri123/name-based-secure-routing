# B3 matched marker-monitor results — 2026-09-14

Classification: DIAGNOSTIC improvement within ten FAIL scale attempts.

Before:0288122db02dce0931326dea3e993fdf78c3d189.
After:d76cc302be4537d4f9cd26f0df135094c106cfb0.
Both release builds use Rust/Cargo1.97.1 and the same build/runtime images.
Direct and destination binaries have identical SHA-256 values in both builds;
only perf_rust_source changes. Complete source archives and build manifests are
retained. Per-cell source snapshots are excerpts; the build archives bind the
complete source, including the new marker-monitor module.

Workload:2048 live authenticated materialized connection/session/channel/stream
bundles,100 starts/s,1second QUIC keepalive,one selected Linux guest CPU,two
source runtime shards. Marker/output files use guest-native `/tmp` in both arms,
then copy to retained storage after each attempt. Five before/after pairs reverse
order on even repetitions. Timeouts, buffer settings and cleanup gates are unchanged.

| Metric | Before | After |
|---|---:|---:|
| Complete passing attempts | 0/5 | 0/5 |
| Median matching source/destination active markers before failure |1470|1774|
| Median source handshake timeouts |578|273|
| Median idle source effective cores |0.549498|0.359704|

Every pair improves these three diagnostic quantities. One source task failure
occurs in each arm and is preserved. Full workload success is still absent;
active marker counts must not be reported as an accepted scale or admissions/s.
All retained source UDP socket counters show zero drops, while destination drops
remain. This failure-only observation does not include closed sockets or identify
when drops occurred, and does not establish a production/hardware ceiling.

All ten copied cell indexes verified before the isolated container was removed.
The container retained no unique evidence after verification. Analysis code,
commands, source/binary bindings, metadata, failures and raw indexes are under
`evidence/performance/v2/b3-marker-monitor-pairs-d76cc302`.

The source-side polling cost is reduced, but residual transport progress is
UNRESOLVED. Next examine B3's one-at-a-time acceptance policy without restoring
the historical pre-armed-deadline defect. Existing two/four-guest-CPU2048 scale
results remain historical at their source; they are not a rerun of the new binary.
