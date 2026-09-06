# Grouped B5 pacing and accounting contract

Status: tested primitives, **NOT live integration or soak evidence**. The Rust
module is deliberately test-only until both Direct and NBSR paths implement the
same pacing, common clock, drain, bounded publication and cleanup contract.
Existing benchmark execution remains unchanged.

The prior grouped source emits separate group results; the existing sustained
runner cannot interpret those as one paced workload. Existing periodic latency
storage also lacks a hard cap. These helpers prepare the smallest common
accounting boundary without changing transport/security behavior.

Pacing uses an exact rational aggregate operations/s rate and fixed windows.
The initial integration contract uses 10 ms windows, up to four groups and 64
streams/group. Stream partition `p = stream * groups + group` receives its share
of the cumulative integer budget. Unused windows expire in O(1); no catch-up or
borrowing is permitted. Reservation only consumes an offered slot; actual write
and response completion require separate counters. Existing outstanding limits
and payload/ACK validation remain mandatory.

Completion counts and globally sampled latency ordinals share one mutex. The
collector has a hard caller-derived sample capacity; overflow latches invalidity
and forbids publication while retaining exact completion accounting. Drained
buffers belong to the caller, which must also bound retained history. Sampling
capacity must account for publication interval, window edges, outstanding work
and stride carry; silently increasing it after an invalid run is not acceptance.

The streaming Python validator retains O(groups) copied counters. It reconciles
aggregate/group conservation, exact global-ordinal sample counts, ordered
quantiles, actual contiguous intervals, immutable issue deadline and final drain.
Intervals are steady, mixed across the deadline, or drain. No exact timer wakeup
is assumed. Mixed/drain intervals are excluded from steady drift analysis, but
their completions remain in drain-inclusive goodput. Finalization cannot invent
unpublished completions. Cleanup, source identity, achieved/offered ratio and
stability remain explicit caller gates, not validator success claims.

Validation: literal RED unresolved Rust helper imports and missing Python module;
GREEN nine new Rust tests (13 including existing B5 tests), 42 Python tests;
release Clippy with `-D warnings`, Rust fmt and scoped Ruff passed. One focused
independent review found no Important findings. Logs/checksums are retained in
`evidence/performance/v2/b5-pacing-contract-cfbe7357/`.

Remaining: integrate a common post-warmup origin and fixed issue deadline across
all runtimes, coherent progress timestamp/counters, stop propagation, equivalent
Direct/NBSR behavior, bounded stdout/resource history, postflight and two-sided
ownership validation. Then run matched calibration, observer checks and the
required long soaks. This preparation establishes no throughput/stability result.
