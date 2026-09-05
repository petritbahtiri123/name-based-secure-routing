# B5 runner reliability repairs

The current P2A v2 result schema and bounded outstanding-operation workload are
supported. The final analyzer rejects throughput decay over 5% or p99 drift
over 20%; the matching live abort checks now use disjoint first/last thirds after at least
three steady-state progress windows. Accepted ceiling-consumption gates remain pending.

Focused synthetic child processes exposed three runner defects in literal RED:

- Writing 1 MiB to unread stderr blocked the child until its existing timeout.
- A rejected progress line left the child running until the workload timeout.
- An exception in the client-start callback left its owned child alive.

The helper now sends stderr to a file, retains a bounded error tail for the
exception, observes reader failures while waiting under the original deadline,
and encloses setup in owned-process cleanup. An explicit stderr path preserves
the complete diagnostic stream; ordinary callers use disposable temporary disk
storage. No production transport or workload timeout changed.

A fourth RED showed that a failed soak lost already received progress, resource
samples and reproduction commands. B5 now retains commands before process
launch, file-backed source/destination logs, partial parsed records, failure
classification and a raw-cell checksum manifest on exit. Failed/aborted runs
remain INCOMPLETE and cannot become stable-soak evidence.

Validation: 21 focused Python tests passed across `test_measured_client_failure`,
`test_long_run_streaming`, `test_b5_current_runner` and `test_sustained_capacity`;
Ruff passed on the changed Python files. These are harness regression results,
not long-duration performance evidence. Current near-ceiling soak execution is
still pending a defensible current strict-stable load and live abort gates.

Live guard regression: immediate reported errors/timeouts and throughput decay
over 5% or p99 drift over 20% stop the owned source through the existing reader
failure path. The offending window is appended before checking, and partial
evidence remains INCOMPLETE. Literal RED tests showed continuation after failure;
21 focused B5 tests then passed, with Ruff and one scoped review.

The first live comparison can contain one sample per third; this is an early
safety gate, not long-run stability qualification. Source progress begins after
the measurement barrier and excludes warmup. Missing latency samples do not
establish PASS. Resource-growth, thermal/power and measured-safe-boundary live
telemetry remain unimplemented; offline checks are not substitutes for them.
