# B5 retained failed trajectories

Question: does the previously observed resident-memory growth eventually reach
a plateau, or continue throughout a longer fixed-load interval? Earlier strict
tests stopped at the first private-growth/p99 gate, leaving the later trajectory
unobserved. This is a diagnostic question, not an acceptance-gate revision.

The Linux diagnostic CLI now accepts `--retain-failed-diagnostic`, only with
`--diagnostic` and a predeclared duration of at most 600 seconds. It records
each observed performance-gate failure while permitting collection until that
duration. Any recorded violation forces `valid=false` and
`FAIL_DIAGNOSTIC_RETAINED`, even when all operations and cleanup finish. Original
correctness failures take precedence. Such rows cannot satisfy repeat gates.

Normal runs still abort at their first performance failure. The stream validator,
errors/timeouts, resource/schema bounds, controller deadline, ownership checks
and cleanup remain unchanged in both modes. Only typed p99/goodput drift and
private-growth exceptions are retained. Because the guard evaluates drift
before memory, the event list is not an exhaustive list of simultaneous
violations; the complete retained resource series must be analyzed separately.

No claim of lower memory, bounded allocation ownership or passed soak follows
from continuing a failed diagnostic. RSS/residency and live allocation remain
different quantities. No production code, timeout or offered load is changed.

Validation includes literal RED tests, the strict abort regression, retained
drift/private-growth failure reporting, bounds, invalid resources, duration and
acceptance-mode rejection, and actual run_one cleanup/report-path coverage with
synthetic peers. Focused tests and Ruff pass. Runtime results follow below.

Initial planned diagnostic: three 600-second NBSR attempts, 16 KiB, eight streams,
depth 1, three-second warmup, 30-second progress, one selected guest CPU, fixed
historical rational rate 64804600000000/7500349701 operations/s. This is not
current-source near-ceiling calibration. Preserve all failures; extend to five
attempts if applicable complete-run goodput or window-p99 CV exceeds 5%.

## Retained results, 2026-09-16

All five 600-second attempts at source
`91a88774ac6780b209dce15c562d453d1ab0a40f` reached a complete traffic final,
with zero errors/timeouts and both final eleven-counter cleanup reports zero.
These are five separate processes/runs, not a continuous 50-minute soak.

| Repeat | Gbit/s | Median steady-window p99, ms | Original classification |
| --- | ---: | ---: | --- |
| 1 | 2.216963 | 1.492388 | FAIL_DIAGNOSTIC_RETAINED |
| 2 | 2.178760 | 1.283673 | DIAGNOSTIC |
| 3 | 2.248254 | 1.129665 | FAIL_DIAGNOSTIC_RETAINED |
| 4 | 2.251705 | 1.094458 | FAIL_DIAGNOSTIC_RETAINED |
| 5 | 2.255937 | 1.068160 | FAIL_DIAGNOSTIC_RETAINED |

First violations: source private growth at 570s (r1), source growth at 180s
(r3), p99 drift at 90s (r4), destination growth at 180s (r5). No performance
gate fired in r2. All five complete finals are included in descriptive CV:
goodput 1.4653%, median-window p99 14.5670%. These are not five valid acceptance
repeats. The declared three-to-five rule triggered on the first-three p99 CV.

MEASURED: source private residency rose by 139264--225280 bytes over the
approximately 600-second sampled intervals; destination by 61440--225280 bytes.
Source FDs stayed 10 and threads 3; destination FDs stayed 7 and threads 1,
in every selected steady sample of all five runs. Continuous owned-resource
sampling was disabled, so zero final ownership is not proof of bounded live
ownership throughout a run.

DERIVED: in the supplemental last-300-second intervals, none of the ten role
series satisfies the existing growth predicate. Source still gains 4096--61440
bytes, so this does not establish a universal plateau or erase any earlier
failure. Resident pages cannot distinguish live allocations, allocator retention
and page residency. A production leak remains NOT_PROVEN.

DERIVED: final first/last-third p99 changes are +0.212%, +9.123%, -15.693%,
-0.515% and -5.887%. In particular, r4's final thirds do not reproduce its
earlier live violation; the earlier violation remains binding. Thus the retained
series does not support a claim of monotonically worsening latency. It also
does not identify the cause of the transient latency increase.

Approximate summed peer CPU across 30-second steady windows ranges from 0.6754
to 0.9664 guest cores across all runs. The r4 range is 0.6767--0.7631; its
latency failure alone does not establish CPU saturation. Phase alignment uses
the existing approximate receive clock; CPU means cannot exclude short stalls
or bursts. No physical-core or global hardware ceiling follows.

Canonical evidence: `evidence/performance/v2/b5-retained-91a88774`.
Raw: `C:/NBSR-build/b5-retained-91a88774`; exact release build:
`C:/NBSR-build/linux-current-91a88774`. Both raw indexes are bound by the
canonical package. All 215 child-index entries passed verification; the sealed
package index SHA-256 is
`5f81034b4222cfdd9bdb98b0d9f874066769e248acff310f6cb5c8e9dc6e3747`.
Reproduction: use the recorded source SHA and commands, then run `analyze.py`
and `correlate.py` beside copies of the raw inputs in a new working directory.
The analysis imports `sustained_capacity.py` from that source revision.

Status: retained-trajectory analysis COMPLETE; accepted sustained soak and
causal attribution remain PARTIAL. No production optimization, new capacity
claim, threshold change or workload change is justified by these results.
