# B4b Task 4c ETW attribution

Classification: **PASS / HARNESS-LIMITED**

The zero-loss kernel trace attributes the 64-to-128 collapse to synchronous 1 ms lifecycle-terminal directory polling on both single-thread Tokio runtimes. The network trace is supplemental and rejected for socket-error conclusions because it lost events.

| Clients | Connected | Control admissions/s | Handshake p99 ms | Total admission p99 ms | Cleanup errors | Source FS samples | Destination FS samples | Source main CS | Destination main CS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 64 | 52.44 | 146.31 | 1143.03 | 0 | 35.58% | 36.59% | 2,949,260 | 3,012,598 |
| 128 | 122 | 9.06 | 211.26 | 8316.76 | 63 | 41.27% | 42.12% | 13,242,356 | 12,931,831 |

Source main-thread context switches grew 4.49x; destination grew 4.29x.

Recommended harness-only change: replace per-task directory scans with one bounded in-memory completion coordinator. Preserve one terminal evidence marker per logical client, unchanged deadlines, and independent client state. Driver sharding is not yet justified.
