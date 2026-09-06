# B5 receive-clock evidence preservation

The failed 1cca67ad baseline exposed a reproducibility gap: the controller's
first-progress receive origin existed in memory but was absent from retained
results. Resource-window alignment could not be reconstructed from that run.

The existing origin is now serialized as `resource_phase_origin_monotonic_ns`
inside qualification, including parser/ownership failure results. No progress
means explicit null. A delayed later record does not rebase the origin. The
existing final result write runs after cleanup; no timed writes, clock reads,
workload, drift threshold or ownership assertions were added or changed.

Literal RED: four focused failures. GREEN:32 controller tests; Ruff PASS.
One parent focused review found no Important issue. Tests cover first/null origin,
no rebase, successful results, parser failure and ownership failure, retained
failure bytes and the existing ACK-after-sampling order.

This is a harness evidence fix, not a performance optimization or drift cause.
Receive-clock alignment remains approximate. Earlier missing clocks remain
unavailable. No new workload or near-ceiling soak ran for this change.

Raw originals and exact tested source snapshots remain at
`C:/NBSR-build/b5-receive-clock-1cca67ad`; external-checksums.sha256 indexes them.
Canonical logs normalize newlines/trailing whitespace; their checksums are
separate from raw actual-byte checksums. verification.json binds tested source.
