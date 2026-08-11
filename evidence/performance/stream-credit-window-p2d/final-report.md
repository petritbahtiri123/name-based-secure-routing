# P2D final report

## Decision

Outcome A — ACCEPTED AND RETAINED.

The sole authoritative exact-final-source campaign is Attempt 8 at selected
concurrency 64. Five matched 60-second pairs measured median throughput
rising from 4,282.05 to 15,567.44 operations/second (+263.55%) and median p99
falling from 18.6981 ms to 5.4623 ms (-70.79%). Throughput CV was 9.444%
BEFORE and 3.465% AFTER. Every pair passed both fixed thresholds and all ten
cells reported zero errors. The three-pair BEFORE CV exceeded 5%, so the
approved stopping rule correctly expanded to its five-pair maximum.

## Live refill and continuity

The smoke used actual Quinn paths at concurrency 64 for 192 operations. AFTER
crossed and refilled three windows, deliberately observed three exhaustion
rejections, reached active-epoch high-water 2, and ended with zero unexpected
errors. The separate continuity cell crossed 16 windows in 1,024 operations,
also with zero errors and active-epoch high-water 2.

The conditional soak ran 300.3870077 seconds and completed 4,832,000 correct
1 KiB echo lifecycles at 16,085.92 operations/second with aggregate p99
5.1656 ms, zero errors, and 75,500 ordered refills. Its 604 bounded session
shards each used the exact replay limit 10,000 and ended at no more than 8,000
entries. First/last/median periodic throughput was 15,419.23 / 14,358.98 /
17,173.51 operations/second; the worst period was 7,936.97 at period 486.
First/last/median periodic p99 was 4.2661 / 4.8610 / 3.6955 ms; the worst was
10.8145 ms at period 485. Periodic extrema are reported as observations, not
substituted for the aggregate acceptance metrics.

## Mandatory gates

| Gate | Result | Evidence |
|---|---|---|
| throughput improvement >=20% | PASS | +263.55% median |
| p99 regression <=5% | PASS | -70.79% median |
| unexpected errors | PASS | zero across smoke, sweep, pairs, continuity, soak |
| security | PASS | focused state/vector/live Quinn matrix |
| refill | PASS | ordered sole-control-stream request/grant, revalidated capacity, bounded epochs |
| continuity | PASS | 16 windows, requirement >=10 |
| soak | PASS | 300.3870077 seconds, correct payloads, zero errors |
| resource | PASS | epoch HWM 2; replay exact 10,000 cap; measured CPU/process state |

## Correction and evidence authority

Attempt 1 is rejected because it exposed replay limit 4,294,967,295. Attempts
2-5 are valid measurements superseded by later source/security/evidence
corrections. Attempt 6 completed its timed cells but is rejected because its
runner exited 1 when the final exclusive-create collided with the existing
`IN_PROGRESS` audit file. Attempt 7 is valid exact-source evidence but is
superseded because it predates enforcement that excludes legacy STREAM_OPEN,
confirm, application authorization, and legacy permits after V1 selection. No
prior measured value was deleted or relabeled.

Attempt 8 is bound to commit
`d5acdd88d44eeda686168f6c080119dc3d712a30`, complete Git tree
`c28559f8a37d4c8e56c3d76cc64541da5ddf7f05`, measured-source SHA-256
`1f90e4425467e9cbdeb76e95abb0ec111b1e7552a66192ceee07e0d87dea9969`,
source binary SHA-256
`29e8f85d3ef4c357c770549a9c0be5c86183408a7591ca8c3328948fbc75b12d`,
and server binary SHA-256
`6b5a769c0505cb0902b49fbbad4430c456871747a42a475042b319ca78da6032`.
Pre-output porcelain-v2 status was exactly empty, `git write-tree` equaled
`HEAD^{tree}`, and the tracked repository contained 2,109 files. The final
atomic runtime audit is PASS: post-output, post-build, every cell boundary,
and final capture retained the exact commit/tree/index, permitted only the
exact Attempt 8 output root, and observed zero disallowed changes.

Across all 28 aggregate cells, 1,363 shards, and 2,726 nested source and
destination endpoints, every measured `replay_limit` is exactly 10,000. Any
violation is a mandatory FAIL, not INCONCLUSIVE.

## Compression and inventory

Eight JSON artifacts larger than 100 MiB across retained attempts are stored
as deterministic gzip level 9 with mtime 0 and an empty filename header. Each
was decompressed to verify its exact original byte count/SHA-256 and
recompressed byte-for-byte to verify the recorded compressed SHA-256. Exact
identities and schema/source bindings are in `compressed-artifacts.json`. No
LFS rule or history migration was used. Attempt 8's 93,530,652-byte soak JSON
is below the 100 MiB threshold and remains directly stored.

The closed checksum inventory contains 330 entries. The package contains 331
files and 926,464,299 bytes including the checksum file; its largest stored
artifact is 93,530,652 bytes, so
no file exceeds 100 MiB.

## Boundaries and non-claims

The evidence is an observed single-host Windows loopback result using release
Rust binaries, actual Quinn streams, persistent Transport Sessions and Service
Channels, and matched 1 KiB semantics. It is not a multi-host, WAN,
adversarial-network, memory-attribution, production-capacity,
production-readiness, or rollout claim. The thousands-channel table is
explicitly an estimate and is not substituted for an observed gate.

## Fresh verification

- P2D Python contract: 21 passed, 0 failed.
- Rust all targets with `benchmark-harness`: 180 passed, 0 failed, 1 existing
  evidence-only ten-minute P1F soak ignored by its annotation.
- Default Rust `cargo test`: 188 passed, 0 failed, 1 existing evidence-only
  soak ignored. The all-target feature command includes 8 feature-only binary
  tests but omits 16 doctests; default includes those doctests and omits the 8.
- `cargo fmt --check`, Ruff check/format, and `git diff --check`: PASS.
- strict all-target `cargo clippy -- -D warnings`: PASS.
- Full repository pytest: 1,796 passed, 1 skipped, and 37 pre-existing
  Core/F75/federation/dependency/vector authority failures; none is hidden or
  used to weaken a P2D mandatory gate.
- Eight deterministic gzip artifacts: original and compressed bytes/SHA-256,
  decompression, and exact recompression verified.
- Attempt-8 whole-tree binding, runtime audit, and both rebuilt release binary
  hashes: exact match.

## Final conclusion

STREAM CREDIT WINDOW ACCEPTED AND RETAINED
