# Short paired native live telemetry

Implementation/release SHA: 94209a9c97b9fbf0442e0423f14f1ca23f5bfbb8.
COMPLETE: short paired live-guard integration, five Direct/NBSR functional pairs,
and three catchable control-EOF trials per target role. DIAGNOSTIC_ONLY.
No production change. Release binary hashes remain identical to earlier native stages.

Workload: 1,000 offered ops/s, 16 KiB, eight streams, depth one, 3-second warmup
and 20-second issue duration. Both peers use WSL guest CPU 0. Original controller
and cleanup deadlines are unchanged. This is not a near-ceiling or physical-core test.

All ten measured cells pass functional accounting with zero errors/timeouts,
all requested NBSR eleven-counter reports zero, all 20 exact owned PIDs absent
before fixture stop. Source and destination logs replay independently; forwarded
progress matches source stdout exactly. Each role has 29–30 evaluated local memory
samples. No short-run private-growth predicate failure occurred. This does not
prove absence of leaks, long-run stability, allocator cost or per-resource cost.

| Path | Median Gbit/s | Throughput CV | Achieved/offered | p99 drift failures |
| --- | ---: | ---: | ---: | ---: |
| Direct | 0.261756 | 0.104670% | 99.67–99.92% | 3/5 |
| NBSR | 0.261911 | 0.056038% | 99.815–99.945% | 2/5 |

Median cell window p50/p95/p99: Direct 844052 / 1888116 / 4506183 ns;
NBSR 816249 / 1784210 / 2792373 ns. These are not pooled quantiles or independent
destination latencies: destination evaluates the forwarded source windows against
its own local memory samples. All unfavorable valid results remain included.

Six cancellation trials PASS_CATCHABLE_EOF_CONTROL after both owned Rust peers
and both guards had live progress/resources. Each target role was tested three
times. Both endpoint failures and group-kill/reap evidence remain retained; all
12 exact owned PIDs absent, no forced local relay termination. This is controlled
EOF cleanup, not graceful eleven-counter cleanup, network partition or SIGKILL
recovery. Remaining-process scans that skip permission failures are supplementary;
the exact same-UID owned-PID checks are the absence evidence.

Review found an ordered-write bug in the new harness integration: pending send
pumped a callback that recursively sent another frame. Literal RED demonstrated
second/first order. Deferring pumping until the current write returns fixes it;
deadline/cancellation checks remain active. Scoped re-review PASS. Final 179 affected
tests and Ruff PASS. Initial ledger/observer/endpoint/replay RED logs are retained.

```powershell
python evidence/performance/v2/native-paired-live-94209a9c/analyze.py --root C:/NBSR-build/native-paired-live-94209a9c --eof-root C:/NBSR-build/native-paired-live-eof-94209a9c
```

Fresh certificates per repeat, exact certificates within each Direct/NBSR pair;
all builds, workload shapes, observer modes and observed placement are checked.
This pairwise experiment does not weaken the generic cohort's constant-authority
gate. No observer-neutrality or stable-capacity claim: matched on/off qualification,
current native strict-stable reference, reference-bound long-duration orchestration
and actual near-ceiling 60/120-minute soak remain open. External/server hardware
and physical-core qualification are NOT_PROVEN.
