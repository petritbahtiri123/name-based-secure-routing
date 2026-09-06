# B5 destination lifetime correction

**FUNCTIONAL_LIFECYCLE_REGRESSION_PASS; performance NOT_MEASURED.**

The B5 controller samples source and destination until the source exits, stops
the sampler, then writes an external completion-ACK file. The single-group
NBSR benchmark destination previously returned after transport cleanup without
waiting for that file. Direct already waited. Thus a healthy destination could
disappear while B5 still required continuous sampling.

An opt-in live regression reproduced this discrepancy with release binaries:
Direct stayed alive, while NBSR exited with code zero before the controller ACK,
after both eleven-counter cleanup reports had validated. This is a demonstrated
harness lifecycle mismatch. It does not retrospectively establish the exact
cause of the earlier sampler capture, whose original exception was discarded.

The optional `--p2a-post-cleanup-ack` flag keeps only the benchmark destination
process alive after `run()` and its final cleanup report. B5 supplies this flag
with the existing controller ACK path. Its wait has a 30-second bound; no
transport timeout is extended. The flag requires a cleanup report. Ordinary
invocations do not enable it, including existing Linux finite controllers.
Transport and run-local handles are already closed before this wait.

No production code, protocol ACK/send completion, wire format, authority,
security check, workload, rate, or observer acceptance threshold changed.
Failed B5 runs still kill/join their owned processes without publishing ACK.

Validation: literal live RED was 1 PASS / 1 FAIL. After the correction, 44
focused Python tests passed. A further Direct/NBSR live test verified actual
Windows process sampling after cleanup and before ACK: 2 PASS. The affected
release Rust server tests passed 23/23. Release build, rustfmt, release Clippy
with `-D warnings`, Ruff and diff checks passed. One focused parent review found
no Important correctness/security issue. These are functional tests, not
performance repeats or qualified capacity observations.

The retained external root is `C:/NBSR-build/b5-destination-hold-a1ec0649`.
All 51 indexed raw artifacts were freshly verified, including before/after
test output, final reports, exact tested source and release binaries. Ephemeral
authority private keys were excluded. Raw index SHA-256:
`5e48fd4cca835249130ed9ecbad487b2ce582b6c12a99e1a5c7bea522b79a206`.

Next: fresh exact-source benchmark qualification. The observed goodput drift
and sub-95% achieved/offered diagnostics are separate unresolved issues; this
lifecycle correction does not establish a near-ceiling soak or new capacity.
