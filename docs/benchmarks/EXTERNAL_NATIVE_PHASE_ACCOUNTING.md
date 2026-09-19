# Native packet phase accounting

Optional capture `--phase-markers` publishes `phase_control_endpoint` in
`capture-ready.json`. Pass this exact endpoint as source peer `--phase-control`.
Both existing release benchmarks use the same counter-control handshake; no
Rust, wire, authority, authentication or workload change is required.

The controller binds only 127.0.0.1, accepts three bounded ordered messages,
submits one distinct UDP token per transition and ACKs submission. Capture
presence is independently verified after completion. Missing, duplicate or
reordered markers invalidate accounting; no retry or silent fallback applies.
The original benchmark's two-second control timeout is unchanged.

Captured packet-order windows are setup, stream validation/warmup, established
work with postflight, and teardown. Established work includes mandatory untimed
postflight payload validation and the existing 100 ms ACK drain. These windows
are not pure timed-operation accounting or exact semantic attribution of every
asynchronous QUIC packet. All windows must reconcile with whole-flow totals.
Generic QUIC/IP/UDP bytes are not an NBSR-specific overhead claim.

Phase-enabled and disabled runs are distinct observer cohorts. Performance
timing remains DIAGNOSTIC. Captures retain complete inventory, zero-drop, MTU,
exact tuple, start/end marker and fixed-work gates. Physical network/server
validation remains separate from Docker namespace evidence.

Implementation verification at parent 52824743: literal missing-module RED and
phase-parser RED retained under C:/NBSR-build; 114 affected tests GREEN, Ruff and
diff whitespace checks pass.

Live validation at 6b1095c5 completes 20/20 cells: five matched pairs each at
1 KiB/64 streams and 16 KiB/eight streams. All four phase windows match separate
TShark packet-count/IP-byte queries. Forty live endpoint joins and 160 negative
identity/port controls pass. See
[canonical results](../../evidence/performance/v2/native-phases-6b1095c5/summary.md).
An initial controller-order mistake and its same-capture read-only reanalysis
are retained separately; none is pooled into the corrected full cohort.
