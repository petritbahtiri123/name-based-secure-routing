# Guest CPU placement diagnostic, source 2da82de2

MEASURED: five counterbalanced pairs, 1024 finite bundles, 200 offered/s, two
source shards, unchanged 1 KiB payload, hold/release/ACK/cooldown gates. Only
owned Rust child CPU placement differs: shared [0]/[0], split [0]/[1]. Controller
placement is unchanged. Fixture hashes match across both arms within each pair.
Fresh namespaces and native local TLS/control storage are used for every cell.

| Placement | Complete passes | Retained failures |
| --- | ---: | ---: |
| Shared guest CPU | 2/5 | 3/5 |
| Split guest CPUs | 5/5 | 0/5 |

All passing cells complete 1024 bundles and all eleven ownership counters return
to zero. Post-run namespace scans returned empty, but skipped PermissionError entries;
therefore those scans alone do not independently prove absence of owned processes.
Use retained owned-child terminal/reap and group-cleanup records for cleanup scope.
Failure cleanup is not proof of graceful zero counters.
Shared repeat 2 fails after activation during close/ACK with failed markers and
timeout diagnostics. Shared repeat 3 fails BEFORE active: its source transcript
ends at readiness_transferred and destination stderr reports HandshakeFailed.
Repeat 5 reports destination cardinality mismatch and ApplicationStreamFailed.
This phase correction was verified against retained raw events on 2026-09-24;
the previous grouping of repeats 2/3 as post-activation was incorrect. These unfavorable valid workload outcomes remain in
the denominator, even though their incomplete endpoint package says INVALID_PARTIAL.

DIAGNOSTIC: split median-cell cold-handshake p50/p95/p99 =
2.660791/36.170890/84.147770 ms, p99 CV 68.670716%. Cold timer includes TLS setup.
Only two pairs fully pass both arms: shared/split p99 707.603146/58.736168 ms and
831.711223/125.576681 ms. These pairs are not a substitute for the failed shared
cells; no all-cohort speedup or strict-stable latency claim is made. Source
admission timer measures a local check, not end-to-end sustainable admission.

This supports guest allocation sensitivity. Split uses an additional selected
CPU. It does not prove a physical hardware ceiling, one-core versus two-core
server scaling, or a production NBSR bottleneck. No production code, security,
timeout, wire semantics or keepalive changed. Further timer/close attribution
remains open; do not invent a production optimization from this experiment.

The first pair completed before the declared 5 GiB reserve paused the driver.
Cargo cache cleanup recovered 5,572,845,568 host bytes; resumed pairs 2-5 kept
original order, fixtures and parameters. run-initial.py, run.py, resume.py and
resume.json preserve this maintenance gap. No cleanup overlapped a workload.
Additional stopped-container/network cleanup is retained separately and does not
claim SSD recovery. All authoritative evidence remains retained.

Verification: exact-source release build with unchanged three Rust hashes; 124
focused tests after literal RED; Ruff; independent endpoint/pair/index/affinity,
fixture-equivalence, hold/ACK/cooldown checks by analyze.py; full checksum/privacy
verification. Reproduce analysis from repository root with:

    python evidence/performance/v2/native-lifecycle-placement-2da82de2/analyze.py
    python C:/NBSR-build/verify-focused-evidence-20260916.py native-lifecycle-placement-2da82de2

raw-evidence.json binds full retained C:/NBSR-build roots and checksum indexes.
No private fixture files are published in this canonical package.
