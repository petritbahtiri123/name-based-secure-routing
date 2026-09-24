# Native same-process sequential lifecycle diagnostic

The separate cycle schema controls one source process and one destination process across 1, 2, 4, 8, 10, 16, 25, 50 or 100 sequential connections. Each connection has one authenticated session, channel and materialized stream carrying the existing 1024-byte round trip. Concurrent bundle and offered-rate semantics are not used. All transport/readiness/cleanup/transfer deadlines remain unchanged. Cycle lengths through16 retain the 120-second controller budget. Longer declared workloads use four seconds per cycle (hold plus cooldown) plus the existing120-second control allowance; peer, manager and retained replay share this exact bound. This extension follows successful16-cycle trials, not a retry of a failed short cell.

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

Current scope: implemented diagnostic orchestration, 133 affected tests/Ruff and focused independent review PASS; fresh release 4375d7ac passes three four-cycle and three sixteen-cycle namespace trials (60/60 cycles), plus six catchable EOF controls. Functional success does not establish sustainable admissions/s, qualified bytes/resource, physical-core efficiency, external hardware or B5 sustained capacity. Per-axis channel/stream scale and larger repeated-cycle workloads remain separate work. Preserve every failed/partial attempt.

Canonical evidence: `evidence/performance/v2/native-cycles-4375d7ac`. FD/thread cooldown counts remain constant (source 6/1, destination 8/2); initial RSS growth is retained, not labeled a leak or allocator cause. Source per-cycle closed ownership and both final eleven-counter reports are zero. Sixteen cycles do not satisfy the external 50-cycle authoritative memory gate.
