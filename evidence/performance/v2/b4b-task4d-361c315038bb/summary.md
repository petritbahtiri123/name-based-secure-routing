# B4b-v2 Multi-client Connection and Route Scaling

Evidence: **FAIL**
System: **SATURATED**

| Clients | Repeats | Admissions | Admissions/s | Established Gbit/s | Goodput CV | p99 ms | p99/base | Cores | Private MiB | Pending | Errors/timeouts | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 3 | 0/0 | 0.00 | 0.714 | 0.33% | 0.309 | 1.000 | 1.30 | 12.6 | 0 | 0/0 | BASELINE |
| 8 | 3 | 8/8 | 30.32 | 0.682 | 3.77% | 0.318 | 1.028 | 1.32 | 17.1 | 8 | 0/0 | STABLE |
| 16 | 3 | 16/16 | 42.96 | 0.684 | 4.03% | 0.324 | 1.047 | 1.31 | 17.5 | 16 | 0/0 | STABLE |
| 32 | 5 | 32/32 | 62.44 | 0.702 | 5.59% | 0.319 | 1.031 | 1.32 | 28.8 | 32 | 0/0 | STABLE |
| 64 | 5 | 64/64 | 66.10 | 0.695 | 3.37% | 0.329 | 1.062 | 1.32 | 52.7 | 64 | 0/0 | STABLE |
| 128 | 5 | 128/128 | 38.65 | 0.657 | 1.75% | 0.354 | 1.144 | 1.36 | 82.3 | 128 | 0/0 | STABLE |
| 256 | 5 | 226/256 | 42.39 | 0.670 | 4.27% | 0.371 | 1.198 | 1.38 | 123.4 | 256 | 177/177 | SATURATED |
| 512 | 5 | 296/512 | 52.98 | 0.681 | 4.71% | 0.398 | 1.287 | 0.87 | 213.9 | 512 | 1015/1004 | SATURATED |

First degraded cell: None
First saturated cell: 256
Stop reason: requested progression completed after SATURATED cell at 512 clients

Each requested logical client is an independent task within one bounded source driver, creating one fresh QUIC transport connection, control session, route/channel admission, and application stream while established forwarding remains active. One concurrent admission destination and the unchanged established-forwarding pair are included in owned-resource telemetry.

The classification uses the Funding-Grade V2 thresholds. A hardware limit is not inferred from throughput alone.

Command: `scripts/run_b4b_v2.py --output evidence/performance/v2/b4b-task4d-361c315038bb`
