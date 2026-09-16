# B5 matched ownership diagnostic

Status: diagnostic step COMPLETE; B5 memory/p99 attribution and accepted soak
remain PARTIAL. No production or harness behavior changed in this step.

## Method

Exact release build `f8925b25b5907a8e79a3f561ae83f7ae2fc1008c`, Linux Docker/WSL
loopback, one selected guest CPU, NBSR 16 KiB / eight streams / depth one.
Historical fixed offered rate `64804600000000 / 7500349701` ops/s, three-second
warmup, 300-second steady phase, 30-second progress windows. This is not a
current-SHA near-ceiling calibration or physical-core/server measurement.

Three counterbalanced ownership-sampling off/on pairs (off/on, on/off, off/on)
used the existing one-second sampler and unchanged gates. Complete-final
goodput and median-window-p99 CV stayed below 5%, so no extension to five was
required. Failed-but-complete runs remain failures, not accepted repeats.
No heavy builds, tests or hashing ran during the timed measurements.

## Measured results

| Repeat | Sampling | Gbit/s | Median window p99 ms | Existing gate result |
|---|---|---:|---:|---|
| 1 | off | 2.238300 | 1.272072 | DIAGNOSTIC |
| 1 | on | 2.241596 | 1.259991 | FAIL: p99 drift at 120 s |
| 2 | on | 2.238467 | 1.252236 | DIAGNOSTIC |
| 2 | off | 2.239792 | 1.284168 | FAIL: destination private growth at 120 s |
| 3 | off | 2.241027 | 1.294375 | FAIL: source private growth at 270 s |
| 3 | on | 2.243480 | 1.316371 | FAIL: destination private growth at 90/120/150 s |

All six runs completed traffic with zero errors/timeouts and all eleven final
ownership counters zero at both peers. Three independent five-minute runs per
observer are not a continuous 30-minute soak.

Off/on cohort median goodput: 2.239792 / 2.241596 Gbit/s (+0.081%). Median of
window-p99 medians: 1.284168 / 1.259991 ms (-1.883%). Approximate summed peer CPU:
0.745762 / 0.747032 guest cores (+0.170%). Goodput CV: 0.061% / 0.113%; p99 CV:
0.870% / 2.743%; CPU CV: 0.561% / 1.295%. Every paired delta for these metrics
was within 5%. These descriptive differences do not establish causality.

Observer qualification remains **NOT_QUALIFIED**: only one run per observer
passed all existing performance gates. No three-pass stability qualification
or claim that instrumentation cannot alter memory behavior follows.

## Ownership versus residency

All three sampling runs passed `SAMPLED_NO_SUSTAINED_GROWTH`, with 300 source and
305 destination snapshots including initial snapshots. Offline full-history
checks found all eleven ownership fields and five emitted retained-capacity
fields constant while each peer had eight application streams and one session.
Setup/cleanup snapshots are preserved separately, not silently excluded from
the evidence. Audit queue occupancy remained 19 source / 27 destination while
active; retained capacity was 1024 at both peers.

Despite constant sampled ownership, the third sampling run triggered destination
private-memory growth three times. Across sampling runs, source private-resident
net growth was 60--300 KiB and destination 84--272 KiB. The source held ten FDs
and three threads. Destination held eight FDs and two threads with sampling,
versus seven FDs and one thread without sampling: the observer itself has a
visible resource footprint. Counts stayed constant within each steady run.

**Supported diagnostic narrowing:** observed residency growth can coexist with
constant sampled NBSR resource counts and map capacities. It is not explained
by accumulating sessions, channels or streams in these samples.

**Not proven:** allocator retention, bounded total live allocation, absence of
a leak, Quinn/Tokio allocation behavior, p99 root cause or a hardware ceiling.
Counters do not cover every allocation, and one-second snapshots cannot exclude
transient changes. Phase alignment uses approximate receive-clock timing.
No production optimization is justified by this evidence alone.

## Reproduction and next boundary

Canonical package: `evidence/performance/v2/b5-ownership-pairs-f8925b25`.
Raw root: `C:/NBSR-build/b5-ownership-pairs-f8925b25`; release build retained at
`C:/NBSR-build/linux-current-f8925b25`. `raw-evidence.json` binds both indexes.
The package preserves the executed runner, all six commands/results, analysis,
repeat decision, and reproduction commands. Use a new output directory; never
overwrite the sealed raw root. The runner checks out the build's exact SHA.

Focused verification: 26 ownership/retained-diagnostic/Linux campaign tests
passed; relevant Ruff checks passed; all 264 child-index entries verified.
No protocol/security or production code changed, so no new production
correctness or security acceptance claim is made.

Next useful step is qualified allocator-accounting or scheduler/wait evidence
for the remaining residency/p99 question. Do not weaken memory/p99 gates, call
these runs an accepted soak, or optimize allocator behavior by assumption.
