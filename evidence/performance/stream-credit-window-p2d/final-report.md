# P2D final report

## Decision

Outcome A — ACCEPTED AND RETAINED.

The sole authoritative exact-final-source campaign is Attempt 7 at selected
concurrency 64. Three matched 60-second pairs measured median throughput
rising from 5,056.57 to 18,936.28 operations/second (+274.49%) and median p99
falling from 13.9433 ms to 3.2508 ms (-76.69%). Throughput CV was 3.338%
BEFORE and 0.228% AFTER. Every pair passed both fixed thresholds and all six
cells reported zero errors, so the approved stopping rule ended at three
pairs.

## Live refill and continuity

The smoke used actual Quinn paths at concurrency 64 for 192 operations. AFTER
crossed and refilled three windows, deliberately observed three exhaustion
rejections, reached active-epoch high-water 2, and ended with zero unexpected
errors. The separate continuity cell crossed 16 windows in 1,024 operations,
also with zero errors and active-epoch high-water 2.

The conditional soak ran 300.2411631 seconds and completed 5,568,000 correct
1 KiB echo lifecycles at 18,545.09 operations/second with aggregate p99
3.8604 ms, zero errors, and 87,000 ordered refills. Its 696 bounded session
shards each used the exact replay limit 10,000 and ended at no more than 8,000
entries. First/last/median periodic throughput was 17,938.31 / 18,632.73 /
19,013.13 operations/second; the worst period was 8,109.91 at period 241.
First/last/median periodic p99 was 3.4214 / 3.1205 / 3.15505 ms; the worst was
6.8864 ms at period 241. Periodic extrema are reported as observations, not
substituted for the aggregate acceptance metrics.

## Mandatory gates

| Gate | Result | Evidence |
|---|---|---|
| throughput improvement >=20% | PASS | +274.49% median |
| p99 regression <=5% | PASS | -76.69% median |
| unexpected errors | PASS | zero across smoke, sweep, pairs, continuity, soak |
| security | PASS | focused state/vector/live Quinn matrix |
| refill | PASS | ordered sole-control-stream request/grant, revalidated capacity, bounded epochs |
| continuity | PASS | 16 windows, requirement >=10 |
| soak | PASS | 300.2411631 seconds, correct payloads, zero errors |
| resource | PASS | epoch HWM 2; replay exact 10,000 cap; measured CPU/process state |

## Correction and evidence authority

Attempt 1 is rejected because it exposed replay limit 4,294,967,295. Attempts
2-5 are valid measurements superseded by later source/security/evidence
corrections. Attempt 6 completed its timed cells but is rejected because its
runner exited 1 when the final exclusive-create collided with the existing
`IN_PROGRESS` audit file. No prior measured value was deleted or relabeled.

Attempt 7 is bound to commit
`100b871db011ba514bd45f0354714e1f698ebdd5`, complete Git tree
`6d84e897b29e358c716c6c83b2ad6efc2ec445fa`, measured-source SHA-256
`921d4276f4aa28d7747c78622bb0a785a3333e3020188a8f45bc1b38483e7cb4`,
source binary SHA-256
`4f0cbd64b3fd6111790faaddcc0bff1262c631413e98a3bc2b3e6e31def57c51`,
and server binary SHA-256
`2d30d6118d6417c775824a85956cae40bc0cd596933449bf44407fa7a6fe9df4`.
Pre-output porcelain-v2 status was exactly empty, `git write-tree` equaled
`HEAD^{tree}`, and the tracked repository contained 2,069 files. The final
atomic runtime audit is PASS: post-output, post-build, every cell boundary,
and final capture retained the exact commit/tree/index, permitted only the
exact Attempt 7 output root, and observed zero disallowed changes.

Across all 24 aggregate cells, 1,257 shards, and 2,514 nested source and
destination endpoints, every measured `replay_limit` is exactly 10,000. Any
violation is a mandatory FAIL, not INCONCLUSIVE.

## Compression and inventory

Eight JSON artifacts larger than 100 MiB across retained attempts are stored
as deterministic gzip level 9 with mtime 0 and an empty filename header. Each
was decompressed to verify its exact original byte count/SHA-256 and
recompressed byte-for-byte to verify the recorded compressed SHA-256. Exact
identities and schema/source bindings are in `compressed-artifacts.json`. No
LFS rule or history migration was used.

The closed checksum inventory contains 282 entries. The package contains 283
files and 717,058,062 bytes including the checksum file; its largest stored
artifact is 22,372,470 bytes, so
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
- Rust all targets with `benchmark-harness`: 176 passed, 0 failed, 1 existing
  evidence-only ten-minute P1F soak ignored by its annotation.
- Default Rust `cargo test`: 184 passed, 0 failed, 1 existing evidence-only
  soak ignored. The all-target feature command includes 8 feature-only binary
  tests but omits 16 doctests; default includes those doctests and omits the 8.
- `cargo fmt --check`, Ruff check/format, and `git diff --check`: PASS.
- strict all-target `cargo clippy -- -D warnings`: PASS.
- Full repository pytest: 1,796 passed, 1 skipped, and 37 pre-existing
  Core/F75/federation/dependency/vector authority failures; none is hidden or
  used to weaken a P2D mandatory gate.
- Eight deterministic gzip artifacts: original and compressed bytes/SHA-256,
  decompression, and exact recompression verified.
- Attempt-7 whole-tree binding, runtime audit, and both rebuilt release binary
  hashes: exact match.

## Final conclusion

STREAM CREDIT WINDOW ACCEPTED AND RETAINED
