# Native same-process channel scaling

MEASURED Docker/WSL namespace release09b36ece:3 repeats each16/32 channels within
one authenticated transport/session,1 materialized1024-byte stream/channel,
4 sequential cycles per repeat.6/6 trials,24/24 cycles,576/576 operations PASS.
All12 owned PIDs absent before container stop, no forced relay cleanup. All source
per-cycle closed and both final eleven ownership counters zero. Destination
per-cycle closed ownership not separately measured. Active counts, every sample
and all per-service public fixture hashes independently replayed.

Final cooldown RSS ranges:16 channels source9.375-9.5MiB,destination6.375-6.5MiB;
32 channels source9.75-9.875MiB,destination6.625-6.75MiB. All first-three RSS CV
below1.12%, so3 repeats satisfy the declared rule. Cooldown FD/thread remain6/1
and8/2. Diagnostic sampled RSS only: no qualified bytes/channel, private memory,
allocator attribution, leak freedom or long-run channel-scale soak claim.
RTT contains deliberate2-second materialization holds, not data-plane latency.
No throughput, sustainable admission, physical-core or server claim.

13 literal RED cases;222 affected tests/Ruff PASS; focused independent review
clean with49 scoped tests PASS. Release Rust hashes unchanged. Minimal native
harness/replay changes only, no production/protocol/security/authority semantics
change. Combined channel/stream axes are explicitly outside this declared workload.
Default one-channel evidence remains compatible.

Two verified inactive Cargo caches recovered705810432 host bytes. Inventory,
commands and results retained; no source/Git/authoritative evidence removed.

Reproduction: docs/benchmarks/NATIVE_SAME_PROCESS_CYCLES.md; retained run.py,
setup.py, exact configs/commands, build manifest and checksums. Independent replay:
python -B evidence/performance/v2/native-channels-09b36ece/analyze.py C:/NBSR-build/native-channels-09b36ece

Classification PASS_FUNCTIONAL_CHANNEL_CYCLES; memory diagnostic only.
Qualified resource costs, observer neutrality, B3/B5 closure and external hardware
remain open. This closes native per-channel workload plumbing/execution, not the
entire engineering campaign.
