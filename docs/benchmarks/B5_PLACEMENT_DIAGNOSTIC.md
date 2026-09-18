# B5 shared versus separate guest CPU diagnostic

Status: harness ready for measurement; no new capacity claim.

The retained scheduler experiment found approximately 0.20 runnable thread-seconds
per second at each peer on one shared guest CPU. Its observer did not qualify for
causal performance attribution. The next intervention changes placement explicitly,
without adding an in-process profiler or changing transport implementation.

`scripts.performance.linux_b5_campaign --diagnostic --placement shared|split`
pins each peer to exactly one selected guest CPU. Shared uses the same CPU for both;
split uses two distinct topology-selected guest CPUs in total. Runtime workers,
payload, streams, outstanding depth, offered rate, ownership sampling, duration and
all existing gates remain identical. The resource sampler checks every observed
thread against its own role's CPU set, including terminal sampling. Commands,
verified affinity and total allocated guest CPU count are retained. This is not a
verified host physical-core comparison or a same-resource optimization claim.

Split placement rejects reference-bound execution: the historical shared-CPU
ceiling must not silently become its calibration. Existing shared mode is unchanged.
The legacy shape field `physical_cores` records topology selection cardinality;
`cpu_allocation.verified_host_physical_cores=false` states the guest limitation.

Planned matched experiment: three counterbalanced shared/split pairs, extended to
five if either arm's first-three goodput or median-window-p99 CV exceeds 5%.
Each cell is 300 seconds at the retained fixed historical diagnostic rate,
16 KiB, eight streams, depth one, three-second warmup, 30-second windows, ownership
sampling enabled in both arms. Preserve failed gates and incomplete attempts;
never replace an unfavorable valid result. No additional scheduler/allocator
observer runs concurrently. Compare goodput, latency, summed CPU, resident memory,
gate failures and final cleanup. A placement effect would not by itself prove a
production implementation bottleneck or a qualified sustained capacity.

Harness validation: literal RED produced five failures before implementation
(split backend, invalid topology, per-role sampler, rejection of shared reference).
Focused GREEN covers exact commands, swapped/widened placement rejection, resource
identity/affinity continuity and unchanged terminal-before-reap ordering. No Rust,
Go, wire/security or timeout changes are part of this stage.
