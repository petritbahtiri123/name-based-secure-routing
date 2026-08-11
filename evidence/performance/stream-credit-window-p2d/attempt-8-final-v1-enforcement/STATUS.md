# Attempt 8 status

This is the **sole authoritative final-source acceptance campaign**. It is
bound to commit `d5acdd88d44eeda686168f6c080119dc3d712a30`, complete Git
tree `c28559f8a37d4c8e56c3d76cc64541da5ddf7f05`, measured-source SHA-256
`1f90e4425467e9cbdeb76e95abb0ec111b1e7552a66192ceee07e0d87dea9969`,
and the exact rebuilt release binary hashes recorded in `build.json`.

Pre-output porcelain-v2 status was exactly empty, `git write-tree` equaled the
HEAD tree, and the post-output, post-build, every-cell-boundary, and final
runtime audits allowed only this exact attempt root. The final audit was
atomically transitioned from the known canonical `IN_PROGRESS` document to
`PASS`; commit, HEAD tree, and index tree remained equal with zero disallowed
changes.

The full live runner returned Outcome A after 1,176.4 seconds with every
mandatory gate PASS. Three-pair BEFORE throughput CV exceeded 5%, so the
runner correctly completed five matched pairs before continuity and soak.
Attempt 7 remains valid historical evidence but is superseded because it
predates enforcement that excludes legacy STREAM_OPEN and legacy permit paths
after the V1 profile is selected.

The 93,530,652-byte soak JSON is below the 100 MiB compression threshold and
is retained directly as `raw/soak/after.json`.
