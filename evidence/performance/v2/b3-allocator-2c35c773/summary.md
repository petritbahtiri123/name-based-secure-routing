# Source allocator observation: retained qualification failure

Source 2c35c773, fresh locked release build. Five counterbalanced observer-off/on
pairs complete ten same-process lifecycle cycles each: 100 cycles, cleanup PASS
in every cell. Each on cell retains initial plus ten post-close glibc XML files:
55 snapshots total. No production transport, authority, wire, timeout, allocator
tuning or mandatory-check change was made. The observer is opt-in and source-only.

OBSERVER_REJECTED_FOR_CAUSAL_PERFORMANCE_ATTRIBUTION. Absolute median shifts:
handshake p95/p99 13.8703%, request p95 7.8326%, request p99 5.5525%, source
CPU 5.1282%, final source private-resident memory 0.4025%. The predeclared 5%
limit is unchanged. Handshake/request dispersion is high in both modes; these
paired shifts do not isolate observer cost from host variability. No stable
performance, speedup or causal production-memory conclusion follows.

XML records arena system bytes, allocator-reported free chunks and mmap bytes.
The derived system-minus-free remainder includes metadata/caches and is not
exact live Rust allocations. Snapshots occur immediately after close, before
cooldown and before all loop-local values necessarily leave scope. They cannot
prove a cooldown allocator plateau, resource leak, or destination heap behavior.
The final cooldown OS measurements are separately retained in each cell.

Literal Rust RED: two assertions fail with the empty implementation. GREEN:
two Linux release allocator tests pass. The initial green image lacks clippy;
that failure is retained, and the existing clippy image passes release
clippy -D warnings. Python missing-parser and option-contract RED logs are
retained; final affected scope is 41 tests PASS, Ruff/fmt/diff PASS.

A source-staging mistake included local target cache in an incomplete tar.
The owned staging process was stopped before a test ran; only that reproducible
4,397,726,208-byte tar was removed. Source, caches and authoritative evidence
remain intact. The replacement stages tracked source files plus the new module.
A CRLF shell launch failure is also retained, not counted as a regression RED.

No longer attribution run or production optimization is justified by this
failed qualification. Allocator closure remains INCONCLUSIVE on this host.
Use an independently qualified observer/host for causal investigation rather
than repeatedly rerunning noisy controls until a favorable result appears.
