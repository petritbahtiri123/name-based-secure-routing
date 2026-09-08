# B4 Linux owned-child exit transition

At source 40b277fb, the one-guest-core admission ladder stopped during the
100/s cell with PermissionError reading /proc/2090/fd. Both diagnostic stat
reads retained start_ticks 706474, state R, RSS zero and flags 4194572
(PF_EXITING bit 0x4 set). Earlier valid cells and the failed prefix remain in
C:/NBSR-build/linux-requalification-40b277fb/admission-1core. This is a resource
observer failure, not a measured NBSR admission ceiling.

The B4-specific sampler now uses the existing identity/affinity-checked exit
observation only after PermissionError. PF_EXITING FD loss is recorded as
UNAVAILABLE_EXITING with absent memory/FD values, never as zero usage. B4
requires a prior matching live identity and subsequent owned Popen completion
before summarization. CPU remains sampled intervals, with terminal fragments
possibly missing. Live permission failures, changed identity, reversed counters,
a return to live state, and unconfirmed exit still fail. No timing, workload,
security, production transport or cleanup gate is changed.

Literal RED: two regression failures on the old backend. GREEN: 69 focused
Python tests, Ruff PASS. A non-root Linux fixture exercised 500 actual owned
Python-child lifecycles and captured four exiting observations with confirmed
completion. This fixture is diagnostic correctness evidence, not NBSR throughput.
One intermediate synthetic fixture clock error and initial Ruff failures are
retained. Raw tests: C:/NBSR-build/b4-exit-07096c08. The actual NBSR ladder must
be rerun on a clean source-bound build; no post-fix capacity is claimed yet.
