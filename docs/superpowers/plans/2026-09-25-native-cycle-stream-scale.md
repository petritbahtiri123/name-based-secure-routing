# Native same-process stream scale

Native cycles currently fix one session/channel/stream. The unchanged Rust harness already supports 1..64 concurrent authorized streams per channel; port this existing workload dimension through the native cycle coordinator. One channel and the existing single-service authority remain fixed. No production/protocol/authority change or speculative optimization.

Add optional exact integer streams (default1, maximum64) to cycle config/CLI/commands/environment and independent replay. Preserve default raw evidence compatibility. Require every declared sample ID, per-cycle stream cardinality, payload length, destination metadata and materialized-active ownership count. Keep process epochs, final cleanup, cycle hold/cooldown and all deadlines unchanged.

Literal RED/GREEN, focused review, fresh release3 repetitions each at16/32/64 streams and4cycles. Preserve failures. Analyze RSS/FD/thread/ownership as diagnostic resource evidence; no qualified bytes/stream, allocator cause, throughput or stable capacity claim. Channel scaling remains separate scope. Extend relevant resource repeats to5 if CV exceeds5%.
