# B3 paced marker publication, 2026-09-16

Status: bounded diagnostic step COMPLETE. Coarse notification prototype
NOT PROMOTED. Production and default harness behavior remain unchanged.

Question: does the idle CPU reduction in B3_EVENT_NOTIFICATION_SPIKE.md survive
100 marker publications/s? Five counterbalanced pairs compare the existing
shared scanner with the unchanged prototype. Each cell registers 2048 waiters,
settles for 30ms and publishes each distinct regular marker at a scheduled
10ms interval. Both arms retain the 120-second diagnostic waiter timeout.
The same current-thread runtime publishes and observes markers on guest CPU 0,
using a native temporary directory with zero unrelated files. This is not QUIC.

| Five-repeat median | Current scanner | Coarse notification prototype |
| --- | ---: | ---: |
| Process CPU, including publisher | 10.7916% | 10.9379% |
| Publication-to-wakeup p50 | 6.462675 ms | 6.396676 ms |
| Publication-to-wakeup p95 | 12.739430 ms | 12.719850 ms |
| Publication-to-wakeup p99 | 13.741964 ms | 13.783819 ms |
| Publication deadline lateness p99 | 2.302280 ms | 1.732387 ms |
| Completed/requested per repeat | 2048/2048 | 2048/2048 |

All ten cells completed and every requested marker identity was observed once.
CPU CV is 0.831%/0.372%; wakeup-p99 CV is 0.269%/0.508%. Publication-lateness
CV is 8.515%/16.532%, with all five repeats retained. Latency columns are medians
of per-run nearest-rank percentiles, not pooled percentiles or handshake timing.
Process CPU is measured at 100 ticks/s and includes identical publisher work.
Timed intervals last approximately 20.48 seconds; setup and analysis are outside.

DERIVED: prototype median CPU is 1.356% higher, and wakeup-p99 is 0.305% higher.
There is no measured material CPU or wakeup-latency benefit in this active cell.
The earlier 94--95% idle-wait saving must not be represented as a saving during
connection starts. The code performs a full pending-file scan whenever any
directory event arrives, so event churn remains a plausible explanation for
the lost benefit; scan-count/function attribution was not measured here.

Decision: retain the negative result and do not integrate this coarse prototype
or spend live QUIC reruns claiming it as a fix. A potential next experiment is
selective filename-based notification, with registration-race, cancellation,
overflow, watch-loss, symlink and unsupported-filesystem fallback tests first.
That design is not implemented or authorized as a production optimization by
this measurement. The B3 handshake and B5 memory/p99 causes remain unresolved.

Verification: 15 focused release tests passed, then the explicitly invoked
paced comparison passed with ten complete results. One focused review checked
matching workloads, timer basis, per-ID completion, preserved timeout and
equivalent publisher accounting. The prototype is byte-identical to the idle
experiment. No unrelated full-suite or production correctness claim is made.

Repository head at experiment: 70210e48. Source archive: 91a88774 plus the
retained experimental modules and `probe.rs`; commands and exact build image
are bound in the evidence. Raw: `C:/NBSR-build/b3-event-paced-70210e48`.
Canonical: `evidence/performance/v2/b3-event-paced-70210e48`.
Reproduce using the recorded Docker command/run.sh, then analyze.py after exit.

Five original work blocks still remain; this completes one diagnostic substep.
No 2048-connection, sustainable admission, CPU hardware ceiling or soak claim
is added. The user-requested checkpoint stops before the next experiment.

Follow-up: B3_SELECTIVE_NOTIFICATION_SPIKE.md records a separate name-selective
candidate with materially lower offline CPU. The negative coarse-prototype
result above remains valid and retained; neither candidate is integrated yet.
