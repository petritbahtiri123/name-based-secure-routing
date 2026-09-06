# Linux FD failure context

The earlier Linux B4 cohort remains INVALID_PARTIAL_DIAGNOSTIC. Its fourth
200/s repeat failed while sampling admission-destination PID74 after512 successful
admissions. Last retained S state is not failure-time state; the existing zombie
recheck did not yield an accepted same-identity Z result. Root cause is UNRESOLVED.
See ../linux-b4-compatibility-c62b1165/REPORT.md for the immutable original evidence.

This harness-only change records the already-read initial and recheck stat fields
when FD PermissionError is re-raised for a live process. The memory sampler adds
before/after-smaps phase notes. Linux B4 failure metadata retains a bounded
traceback with exception notes and no captured locals. No successful-path reads,
retry, permission bypass, accepted state, workload or timeout changed.

Five literal RED cases failed on missing notes/helper;67 affected tests then
passed. Ruff passed on all changed Python files. The existing zombie/identity
and live-resource fail-closed regression tests remain passing. This is diagnostic
support, not a fix for the original denial, nor a performance or capacity result.

Commands: python -m pytest tests/performance/test_linux_failure_context.py -q
(RED); then the same new test plus test_linux_sampler_zombie.py,
test_linux_resources.py and test_b4_linux.py (GREEN). Ruff covered the four
changed implementation files and new test. Raw logs/source snapshots are bound
externally; repository logs normalize line endings and trailing whitespace.

One focused independent review is recorded in review.txt. Original run evidence
is unchanged. A fresh diagnostic must use the new failure helper to retain notes.
