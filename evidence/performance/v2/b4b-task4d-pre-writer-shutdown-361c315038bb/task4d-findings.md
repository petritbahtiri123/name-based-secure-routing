# Task 4d In-memory Lifecycle Coordination Findings

Classification: **Evidence FAIL / System SATURATED / Boundary HARNESS-LIMITED (next root cause unresolved)**

The bounded coordinator removed lifecycle directory polling from both current-thread Tokio runtimes. Each logical client now records one in-memory terminal state, then queues one evidence marker to a dedicated bounded writer. Run completion depends on in-memory state; marker verification occurs only after the writer joins.

## Measured boundary

- Stable: 8, 16, 32, 64, and 128 clients. Every requested admission succeeded, evidence markers were exact, processes exited, and ownership counters returned to zero.
- Degraded: no cell met only the DEGRADED criteria.
- Saturated: 256 and 512 clients.
- Highest fully successful client count: 128/128 in every repeat.
- Highest median admission rate: 74.71 admissions/s at 128 clients.
- 1024 clients were not run because the 512-client cell admitted only 314/512 at the median and exceeded destination cleanup bounds.

| Clients | Task | Median admissions | Admissions/s | Admission p99 ms | Established Gbit/s | Effective cores | Private MiB | Threads | Handles | Cleanup |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 64 | Task 4b | 64/64 | 81.85 | 604.47 | 0.631 | 1.37 | 54.2 | 18 | 394 | PASS |
| 64 | Task 4d | 64/64 | 58.17 | 471.58 | 0.650 | 1.32 | 52.0 | 19 | 394 | PASS |
| 128 | Task 4b | 126/128 | 6.26 | 8260.08 | 0.549 | 1.91 | 102.0 | 18 | 460 | FAIL |
| 128 | Task 4d | 128/128 | 74.71 | 1188.79 | 0.648 | 1.33 | 82.6 | 19 | 459 | PASS |
| 256 | Task 4b | 83/256 | 4.12 | 4895.19 | 0.607 | 1.27 | 145.4 | 18 | 592 | FAIL |
| 256 | Task 4d | 229/256 | 43.47 | 3518.41 | 0.629 | 1.39 | 124.6 | 19 | 591 | PASS cleanup; SATURATED admission |
| 512 | Task 4d | 314/512 | 49.98 | 4127.94 | 0.687 | 0.86 | 213.5 | 19 | 855 | FAIL |

Task 4d eliminated the measured filesystem polling mechanism: there are no lifecycle `read_dir` loops or driver-complete polling, and only one terminal marker is written per client outside the network runtime. The previous ETW counts and current Typeperf context-switch rates use different scopes, so they are not treated as a numeric before/after comparison.

## Next measured boundary

At 256 clients, the first failures are the unchanged five-second QUIC handshake deadline: the five repeats admitted 219--255 clients while host CPU median was 23.6%, processor queue median was zero, and more than 6.9 GiB memory remained available. At 512, median completion fell to 314/512 and destination shutdown exceeded the existing 15-second observation bound in multiple repeats. This excludes whole-host CPU, scheduler queue, and memory exhaustion as the measured cause.

The failure mechanism is concurrent QUIC handshakes expiring before the single source/destination current-thread harness completes them. The underlying scheduling or network-stack hotspot is not attributable from the non-profiled Task 4d telemetry. A matched elevated ETW comparison at 128 and 256 clients is required before driver sharding or another harness change; no production bottleneck is claimed.
