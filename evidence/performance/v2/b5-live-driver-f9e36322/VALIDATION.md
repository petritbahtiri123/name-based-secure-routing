# B5 live driver and timer diagnosis

Classification: DIAGNOSTIC integration, not stable capacity or sustained soak.
Base: f9e3632250d5df0e285cbee005e4c829ca178a4a; dirty source snapshots and
binary hashes are retained in each live GREEN raw directory. Final test-module
aliases make unit tests exercise the live helpers; current-SHA calibration remains required.

Both benchmark binaries now opt into the same bounded grouped driver. Warmup
precedes one common origin; reservations stop at a fixed deadline; issued work
drains before final publication permits postflight. Group/publisher failures wake
waiters. Group threads and the publisher join before the sole final record.
Existing frames, validation, ACCEPT/ACK behavior and production transport are unchanged.
Nonzero cooldown is rejected rather than silently omitted. Defaults remain unpaced.

The old binaries produced no grouped B5 final record (live RED). Initial integrated
Direct/NBSR probes passed accounting and cleanup but completed only 225–257 of
400 offered operations. This unfavorable result is retained. Three isolated
100-wake comparisons measured Tokio 10 ms waits skipping 68–76 windows versus
zero for std sleep. This is a local benchmark timer diagnosis, not an OS-wide ceiling.

The driver now uses one shared sleeping timer thread to notify registered waiters.
It neither borrows expired budgets nor catches up missed operations. Three repeats
per Direct/NBSR 1/2/4-group cell at 200 offered operations/s for two seconds yielded
400/400 except one NBSR two-group repeat at 396/400. Maximum count CV is 0.5793%.
All NBSR source/destination eleven-counter reports passed; Direct proves process
exit only. No near-ceiling observer/stability claim follows from these light probes.

Validation: literal driver, metadata, cooldown and load RED logs retained; 76 Rust
tests PASS and one explicit timer diagnostic ignored in ordinary runs, release
Clippy with tests and -D warnings PASS, 80 focused Python tests PASS. Focused
independent review identified the cooldown omission; rejection regression closes
it. Timer and integration re-review found no remaining Important finding.

raw-index.json binds five retained external directories and 360 verified raw files.
Canonical logs normalize line endings/trailing whitespace; original logs remain
under C:/NBSR-build. Scripts here reproduce short integration diagnostics only.
Remaining: bounded live controller, failure integration, current-SHA calibration,
observer qualification, resource/drift gates and 60/120-minute repeated soaks.
