# Native same-process sequential lifecycle diagnostic

The separate cycle schema controls one source process and one destination process across 1, 2, 4, 8, 10, 16, 25, 50 or 100 sequential connections. Each connection has one authenticated session. Optional `channels` selects1..32 service channels (default1). Optional `streams` selects 1..64 concurrent materialized streams, each carrying the existing 1024-byte round trip (default1). Concurrent bundle and offered-rate semantics are not used. All transport/readiness/cleanup/transfer deadlines remain unchanged. Cycle lengths through16 retain the 120-second controller budget. Longer declared workloads use four seconds per cycle (hold plus cooldown) plus the existing120-second control allowance; peer, manager and retained replay share this exact bound. This extension follows successful16-cycle trials, not a retry of a failed short cell.

Use the role objects from `EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md` with fresh disjoint private lifecycle/output roots and an exact clean release build. Replace the top-level schema/count/rate/shards fields with:

```json
{"schema":"nbsr-native-cycle-coordinator-v1","source_sha":"<exact 40-hex release SHA>","cycles":4,"source":{},"destination":{}}
```

The empty role objects above are placeholders for the complete existing role objects, not runnable credentials or an example claiming server access. Run:

```text
python3 -B -m scripts.performance.linux_native_cycle_run --config /srv/config/cycles.json --output /srv/evidence/cycles-r1
```

The management stream prepares the source before destination readiness. For each ordinal it arms destination then source, verifies both active snapshots, holds at least two seconds, releases destination then source, waits for source ACK, and cools down at least two seconds before the next start. Final source and destination report gates keep both processes observable through the final cooldown. Catchable cancellation/EOF uses the existing owned-child cleanup and bounded evidence collection.

Independent replay checks exact sequential commands, source/build/authority identity, every cycle completion observation, one PID/start-time epoch per role, cycle event ordering, local hold/cooldown intervals, point-in-time socket identity and explicit final eleven-counter zero cleanup. ACK is not proof that all background resources are already reclaimed. Retained RSS/private memory is not automatically a leak. Socket snapshots do not prove continuous ownership.

Current scope: implemented diagnostic orchestration, 133 affected tests/Ruff and focused independent review PASS; fresh release 4375d7ac passes three four-cycle and three sixteen-cycle namespace trials (60/60 cycles), plus six catchable EOF controls. Functional success does not establish sustainable admissions/s, qualified bytes/resource, physical-core efficiency, external hardware or B5 sustained capacity. Qualified private-memory measurements remain separate work; later cycle/stream stages are listed below. Preserve every failed/partial attempt.

Canonical evidence: `evidence/performance/v2/native-cycles-4375d7ac`. FD/thread cooldown counts remain constant (source 6/1, destination 8/2); initial RSS growth is retained, not labeled a leak or allocator cause. Source per-cycle closed ownership and both final eleven-counter reports are zero. That sixteen-cycle stage did not satisfy the external 50-cycle workload length. The later b7672a57 cohort completes three 50-cycle repetitions (150/150), CV source 1.37% / destination 2.0%, with final and source per-cycle ownership zero. See `evidence/performance/v2/native-cycles50-b7672a57`. Source RSS is flat in every second half; destination has one retained 128 KiB late step. Private-memory cost/allocator attribution and full B3 acceptance remain unqualified. Request RTT includes the deliberate materialization hold and must not be reported as data-plane latency.

Stream-scale configuration at b9a29408: add `"streams":16` (or32/64) to the same cycle schema. Each cycle must complete exactly that many uniquely indexed samples and show matching source/destination materialized ownership counts. Streams>1 require channels1; channels>1 require streams1. Combined axes are not declared. Default1 preserves earlier evidence. Use at least3 repeats, extending to5 when resource CV exceeds5%; retain failed runs.

September25: native per-channel stream scale at b9a29408 passes3 repeats each
16/32/64 streams,4cycles:36/36 cycles and1344/1344 round trips.18 owned PIDs
absent; source per-cycle/both final ownership zero; cooldown FD/thread6/1 and8/2.
RSS repeat CV<2.16%; no5-repeat extension required. Canonical native-streams-b9a29408
retains all raw evidence and independent replay. Diagnostic RSS totals only;
no qualified bytes/stream, allocator, throughput or physical-hardware claim.
Channel scale and qualified memory/B3/B5 closure remain open. No production change.

Channel configuration09b36ece: add `"channels":16` or32, leaving streams1. Supply a fresh authority directory for every service ordinal00..15/31 using the existing fixture generator. All public fixture hashes must match across peers and remain unchanged.

September25: native channel-axis scale09b36ece completes3 repeats each16/32
channels,1stream/channel,4cycles:24/24 cycles and576/576 operations PASS.
12 owned PIDs absent; source per-cycle/both final ownership zero; FD/thread6/1,
8/2. Final RSS CV<1.12%. Package native-channels-09b36ece. This closes native
channel workload execution; private-memory/bytes-resource/observer qualification
and full B3/B5 remain open. No production change or new capacity claim.
