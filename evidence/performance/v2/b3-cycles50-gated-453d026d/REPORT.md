# B3: five same-process 50-cycle repeats

MEASURED Windows loopback lifecycle evidence. Source SHA `453d026da19f80b94538374301593ea97351c7f9`; retained source patch and executable hashes are authoritative. All 50 raw manifest entries were verified before packaging.

Each repeat opened, held, exchanged and closed one session/channel with 64 authorized streams per cycle, for 50 cycles in the same source and destination processes. The destination report gate separates final JSON serialization from the last cooldown sample. All five repeats completed; all source per-cycle and both final ownership checks were zero. Handles returned to the same first-cycle cooldown count in both roles.

**Scope:** held resources are admitted application registries and source stream handles. Quinn streams were not materialized at the destination until the first request after release. This does not establish the memory cost of 64 simultaneously materialized two-sided transport streams. A separate workload tests that state.

| Repeat | Source private delta (bytes) | Destination private delta (bytes) | Source/destination handle delta | Ownership |
| --- | ---: | ---: | --- | --- |
| cycles-50-r1 | 61440 | 843776 | 0/0 | CLEAN |
| cycles-50-r2 | 24576 | 995328 | 0/0 | CLEAN |
| cycles-50-r3 | 221184 | 901120 | 0/0 | CLEAN |
| cycles-50-r4 | 86016 | 757760 | 0/0 | CLEAN |
| cycles-50-r5 | -98304 | 430080 | 0/0 | CLEAN |

Private deltas compare median cooldown samples of cycle 49 with cycle 0. Per-cycle samples, full and second-half linear slopes are retained in `analysis.json`; no unfavorable samples were removed. Memory cause is **INCONCLUSIVE**: OS private bytes include runtime/allocator state and harness-retained measurement records. Zero owned resources does not prove zero untracked allocations, and positive private-byte slopes do not prove a production leak or allocator-only retention. No bytes-per-stream or hardware ceiling claim follows.

Earlier five-repeat cohort `C:/NBSR-build/b3-v2-cycles50-dda3938d` remains retained with its final-report allocation phase confound. It is not silently replaced or pooled with this cohort.

Reproduction (fresh output; build the recorded release source first):
```powershell
python scripts/run_b3_v2.py --output C:/NBSR-build/b3-cycles50-reproduction --axis cycles --counts 50 --repeats 5
python -m scripts.performance.b3_v2_analysis C:/NBSR-build/b3-cycles50-reproduction --output C:/NBSR-build/b3-cycles50-reproduction-analysis.json
```

The runner copies existing release binaries from its `--target`; source checkout alone does not rebuild them. Verify retained binary hashes and source provenance before comparing. Full raw evidence remains at the exact external path bound by `external-inputs.json`.
