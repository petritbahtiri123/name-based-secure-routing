# Native 60-second diagnostic preflight

Release/source 4144d8fa226b1cbee3c8e2227d8d357b73584434.
COMPLETE functional preflight; DIAGNOSTIC_ONLY, not a qualified soak.
Three matched Direct/NBSR pairs all pass accounting and cleanup. First-three
throughput CV is below 5% for both paths, so the predeclared extension to five
is not triggered. All six attempts are retained, including numerical failures.

Workload: 1,000 offered ops/s, 16 KiB, eight streams, depth one, 3-second warmup
and 60-second issue duration. Both peers select guest CPU 0. Live source and
destination guards plus post-close reports are enabled. Twelve exact owned PIDs
are absent before fixture stop; zero errors/timeouts, all requested NBSR eleven
ownership counters zero. Rust release hashes are unchanged from 94209a9c.

| Path | Median Gbit/s | CV | Achieved/offered | p99 drift failures | Source/destination private-growth failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 0.261531 | 0.031390% | 99.727–99.788% | 2/3 | 1/3, 1/3 |
| NBSR | 0.261372 | 0.095200% | 99.570–99.753% | 3/3 | 2/3, 0/3 |

Private-growth predicates are diagnostics, not proof of leaked ownership or
allocator cause. Final ownership cleanup is a separate measurement. The observer
was already rejected for timing at the shorter workload; neither numerical
stability nor observer neutrality is established here. Quantiles in analysis.json
are medians of window summaries, not pooled latency. No near-ceiling load,
physical-core/server ceiling, steady CPU ns/op or production speedup is claimed.

Implementation preserves the default short contract. Explicit 60/3600/7200-second
diagnostics use their declared duration plus the existing 120-second management
allowance, with unchanged readiness/cleanup/transfer limits. This does not extend
failed short runs. Fourteen literal RED cases preceded implementation. Final 147
affected tests and Ruff PASS; independent review and scoped metadata re-review
are clean. A synthetic two-hour transcript (1440 windows, 300 resources per role)
replays independently, and historical short raw evidence still verifies. Synthetic
replay is not an actual two-hour execution.

Safe maintenance removed only three inactive Cargo targets: task4i-review,
task4k-review and task4d-red. Verified tags, path containment, inventory and absence
of active builders/peers preceded `cargo clean --locked`. Measured recovered space
743,329,792 bytes. No source, private fixture, Git or authoritative raw was deleted.

```powershell
python -B evidence/performance/v2/native-long-4144d8fa/analyze.py --root C:/NBSR-build/native-long-4144d8fa
```

Reference-bound execution, qualified current reference, live-observer qualification
and genuine near-ceiling 60/120-minute acceptance remain open at this stage.
