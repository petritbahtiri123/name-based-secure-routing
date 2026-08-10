# NBSR Performance Task P1B — Destination-Side Rust Retained-Memory Ownership Attribution

## Executive summary

**Final classification: B — Destination container/capacity retention attributed.**

Root ownership is now known at the application boundary: destination `ChannelStreams.used_stream_ids` `HashSet` retained capacity. In all three 75% runs, full-window destination working-set growth reproduced at 60.6–61.5 KB/s while replay insertions were exactly one per completed stream. Replay-capacity steps correlated 0.9981–0.9998 with working set and 0.9981–0.9997 with private bytes. When `ControlSession` dropped, logical replay entries and exact container capacity returned to zero and process WS/private bytes returned below steady-window starts. This is attribution, not an optimization or allocator/Quinn leak claim.

## Git boundaries

- Task branch: `codex/nbsr-perf-p1b-destination-memory-attribution`
- P1B base SHA: `275315e3fb6e57ee272264a6b0385813bb60a8f7`
- Underlying accepted product SHA: `4e25ee026618a502327331f352d90e26d29284e3`
- Local SHA at report generation: `b9571a5ebc071b84c724b95c9c3d08932e906024` (the final evidence commit SHA is reported in the task response because a commit cannot self-identify its own SHA)
- Pre/post remote `main`: `1938154d498b32d81a3564319969430644e8a688`
- Pre/post remote accepted branch: `4e25ee026618a502327331f352d90e26d29284e3`
- P1A branch/commit: local branch present at required `275315e3fb6e57ee272264a6b0385813bb60a8f7`; history unchanged
- Push: no; merge: no; rebase: no; pull: no
- Final Git status is reported after the local evidence commit in the task response.

## Baseline-failure verification

P1A's exact 38-node cache was recovered. Against a pristine detached accepted-base worktree, the same 37 frozen baseline/vector/manifest nodes failed and the streaming node passed; it then passed 10/10 isolated repeats. The discrepancy was a P1A test-only defect: its fixture intentionally added three diagnostic records (9 to 12) without updating the expected callback count. P1B corrected that assertion by RED/GREEN testing. No P1A product regression or new P1B failure was found. Exact node IDs and dispositions are in `baseline-failure-verification.json`.

## Files changed

- Rust: destination sampler, destination benchmark peer wiring, and bounded post-load hold; existing owner atomics and protocol owners reused.
- Python: destination launch wiring, drain phase correctness, P1B orchestration, analysis/report/checksum builder.
- Tests: sampler lifecycle/file-failure/privacy, launch opt-in, drain phase, bounded run plan, observer guardrails, and A-E classification.
- Evidence: additive `evidence/performance/rust-memory-attribution-p1b/`; P1A and accepted benchmark evidence were not modified.

## Diagnostic architecture

The destination hot path updates only fixed aggregate atomics already introduced by P1A. A dedicated `std::thread` reads immutable atomic snapshots approximately once per second and writes NDJSON through a 64 KiB `BufWriter` to a file opened before readiness/workload. It flushes every ten records and at shutdown, uses an atomic stop flag plus thread unpark, and joins after protocol shutdown and the bounded drain. Open/write/thread failures only disable evidence and never change protocol results. No hot-path file I/O, JSON, channel send, async telemetry, telemetry lock, per-stream allocation, per-object log, Tokio telemetry task, labels, or retained protocol/Quinn reference exists.

## Diagnostic inventory

| Metric | Owner | Update event | Terminal/removal event | Expected post-drain |
|---|---|---|---|---:|
| Transport Session lifecycle | `ControlSession` | construction | drop | live 0 |
| Service Channel lifecycle | `ChannelRegistry` | admission | registry/session drop | live 0 |
| Application Stream lifecycle | `ChannelStreams` | committed open | release/revoke/drop | live 0 |
| Replay entries/capacity | `ChannelStreams.used_stream_ids` | successful insert and actual `len/capacity` observation | session drop | entries 0, capacity 0 |
| Pending routes | pending channel map | insertion/observation | confirmation/drop | entries 0 |
| Channel registry | pending/active/terminal maps | transition observation | transition/drop | entries 0 |
| Stream registry | active stream map | committed open | release/revoke/drop | entries 0 |
| Audit queue | `AuditLog.events` | enqueue | pop/drop | entries 0 |
| NBSR tasks | NBSR-owned task counter | not applicable in sequential peer | not applicable | live 0 |
| Quinn connection wrappers | authenticated public wrapper | open | wrapper close/drop | live 0 |
| Quinn stream wrappers | application stream wrapper | open | close/drop | live 0 |
| Process WS/private/CPU | destination PID | one-second OS sampling | process termination | bounded drain observation |

## Observer effect

| Pair | Disabled ops/s | Enabled ops/s | Throughput delta | Disabled p99 ns | Enabled p99 ns | p99 delta | Disabled errors | Enabled errors |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 843.750 | 843.750 | 0.000000% | 585519 | 734237 | 25.399347% | 0 | 0 |
| 2 | 843.750 | 843.750 | 0.000000% | 605578 | 565607 | -6.600471% | 0 | 0 |
| 3 | 843.750 | 843.750 | 0.000000% | 554874 | 572337 | 3.147201% | 0 | 0 |
| 4 | 843.750 | 843.750 | 0.000000% | 605141 | 550667 | -9.001869% | 0 | 0 |
| 5 | 843.750 | 843.750 | 0.000000% | 569511 | 592922 | 4.110720% | 0 | 0 |

Median throughput degradation: `0.000000%` (limit 3%). Median p99 degradation: `-2.251336%` (limit 5%). Additional protocol errors: `0` (required 0). **PASS**.

## Attribution runs

| Run | Load | Warm-up | Measured | Drain samples | Offered | Completed | Errors | CPU mean | WS start | WS peak | WS end | WS post | Private start | Private peak | Private end | Private post | WS full B/s | WS final-quarter B/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rust-rust-p1b-50pct-r1 | 50% | 60s | 600s | 20s | 506250 | 506250 | 0 | 1.882% | 11227136 | 42201088 | 37494784 | 9265152 | 4677632 | 30916608 | 30916608 | 2564096 | 41123.980 | 95924.734 |
| rust-rust-p1b-75pct-r1 | 75% | 60s | 900s | 20s | 1139062 | 1139062 | 0 | 2.694% | 13209600 | 73895936 | 64454656 | 9269248 | 6950912 | 58269696 | 58236928 | 2641920 | 61537.058 | -98.961 |
| rust-rust-p1b-75pct-r2 | 75% | 60s | 900s | 20s | 1139062 | 1139062 | 0 | 2.639% | 13225984 | 73285632 | 63844352 | 9330688 | 6995968 | 57298944 | 57298944 | 2654208 | 60574.826 | 0.000 |
| rust-rust-p1b-75pct-r3 | 75% | 60s | 900s | 20s | 1139062 | 1139062 | 0 | 2.671% | 13242368 | 73895936 | 64454656 | 9273344 | 6967296 | 58187776 | 58187776 | 2592768 | 61518.648 | 0.000 |

Private-byte full/final-quarter slopes and per-operation WS/private changes are recorded exactly in `summaries/analysis.json`. All offered operations, including warm-up, also reconciled in each terminal manifest: 556,875 for control and 1,215,000 for each 75% run, with zero failures/timeouts.

## Destination owner trends

| Run | Replay inserts | High-water entries | High-water capacity | Post entries | Post capacity | Capacity growth events | Entries/op | Capacity/op | Capacity↔WS r | Capacity↔private r |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rust-rust-p1b-50pct-r1 | 556875 | 556875 | 917504 | 0 | 0 | 11 | 1.000000 | 1.647594 | 0.999275 | 0.999271 |
| rust-rust-p1b-75pct-r1 | 1215000 | 1215000 | 1835008 | 0 | 0 | 11 | 1.000000 | 1.510295 | 0.998460 | 0.998460 |
| rust-rust-p1b-75pct-r2 | 1215000 | 1215000 | 1835008 | 0 | 0 | 11 | 1.000000 | 1.510295 | 0.999828 | 0.999716 |
| rust-rust-p1b-75pct-r3 | 1215000 | 1215000 | 1835008 | 0 | 0 | 11 | 1.000000 | 1.510295 | 0.998101 | 0.998099 |

The shorter windows naturally reached lower entry/capacity thresholds than P1A's 30-minute cells: destination control reached 917,504 capacity; all 75% runs reached 1,835,008. This does not contradict P1A's later 1,835,008/3,670,016 thresholds; it confirms the same geometric container growth at destination with less completed work.

## Conservation

- `transport_sessions`: 1 - 1 - 0 = 0 (PASS).
- `service_channels`: 1 - 1 - 0 = 0 (PASS).
- `application_streams`: 1215000 - 1215000 - 0 = 0 (PASS).
- `nbsr_tasks`: 0 - 0 - 0 = 0 (PASS).
- `quic_connections`: 1 - 1 - 0 = 0 (PASS).
- `quic_streams`: 1215000 - 1215000 - 0 = 0 (PASS).

Every collection (`pending_routes`, channel registry, stream registry, audit queue, replay registry) had post-drain entries 0. Replay removals equaled inserts when the session dropped, and retained capacity returned to 0 with the owning `ChannelStreams` object.

## Correlation analysis

Observation: destination replay growth was exactly one insertion per committed stream, capacity changed in discrete `HashSet` growth steps, and WS/private bytes followed those steps with correlations above 0.998 in every cell. Observation: after owner drop, capacity and process memory fell together. Attribution: this identifies `ChannelStreams.used_stream_ids` retained container capacity as the destination application owner. Non-claim: it does not establish bytes-per-entry allocation accounting, a Rust allocator defect, a Quinn leak, or a production optimization.

The 75% final-quarter slopes plateaued near zero because each 15-minute cell had already crossed its last 1,835,008-capacity growth event. Full-window slopes reproduced strongly and the exact owner relationship plus post-drain release reproduced in 3/3, so a 30-minute extension was unnecessary.

## Tests

Fresh final commands/counts are recorded in `verification.json`. No passing claim is made here beyond commands actually recorded there.

## Evidence integrity

- Raw snapshots: each run/observer `finalized-cell/destination-diagnostics.ndjson`.
- Durable manifests: each run/observer `terminal-manifest.json`.
- Analysis: `summaries/analysis.json`; manifest: `manifest.json`; checksums: `checksums.json`.
- Rejected attempts are additive under `attempts/` and excluded from attribution.
- Existing LFS policy is reused; LFS state is recorded in `verification.json`.
- P1A and accepted benchmark evidence are unchanged by Git diff. P1A's historical checksum verifier still reports the known 68 Windows checkout normalization/LFS-availability mismatches; P1B checksums verify independently with zero mismatches. Commands and dispositions are recorded in `verification.json`.

## Final classification

**B — Destination container/capacity retention attributed.** Evidence: 3/3 reproducible positive full-window slopes; exact one-per-stream destination replay insertion; >0.998 replay-capacity/process-memory correlations; complete lifecycle conservation; synchronized replay capacity and process-memory return at post-drain.

## Ruled out

- Destination logical object leakage after session drain.
- Destination replay entries surviving session drop.
- Pending-route/channel/stream registry or audit-queue entry leakage.
- NBSR-owned task leakage in this sequential workload.
- Quinn public-wrapper leakage.
- P1A behavior non-reproduction: full-window 75% growth reproduced 3/3.
- Observer-induced protocol errors: five pairs added zero.
- Need for allocator/native attribution to explain the observed load growth.

## Still unresolved

- Exact allocator bookkeeping and bytes attributable to each `HashSet` allocation are not measured.
- Whether production policy should retain replay history for the full session is a design/security question outside P1B.
- No fix, optimization, allocator claim, Quinn-internal claim, or production-readiness claim is made.

## Recommended next hypothesis

Recommend exactly one next task: a separately approved, replay-semantics-preserving investigation of `ChannelStreams.used_stream_ids` lifetime/capacity policy that begins with frozen replay-security tests and evaluates one minimal bounded-lifetime design without changing any protocol authority. **Not implemented here.**
