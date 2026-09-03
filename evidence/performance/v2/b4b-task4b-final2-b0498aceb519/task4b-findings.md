# Task 4b Bounded Multi-client Harness Findings

Classification: **Evidence FAIL / System SATURATED / Boundary HARNESS-LIMITED (exact stack attribution pending)**

- Stable: 8, 16, 32, and 64 clients. All requested admissions succeeded and cleanup returned to zero.
- Saturated: 128, 256, and 512 clients.
- Highest fully successful client count: 64/64.
- Highest median successful-admission count: 126/128.
- Peak stable admission rate: 114.83 admissions/s at 32 clients.
- Stable 64-client result: 81.85 admissions/s, 0.631 Gbit/s established forwarding, 604.47 ms admission p99.
- 128-client result: 126/128 median admissions, 6.26 admissions/s, 0.549 Gbit/s, 8.260 s admission p99.
- 256-client result: 83/256 median admissions, 4.12 admissions/s, 0.607 Gbit/s, 4.895 s admission p99.
- 512-client result: 94/512 median admissions, 4.64 admissions/s, 0.588 Gbit/s, 4.868 s admission p99.
- 1024 was not run because the 512-client cell completed only 18.4% of requested admissions.

## Fan-out reduction

| Clients | Harness | Processes | Threads | Handles |
| ---: | --- | ---: | ---: | ---: |
| 64 | Task 4 | 64 | 305 | 5,313 |
| 64 | Task 4b | 4 | 18 | 394 |
| 256 | Task 4 | 224 | 906 | 18,123 |
| 256 | Task 4b | 4 | 18 | 592 |

The process count is now bounded independently of logical-client count. Each logical client retains its own connection, ControlSession, admitted route/channel/application stream, result record, and terminal marker.

## Cleanup and next boundary

All destination ownership counters and driver tasks returned to zero through 64 clients. At 128--512, processes exited but some in-process destination ownership remained live at the fixed cleanup observation bound, so the evidence classification fails closed as FAIL.

Host CPU remained approximately 21--23% median with a zero median processor queue and more than 6.9 GiB available memory. The observed collapse is therefore not a host CPU or memory ceiling. It occurs in the bounded harness while one current-thread source driver and one current-thread destination endpoint drive many concurrent QUIC connection/session lifecycles under the unchanged handshake deadline. A matched elevated WPR profile is required to attribute the exact stack/wait hotspot; no production optimization or fixed 2/4 driver sharding is justified from this evidence.
