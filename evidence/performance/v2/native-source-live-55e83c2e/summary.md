# Short native source live observer

Implementation and measured release source: 55e83c2e6e1cb75280f0461e22a5e22000a28cba.
COMPLETE: source-only observer integration and five counterbalanced functional
Direct/NBSR pairs. DIAGNOSTIC_ONLY: 1,000 offered operations/s, 16 KiB, eight
streams, depth one, 3-second warmup / 20-second issue, one WSL guest CPU per peer.
No production change; all three release binary hashes match earlier native stages.

All 10 cells pass functional accounting, zero errors/timeouts, requested NBSR
post-close ownership counters zero, and 20 exact owned PIDs absent before fixture
stop. All source event logs replay successfully against copied/original stdout.
Each source has 29 or 30 private-resident samples actually evaluated at steady
progress. No source private-growth predicate failure occurred in this short run;
this is not a leak, long-run memory, per-object cost or destination-memory claim.

| Path | Median Gbit/s | Throughput CV | Achieved/offered | p99 drift failures |
| --- | ---: | ---: | ---: | ---: |
| Direct | 0.261742 | 0.041284% | 99.79–99.90% | 3/5 |
| NBSR | 0.261612 | 0.149241% | 99.565–99.925% | 3/5 |

Median cell window p50/p95/p99: Direct 836257 / 2060531 / 5203830 ns;
NBSR 884756 / 1749711 / 3530022 ns. These are not pooled quantiles.
Observed source peak private-resident ranges: Direct 5,029,888–5,148,672 bytes;
NBSR 5,910,528–6,176,768 bytes. Linux private resident is not Windows private bytes.
All ten results, including drift failures, remain in analysis.json.

138 affected tests, Ruff, focused independent review and scoped re-review PASS.
Literal RED includes initial integration, replay PID/affinity/counter mutations
and source-only reporting. Exact commands and test logs are in retained roots.

Reproduce analysis:

```powershell
python evidence/performance/v2/native-source-live-55e83c2e/analyze.py --root C:/NBSR-build/native-source-live-55e83c2e
```

The generic cohort gate correctly rejects these fresh-per-repeat certificates,
because it requires one authority across its entire cohort. That contract is
unchanged. This experiment-specific analysis independently verifies every pair,
all source/build/placement identities, unique indexes and exact within-pair
certificate equality; certificates intentionally vary between repeats. It is
pairwise diagnostic evidence, not a generic qualified cohort/reference.

Observer neutrality NOT_ESTABLISHED: no matched on/off control was run in this
stage; old different-SHA controls are not substituted. p99 drift remains visible.
Destination private-memory monitoring and relay integration, genuine near-ceiling
60/120-minute soak, physical-core/server qualification remain open. No new stable
capacity, admissions rate, production bottleneck or hardware ceiling is claimed.
