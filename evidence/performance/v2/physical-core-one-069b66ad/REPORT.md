# Shared physical-core forwarding diagnostic

**DIAGNOSTIC / DISPERSION. No strict-stable ceiling established.** Both Direct secure QUIC and NBSR ran inside the same single physical-core CPU pool (`0x1`), excluding its SMT sibling. Windows topology reports four physical cores/eight logical processors. Every source/destination process affinity readback matched the requested mask.

Release workload: 16 KiB, one stream, one endpoint group, one runtime worker per role, three seconds warmup and 20 seconds measured work. Direct/NBSR order alternated; every cell escalated from three to five repeats because CV exceeded 5%. All 40 runs were valid, error-free and cleanup passed. All retained raw checksums were verified.

| Outstanding | Direct median Gbit/s | NBSR median Gbit/s | NBSR CV | NBSR p99 ms | Sampled NBSR effective cores |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.662 | 0.560 | 17.34% | 0.801 | 0.909 |
| 4 | 0.630 | 0.745 | 11.86% | 3.436 | 0.898 |
| 8 | 0.883 | 0.774 | 12.14% | 5.598 | 0.905 |
| 16 | 0.924 | 0.895 | 9.27% | 7.895 | 0.904 |

At outstanding=16, NBSR completed a median 3,415 operations/s; sampled aggregate source+destination CPU cost was approximately 267,385 ns/completed operation. These CPU metrics are DERIVED estimates from 0.5-second process samples in the final measured-duration window. Missing boundary fragments and host interrupt work are not included. This is neither isolated production-core cost nor an allocation/syscall measurement.

Increasing concurrency raised latency sharply. The sampled processes consumed approximately 90% of the restricted core at several points, but these data do not establish a general host or production NBSR ceiling. Every cell exceeds the repeatability threshold; the ladder cannot supply a strict-stable baseline or funding capacity claim. No production hotspot was attributed or optimized here.

Focused Python tests and review/fix commands occurred during early outstanding=1 runs. Later work was read-only inspection and source/document authoring; no builds or other benchmarks ran during timing. All results remain retained, and this experiment is not presented as a quiet-host capacity measurement. A final controlled rerun remains required.

The harness fix makes custom payload/stream/outstanding arguments reach the actual binary and aggregation, and uses the actual allocated CPU count rather than hard-coded four-core normalization. A separate failure-path regression proved source-process leakage after affinity exceptions; cleanup now stops the sampler, terminates/drains the source and preserves partial output. Both defects had literal RED then GREEN tests. Fifteen focused/related Python tests and Ruff passed; one focused independent review and scoped fix re-review found no remaining Important issues.

Reproduce with a new output directory: `python scripts/run_physical_core_v2.py --output C:\NBSR-build\physical-core-NEW --cores 1`. Use `--cores 2` or `--cores 4`, with explicit endpoint groups, for subsequent matched scaling. This diagnostic used the retained pre-cleanup-fix runner snapshot; its successful paths did not trigger that failure-path defect. Parent SHA alone does not identify the uncommitted runner; source copies/patch and binary hashes are retained.
