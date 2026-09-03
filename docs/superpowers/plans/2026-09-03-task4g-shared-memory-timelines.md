# Task 4g: bounded shared-memory timeline observer

Approved scope: benchmark-only diagnostics, no production, frozen authority,
transport API, deadline, logging, lifecycle coordination, or sharding changes.
Start baseline: `e4ce037ebaf4024609497aec5fc594720812386e`.

## Implementation and verification

1. RED: parent mapping bounds/retention/validation and Rust stage-order tests.
2. GREEN: parent-owned Windows pagefile mapping, 64-byte header and one
   256-byte record per client/accept slot, maximum 1024 records per process.
   Mapping names are private random run identifiers, not client identities.
3. Integrate fixed QPC milestones in the existing benchmark lifecycle paths.
   Source client IDs and destination accept slots are separate namespaces.
   No matching based on ordinal or nearest timestamp is permitted.
4. Read and persist the mappings only after all measured processes exit.
   Preserve original `.bin` mappings even when validation rejects their content.
   Existing admission elapsed time still ends when the parent observes the
   source process exit. Shared memory never advances lifecycle completion.
5. Run release smoke validation, focused Rust/Python tests, formatter, clippy
   with warnings denied, dependency/privacy checks, and review the scoped diff.
6. Run 128 and 256 clients, alternating OFF/ON order across matched pairs;
   minimum three repeats, five when goodput or admission-rate CV exceeds 5%.
   Each run retains the existing 20-second forwarding window and 2-second warmup.
7. Gate on absolute median goodput/admissions/latency impact <=5%, admission
   success shift <=1 percentage point, and zero new cleanup failures. Relevant
   latency includes successful handshake and admission/forwarding p50/p95/p99.
8. If rejected, report PARTIAL/UNRESOLVED and stop without ETW or optimization.
   If accepted, assess whether lightweight ETW can distinguish the remaining
   runtime, timer, network, or admission-stage alternatives without distortion.
9. Store environment/source/binary hashes, original logs, checksums and report.
   One atomic commit; stop before optimization, sharding or B3-v2.

## Observation semantics and limits

`requested` is slot claim, `task_started` is the first instrumented task entry,
and `connect_first_poll` is the first poll of the existing connect/accept future.
`connected` is successful authenticated transport return. Control hello and
route milestones observe existing operations; `admitted` follows channel bind,
not application stream acceptance. `cleaned` observes local lifecycle return/drop;
the existing zero-ownership diagnostics remain the independent cleanup authority.

Connect/accept poll count and QPC poll duration are fixed-size diagnostic counters,
not proof of ready time, blocking, timer expiry, packet loss or causal attribution.
The frozen accept API combines incoming arrival and handshake, so no invented
internal handshake milestones are reported. Terminal event kind is retained;
exact source errors remain in existing stdout, destination errors in drained stderr.
The reserved numeric error-code field is zero (no additional error API).

Mapping validation rejects missing claims/finalization/cleanup, invalid guards,
duplicate/order violations, overflow flags and incomplete successful prefixes.
Failure before first task poll can retain a terminal cancellation without inventing
a task-start timestamp. All mappings are closed by scoped owners after extraction.
No names, payload, keys, grants or authorization contents enter timeline records.

Rollback: revert the single Task-4g commit. Historical Task-4f evidence is untouched.
Status: implementation and focused verification complete. Twenty matched runs
finished; both observer gates rejected. Attribution PARTIAL / UNRESOLVED.
No ETW, optimization, sharding or B3-v2 was started. See
`evidence/performance/v2/b4b-task4g-e4ce037ebaf4/REPORT.md` for results and the
explicit distinction between captured and post-review code.
