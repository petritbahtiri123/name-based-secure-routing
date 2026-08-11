# P2B profile design

One operation preserves the accepted warm lifecycle benchmark: an existing QUIC Transport Session and authorized Service Channel, one new `STREAM_OPEN`, destination validation/admission, one new QUIC bidirectional Application Stream, one 1 KiB validated exchange, and terminal release/cleanup.

Direct uses one existing QUIC connection per logical run. NBSR logical runs are composed of sessions capped at 8,000 operations so normal profiling remains below the frozen 10,000-entry P1F replay cap. Session setup and teardown are excluded from timed lifecycle metrics. Offered rates are the accepted capacity percentages: Direct 2,375/4,275 ops/s and NBSR 843.75/1,518.75 ops/s for 50%/90%.

Instrumentation is compiled only with `benchmark-harness`, enabled only by `NBSR_P2B_PROFILE`, fixed to 18 aggregate phase labels, and emits no request IDs, payloads, tickets, keys, or retained object references. Timers do not alter success/failure control flow.

The destination control path is a single read, authorize, respond loop. Phase timers distinguish idle/dependency wait (`destination_control_read`, `quinn_accept_bi`) from active validation/admission subphases; idle/dependency timers are not interpreted as CPU ownership.
