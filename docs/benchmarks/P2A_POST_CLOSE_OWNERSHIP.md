# P2A post-close ownership evidence

The pre-repair stage4 `cleanup_pass` establishes workload drain and successful
process exit. For one-group NBSR it used zero measured-window creation/replay
deltas, taken before teardown. Those deltas do not prove zero residual ownership.
Grouped NBSR additionally retained a source snapshot after group runtimes joined.
Destination PASS records did not contain post-close ownership gauges.

This is an evidence-scope defect, not evidence of a production leak. Existing
raw results remain immutable and useful for their stated timing/workload scope.
Two-sided zero ownership must not be inferred from their `cleanup_pass` field.
This qualification applies to the earlier physical-core forwarding packages too.

The optional `--ownership-reports` physical-core runner mode now enables NBSR
diagnostics before resource acquisition and requests one PID-bound source report
plus one report per destination. All eleven live/entry gauges must be present,
integer and zero. Missing, malformed, mismatched or nonzero reports fail the run.
New records distinguish process cleanup from `ownership_cleanup` explicitly.
Default timed mode remains unchanged and reports ownership as NOT_MEASURED.
Direct does not have NBSR ownership counters; it remains NOT_MEASURED here.

Single-source and destination snapshots run after `run()` returns and its local
handles drop, while the enclosing runtime is alive. Grouped-source snapshots are
explicitly after all group runtimes join; they do not prove runtime-alive group
cleanup. No transport-library, protocol, timeout, credit or ACK change was made.

Literal live RED: old release binaries completed the workload but failed with
`MISSING_POST_CLOSE_REPORT:destination`. GREEN: one-group and four-group smokes
produced zero in every required source/destination gauge. These are diagnostic
integration smokes, not three-repeat capacity or long-run cleanup qualification.
Validation: 29 focused Python tests, scoped Ruff, release build, release
benchmark Clippy with `-D warnings`, fmt and diff checks PASS. One focused
independent review found no Important findings.

Raw evidence and source patch: `C:/NBSR-build/p2a-cleanup-gap-623e4db0`.
Canonical index: `evidence/performance/v2/p2a-post-close-623e4db0`.
The destination counters add observation during the workload. Matched on/off
observer qualification remains PENDING. If material, retain separate ownership
accounting runs and unobserved performance evidence; never silently pool them.

Reproduction after a clean commit, using fresh external output directories:

```powershell
python scripts/run_physical_core_v2.py --output C:/NBSR-build/p2a-post-close-current-1core --target C:/NBSR-build/b4b-task4k --cores 1 --groups 1 --payload 1024 --streams 64 --outstanding 1 --warmup 3 --duration 30 --ownership-reports
python scripts/run_physical_core_v2.py --output C:/NBSR-build/p2a-post-close-current-4core --target C:/NBSR-build/b4b-task4k --cores 4 --groups 4 --payload 16384 --streams 1 --outstanding 1 --warmup 3 --duration 30 --ownership-reports
```

Run equivalent controls without the last flag. Compare matched same-SHA/binary
workload observations before accepting timing claims. Each command performs
three repeats per path, extending to five when either path's CV exceeds 5%.
