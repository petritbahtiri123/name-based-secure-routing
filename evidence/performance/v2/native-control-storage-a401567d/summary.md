# Native control-storage sensitivity

Five predeclared counterbalanced pairs at a401567d use identical release peers,
256 materialized bundles, 100 offered/s, two source runtime shards, one guest
CPU per role and unchanged payload/security/timeouts. Actual filesystem types
are retained: Windows Docker bind is v9fs; Linux-local /tmp is overlayfs.
Both arms use the same separate control-watcher thread and per-role barriers.

Linux-local passes all five cells: 1,280 complete connections, all named active
markers, 1,285 point-in-time live socket records, complete release/ACK inventories
and both peers' eleven final ownership fields zero. Windows bind fails all five;
source active counts at cancellation are 78/82/72/77/82 and observed failed-marker
counts are 17/9/16/15/12. These are incomplete prefixes, not full admission totals.
Both wrappers are cancelled only after an existing failure, preserving all raw
markers, source errors, available failure UDP snapshots and forced-cleanup data.

This demonstrates functional dependence on benchmark control-root placement in
this instrumented fixture. It rules out a universal 256-connection implementation
ceiling. It does not isolate filesystem latency from selective-marker fallback,
control-watcher interference or VM scheduling, and it is not observer-qualified
causal performance attribution. Do not compare the cancellation-prefix counts
with the older 120-second failure totals or claim a latency/throughput speedup.
No production transport optimization follows. The earlier no-watcher 256 failure
and historical six failed 2048 location attempts remain separately retained.

Use Linux-local control roots for further native functional fixture progression;
keep public/raw outputs separately preserved. All command, source/build/fixture
checks, per-role resource trajectories, binding identities and failures are
retained. Peak RSS describes whole processes with coupled resources; it is not
independent bytes/connection/session/channel or a retained-memory plateau.
This shared WSL result is not physical-server, stable admission or soak evidence.
