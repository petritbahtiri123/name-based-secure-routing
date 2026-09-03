# B4b-v2 Multi-client Connection and Route Scaling

Evidence: **PASS**
System: **SATURATED**

| Clients | Repeats | Admissions | Admissions/s | Established Gbit/s | Goodput CV | p99 ms | p99/base | Cores | Private MiB | Pending | Errors/timeouts | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 3 | 0/0 | 0.00 | 0.705 | 2.74% | 0.327 | 1.000 | 1.30 | 17.7 | 0 | 0/0 | BASELINE |
| 8 | 3 | 8/8 | 23.88 | 0.639 | 1.25% | 0.353 | 1.081 | 1.30 | 29.5 | 6 | 0/0 | STABLE |
| 16 | 3 | 16/16 | 32.29 | 0.630 | 1.10% | 0.380 | 1.163 | 1.32 | 35.4 | 3 | 0/0 | DEGRADED |
| 32 | 5 | 32/32 | 44.47 | 0.616 | 19.47% | 0.468 | 1.434 | 1.31 | 58.1 | 0 | 0/0 | DEGRADED |
| 64 | 3 | 64/64 | 40.14 | 0.588 | 1.59% | 0.551 | 1.686 | 1.30 | 108.2 | 0 | 0/0 | DEGRADED |
| 128 | 3 | 128/128 | 42.93 | 0.543 | 0.25% | 0.634 | 1.941 | 1.29 | 81.6 | 0 | 0/0 | DEGRADED |
| 256 | 5 | 81/256 | 11.17 | 0.441 | 2.16% | 0.660 | 2.023 | 1.32 | 350.1 | 111 | 1736/868 | SATURATED |

First degraded cell: 16
First saturated cell: 256
Stop reason: three valid SATURATED repeats at 256 clients

Each requested client is an independent process creating one fresh QUIC transport connection, control session, route/channel admission, and application stream while established forwarding remains active. Separate destination listener processes are benchmark plumbing and are included in owned-resource telemetry.

The classification uses the Funding-Grade V2 thresholds. A hardware limit is not inferred from throughput alone.

At 256 clients the median admission result was 81/256, with 868 total QUIC handshake timeouts across five valid repeats, 111 median peak pending clients, 224 peak owned processes, 906 threads, and 18,123 handles. Host Processor Time was 47.7% median, Processor Queue Length was zero median, and approximately 7.0 GB remained available. All destination ownership counters returned to zero and every owned process exited.

The measured limiting boundary is therefore **HARNESS-LIMITED_PROCESS_LISTENER_FANOUT_HANDSHAKE_DEADLINE**: the process/listener-per-client topology reaches the existing handshake deadline before CPU or memory saturation. This evidence does not distinguish Windows scheduling delay from process-launch or QUIC scheduling contributions without ETW, and does not establish a production NBSR or hardware limit. The 512-client cell was not run because five valid 256-client repeats already satisfied the saturation stop rule.

Command: `scripts/run_b4b_v2.py --output 'evidence\performance\v2\b4b-772996e9cced' --duration-seconds 20 --warmup-seconds 2`
