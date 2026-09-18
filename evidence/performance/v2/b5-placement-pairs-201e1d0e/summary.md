# B5 shared versus separate guest CPU diagnostic

Status: COMPLETE diagnostic, sustained acceptance FAIL; no new capacity claim.

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

The first live split attempt exposed an additional prelaunch restriction in the
single-CPU environment identity helper. A focused RED test preceded its correction:
explicit diagnostic selection can validate two CPUs and requires quota for both;
the reference loader still defaults to exactly one CPU. The preceding complete
shared run and failed split setup remain retained under
`C:/NBSR-build/b5-placement-pairs-5e0b94dd`. They are not a complete matched cohort.
An earlier non-root container setup failure is retained separately under
`C:/NBSR-build/b5-placement-5e0b94dd`; benchmark peers never started there.

## Matched results at 201e1d0e

Five counterbalanced pairs completed. The first-three p99 CVs were 14.6423%
shared and 5.6439% split, requiring extension to five. Both arms use precisely
the same release binaries; fresh builds at 5e0b94dd and 201e1d0e reproduced all
three binary hashes from the retained f8925b25 build. Only controller placement
changed. Source CPU is guest 0; destination is guest 0 shared and guest 2 split.
Guest topology reports these as different cores. Native host isolation is unproven.

| Five-run median | Shared, one selected guest CPU | Split, two selected guest CPUs | Split change |
| --- | ---: | ---: | ---: |
| Application goodput, Gbit/s | 2.149237 | 2.229769 | +3.7470% |
| Median steady-window p99, ms | 1.552181 | 1.083359 | -30.2041% |
| Summed peer CPU, effective guest cores | 0.727288 | 0.851445 | +17.0712% |
| Approximate CPU ns/completed op, derived | 88707.8 | 100100.5 | +12.8430% |
| Missed/offered operation fraction | 5.1099% | 1.5544% | Lower, but not admission rate |
| Runs passing all existing gates | 0/5 | 0/5 | FAIL in both arms |

CPU ns/op uses sampled steady-phase CPU and final completed operations over
300 seconds; phase boundaries are receive-clock approximations. It is not an
allocation measurement or a hardware cycle counter. p99 is the median of the
observed steady-window quantiles, not a pooled operation quantile. Runs emit nine
or ten steady progress windows; a boundary update can be labeled drain. The
unchanged analysis uses only steady windows in both arms.

Every pair has lower median-window p99 with split (18.7314% to 43.4763%), and
every pair consumes more summed CPU (8.8254% to 26.9996%). Goodput changes range
from -0.1366% to +4.5900%. Final goodput CVs are 2.2182% shared / 0.4485% split;
p99 CVs are 13.4910% / 4.3855%. Shared dispersion remains unresolved after five.

All ten runs finish with zero errors/timeouts, joined groups, sampled ownership
without sustained growth, and both peers' final 11 counters zero. Existing gates
still fail: shared has private-growth failures in three runs, p99 drift in three,
and goodput drift in two; split has private-growth failures in four, p99 drift in
four, and goodput drift in one. Categories overlap. No failed gate is waived.
Observed source private-resident deltas are 92-320 KiB shared / 168-244 KiB split;
destination deltas are 48-176 KiB / 104-236 KiB. No memory-saving or leak claim.

## Attribution and remaining boundary

MEASURED: separate guest-CPU placement reduces this workload's typical window
p99, at increased CPU allocation and consumption. It does not eliminate spikes,
memory-growth gates or other drift. This supports a placement contribution to
latency; the earlier scheduler observer is still unqualified and does not prove
the exact internal cause. No production optimization is justified by this result.

PLATFORM_DIAGNOSTIC_LIMIT: the remaining Windows/WSL drift and resident-memory
cause is unresolved after the retained observer and placement experiments. Do not
keep adding invasive hooks or repeat this cohort seeking PASS. Next causal work
requires a separately qualified observer or native Linux/server validation. The
existing Windows CPU capture remains ADMIN_REQUIRED; the current terminal was
again checked non-elevated. No security setting was changed.

Not proven: a host ceiling, production NBSR bottleneck, stable capacity increase,
qualified observer, 60-minute sustained soak, memory leak or absence of a leak.
Do not combine these ten independent five-minute runs into a 50-minute soak.

## Evidence and verification

Canonical: `evidence/performance/v2/b5-placement-pairs-201e1d0e`.
Raw: `C:/NBSR-build/b5-placement-pairs-201e1d0e`, plus the two retained incomplete
predecessor roots and both exact release-build roots referenced in raw-evidence.json.
The valid unfavorable shared run at 5e0b94dd is retained as an unmatched predecessor,
not substituted into the corrected matched cohort.

187 focused Python tests PASS; Ruff PASS. Analysis verified all 450 child-index
entries, exact per-role commands/affinity, continuous identity, active ownership
ranges, final cleanup and all failed gates. No Rust/Go/crypto/dependency changes;
both fresh release builds PASS. One focused parent review covered role placement,
reference rejection, quota/identity validation and unchanged terminal sampling.
