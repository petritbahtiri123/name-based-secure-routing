# Native 512/1024 finite cardinality at 200 offered/s

**MEASURED: five of five complete cells at each cardinality.** Exact release
source `3c3f784a`, unchanged Rust binaries, two source shards, native local
TLS/control/output, fresh Docker namespaces and guest affinity `[0]` for both
roles on one WSL host. No keepalive or timeout change.

| Cardinality | Repeats | Completed | Held RSS source / destination | Held FDs | Threads |
| --- | ---: | ---: | --- | --- | --- |
| 512 | 5/5 PASS | 2,560/2,560 | 199.125 / 164.25 MiB | 523 / 8 | 4 / 2 |
| 1024 | 5/5 PASS | 5,120/5,120 | 384.5 / 320.5 MiB | 1035 / 8 | 4 / 2 |

RSS/FD/thread figures are the median of each cell's median samples during the
fully active hold. Both roles have exact named active/release/ACK sets, validated
payload cardinality, live socket binding, zero final values for all eleven owned
resource counters and zero process exit. Independent process scans find no
measurement executable remaining before each container is stopped.

Each bundle couples one connection/session/channel/materialized stream under
shared test identities and one service. These are not independent subscribers
or tenants. A paired increase of 512 bundles gives a **DERIVED** median combined
RSS increment of 698,112 bytes (681.75 KiB) per additional bundle. This includes
QUIC/TLS, allocator and benchmark state; it is not a separate per-session or
per-connection allocation measurement. Fresh processes cannot establish
same-process retention, allocator plateau or a leak.

## Timing and CPU remain diagnostic

| Count | Median cell cold-handshake p50 / p95 / p99 | p99 CV across five cells |
| --- | --- | ---: |
| 512 | 74.751 / 146.030 / 166.659 ms | 67.967% |
| 1024 | 361.874 / 1017.727 / 1028.178 ms | 48.726% |

The timer includes synchronous TLS reads/configuration before QUIC connect.
The held-payload interval is deliberate and is not forwarding latency. High
dispersion remains visible; functional completion is not latency stability.
Startup-to-active sampled CPU averages approximately 0.552 / 0.404 guest cores
at 512 and 0.521 / 0.442 at 1024 for source/destination respectively. Their
intervals differ, so do not sum them into a measured simultaneous utilization
or physical hardware ceiling. Shared guest CPU pressure is a defensible next
measurement question, not an established explanation for every delay.

## Comparability, tests and retained evidence

This is a **new 200/s workload**, counterbalanced 512→1024 on odd repeats and
1024→512 on even repeats. The earlier 100/s cohort is not replaced. At 100/s the
nominal 1024 launch span plus hold exceeds the existing destination idle lifetime;
at 200/s the nominal span is 5.115 seconds before the unchanged two-second hold.
The new workload is not an achieved or sustainable 200 admissions/s claim.

Each cell has equivalent fresh test certificates, byte-identical between its
two roles, not across cardinality cells. This is a cardinality/resource study,
not exact-certificate-byte causal attribution. Historical keepalive-enabled
2048-bundle results remain separate; 1024 is not asserted as the largest scale
ever observed or as a production ceiling.

Three literal RED tests establish the previous Python-only 512 bound. The
extension uses one shared cardinality contract, keeps 2048/bool rejection and
requires all 1024 clients rather than accepting 1023. All 112 focused tests,
Ruff and diff checks pass. No production or dependency change was required; the
new release rebuild produces the same three Rust binary hashes as before.

`analyze.py` independently rechecks complete endpoint/pair indexes, local and
coordinator hold/cooldown, exact workload/source provenance, cleanup and sampled
resource intervals. `analysis.json` retains every cell and the five individual
RSS deltas. `raw-evidence.json` binds raw roots and tests by checksum.

```powershell
python evidence/performance/v2/native-lifecycle-1024-3c3f784a/analyze.py
```

**NOT_PROVEN:** sustained admission, observer-qualified latency, current physical
single-/multi-core capacity, independent object cost, same-process retention,
60/120-minute soak, physical server/NIC/WAN behavior or a production ceiling.
