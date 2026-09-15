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
