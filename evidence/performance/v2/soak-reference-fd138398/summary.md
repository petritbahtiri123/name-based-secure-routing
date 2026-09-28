# Fresh one-core reference for sustained-load evaluation

MEASURED at `fd138398549a579b50dd0693fc278d3998b0b3e0`, Windows loopback,
release binaries, one verified physical core, one endpoint group, eight streams,
16 KiB payload, twenty seconds per cell after three seconds warmup.
Direct and NBSR use equivalent workload shapes. Twelve valid cells contain
three repeats of each path/depth. All goodput CVs are at most 5%, so the existing
repeat policy did not require extension to five.

| Path/depth | Classification | Median Gbit/s | CV | Median p99 ms |
| --- | --- | ---: | ---: | ---: |
| Direct / 1 | STABLE | 1.076719 | 1.087% | 3.3386 |
| NBSR / 1 | STABLE | 1.031167 | 4.294% | 3.9816 |
| Direct / 2 | DEGRADED | 1.111379 | 0.487% | 5.8152 |
| NBSR / 2 | DEGRADED | 1.159379 | 0.924% | 5.9108 |

The existing `classify_ladder` function supplies these classifications; no gate
was changed. NBSR depth one measures 3933.590 ops/s and 0.956199 effective cores,
with median p50/p95 1.9296/3.2414 ms. CPU ns/op is DERIVED: 239968.103.
The NBSR individual peak 1.164803 Gbit/s is DIAGNOSTIC, not stable capacity.

This deliberately narrow fresh reference permits a source/binary-bound 75%
offered-load target of approximately 0.773375 Gbit/s. It is not a new global
forwarding maximum, an offered-rate sustainable claim, a multicore rerun, or
a hardware ceiling. Historical four-core results retain their own source and
workload scope. A twenty-second reference cannot establish long-run stability.

Reproduce from a clean checkout at the stated source:

```powershell
python -B scripts/run_physical_core_v2.py --output C:/NBSR-build/soak-reference-fd138398-20260926 --target C:/NBSR-build/b4b-task4k --cores 1 --groups 1 --payload 16384 --streams 8 --outstanding 1 2 --duration 20
```

Use a new output directory for reproduction. `raw-evidence.json` binds the
retained raw checksum index; `classification.json` records the complete ladder
classification, and `summary.json` retains CPU/latency statistics.
