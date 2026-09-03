# B4b-v2 Multi-client Connection and Route Scaling

Evidence: **FAIL**
System: **SATURATED**

| Clients | Repeats | Admissions | Admissions/s | Established Gbit/s | Goodput CV | p99 ms | p99/base | Cores | Private MiB | Pending | Errors/timeouts | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 3 | 0/0 | 0.00 | 0.692 | 3.78% | 0.326 | 1.000 | 1.32 | 15.7 | 0 | 0/0 | BASELINE |
| 8 | 3 | 8/8 | 55.96 | 0.647 | 0.19% | 0.330 | 1.011 | 1.31 | 16.5 | 8 | 0/0 | STABLE |
| 16 | 3 | 16/16 | 110.85 | 0.644 | 0.36% | 0.340 | 1.043 | 1.32 | 17.2 | 16 | 0/0 | STABLE |
| 32 | 3 | 32/32 | 114.83 | 0.644 | 0.23% | 0.341 | 1.046 | 1.31 | 28.2 | 32 | 0/0 | STABLE |
| 64 | 5 | 64/64 | 81.85 | 0.631 | 0.86% | 0.375 | 1.151 | 1.37 | 54.2 | 64 | 0/0 | STABLE |
| 128 | 5 | 126/128 | 6.26 | 0.549 | 6.33% | 0.453 | 1.389 | 1.91 | 102.0 | 128 | 486/473 | SATURATED |
| 256 | 5 | 83/256 | 4.12 | 0.607 | 2.88% | 0.400 | 1.226 | 1.27 | 145.4 | 256 | 1325/1086 | SATURATED |
| 512 | 5 | 94/512 | 4.64 | 0.588 | 2.90% | 0.413 | 1.267 | 1.27 | 228.3 | 512 | 2591/2350 | SATURATED |

First degraded cell: None
First saturated cell: 128
Stop reason: requested progression completed after SATURATED cell at 512 clients

Each logical client is an independent task in one bounded source-driver process and creates one fresh QUIC transport connection, ControlSession, route/channel admission, and application stream. One concurrent admission destination/listener is used; established forwarding remains the unchanged separate source/destination pair. Logical clients do not share NBSR sessions, and the authenticated TLS edge identity remains `source.edge`.

Harness fan-out comparison at 64 clients: Task 4 used 64 processes, 305 threads, and 5,313 handles at peak; Task 4b used 4 processes, 18 threads, and 394 handles. At 256 clients, peak process count fell from 224 to 4 and peak handles from 18,123 to 592.

Cleanup was complete through 64 clients. At 128--512, every owned process exited, but one or more destination ownership snapshots did not return to zero before the fixed cleanup bound; therefore evidence remains **FAIL**, not PASS. These bad-but-valid saturated cells are preserved.

The measured next boundary is harness-side connection/session scheduling through the single current-thread source driver and destination endpoint under the unchanged handshake deadline. Host CPU remained about 21--23% median with zero median processor queue and ample memory, so no hardware limit is claimed. Exact stack-level attribution requires a separate WPR profile.

The classification uses the Funding-Grade V2 thresholds. 512 clients was not technically meaningful enough to justify 1024: median completion was 94/512 (18.4%).

Command: `scripts/run_b4b_v2.py --output evidence/performance/v2/b4b-task4b-final2-b0498aceb519`
