# Linux FD denial: failure-only attribution context

The Linux B4 compatibility cohort at c62b1165 retained six valid repeats, then
aborted on `/proc/74/fd` during the fourth 200/s repeat. PID74 was the admission
destination, with512 admissions and a PASS result already retained. Its last
resource state was S, not an observation at the exception. The failure-time
state and traceback were not preserved. Root cause remains UNRESOLVED.

1. Literal RED: preserve the already-read initial/recheck stat values when live
   FD access remains denied, label the memory sampler subphase, retain traceback
   and exception notes in bounded failure metadata.
2. Minimal change: add context only on the existing exception path. No new
   successful-path reads, retries, sleeps, permission bypass or accepted states.
3. Focused tests, one review, evidence and atomic commit. A later fresh diagnostic
   may use the context; original failures and valid repeats remain immutable.

Status: COMPLETE for diagnostic support. Five literal RED failures preceded the
minimal change;67 affected tests and scoped Ruff pass. One independent focused
review found no Important issues. The original denial remains UNRESOLVED; no
performance rerun or permission-recovery change is claimed.
