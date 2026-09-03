# B4b-v2 Multi-client Connection and Route Scaling

Evidence: **FAIL**
System: **SATURATED**

| Clients | Repeats | Admissions | Admissions/s | Established Gbit/s | Goodput CV | p99 ms | p99/base | Cores | Private MiB | Pending | Errors/timeouts | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 3 | 0/0 | 0.00 | 0.714 | 0.58% | 0.307 | 1.000 | 1.31 | 16.9 | 0 | 0/0 | BASELINE |
| 8 | 5 | 8/8 | 31.12 | 0.657 | 0.43% | 0.317 | 1.034 | 1.33 | 13.5 | 8 | 0/0 | STABLE |
| 16 | 3 | 16/16 | 42.04 | 0.665 | 4.29% | 0.318 | 1.037 | 1.31 | 17.6 | 16 | 0/0 | STABLE |
| 32 | 5 | 32/32 | 50.99 | 0.645 | 0.60% | 0.345 | 1.124 | 1.32 | 28.6 | 32 | 0/0 | STABLE |
| 64 | 5 | 64/64 | 58.17 | 0.650 | 0.31% | 0.334 | 1.087 | 1.32 | 52.0 | 64 | 0/0 | STABLE |
| 128 | 3 | 128/128 | 74.71 | 0.648 | 0.37% | 0.353 | 1.152 | 1.33 | 82.6 | 128 | 0/0 | STABLE |
| 256 | 5 | 229/256 | 43.47 | 0.629 | 0.97% | 0.389 | 1.266 | 1.39 | 124.6 | 256 | 110/110 | SATURATED |
| 512 | 5 | 314/512 | 49.98 | 0.687 | 5.32% | 0.387 | 1.261 | 0.86 | 213.5 | 512 | 1069/1056 | SATURATED |

First degraded cell: None
First saturated cell: 256
Stop reason: requested progression completed after SATURATED cell at 512 clients

Each requested logical client is an independent task within one bounded source driver, creating one fresh QUIC transport connection, control session, route/channel admission, and application stream while established forwarding remains active. One concurrent admission destination and the unchanged established-forwarding pair are included in owned-resource telemetry.

The classification uses the Funding-Grade V2 thresholds. A hardware limit is not inferred from throughput alone.

Command: `scripts/run_b4b_v2.py --output evidence/performance/v2/b4b-task4d-361c315038bb`
