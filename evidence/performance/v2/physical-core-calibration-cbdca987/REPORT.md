# Current physical-core forwarding calibration

MEASURED: release Windows loopback, clean cbdca987 source, both roles share
one verified physical core (logical mask 1, no SMT sibling). Fixed shape within
each ladder; 3-second warmup and 30-second measurement; matched alternating
Direct/NBSR order, three repeats and five where CV exceeded 5%.

| Workload | Depth | NBSR class | Median Gbit/s | p99 ms | Repeats |
| --- | --- | --- | ---: | ---: | ---: |
| 16k8 | 1 | STABLE | 1.052536 | 3.7861 | 3 |
| 16k8 | 2 | DEGRADED | 1.157283 | 5.8514 | 3 |
| 16k8 | 4 | SATURATED | 1.133049 | 9.9408 | 3 |
| 16k8 | 8 | SATURATED | 1.179814 | 19.2356 | 5 |
| 1k64 | 1 | STABLE | 0.865859 | 2.4867 | 3 |
| 1k64 | 2 | DEGRADED | 0.915900 | 4.2475 | 3 |
| 1k64 | 4 | SATURATED | 0.940972 | 7.0855 | 3 |

All 46 runs are valid, zero errors/timeouts, bounded outstanding work and
process/window cleanup pass. Periodic ownership and eleven-counter post-close
observers were disabled to keep this timing calibration separate from their
qualification. Process/window cleanup is not a runtime-residue proof.

At NBSR depth1, sampled aggregate process use was 0.967658 effective cores for
16KiB/8 and 0.982960 for 1KiB/64. These support an allocated-core CPU saturation
statement for these finite workloads, not a whole-host, NIC, WAN or production
system ceiling. CPU accounting is DERIVED from 0.5-second samples over the
measurement window and excludes boundary fragments and host IRQ work.

NBSR depth1 CPU ns/op: 242551.717 (16KiB/8) and 18601.695 (1KiB/64).
Operations/s: 4015.106 and 52847.849 respectively. Different shapes have separate
latency baselines and must not be pooled. Quantile and CPU method limitations
remain those recorded in environment.json. Allocation, syscall, context-switch,
frequency and thermal measurements are NOT_MEASURED.

The strict-stable results are 1.052536 and 0.865859 Gbit/s for these respective
shapes. Higher diagnostic peaks do not replace them. Direct results and every
unfavorable valid repeat are retained in the same package. No production code
was optimized as a result of this calibration. The later paced observer failure
is preserved separately; finite strict stability does not establish long-soak
stability.

Raw evidence roots and actual-byte manifest hashes are in analysis.json.
Canonical normalized text copies are checksummed separately. These inputs may
serve a soak reference only while its exact clean source/binary checks pass;
a later source change requires a new compatible calibration reference.
