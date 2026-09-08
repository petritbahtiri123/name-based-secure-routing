# B3 explicitly active bundle workload

The historical `bundles` workload remains unchanged, including its 1024-client
idle-expiry failures. `live-bundles` is a separate resource-scale scenario:
standard QUIC keepalive every one second maintains transport activity while
the controller admits and holds all bundles. It is not evidence that the
original idle workload passed, or a production optimization.

Use `scripts.run_b3_v2 --axis live-bundles --materialized-streams` with the
existing release provenance, Linux telemetry and repeat requirements. Each
bundle retains an authenticated connection, session, channel, authorized
request and both endpoint stream handles. Five repeats each at 512 and 1024
passed at 40b277fb. The active scenario now permits the next 2048/4096 steps;
those larger cells require their own evidence. The ordinary idle workload's
1024 bound, admission pace, sampling, release, cleanup and idle timeouts remain
unchanged. The larger Rust bound requires both the explicit keepalive and hold
flags with benchmark-harness enabled. Resource scopes and names differ so old
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

## Executed 40b277fb evidence

`evidence/performance/v2/b3-live-bundles-40b277fb` binds release binaries,
commands, all raw indexes, RED/GREEN logs and independently recomputed analyses.
512 and 1024 materialized live bundles pass five repeats each, all eleven
ownership fields zero on both roles, with process exit. Active private-resident
CV is 0.52-0.84% across the four count/role cells. Sums of the role-specific
active private-resident medians are 354,717,696 and 692,006,912 bytes respectively. The derived
658,768 bytes/bundle slope is only a two-point 512-to-1024 estimate including
QUIC, runtime, allocator and fixture costs, not pure NBSR object size.

Five same-process 100-cycle repetitions complete 500 cycles with clean owned
resources and zero first-to-last FD/thread growth. Source private-resident
first-to-last growth is 3,231,744-3,256,320 bytes; destination growth is
126,976-503,808 bytes. Second-half slopes remain positive in some repeats;
memory cause and a general plateau remain INCONCLUSIVE. Do not call this a
leak or proven allocator retention. It is not a forwarding/admission soak.

This is Docker/WSL on one selected guest CPU, not verified host physical-core
or server capacity. The old idle workload and the new materialized keepalive
workload differ; matched materialized idle controls remain pending here.
