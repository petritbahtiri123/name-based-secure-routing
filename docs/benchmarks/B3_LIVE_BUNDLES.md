# B3 explicitly active bundle workload

The historical `bundles` workload remains unchanged, including its 1024-client
idle-expiry failures. `live-bundles` is a separate resource-scale scenario:
standard QUIC keepalive every one second maintains transport activity while
the controller admits and holds all bundles. It is not evidence that the
original idle workload passed, or a production optimization.

Use `scripts.run_b3_v2 --axis live-bundles --materialized-streams` with the
existing release provenance, Linux telemetry and repeat requirements. Each
bundle retains an authenticated connection, session, channel, authorized
request and both endpoint stream handles. Start with 512 and 1024; preserve
failures. The existing 1024 bound, admission pace, sampling, release, cleanup
and idle timeouts remain unchanged. Resource scopes and names differ so old
idle and new active scenarios cannot be pooled in analysis.

The keepalive configuration is available only with `benchmark-harness`.
It uses the existing transport configuration and TLS/peer policy; normal
production defaults are unchanged. Tests verify ordinary idle expiry,
keepalive liveness, invalid intervals, and wrong-identity rejection.

Implementation validation: literal Python RED 5 failures and Rust RED missing
method; GREEN 52 affected Python tests, 27 affected Rust tests, scoped release
clippy with warnings denied, and default-feature release check. Raw logs:
`C:/NBSR-build/b3-keepalive-09a669a3`. One intermediate compiler failure is
retained. Actual scale results must be reported separately after execution.
