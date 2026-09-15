# B3 failure-only marker timing

The c267837c acceptance-window comparison did not establish a reliable fix.
Existing marker publication separates starts, transport connection completion,
materialization and release. Previously only marker names survived failed runs.

The runner now saves `failure-markers.json` after stopping its child processes
and before temporary-directory cleanup. Only named lifecycle marker metadata is
retained: filename, filesystem modification timestamp and byte size. Contents,
unrelated files, directories and symlinks are excluded. Filesystem errors mark
the snapshot unavailable and do not create a passing workload.

This introduces no new operation inside the measured workload. Differences
between timestamps are DERIVED marker-publication intervals, including scheduler
and filesystem work. They are not exact QUIC or NBSR admission latency. Wall
clock adjustment and filesystem timestamp resolution must be checked before
interpreting intervals; negative intervals are invalid diagnostic timing.

Validation: three literal failing stub tests, then 14 focused passing tests and
scoped Ruff/diff checks. The initial test fixture's byte-size expectation was
corrected from 24 to 23; that correction does not affect timestamp assertions.
Matched runtime evidence is pending. No throughput or capacity claim follows
from this diagnostic change, and the default acceptance window stays one.

## Five current-source attempts, 2026-09-15

At 72a9cafb, five 2048-bundle, one-guest-CPU attempts completed: repeats 1, 2
and 5 passed with zero final owned resources; repeats 3 and 4 failed. This is
not a repeatable stable scale. Release binary hashes match c267837c exactly.
All 6287 child-index entries were verified after copying guest-native evidence.

Repeat 3 had 249 handshake timeouts, all without a connected marker. Repeat 4
had 482 handshake timeouts without connected markers and one client-task failure
after connection but before active materialization. All first 1024 clients in
both failed attempts reached active. Failures concentrate in later client IDs.
Start publication spans were 20.4684 and 20.4654 seconds for 2048 clients at the
unchanged 100 starts/s. Start timestamps were nondecreasing.

For successful connections in the final 512-client cohort, start-to-connected
p99 marker intervals were 5016.285 and 5007.321 ms; connected-to-active p99 was
120.006 and 144.010 ms respectively. These are survivor-only filesystem timing
distributions, not a replacement for measured handshake latency. No negative
intervals were found; wall-clock adjustment was not independently qualified.
The dominant missing stage is before connection publication. This does not yet
separate source scheduling, configuration, socket processing and TLS progress.

Failure-only destination UDP drop totals were 3336 and 15688, with retained
source sockets reporting zero. Timing/closed-socket limitations still apply.
No default change or production optimization is justified by this series.

Canonical evidence: `evidence/performance/v2/b3-failure-markers-72a9cafb`.
Raw evidence: `C:/NBSR-build/b3-failure-markers-72a9cafb`; exact release build:
`C:/NBSR-build/linux-current-72a9cafb`. All attempts and failures are retained.
