# Native cycle private-memory diagnostics

RSS-only cycle evidence cannot distinguish shared pages or measure private resident memory. Reuse the existing identity-checked Linux smaps_rollup sampler in a separate opt-in native-cycle observer, at most once per second. Default workload/telemetry unchanged. No timed throughput attribution or observer-neutrality claim. Existing process ownership, CPU affinity, deadlines and cleanup remain mandatory.

Retain bounded memory records with capture start/end, PID/start epoch, affinity, RSS/PSS/private resident/hugetlb, explicit unavailable zombie state, and independent raw replay. Missing/malformed samples or summary mismatch fail closed; never invent zero memory. Wire/config/peer/controller binding must agree. No new thread, child or production change.

RED/GREEN helper plus config/replay tests; affected tests and focused review. Fresh release paired diagnostic observations on1/16/32 channels and1/16/64 streams (one axis at a time),4cycles,3repeats or5 when relevant final private-memory CV>5%. Preserve every failure. Analyze active/cooldown private memory only as measured diagnostic totals; incremental cost remains unqualified without observer and allocator attribution. If overhead or permissions invalidate sampling, retain and classify the limitation without repeated intrusive diagnostics.
