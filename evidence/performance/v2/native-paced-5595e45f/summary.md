# Short native paced integration

MEASURED: source 5595e45f, exact release build, byte-identical Rust binaries,
Docker/WSL internal bridge with both Rust peers on guest CPU 0. Five counterbalanced
Direct/NBSR pairs, 16 KiB / eight streams / depth one, 1,000 offered operations/s,
3 s warmup, 20 s issue duration and 5 s progress cadence. Fixed controller cap
unchanged. This is a low-rate functional diagnostic, not a near-ceiling workload.

All 10 pairs pass grouped accounting, exact-source/native command binding,
post-close mode, role/PID cleanup and independent evidence integrity. Zero
errors/timeouts; all owned PIDs absent before fixture stop. NBSR role reports
pass the existing eleven-zero-counter contract; Direct remains process-only.

| Diagnostic | Direct | NBSR |
| --- | --- | --- |
| Median goodput including drain, Gbit/s | 0.261676644 | 0.261821567 |
| Goodput CV | 0.07872% | 0.11800% |
| Achieved/offered range | 99.75–99.93% | 99.70–99.99% |
| Median cell p50 window-quantile, ms | 0.831364 | 0.849465 |
| Median cell p95 window-quantile, ms | 1.940597 | 1.905236 |
| Median cell p99 window-quantile, ms | 4.364754 | 3.043603 |
| Cells with retained p99 drift violation | 3/5 | 1/5 |

Latency entries aggregate steady-window quantiles, not individual-operation
pooled quantiles. Original per-window records and failed drift gates are retained.
A functional pass does not erase a performance-gate violation. Light controller-side
engineering occurred during this diagnostic cohort; no performance attribution is
made. The separate ac40740c observer qualification was rejected, and no new
observer qualification is claimed at this source.

NOT_PROVEN: strict-stable capacity, host/physical-core ceiling, full live private
memory drift qualification, continuous ownership qualification, sixty-minute
soak or external-server behavior. Requested rate is not admissions/s. Existing
historical capacity results remain unchanged. No production optimization occurred.

Implementation verification: 21 literal RED cases, two integration RED cases,
122 affected tests PASS, Ruff PASS and one focused independent review. A subsequent
cohort comparison fix b2bd7141 adds the missing post-close observer identity field:
one focused RED/GREEN and 21 cohort/post-close tests PASS, scoped re-review clean.
It does not alter the retained 5595e45f peer workload or release binaries.

Safe maintenance removed 76 stopped campaign fixture containers only after
verifying canonical raw roots and endpoint indexes. Logical writable bytes freed:
2,368,540,672. Host free bytes changed 6,141,243,392 to 6,139,457,536; no host SSD
recovery is claimed from that Docker deletion. Images, source, Git, private
fixtures and authoritative raw evidence remain retained.

Reproduce independent analysis from repository root:
`python evidence/performance/v2/native-paced-5595e45f/analyze.py`.
Raw commands, predeclared workload, all cells, release build, focused tests and
cleanup inventories are indexed in raw-evidence.json. Checksums are not signatures.
