# Linux B4 FD-failure attribution: bounded non-reproduction

**NOT_REPRODUCED_IN_FIVE_ATTEMPTS; cause UNRESOLVED.** The failure-only diagnostic
controller at9397429f ran five attempts at200 admissions/s against old3644 Rust
binaries in immutable image dd08db4a. No PermissionError recurred within that
bound, so no new exception notes or traceback were generated. This is not FIXED
and does not identify why the earlier failure occurred.

All five attempts admitted512 independent clients each, with zero recorded
errors/timeouts and the existing terminal/process/cleanup gates passing.
Independent checks verified all2560 raw source success IDs and all eight existing
destination gauges at zero in both destination reports for each attempt. The
original temporary-marker checks are preserved in records; deleted marker files
cannot be independently recreated from this package. Full source runtime ownership
remains NOT_MEASURED, as does per-shard CPU on non-Windows Rust thread IDs.

The unchanged shape used two source shards,512 finite clients,30-second
established eight-stream1KiB forwarding plus2-second warmup, one shared guest
logical CPU and unchanged protocol/cleanup deadlines. This was a maximum-five
attribution diagnostic, not a CV-qualified current-binary capacity campaign.
Linux observer cost remains NOT_QUALIFIED. The prior failed c62b1165 cohort is
preserved separately and is not pooled with this new controller SHA.

Classification remains DIAGNOSTIC_BINARY_SOURCE_MISMATCH: current Linux CLI
build acceptance, physical hardware capacity, external-host execution and a
sampler-cause claim are not established. No build or image pull occurred.

The exact nonroot/read-only/network-none/capability-drop/no-new-privileges
container used one CPU quota,1GiB memory and128 PIDs. A nonempty tar containing
all80 indexed raw artifacts was copied and hash-verified before the wrapper was
released. It exited0. Only the exact stopped owned container was removed after
preserving its inspect metadata and receipts. Full raw logs, source archive,
236 staged source hashes, image metadata and capture evidence remain external.
Canonical checksums cover canonical LF bytes separately from the raw indexes.
