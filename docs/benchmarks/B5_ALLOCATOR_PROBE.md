# B5 allocator-accounting feasibility probe

Status: controlled-fixture step COMPLETE; actual B5 attribution remains
UNRESOLVED. This probe executes no NBSR workload or production binary.

The previous matched ownership diagnostic showed that residency can grow while
sampled NBSR counters stay constant. Existing `calloc` traces record allocation
addresses but do not track `free`, so they cannot establish live allocation
totals. This step checks whether allocator accounting can distinguish known
allocation, page-touch and free transitions in the retained Linux environment.

## Controlled experiment

Standalone C fixture, compiled with `cc -O2 -Wall -Wextra -Werror
-fno-builtin-calloc`; runtime UID/GID 65532, default Docker controls, no added
capabilities. Build and runtime report Debian glibc 2.36-9+deb12u14. Exact image
IDs, compiler/linkage output, source and commands are preserved in the package.
Repository checkpoint: `3646c6ba85af294c34b155e005a16805b327ae68`.

Five independent processes per mode, each recording baseline, allocated,
partial-touch, full-touch, freed and one-second cooldown phases:

- Large: one `calloc` of 3,014,656 bytes, matching the previously identified
  receive-buffer requested size. The fixture is not Quinn and does not receive
  packets. Partial touch writes at 100 page-stride offsets; full touch writes
  at every page-stride offset and the final byte.
- Small: 16,384 separately allocated 64-byte blocks, all explicitly freed.

Both modes record `mallinfo2` fields and `/proc/self/smaps_rollup` private
residency. Fixture-owned requested bytes come from its explicit allocation/free
sequence. `uordblks + hblkhd` is reported as allocator accounting, never as exact
application-owned bytes. No allocator tuning, trimming or interposition is used.
Initial three-repeat freed-phase call-duration CV exceeded 5%; both modes were
extended to five. Every original observation remains in the evidence.

## Results

All ten processes passed the controlled transition assertions (60 observations).

| Quantity | Large mode | Small mode |
|---|---:|---:|
| Fixture requested bytes while allocated | 3,014,656 | 1,048,576 |
| Allocator-accounting increase | 3,018,752 | 1,310,720 |
| Additional private residency from explicit touching | 3,014,656 | 0 |
| Accounting above baseline after free/cooldown | 0 | 560 |
| Private residency above baseline after free/cooldown | 4,096--32,768 | 1,437,696--1,441,792 |
| Arena free bytes above baseline after cooldown | 0 | 1,215,952 |

Accounting stayed exactly constant between allocation and both touch phases in
every process. Large-mode mapped-block count returned to baseline after free.
Small-mode fixture ownership returned to zero while residency stayed elevated;
the 560-byte accounting residual also demonstrates why allocator totals must
not be presented as exact fixture ownership.

These are **MEASURED controlled-fixture results**, not causal evidence about
NBSR. They establish that the available interface can distinguish these known
transitions on this image. They do not establish why B5 memory grows, whether
NBSR has a leak, or whether all retained memory is bounded.

## Observer decision

Observed `mallinfo2` call durations: 300--2,500 ns for large-mode samples and
300--180,611 ns for small-mode samples. These exclude smaps collection and
output. The fixture is single-threaded; neither concurrent allocator contention
nor B5 latency impact is measured. No negligible-overhead claim is justified.

Classification: `CONTROLLED_FIXTURE_PASS_NOT_NBSR_ATTRIBUTION`;
observer `NOT_QUALIFIED_FOR_B5`.

Next: an opt-in diagnostic sampler outside the operation hot path, with matched
off/on release workloads, must establish its own observer effect before causal
use. It must preserve the separate allocator fields, private residency and
NBSR ownership counters. Do not subtract unrelated process clocks or identify
an allocator-accounting residual as a leak. Do not change memory/p99 gates or
production allocation behavior based on this fixture.

## Evidence and verification

Canonical: `evidence/performance/v2/b5-allocator-probe-3646c6ba`.
Raw: `C:/NBSR-build/b5-allocator-probe-3646c6ba`, bound by `raw-evidence.json`.
The package retains source, ten original phase logs, analyzer, compiler/runtime
identity, reproducibility commands and checksum indexes. Reproduce in a fresh
output directory. Analyzer assertions and Ruff passed; C compilation used
warnings-as-errors. No production Rust/Go code changed and no benchmark capacity,
security-regression or accepted-soak claim follows.
