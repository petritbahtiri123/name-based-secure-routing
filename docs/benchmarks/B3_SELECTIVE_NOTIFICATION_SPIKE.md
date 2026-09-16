# B3 selective notification step, 2026-09-16

Status: offline candidate evaluation COMPLETE; NOT INTEGRATED. No production
or default benchmark behavior changed. The live handshake cause remains open.

The coarse prototype in B3_EVENT_PACED_PUBLICATION.md scanned every pending
path after any directory event. This experiment parses changed filenames and
stats only matching pending paths. Cancelled waiters are still removed, new
registrations still force a full scan, and every successful notification must
still pass the original is_file check. Per-wait deadlines remain unchanged.
Malformed events, queue overflow, watch loss, read failure or root replacement
fall back to full scanning. Notifications never authorize a protocol operation.

The workload probe is byte-identical to the preceding paced comparison:
2048 regular-file waiters, 100 publications/s, 30ms settling, a native temporary
directory, one selected guest logical CPU, and five counterbalanced pairs.
These are marker waits, not QUIC connections or admissions.

| Five-repeat median | Current scanner | Selective prototype |
| --- | ---: | ---: |
| Process CPU, including publisher | 10.4998% | 2.9791% |
| Publication-to-wakeup p50 | 6.287306 ms | 4.620812 ms |
| Publication-to-wakeup p95 | 12.592610 ms | 10.396701 ms |
| Publication-to-wakeup p99 | 13.633569 ms | 10.921053 ms |
| Publication deadline lateness p99 | 1.855846 ms | 2.067161 ms |
| Completed/requested per repeat | 2048/2048 | 2048/2048 |

DERIVED: process CPU falls 71.627%, wakeup-p99 falls 19.896%. CPU CV is
0.510%/1.811%; wakeup-p99 CV is 0.483%/1.945%. All ten results are retained.
Publication lateness did not improve: its median p99 increased, with high CV
19.701%/14.234%. Do not describe every latency metric as improved. Reported
latencies are medians of per-run nearest-rank percentiles, not pooled values.
CPU includes equivalent publisher work and has 10ms tick resolution.

Validation: literal RED failed the named-event selection assertion (two other
tests passed); GREEN passed 19 focused release tests and the explicitly invoked
ten-cell paced comparison. Tests cover name coalescing, exact-name selection,
overflow/watch-loss fallback, malformed/truncated/path-like names, native create
and rename, root replacement, cancellation and existing timeout/file semantics.
A focused test counts stat candidates and proves unrelated pending paths are
not checked during a selective scan; the fallback checks all pending paths.

One focused review found the same deliberate prototype boundary: one fixed
native directory with regular marker paths. Before integration, mixed roots,
symlinks (including targets changing outside the watched directory), unsupported
filesystems, late registration races and descriptor cleanup require explicit
backend selection/fallback coverage. Synthetic overflow parsing is covered;
a live kernel overflow campaign has not been performed. No full production
clippy/security suite or supported cross-platform backend is claimed here.

Decision: this candidate merits the next bounded harness-integration step,
with the missing correctness/fallback tests first, then five matched live B3
2048-bundle pairs. The offline CPU reduction does not establish that handshake
timeouts will disappear or that sustainable admissions will rise. Do not change
production transport, security, timeouts, packet semantics or acceptance gates.

Raw: `C:/NBSR-build/b3-event-selective-4f6c66f1`.
Canonical: `evidence/performance/v2/b3-event-selective-4f6c66f1`.
Repository head at experiment: 4f6c66f1; source archive base: 91a88774.
The archive, exact overlays, generation script, release test binary, logs,
commands and image identity are retained and hashed. Reproduce with run.sh;
run analyze.py after exit. The generator references the preceding retained
prototype, while the generated module is also retained directly.

This closes one diagnostic substep. The five original campaign blocks still
remain, including the unresolved B3/B5 fix block. B5 memory/p99 is unchanged.
