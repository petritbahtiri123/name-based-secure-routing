# Task 4d In-memory Lifecycle Coordination Findings

Classification: **Evidence FAIL / System SATURATED / Boundary HARNESS-LIMITED; next root cause UNRESOLVED**.

This is Windows loopback evidence with the unchanged established-forwarding pair, one source driver, and one concurrent admission destination. No production, protocol, security, wire, timeout, or frozen-authority code changed.

## Final measured boundary

- 34 valid repeats: 3 at baseline, 8 and 16 clients; 5 at 32, 64, 128, 256 and 512.
- STABLE under the existing classifier: 8--128 clients, with every requested admission successful and zero ownership after cleanup.
- DEGRADED: no cell met only that classification.
- SATURATED: 256 and 512 clients.
- Highest fully successful client count: 128/128 in every repeat.
- Highest median admission rate: 66.10/s at 64 clients.
- 512 admitted 296/512 at the median and exceeded destination cleanup bounds; 1024 was not meaningful and was not run.

| Clients | Task | Median admissions | Admissions/s | Admission p99 ms | Established Gbit/s | Established p99 ms | Effective cores | Private MiB | Threads | Handles | Cleanup |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 64 | 4b | 64/64 | 81.85 | 604.47 | 0.631 | 0.375 | 1.37 | 54.2 | 18 | 394 | PASS |
| 64 | 4d | 64/64 | 66.10 | 345.45 | 0.695 | 0.329 | 1.32 | 52.7 | 19 | 393 | PASS |
| 128 | 4b | 126/128 | 6.26 | 8260.08 | 0.549 | 0.453 | 1.91 | 102.0 | 18 | 460 | FAIL |
| 128 | 4d | 128/128 | 38.65 | 3040.36 | 0.657 | 0.354 | 1.36 | 82.3 | 19 | 459 | PASS |
| 256 | 4b | 83/256 | 4.12 | 4895.19 | 0.607 | 0.400 | 1.27 | 145.4 | 18 | 592 | FAIL |
| 256 | 4d | 226/256 | 42.39 | 3263.50 | 0.670 | 0.371 | 1.38 | 123.4 | 19 | 592 | PASS cleanup; admission SATURATED |
| 512 | 4d | 296/512 | 52.98 | 4234.30 | 0.681 | 0.398 | 0.87 | 213.9 | 19 | 855 | FAIL |

The historical comparison is `../b4b-task4b-final2-b0498aceb519/analysis.json`. Task 4d admission elapsed time ends at source-process terminal completion, including close and writer drain; Task 4b observed its filesystem completion markers. Rates are therefore conservative operational comparisons, not an isolated admission-code speedup. Payload, operation, deadline, and per-client outcome accounting are unchanged. STABLE describes the existing forwarding/completion criteria, not an absolute admission-latency SLO: 128-client admission p99 is still 3.04 seconds.

Successful-handshake percentile medians across repeats (milliseconds; failed handshakes are censored at the unchanged deadline and excluded, not treated as fast successes):

| Clients | Task 4b p50/p95/p99 | Task 4d p50/p95/p99 |
| ---: | --- | --- |
| 64 | 96.390 / 114.307 / 115.369 | 77.174 / 100.421 / 100.492 |
| 128 | 155.720 / 1418.111 / 2876.127 | 158.173 / 1108.247 / 3026.246 |
| 256 | 279.702 / 313.468 / 314.187 | 1151.955 / 3148.959 / 3150.326 |
| 512 | 469.666 / 496.620 / 503.843 | 1334.018 / 3339.472 / 3343.872 |

These are reproducible from each repeat's `admission-source.stdout`, filtering successful rows with `transport_handshake_ns`, applying `scripts.run_b4b_mixed_connections.percentile` at 0.50/0.95/0.99, then taking the median across repeats. The high-load distribution changed because more slow handshakes now succeed; it must not be interpreted independently of admission completion ratio.

## Coordination and cleanup

Each client records one in-memory terminal state before enqueuing its marker. Unknown/duplicate IDs cannot advance completion. The bounded dedicated writer uses create-new files and checks exactly one `.ack` or `.failed` per expected ID. It signals completion in memory; `finish` uses one deadline and joins only a finished writer. A writer timeout invalidates the run and cannot make Tokio runtime shutdown wait on a blocked join.

Python additionally requires a successful source/writer exit, not merely exact marker filenames, before accepting terminal evidence. Filesystem failure leaves the recorded lifecycle outcome unchanged and fails evidence validity.

All source terminal markers were exact in every final repeat. All eight destination ownership counters were zero through 256 clients. At 512, every destination exceeded the existing 15-second process cleanup observation bound; repeat 5 also retained one QUIC connection at the final telemetry sample. The overall evidence remains FAIL rather than hiding this result.

Source process completion at 128 took 1.687--3.522 seconds; at 256 it took 5.253--5.378 seconds. The runner does not isolate cleanup-only duration from admission/close/writer time, so no separate cleanup-duration number is claimed. Pending-client telemetry remains a peak/process-completion observation, not a per-client time series.

The old lifecycle `read_dir` polling path is absent from both Rust binaries and Python lifecycle synchronization. Current host context-switch medians were approximately 41,000--44,000/s. No post-change ETW trace was captured, so these aggregate Typeperf measurements are not numerically compared with Task 4c per-thread ETW switch counts. Removal of the filesystem polling hotspot is code-verified; disappearance of all filesystem/context-switch pressure is not claimed.

## Next boundary and stop

At 256, all 177 failed admissions across five repeats were unchanged five-second handshake timeouts; 198--233 clients succeeded per repeat. Host CPU median was 22.8%, processor queue median zero, and memory remained available. At 512, 282--347 clients succeeded per repeat and destination shutdown stalled. These data do not establish a hardware ceiling.

The measured failure mechanism is concurrent QUIC handshakes expiring plus destination accept/cleanup completion stalling at higher client counts. The exact runtime, socket, or scheduler hotspot is UNRESOLVED without a new matched ETW trace at 128/256. No sharding, deadline adjustment, or further optimization was implemented. B3-v2 was not started.

## Preserved non-final runs

- `../b4b-task4d-pre-writer-shutdown-361c315038bb/`: complete 34-repeat draft run, superseded after a focused test proved the blocking-join shutdown defect. Raw data retained.
- `../b4b-task4d-interrupted-baseline-361c315038bb/`: interrupted baseline, rejected because Rust verification overlapped it. Not used in final measurements.

Final results are only those in this directory's `analysis.json` and `raw/`.
