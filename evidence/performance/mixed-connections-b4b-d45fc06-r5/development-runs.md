# B4b Development and Prior Valid Runs

The authoritative result for this harness generation is this directory (`r5`).

In generated summary tables, throughput, latency, resource, scheduled-admission, and successful-admission fields are medians across repeats; `Fail/timeout` values are totals across all three repeats.

- `mixed-connections-b4b-d45fc06-r2` is retained because it contains valid low-to-high-load measurements and bad-but-valid 64-client `HandshakeTimeout` results. Its earlier failure accounting did not retain complete metrics for every failed repeat, so it is not the authoritative classification.
- `mixed-connections-b4b-d45fc06-r4` is retained because it is a valid three-repeat 0–64-client campaign. It includes a non-monotonic 1-client forwarding outlier that recovered at higher loads and motivated the terminal-region classification test.
- Two repository-excluded development campaigns were invalid harness evidence and remain on the measurement host under `C:\NBSR-build\b4b-invalid-16-connections-20260830` and `C:\NBSR-build\b4b-invalid-warmup-order-20260830`. The first scheduled 16 serial connection lifecycles per client and exceeded the fixed cleanup guard. The second started admission destinations before a five-second established-traffic warmup, causing their unchanged handshake timeout to expire before clients started. The latter produced the literal RED evidence for `test_admission_destinations_start_after_established_warmup`; the corrected ordering passed GREEN without changing a timeout or protocol behavior.

No result above is WAN, shared-destination-runtime, server-class, production, or hardware-limit evidence.
