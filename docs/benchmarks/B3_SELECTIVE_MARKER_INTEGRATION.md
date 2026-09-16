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
`C:/NBSR-build/marker-integration-green-3768a0eb`. Matched live evidence is pending:
five counterbalanced before/after 2048-bundle cells on one guest CPU, two source
shards, original 100 starts/s and acceptance window 1. All failures must remain.
The before build is exact source 91a88774 (identical baseline Rust implementation
to 3768a0eb); the after build will bind the integration commit. No stable scale
or admissions improvement follows until those results are analyzed.
