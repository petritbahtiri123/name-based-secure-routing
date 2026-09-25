# Go/Linux lifecycle and benchmark-clock closure — September 25

Classification: **DIAGNOSTIC_SCOPED**, not stable capacity or complete B3/B5.

The Go/Linux channel, stream and repeated-cycle cohort completed 30/30 cells,
16,800/16,800 authenticated round trips, including five same-process runs of
50 cycles (250 cycles, 16,000 round trips). Every completed cell has verified
source/destination exit and zero in the eight destination ownership counters.
Full Go source ownership is NOT_MEASURED. Final source memory is unavailable
after verified exit; it is not reported as zero. There are 49 live source
cooldowns and 50 destination cooldowns per cycle run.

Active private-resident medians (source/destination bytes):

| Shape | Source | Destination |
| --- | ---: | ---: |
| 16 streams | 8159232 | 4263936 |
| 32 streams | 8302592 | 4272128 |
| 64 streams | 8585216 | 4292608 |
| 16 channels | 8536064 | 4263936 |
| 32 channels | 9117696 | 4296704 |
| 50 cycles | 13207552 | 5939200 |

All shapes have five repeats; maximum active private-memory CV is about 1.514%.
Source memory rises during the repeated cycles. Last-ten-cycle source slopes
range from 1638 to 54415 bytes/cycle, with fluctuations. Memory cause remains
INCONCLUSIVE: this is neither proof of a leak nor a bounded allocator-retention
claim. Do not extrapolate isolated per-resource cost from these measurements.

## Retained failures and narrowly justified repairs

The initial build failed due to missing cached dependencies; a second build
exposed the absent Linux Go benchmark clock. Both are retained. The Linux
monotonic clock was added at d88663af, then built and tested with Go race/vet.
The first cohort completed five 16-stream cells, then sampling failed with ESRCH.
A separate thread-churn reproduction proved transient nonleader task exit;
7255c9d6 tolerates that case only. Leader/permission/identity failures still fail.

An additional scale attempt completed two 64-stream cells then failed initial
sampling. The exception-only rerun retained the exact failing smaps_rollup read.
A controlled exec reproduction returned ESRCH in 10/10 reads through a proc
handle opened before exec, while PID epoch and liveness remained unchanged.
The original failure did not trace exec directly. At de50692f, initial Linux Go
sampling waits for its existing exclusive runtime file, created after exec and
before the first connection start marker. No protocol deadline was increased.
Four literal RED regressions became GREEN; 38 affected tests and Ruff pass.

The startup-gated scale rerun passed 30/30 cells: five repeats each at
64, 128, 256, 512, 1024 and 2048 application streams across 32 fixed channels
in one connection/session. All 20,160/20,160 round trips completed, all eight
destination counters returned to zero and both processes exited. This is the
largest exercised Go stream shape, not 2048 connections or a demonstrated
maximum. The scale rerun and all failures are separately indexed. See
scale-analysis.json; its timing is not observer-qualified throughput.

Separately a9048589 fixes Windows QPC duration multiplication overflow using
full-width arithmetic. The synthetic two-hour test first returned a negative
duration; regression/race/vet pass after repair. It is not an actual long soak.

## Provenance and limits

Controller 7255c9d6 for the 30-cell lifecycle cohort, de50692f for the startup-gated
scale rerun. Executed Linux binaries are from d88663af; the retained manifests
explicitly classify the source/binary mismatch as diagnostic. Neither Python
sampler change modifies those binaries. Do not relabel this as an exact-final-SHA
performance campaign. Build and image hashes are retained in indexed metadata.

Docker Linux loopback on one selected guest CPU is not verified exclusive
physical-core/server/NIC capacity. Go receive-buffer warnings are preserved.
Stream registry hold does not prove remote payload materialization. No live
runtime federation, qualified 60-minute soak, observer neutrality or production
hardware ceiling is established here. Security/wire/ACK semantics are unchanged.

Reproduce the cohort analysis with `python -B analyze.py`; it verifies source
indexes and retained records before calculating the table. The runbook is
`docs/benchmarks/GO_LINUX_LIFECYCLE_VALIDATION.md`. `raw-evidence.json` binds all
local retained roots, including unfavorable and incomplete runs. The final
verification root includes the exact scale-analysis replay helper and probes.
No off-host backup is claimed. Additional lossless compression preserved all
indexed bytes and recovered 86,357,917 allocated bytes across 39 files.
