# B3 selective marker integration

Benchmark-only change following B3_SELECTIVE_NOTIFICATION_SPIKE.md. The measured
offline paced CPU reduction was 71.627%; it is not a live handshake capacity claim.

The existing runtime-owned scanner now filters pending paths by Linux inotify
names on canonical local ext4/tmpfs/overlay directories. Readiness still requires
the same is_file check. Windows and other builds retain full polling. Unknown
filesystems, mixed roots, symlinks, changed roots, malformed/overflow/watch-loss
events and a backlog larger than one bounded batch permanently restore polling.
Watch descriptors have owned File lifetime and are dropped on fallback or scanner
shutdown. No timeout, arrival schedule, transport/security behavior or production
library code changes. The existing locked libc version is exposed as a Linux-only
optional benchmark dependency; no dependency version was upgraded.

Literal RED: named-selection regression failed with an always-polling stub.
The first implementation test caught a root close event immediately disabling
the watch; only unneeded open/read-close notifications were removed from the
watch mask, preserving the original assertion. Tests cover external symlink
targets, late registration, mixed roots, backlog, malformed/overflow events,
root replacement, cancellation, shutdown and file/timeout ordering.

Validation: 17 focused Linux release tests, release source-bin clippy with
`-D warnings`, Windows benchmark-feature source-bin check, 55 affected Python
tests, scoped Ruff, fmt and diff checks passed. Initial setup/compiler-tool
wrapper errors are retained separately; the final wrapper completed successfully.
One focused review checked conservative fallbacks, bounded event reads, owned
descriptors, cross-platform compilation and unchanged protocol/security paths.

Raw validation: `C:/NBSR-build/marker-integration-red-3768a0eb` and
`C:/NBSR-build/marker-integration-green-3768a0eb`. Matched live evidence follows:
five counterbalanced before/after 2048-bundle cells on one guest CPU, two source
shards, original 100 starts/s and acceptance window 1. All failures must remain.
The before build is exact source 91a88774 (identical baseline Rust implementation
to 3768a0eb); the after build binds integration commit f8925b25.

## Matched live outcome

All ten original cells passed: before 5/5 and after 5/5, each with 2048 live
materialized bundles, zero final eleven-counter ownership reports on both sides
and joined/exited source and destination processes. All 20775 child-index entries
were verified after preserving the originals. No failed cell was replaced.

| Five-repeat median | Before | After |
| --- | ---: | ---: |
| Source pre-start effective cores | 0.319825 | 0.140376 |
| Destination pre-start effective cores | 0.014998 | 0.014997 |
| Source active private resident bytes | 833425408 | 833708032 |
| Destination active private resident bytes | 612315136 | 610897920 |
| Full lifecycle passes | 5/5 | 5/5 |

DERIVED: source pre-start CPU falls 56.109%. Source CPU CV is 3.670%/4.408%;
active private-memory CV stays below 0.65% for both roles/arms. Destination
pre-start CPU CV is 21.066%/0.013%, with all five originals retained; this
small CPU value is not a basis for claiming a destination optimization.
Pre-start CPU can include setup and is not isolated polling or handshake CPU.
Memory differences are small and no memory-saving claim is made.

The accepted result is reduced benchmark-side CPU cost with no lifecycle failure
in this matched sample. It is NOT proof of a moved admission boundary, increased
throughput, a hardware ceiling, or eradication of the historical sporadic
one-CPU handshake failure: the unchanged baseline also passed all five here.
Guest CPU affinity remains distinct from verified dedicated physical-core use.
B5 memory/p99 and a qualified sustained soak remain unresolved.

Canonical: `evidence/performance/v2/b3-selective-pairs-f8925b25`.
Raw: `C:/NBSR-build/b3-selective-pairs-f8925b25`. The package binds both exact
release builds, raw validation roots, commands, every result, analysis and all
checksums. The controlled integration/rerun step is COMPLETE; it closes one
harness artifact, not the entire root-cause/funding campaign. Five original
work blocks remain because the residual attribution/B5 fix block is still open.

Integrity/privacy: 19 canonical indexed files, 20 canonical files checked for
credential markers and 20886 raw indexed files passed. Canonical index SHA-256:
`556626c0b4c902e09bf3b7398f130ddfa9545f6cc318484a8d444e50fa562145`.
After verification, the five stopped campaign-owned test/build/run containers
were removed (nbsr-marker-green-3768, nbsr-marker-green-retry,
nbsr-marker-green-final, nbsr-build-f8925b25, nbsr-selective-pairs-f8925b25).
Only disposable writable container layers were removed; source, raw evidence,
release binaries, build images and hashes remain. Host SSD recovery was not
measured, so no recovered-space number is claimed.
