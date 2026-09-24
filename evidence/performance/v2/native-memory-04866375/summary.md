# Native private-resident/PSS diagnostic scale

MEASURED release04866375 in Docker/WSL namespaces:15/15 trials,60/60 cycles,1548/1548 authenticated1024-byte round trips. Three repeats each baseline1channel/1stream,16/32channels with1stream each, and16/64streams in1channel. Four cycles/trial; both roles retain one process epoch. All30 owned PIDs absent before container stop, no forced relays; source per-cycle closed and both final eleven ownership counters zero. Destination per-cycle closed ownership remains separately unmeasured.

Final-cycle median across repeats of phase private-resident medians (MiB;1MiB=1048576bytes):

|Channels|Streams/channel|Source active|Source cooldown|Destination active|Destination cooldown|
|---:|---:|---:|---:|---:|---:|
|1|1|7.421875|7.421875|4.468750|4.445312|
|16|1|7.722656|7.726562|4.753906|4.753906|
|32|1|8.058594|8.062500|5.171875|5.152344|
|1|16|7.632812|7.640625|4.714844|4.714844|
|1|64|8.589844|8.597656|5.714844|5.730469|

All final active/cooldown private-resident repeat CVs below1.63%; no five-repeat extension required. Per-cycle PSS, private resident, RSS, FD/thread and capture durations retained in analysis/raw. Cooldown FD/thread remain6/1 source,8/2 destination. Memory samples are wholly contained within active/cooldown intervals and independently bound to PID/start-time/affinity, process lifetime and terminal CPU. Zombie memory is unavailable, never invented zero.

DIAGNOSTIC: observer runs at most once/second; maximum measured capture13.226551ms. This duration is not total observer cost or proof of neutrality. No performance timing or causal overhead claim. These are process totals including allocator/runtime/fixture retention, not qualified NBSR bytes/channel/stream, allocator cause, general leak freedom or long-run stability. Ownership reaching zero does not require private pages to return immediately. Four cycles do not replace long-cycle observation.

13 helper/config RED,2 integration RED,2 review-found lifetime/CPU RED;298 affected tests/Ruff PASS. Focused review/re-review clean after binding memory to retained lifetime;19 focused tests. Three external-definition contract tests PASS. Rust hashes unchanged; no production/protocol/security change. Existing default evidence remains replayable.

Five verified inactive Cargo caches recovered1466081280 measured host bytes in two cleanup batches; canonical inventory/commands/results retained. No source/Git/authoritative evidence deleted.

Reproduce via NATIVE_SAME_PROCESS_CYCLES.md with memory_observer:true. Retained run.py/setup.py/configs/build manifest reproduce the namespace campaign. Replay: python -B evidence/performance/v2/native-memory-04866375/analyze.py C:/NBSR-build/native-memory-04866375

Classification MEASURED_DIAGNOSTIC_PRIVATE_MEMORY. Observer neutrality, marginal resource costs, retention attribution, physical-server evidence and full B3/B5 acceptance remain open.
