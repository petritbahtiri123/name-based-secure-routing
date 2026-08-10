# NBSR Performance Task P1A — Rust Retained-Memory Ownership Attribution

## Result

Primary classification: **E — Still inconclusive**.

The positive destination-process late-run slope reproduced in all three 75% runs, but destination-process internal Rust ownership snapshots could not be collected within the observer-effect safety boundary. The precise invisible layer is the destination process's `ControlSession`/channel-stream replay registry, audit queue, Quinn wrapper, and task ownership time series, together with a complete destination post-drain process-memory observation. Source-side owner metrics are strongly correlated but are not treated as proof of destination ownership.

## Git and scope

- Task branch: `codex/nbsr-perf-p1-rust-memory-attribution`
- Required base: `4e25ee026618a502327331f352d90e26d29284e3`
- No push, merge, rebase, allocator change, optimization, protocol change, security change, capacity change, or accepted-evidence overwrite occurred.
- Accepted capacity: Rust-to-Rust 1,687.5 ops/s; loads: 843.75 (50%) and 1,265.625 (75%).

## Observer effect

- Five paired comparisons, 843.75 ops/s, 5-second warm-up, 30-second measured window.
- Median throughput degradation: `0.000000%` (limit 3%).
- Median p99 degradation: `1.105339%` (limit 5%).
- Additional protocol errors: `0`.
- Source-only diagnostic build gate: `PASS`.
- Destination-emission attempts are retained under `attempts/`; they produced protocol/finalization errors and therefore were rejected rather than used for attribution.

## Primary run results

All primary runs used a 60-second warm-up, 1,800-second measurement, one-second cadence, and 20-second explicit drain. Bytes/completed-operation is an observational ratio, not allocation ownership.

| Run | Offered | Completed | Errors | WS begin | WS peak | WS end-load | WS full slope B/s | WS final-quarter B/s | Private final-quarter B/s | WS change/op | Source replay entries end-load | Source replay entries post-drain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rust-rust-p1a-50pct-r1 | 1518750 | 1518750 | 0 | 11153408 | 73224192 | 63782912 | 34060.740 | 0.000 | 0.000 | 34.653171 | 1568533 | 0 |
| rust-rust-p1a-75pct-r1 | 2278124 | 2278124 | 0 | 12546048 | 137175040 | 118296576 | 61143.187 | 59367.418 | 59478.910 | 46.420005 | 2354062 | 0 |
| rust-rust-p1a-75pct-r2 | 2278124 | 2278124 | 0 | 12541952 | 137170944 | 118292480 | 61146.345 | 59133.050 | 59248.545 | 46.420005 | 2352798 | 0 |
| rust-rust-p1a-75pct-r3 | 2278124 | 2278124 | 0 | 12546048 | 137170944 | 118292480 | 61144.559 | 59364.461 | 59475.948 | 46.418207 | 2354062 | 0 |

Destination post-drain memory is not a complete 20-second series because the accepted server exits after its existing completion acknowledgement. This missing evidence is part of classification E.

## Owner reconciliation

For Transport Sessions, Service Channels, Application Streams, NBSR tasks, Quinn connections, and Quinn streams, the equation is `created - terminal_success - terminal_failure_or_cancel = current_live`. In every source-side primary run the equation reconciled and post-drain live counts were zero.

Application Streams and Quinn stream wrappers had high-water live count 1 and returned to zero continuously. Pending-route, channel-registry, stream-registry, and audit-queue current entries returned to zero after drain. The source replay/used-stream set grew once per completed Application Stream—1,569,375 entries at 50% and 2,354,062 entries in each 75% run—then returned to zero when the session terminated. Its high-water retained HashSet capacity was 1,835,008 at 50% and 3,670,016 at 75%.

The matching source/destination process slopes and source replay growth implicate replay history as a hypothesis only. They do not establish destination causation without destination internal snapshots.

## Diagnostic inventory

| Metric | Owner | Increment/observation event | Terminal/removal event | Expected post-drain |
|---|---|---|---|---:|
| `transport_sessions_*` | `ControlSession` | `ControlSession::new_inner` | `ControlSession::drop` | live 0 |
| `service_channels_*` | `ChannelRegistry` | pending admission | registry/session drop | live 0 |
| `application_streams_*` | `ChannelStreams` | committed stream open | release, revoke, or drop | live 0 |
| `pending_routes_*` | pending channel map | map observation after admission/confirmation | confirmation/drop | entries 0 |
| `channel_registry_*` | pending/active/terminal maps | aggregate map observation | transition/drop | entries 0 |
| `stream_registry_*` | per-channel stream maps | committed open | release/revoke/drop | entries 0 |
| `audit_queue_*` | `AuditLog.events` | enqueue | pop/drop | entries 0 |
| `replay_state_*` | `ChannelStreams.used_stream_ids` | committed unique stream ID | session drop | entries 0 |
| `nbsr_tasks_*` | NBSR-owned tasks | no applicable owned task in accepted sequential workload | not applicable | live 0 |
| `quic_connections_*` | authenticated Quinn wrapper | successful authentication | wrapper drop | live 0 |
| `quic_streams_*` | application-stream wrapper | wrapper creation | wrapper drop | live 0 |

Caches and separate channel queues were not present in this accepted sequential workload. Quinn internals, Tokio runtime-global tasks, allocator arenas, and native transport allocations remain intentionally invisible.

## TDD, correctness, and security

Focused RED evidence retained in the task history:

- Rust diagnostics API initially failed to compile because the module was absent; GREEN: 3 tests, later 4 tests.
- Durable diagnostics test initially failed because `diagnostics.ndjson` was absent; GREEN: 6 tests.
- Stream routing test initially failed because diagnostic lines were interpreted as completion metadata; GREEN after separate routing.
- Attribution-plan test initially failed on the drain bound; GREEN with the explicit 20-second drain.
- Classification fixtures cover A/B/C/D/E behavior and the two-of-three rule.

Fresh final validation: Rust passed 124 tests with zero failures; `cargo fmt --check`, Ruff, and Clippy with `-D warnings` passed. The complete Python repository run produced 1,730 passed, 1 skipped, and 38 failures. Thirty-seven failures are frozen baseline/vector digest or manifest checks affected by the Windows worktree checkout; one performance streaming timing assertion expected 9 callback lines but observed 12. The performance suite separately produced 101 passed and that same one timing failure. These failures are disclosed rather than repaired because modifying frozen authorities or unrelated timing behavior is outside P1A.

## What is ruled out

- Reproducibility failure: ruled out; three of three 75% slopes were positive and closely matched.
- Source-side live Application Stream, Quinn stream, session, or channel leakage: ruled out by conservation and zero post-drain live counts.
- Source pending-route, active stream-registry, or audit-queue entry retention: ruled out by zero post-drain entries.
- Protocol errors in accepted primary runs: ruled out; every offered operation completed and errors were zero.
- Safe destination attribution: not established; attempts exceeded the zero-additional-error observer boundary.

## What remains unresolved

Whether destination process memory is owned by its session-lifetime replay/used-stream history, another destination container, Quinn/native state, or allocator retention cannot be distinguished without safe destination internal snapshots and complete destination post-drain process sampling.

## Recommended next hypothesis

Export destination aggregate snapshots through one pre-opened append-only file from a non-Tokio sampler, prove zero additional protocol errors in five paired comparisons, then repeat only the three 75% attribution runs. Do not change replay semantics or fix retention until that evidence is reviewed.
