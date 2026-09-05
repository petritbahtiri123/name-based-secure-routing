# Post-change AFD verification: Windows 1 MiB listener receive buffer

MEASURED: no AFD datagram-drop (1033) events in the entire matched post-change trace. The same enabled provider/filter produced 13,248 create and 10,592 bind events, confirming active collection. Trace reports zero lost events and buffers. All five repeats at 200/s and all five at 250/s have zero captured drops. This verifies removal of the previously observed socket-buffer loss in these captured workloads; it does not prove absence of drops in every possible workload or establish host capacity.

Control/capture repository SHA, full recorded source fingerprints and release binaries match at 2ee765e70ae8b80471f3867771868ecaf246f638. Both raw manifests and ETL hash verified. All 20 records are valid with zero cleanup residuals. All 20 admission destination logs report actual udp_receive_buffer_bytes=1048576.

| Offered/s | Unobserved admissions/s | Captured admissions/s | Unobserved/captured handshake p99 ms | AFD drops |
|---|---|---|---|---|
| 200 | 172.626 | 177.491 | 19.563 / 18.399 | 0 |
| 250 | 148.062 | 120.065 | 116.524 / 192.596 | 0 |

DIAGNOSTIC: both observer gates fail, so capture timings are not interchangeable with control timings. Block order also permits temporal host drift. The captured receive-buffer artifact is removed, but admission saturation remains. Historical strict-stable throughput/admission claims are unchanged; stable/degraded/saturated boundaries still require progressive remeasurement after residual artifacts are attributed.

Next attribution target: destination benchmark accept-loop progress and timer wake latency. Current harness repeatedly scans pending accept futures and races that scan against a 1 ms sleep. This source observation is only a profiling lead, not proof of a bottleneck. No new optimization is justified without timing evidence and an observer-impact check.

Reproduce role analysis using scripts/analyze_b4b_task4l_afd.py with the external root and a new output path. Raw ETL, ordered AFD export, measurements and complete checksum manifests remain external; external-inputs.json binds them. Privacy: only loopback port mappings and aggregate event counts enter this package. No protocol/security/trust/authority change is made by this evidence stage.
