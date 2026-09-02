# Benchmark V2 Task 3 Stage 5: full-host CPU and SMT ceiling

Classification: **PASS / CPU-HOST-LIMITED FOR THIS BENCHMARK TOPOLOGY**.

Stage 5 kept the Stage-4 independent endpoint/current-thread-runtime harness unchanged and compared physical-core representative affinity (`0x55`) with all eight SMT logical processors (`0xFF`). The authoritative workload was 16 KiB, one stream per endpoint group, outstanding depth four, two and four groups, with five repeats for every Direct/NBSR cell.

| Affinity | Path | Groups | Median Gbit/s | Max Gbit/s | CV | Effective cores | p99 ms | Peak working set MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `0x55` | Direct | 2 | 2.121 | 2.170 | 2.15% | 3.476 | 2.001 | 27.3 |
| `0x55` | Direct | 4 | 1.900 | 1.963 | 4.55% | 3.706 | 10.604 | 43.6 |
| `0x55` | NBSR | 2 | 3.010 | 3.258 | 8.58% | 3.714 | 1.669 | 27.8 |
| `0x55` | NBSR | 4 | 2.692 | 2.781 | 2.68% | 3.769 | 17.058 | 46.1 |
| `0xFF` | Direct | 2 | 2.338 | 2.501 | 4.97% | 3.925 | 2.270 | 26.4 |
| `0xFF` | Direct | 4 | 2.264 | 2.347 | 4.47% | 6.500 | 8.785 | 44.1 |
| `0xFF` | NBSR | 2 | 2.759 | 2.845 | 5.37% | 3.867 | 1.574 | 27.9 |
| `0xFF` | NBSR | 4 | 3.040 | 3.167 | 3.64% | 7.001 | 6.428 | 46.3 |

SMT did not provide a repeatable material ceiling increase. The best `0xFF` median was 3.040 Gbit/s at four groups, only 0.98% above the best current-run `0x55` median of 3.010 Gbit/s at two groups. The `0xFF` four-group cell consumed approximately 7.00 effective cores across all eight logical processors and raised p99 approximately fourfold relative to `0xFF` two groups. This is the measured full-host CPU boundary for this specific laptop/loopback harness topology.

The highest single Stage-5 NBSR run was 3.258 Gbit/s (`0x55`, two groups). The previously preserved Stage-4 single-run maximum remains 3.407 Gbit/s. The highest repeatable Stage-5 result under the five-repeat/CV <=5% rule is 3.040 Gbit/s (`0xFF`, four groups), but it is SATURATED rather than strict-stable because of latency degradation. A strict-stable NBSR result is therefore **NOT ESTABLISHED** in Stage 5.

All 40 authoritative runs were valid, reached their configured outstanding-work depth, had zero errors and zero timeouts, and passed cleanup. Combined working set remained below 47 MiB. TypePerf captured Processor Utility, Processor Performance, and nominal Processor Frequency. The frequency counter stayed at 2101 MHz and ACPI temperature was unavailable; no thermal-throttling cause is claimed. An eight-group run was not useful because four groups already consumed the full-host SMT CPU pool without materially raising the ceiling.

Measured NBSR-minus-Direct deltas are preserved in raw evidence but are not generalized as protocol overhead because the Direct/NBSR cells have different variance and latency regions. This result does not establish a server-class, WAN, NIC, production-runtime, or general NBSR hardware ceiling.

Raw-evidence note: an inherited Stage-4 free-text placement sentence says source mask `0x55` in every raw record, including the `0xFF` cells. The structured `source_process_mask`, endpoint masks, and verified OS-affinity fields are authoritative and correct. The raw records remain unmodified; the runner was corrected to generate future placement text from the actual masks.
