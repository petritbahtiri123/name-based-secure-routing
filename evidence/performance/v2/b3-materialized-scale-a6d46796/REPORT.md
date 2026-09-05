# B3 materialized resource scale and same-process lifecycle

MEASURED / Windows loopback. Ten separately bound raw cohorts preserve 136
completed valid cells and five failed attempts; all 9,666 raw artifact hashes
were verified. Failed cohorts are not silently replaced or pooled with reruns.
The analysis preserves each source SHA, binary identity and setup cadence.

| Workload | Completed repeats | Result and qualification |
|---|---:|---|
| 16/32/64/128/256 bundles, 100 starts/s, 797aabf1 | 5 per count | PASS at each count; following 512 attempt failed completion |
| 512 bundles, 125 starts/s, 797aabf1 | 1 diagnostic + 3 subsequent successes | Following fourth repeat failed; not a qualified successful five-repeat cohort |
| 512 bundles, 100 starts/s, 36e8970b | 5 | PASS; previous completion failure did not recur, cause remains unresolved |
| 1024 bundles, 100 starts/s, 36e8970b | 0 | FAILED_SETUP: 547 ready diagnostics and 477 handshake timeouts; no active measurement or completed-client success |
| 1/2/4/8/16/32 channels, one stream/channel, 797aabf1 | 5 per count | PASS; channel and stream cost are coupled |
| 8/16/32/64/128/256/512 streams, eight fixed channels, a6d46796 | 5 per count | PASS after concurrent audit-consumer repair |
| 50 cycles, one session/channel and 64 materialized streams/cycle, a6d46796 | 5 | 250 same-process cycles completed; ownership CLEAN in the measured scopes |

Earlier streams attempts remain retained: 797aabf1 stopped on a Windows marker
PermissionError after two successful cells (INVALID_HARNESS); 36e8970b completed
30 cells through 256 streams, then 512 failed AuditUnavailable before active
sampling. The latter was the missing concurrent setup audit consumer, repaired
without changing mandatory audit generation or its 1,024-event fail-closed cap.
The retained source audit high-water fell from 536 events at the old 256-stream
cell to 5 at the new 512-stream cell; destination high-water was 792 and 512,
respectively. These are different cardinalities and are not a timing comparison.
See ../b3-audit-consumer-36e8970b/REPORT.md for literal RED/GREEN and tests.

## Memory accounting

DERIVED least-squares slopes below use median active Windows private bytes at
each count. They include runtime, transport, allocator and harness memory and
are not isolated NBSR object sizes or allocation counts. Incremental slopes use
active minus same-cell idle samples; the idle setup itself can depend on count.
Different source/cadence/resource-axis cohorts remain separate.

| Series | Source active bytes/unit | Destination active bytes/unit | Combined active bytes/unit | Combined incremental bytes/unit |
|---|---:|---:|---:|---:|
| 16..256 connection+session+channel+stream bundles |473841.20|363656.26|837497.46|787485.94|
| 1..32 channels, one stream each |24957.36|27629.81|52587.17|53403.75|
| 8..512 streams, eight fixed channels |19738.67|20478.64|40217.31|40209.50|

The separately measured 512-bundle cohort's median active private bytes were
244,744,192 source and 188,911,616 destination. It is not appended to the earlier
16..256 regression across changed source. At 512 streams in the clean a6d46796
cohort, medians were 11,816,960 and 12,374,016 bytes. The full ranges, five-repeat
CVs, idle baselines and derived slopes are in analysis.json. No independent
bytes/connection, bytes/session or pure bytes/channel claim follows from the
coupled axes. No host memory ceiling or allocator-heap attribution is proven.

## Ownership and retention

The original runner gates eight counters. Additional analysis of retained raw
diagnostics verifies all eleven current-live/current-entry counters, including
pending routes, channel registry and stream registry, at both roles' final
cleanup in every completed cell. In the five cycle repeats, all fifty source
per-cycle closed snapshots also have all eleven counters zero. Destination
per-cycle zero is not asserted from its final-only cleanup series. Final
process exits and the same-process identities remain in retained records.

| Cycle repeat | Source private cooldown delta | Destination private cooldown delta | Source/destination handle delta |
|---|---:|---:|---|
|1|28672|1216512|0/0|
|2|24576|32768|0/0|
|3|167936|720896|0/0|
|4|-28672|577536|0/0|
|5|172032|430080|0/0|

Private deltas compare median cycle49 cooldown with cycle0. Positive second-half
private-byte slopes remain explicit in the analysis. Ownership is CLEAN in the
measured scopes; private-memory cause is INCONCLUSIVE. Zero tracked resources
and unchanged handles neither prove zero untracked allocations nor prove an
allocator-only explanation. These results do not establish a leak or a bounded
private-memory plateau. Requests and both endpoint stream handles were retained
before common release, with unchanged response and send-ACK completion.

## Reproduction and remaining work

Build the recorded release source first; run_b3_v2.py copies existing binaries
from --target and does not build them. Use a fresh output directory:

```powershell
$env:CARGO_TARGET_DIR='C:/NBSR-build/b4b-task4k'
cargo build --release --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source --bin wp8_interop_server
python scripts/run_b3_v2.py --output C:/NBSR-build/b3-streams-reproduction --target C:/NBSR-build/b4b-task4k --axis streams --counts 8 16 32 64 128 256 512 --repeats 5 --materialized-streams
python scripts/run_b3_v2.py --output C:/NBSR-build/b3-cycles-reproduction --target C:/NBSR-build/b4b-task4k --axis cycles --counts 50 --repeats 5 --materialized-streams
```

A separate fixed-32-channel series is planned within existing authority and
transport bounds; it is NOT_RUN here. The 1024-bundle setup stall remains
UNRESOLVED, not a production or hardware capacity claim. Allocation/native-heap
attribution, near-ceiling soak and external-server results remain separate gates.
Raw evidence is authoritative at the exact external paths in external-inputs.json;
do not delete it as disposable build output. The retained packaging script
recomputes analyses and validates existing ownership observations without
modifying old raw results. No build, test or Docker workload ran during timing;
lightweight read-only inspection and external planning were performed.
