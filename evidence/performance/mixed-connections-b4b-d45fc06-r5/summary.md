# B4b Mixed Connections and Route Admissions

Evidence: **PASS**
System: **SATURATED**

| Clients | Connections/client | Admissions/s | Established Gbit/s | Goodput/base | p95/p99 ms | p99/base | CPU s | Peak private MiB | Pending clients | Fail/timeout | Status |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 0 | 0.00 | 0.388 | 1.000 | 0.502/0.647 | 1.000 | 44.72 | 15.2 | 0 | 0/0 | BASELINE |
| 1 | 4 | 7.53 | 0.365 | 0.943 | 0.554/0.699 | 1.079 | 45.17 | 12.5 | 1 | 0/0 | STABLE |
| 2 | 4 | 12.98 | 0.363 | 0.938 | 0.564/0.717 | 1.108 | 45.28 | 14.5 | 2 | 0/0 | STABLE |
| 4 | 4 | 25.57 | 0.364 | 0.938 | 0.568/0.716 | 1.107 | 44.64 | 17.3 | 4 | 0/0 | STABLE |
| 8 | 4 | 34.56 | 0.361 | 0.932 | 0.593/0.758 | 1.171 | 45.06 | 30.6 | 8 | 0/0 | STABLE |
| 16 | 4 | 49.02 | 0.334 | 0.863 | 0.635/0.807 | 1.247 | 46.23 | 55.2 | 16 | 0/0 | DEGRADED |
| 32 | 4 | 57.75 | 0.336 | 0.866 | 0.678/0.882 | 1.363 | 45.75 | 82.2 | 12 | 0/0 | DEGRADED |
| 64 | 4 | 60.79 | 0.297 | 0.766 | 0.774/1.079 | 1.666 | 46.59 | 121.6 | 19 | 0/0 | DEGRADED |
| 128 | 4 | 22.22 | 0.271 | 0.699 | 0.803/1.092 | 1.687 | 47.66 | 205.5 | 71 | 1032/258 | SATURATED |

First saturation: 128 clients — admission failures; timeouts; admission completion below 90%; established goodput below 75%

Each admission creates a fresh QUIC transport connection, ControlSession, federated route/channel, and application stream from an independent client process. All ownership counters must return to zero.

Limitation: established forwarding and admission churn use separate destination processes/listeners on the same Windows loopback host. This measures host contention and multi-client lifecycle behavior, not contention inside one shared destination runtime or WAN/server-class scaling.

Base Git SHA: `d45fc06fe9df7105f9517a8493d9135437dfdf4d`
Host: Windows-11-10.0.26200-SP0 / Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz
Command: `scripts/run_b4b_mixed_connections.py --output evidence/performance/mixed-connections-b4b-d45fc06-r5 --repeats 3 --duration-seconds 30 --warmup-seconds 5 --clients 0,1,2,4,8,16,32,64,128 --connections-per-client 4`
