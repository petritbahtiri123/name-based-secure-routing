# Socket observation temporal/history gate

COMPLETE: bounded offline evidence-validation hardening. Measurement source
remains 11677eca; checker source is 206244b6. Existing authoritative evidence is
read-only and is not relabeled as a new-source workload run.

The previous pair gate checked socket snapshot identity and local binding but
not its resource-time interval or the retained attempt log. Ten deliberately
resealed malformed fixture variants were accepted before the fix: times before
or after process observations, absent/mismatched attempt history, observation
after success, too many attempts, reversed attempts, foreign PID, boolean time,
and regressing resource clock. These are evidence-validator defects, not a
production protocol/security exploit or proof that accepted live data was wrong.

New checks require monotonic integer resource timestamps, one to twenty retained
attempts within that host process interval, matching identity, UNAVAILABLE status
before success, and exact terminal-attempt/report equality. Unavailable attempts
remain preserved. Existing uninstrumented evidence retains its original contract.
This does not synchronize clocks between hosts, authenticate evidence, establish
continuous/exclusive socket ownership or separate traffic phases.

RED: ten negative fixtures failed to reject, one positive passed. GREEN: 77 tests
across affected pair/cohort/fixed-work/socket/history scope, followed by twelve
focused history tests after adding valid failed-then-success coverage. Scoped
Ruff and git diff checks PASS. These overlapping test groups are not summed.

Read-only reanalysis of the original five Direct/NBSR pairs passes all ten cells
and all twenty peer histories under the new rules. Original checksums remain
unchanged and are reverified. No new benchmark, release build, Docker run,
production change, protocol/security change or timeout change occurred.
