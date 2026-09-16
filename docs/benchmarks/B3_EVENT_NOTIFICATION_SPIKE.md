# B3 notification feasibility step, 2026-09-16

Status: offline feasibility step COMPLETE; prototype NOT INTEGRATED. The
remaining B3/B5 attribution block is still PARTIAL. No production change.

The previously measured shared scanner checks 2048 absent marker paths every
10ms. This isolated Linux experiment compares that exact module with a copied
prototype that uses a nonblocking inotify watch to suppress full scans when
the directory has not changed. New registrations still force a scan; any
directory event also forces a scan. Pending cancellation is checked in memory.
The original per-wait timeout, file-before-timeout behavior and matching-file
check are retained. Events themselves never declare a marker successful.

The experiment uses five counterbalanced repeats per arm, 2048 waiters,
0/8192 unrelated files, 30ms settling, four-second timed intervals and one
selected guest logical CPU. The native container filesystem is used; there
is no QUIC traffic, no bind-mounted marker directory and no admission result.

| Unrelated files | Current scanner median CPU | Prototype median CPU | Pending-task control |
| ---: | ---: | ---: | ---: |
| 0 | 15.4934% | 0.7497% | 0 observed CPU ticks |
| 8192 | 15.7421% | 0.9997% | 0 observed CPU ticks |

DERIVED: approximately 95.16% and 93.65% lower idle-wait polling CPU. This
does not mean a corresponding throughput or admission improvement. Current
scanner CV is 1.14%/0.87%; prototype CV is 16.11%/15.22%. All five repeats
are retained, including the quantization of low CPU usage at 100 ticks/s.
Zero observed control ticks is below measurement resolution, not zero cost.

Validation: literal RED failed the unchanged-directory suppression assertion;
GREEN ran 15 focused release tests plus the ignored, explicitly invoked CPU
comparison. Coverage includes matching-marker wakeup, absent-marker timeout,
directory rejection, cancellation, monitor shutdown, gate creation detection
and permanent polling fallback after root replacement. The exact baseline
module copied out of the build matches the repository copy byte-for-byte.
No full production tests or live B3 reruns are claimed for this prototype.

Focused review: this is intentionally not a general marker backend. It assumes
one fixed native directory and regular marker paths. Mixed directories,
symlink targets and remote-filesystem changes require explicit fallback or
support before integration. Watch loss, malformed records, read errors and
overflow request permanent full scanning; overflow behavior has not been
fault-injection tested. File descriptors use owned File cleanup. The watch is
installed before the initial scan so existing markers are still checked.

The key remaining performance question is event churn: at 100 marker writes/s,
this coarse prototype may scan nearly as often as the existing implementation.
Do not promote it based on an idle result. The next bounded step is a matched
paced-publication test and missing correctness/fallback cases; only then
consider integration and five matched live 2048-bundle repeats. No kernel
permission or security setting is changed by this experiment.

Reproduce with the retained `prepare.py` and `run.sh` using the recorded build
image and source archive; run `analyze.py` only after the comparison exits.
Raw evidence: `C:/NBSR-build/b3-event-spike-a0fb3b36`.
Canonical package: `evidence/performance/v2/b3-event-spike-a0fb3b36`.
Repository head at the experiment: a0fb3b36; archive source: 91a88774.
Only a throwaway copy is changed, fully retained with its generation script.

Remaining count: five original work blocks remain, because this closes a
diagnostic substep rather than the complete root-cause/fix block. B5 memory/p99
and the live one-CPU 2048 failure remain unresolved. This is the requested
one-step checkpoint, not authorization to claim an accepted fix or final soak.

Follow-up: B3_EVENT_PACED_PUBLICATION.md now records five active-publication
pairs. The idle CPU benefit did not persist at 100 publications/s; the coarse
prototype was not promoted. Keep the idle result scoped accordingly.
