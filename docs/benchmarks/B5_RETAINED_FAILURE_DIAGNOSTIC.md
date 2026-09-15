# B5 retained failed trajectories

Question: does the previously observed resident-memory growth eventually reach
a plateau, or continue throughout a longer fixed-load interval? Earlier strict
tests stopped at the first private-growth/p99 gate, leaving the later trajectory
unobserved. This is a diagnostic question, not an acceptance-gate revision.

The Linux diagnostic CLI now accepts `--retain-failed-diagnostic`, only with
`--diagnostic` and a predeclared duration of at most 600 seconds. It records
each observed performance-gate failure while permitting collection until that
duration. Any recorded violation forces `valid=false` and
`FAIL_DIAGNOSTIC_RETAINED`, even when all operations and cleanup finish. Original
correctness failures take precedence. Such rows cannot satisfy repeat gates.

Normal runs still abort at their first performance failure. The stream validator,
errors/timeouts, resource/schema bounds, controller deadline, ownership checks
and cleanup remain unchanged in both modes. Only typed p99/goodput drift and
private-growth exceptions are retained. Because the guard evaluates drift
before memory, the event list is not an exhaustive list of simultaneous
violations; the complete retained resource series must be analyzed separately.

No claim of lower memory, bounded allocation ownership or passed soak follows
from continuing a failed diagnostic. RSS/residency and live allocation remain
different quantities. No production code, timeout or offered load is changed.

Validation includes literal RED tests, the strict abort regression, retained
drift/private-growth failure reporting, bounds, invalid resources, duration and
acceptance-mode rejection, and actual run_one cleanup/report-path coverage with
synthetic peers. Focused tests and Ruff pass. Runtime evidence remains pending.

Initial planned diagnostic: three 600-second NBSR attempts, 16 KiB, eight streams,
depth 1, three-second warmup, 30-second progress, one selected guest CPU, fixed
historical rational rate 64804600000000/7500349701 operations/s. This is not
current-source near-ceiling calibration. Preserve all failures; extend to five
attempts if applicable complete-run goodput or window-p99 CV exceeds 5%.
