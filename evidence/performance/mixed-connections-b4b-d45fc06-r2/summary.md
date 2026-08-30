# B4b Mixed Connections and Route Admissions

Evidence: **INCONCLUSIVE**
System: **DEGRADED**

| Clients | Connections/client | Admissions/s | Established Gbit/s | Goodput/base | p95/p99 ms | p99/base | CPU s | Peak private MiB | Pending clients | Fail/timeout | Status |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 0 | 0.00 | 0.358 | 1.000 | 0.560/0.701 | 1.000 | 28.30 | 8.7 | 0 | 0/0 | BASELINE |
| 1 | 4 | 7.44 | 0.342 | 0.955 | 0.600/0.744 | 1.062 | 28.88 | 9.2 | 1 | 0/0 | STABLE |
| 2 | 4 | 13.52 | 0.340 | 0.951 | 0.596/0.735 | 1.049 | 28.39 | 10.4 | 2 | 0/0 | STABLE |
| 4 | 4 | 22.10 | 0.338 | 0.946 | 0.606/0.751 | 1.072 | 28.44 | 16.9 | 4 | 0/0 | STABLE |
| 8 | 4 | 42.57 | 0.332 | 0.927 | 0.635/0.793 | 1.131 | 29.33 | 29.8 | 8 | 0/0 | STABLE |
| 16 | 4 | 56.90 | 0.328 | 0.918 | 0.656/0.842 | 1.202 | 29.25 | 55.5 | 15 | 0/0 | STABLE |
| 32 | 4 | 57.53 | 0.308 | 0.860 | 0.722/0.954 | 1.361 | 30.20 | 92.1 | 15 | 0/0 | DEGRADED |
| 64 | 4 | 64.19 | 0.288 | 0.806 | 0.779/1.099 | 1.568 | 31.30 | 147.6 | 15 | 0/0 | DEGRADED |

First saturation: not observed

Each admission creates a fresh QUIC transport connection, ControlSession, federated route/channel, and application stream from an independent client process. All ownership counters must return to zero.

Limitation: established forwarding and admission churn use separate destination processes/listeners on the same Windows loopback host. This measures host contention and multi-client lifecycle behavior, not contention inside one shared destination runtime or WAN/server-class scaling.

Base Git SHA: `d45fc06fe9df7105f9517a8493d9135437dfdf4d`
Host: Windows-11-10.0.26200-SP0 / Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz
Command: `scripts/run_b4b_mixed_connections.py --output 'evidence\performance\mixed-connections-b4b-d45fc06-r2'`
