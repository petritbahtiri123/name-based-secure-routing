# B4b Mixed Connections and Route Admissions

Evidence: **PASS**
System: **SATURATED**

| Clients | Connections/client | Admissions/s | Established Gbit/s | Goodput/base | p95/p99 ms | p99/base | CPU s | Peak private MiB | Pending clients | Fail/timeout | Status |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 0 | 0.00 | 0.387 | 1.000 | 0.504/0.646 | 1.000 | 44.41 | 14.1 | 0 | 0/0 | BASELINE |
| 1 | 4 | 5.96 | 0.199 | 0.513 | 0.855/1.150 | 1.780 | 48.69 | 8.7 | 1 | 0/0 | SATURATED |
| 2 | 4 | 13.08 | 0.365 | 0.942 | 0.565/0.711 | 1.101 | 46.05 | 14.5 | 2 | 0/0 | STABLE |
| 4 | 4 | 25.05 | 0.362 | 0.936 | 0.573/0.728 | 1.126 | 44.89 | 17.1 | 4 | 0/0 | STABLE |
| 8 | 4 | 35.32 | 0.362 | 0.935 | 0.577/0.741 | 1.147 | 45.88 | 30.8 | 8 | 0/0 | STABLE |
| 16 | 4 | 48.40 | 0.349 | 0.902 | 0.621/0.802 | 1.241 | 45.84 | 55.2 | 16 | 0/0 | STABLE |
| 32 | 4 | 55.12 | 0.334 | 0.863 | 0.683/0.889 | 1.376 | 45.95 | 87.5 | 11 | 0/0 | DEGRADED |
| 64 | 4 | 61.40 | 0.294 | 0.760 | 0.777/1.062 | 1.644 | 45.73 | 102.9 | 16 | 0/0 | DEGRADED |

First saturation: 1 clients — established goodput below 75%

Each admission creates a fresh QUIC transport connection, ControlSession, federated route/channel, and application stream from an independent client process. All ownership counters must return to zero.

Limitation: established forwarding and admission churn use separate destination processes/listeners on the same Windows loopback host. This measures host contention and multi-client lifecycle behavior, not contention inside one shared destination runtime or WAN/server-class scaling.

Base Git SHA: `d45fc06fe9df7105f9517a8493d9135437dfdf4d`
Host: Windows-11-10.0.26200-SP0 / Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz
Command: `scripts/run_b4b_mixed_connections.py --output evidence/performance/mixed-connections-b4b-d45fc06-r4 --repeats 3 --duration-seconds 30 --warmup-seconds 5 --connections-per-client 4`
