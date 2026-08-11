# P2D final report

## Decision

Outcome A — ACCEPTED AND RETAINED.

The sole authoritative exact-final-source campaign is Attempt 5 at selected
concurrency 64. Three matched 60-second pairs measured median throughput
rising from 4,979.12 to 18,704.12 operations/second (+275.65%) and median p99
falling from 14.0123 ms to 3.4331 ms (-75.50%). Throughput CV was 4.064%
BEFORE and 0.962% AFTER. Every pair passed both fixed thresholds and all six
cells reported zero errors, so the approved stopping rule ended at three
pairs.

## Live refill and continuity

The smoke used actual Quinn paths at concurrency 64 for 192 operations. AFTER
crossed and refilled three windows, deliberately observed three exhaustion
rejections, reached active-epoch high-water 2, and ended with zero unexpected
errors. The separate continuity cell crossed 16 windows in 1,024 operations,
also with zero errors and active-epoch high-water 2.

The conditional soak ran 300.2110533 seconds and completed 5,576,000 correct
1 KiB echo lifecycles at 18,573.60 operations/second with aggregate p99
3.5048 ms, zero errors, and 87,125 ordered refills. Its 697 bounded session
shards each used the exact replay limit 10,000 and ended at no more than 8,000
entries. First/last/median periodic throughput was 19,965.10 / 18,618.93 /
18,923.00 operations/second; the worst period was 11,548.02 at period 190.
First/last/median periodic p99 was 2.9748 / 3.0320 / 3.1500 ms; the worst was
5.7913 ms at period 38. Periodic extrema are reported as observations, not
substituted for the aggregate acceptance metrics.

## Mandatory gates

| Gate | Result | Evidence |
|---|---|---|
| throughput improvement >=20% | PASS | +275.65% median |
| p99 regression <=5% | PASS | -75.50% median |
| unexpected errors | PASS | zero across smoke, sweep, pairs, continuity, soak |
| security | PASS | focused state/vector/live Quinn matrix |
| refill | PASS | ordered sole-control-stream request/grant, revalidated capacity, bounded epochs |
| continuity | PASS | 16 windows, requirement >=10 |
| soak | PASS | 300.2110533 seconds, correct payloads, zero errors |
| resource | PASS | epoch HWM 2; replay exact 10,000 cap; measured CPU/process state |

## Correction and evidence authority

Attempt 1 is retained but rejected and non-authoritative because its live
sessions exposed replay limit 4,294,967,295. Attempts 2 and 3 are valid but
superseded by later source freezes. Attempt 4 is valid bounded-replay evidence
but is superseded by the consolidated security/evidence-integrity fix round.

The corrected final source rejects refill requests while an epoch drains,
tracks assigned credited admissions compactly per epoch until exact terminal
release, enforces one ordered control stream per authenticated connection,
revalidates channel/P1F/quota headroom before a grant without reserving it,
fails any nested measured replay-limit violation, and binds every compiled or
imported source/input plus exact clean/diff identities. Attempt 5 reran the
entire ladder from the frozen corrected commit and is the sole authority.

Attempt 5 is bound to commit
`8cc935e1a08de20eaab1abd814906d1854da9bc8`, complete measured-source
SHA-256 `e32e8b4c4b2187c2fb1412909fcdc2449b771e2b096c763175ade7e2396c2cb3`,
source binary SHA-256
`4f0cbd64b3fd6111790faaddcc0bff1262c631413e98a3bc2b3e6e31def57c51`,
and server binary SHA-256
`2d30d6118d6417c775824a85956cae40bc0cd596933449bf44407fa7a6fe9df4`.
All 35 bound files match, and bound status/worktree/index diff identities are
the exact empty SHA-256 with zero bytes. The generic repository-dirty flag is
true only because the runner created its immutable output directory before
capturing repository-wide status; no bound input was dirty.

Across all 24 aggregate cells, 1,252 shards, and 2,504 nested source and
destination endpoints, every measured `replay_limit` is exactly 10,000. Any
violation is a mandatory FAIL, not INCONCLUSIVE.

## Compression and inventory

Six JSON artifacts larger than 100 MiB across retained attempts are stored as
deterministic gzip level 9 with mtime 0 and an empty filename header. Each was
decompressed to verify its exact original byte count/SHA-256 and recompressed
byte-for-byte to verify the recorded compressed SHA-256. Exact identities and
schema/source bindings are in `compressed-artifacts.json`. No LFS rule or
history migration was used.

## Boundaries and non-claims

The evidence is an observed single-host Windows loopback result using release
Rust binaries, actual Quinn streams, persistent Transport Sessions and Service
Channels, and matched 1 KiB semantics. It is not a multi-host, WAN,
adversarial-network, memory-attribution, production-capacity, production-
readiness, or rollout claim. The thousands-channel table is explicitly an
estimate and is not substituted for an observed gate.

## Fresh verification

- P2D Python contract: 12 passed, 0 failed.
- Focused Rust state/vector/live Quinn suites: 22 passed, 0 failed.
- Rust all targets with `benchmark-harness`: 176 passed, 0 failed, 1 existing
  evidence-only ten-minute P1F soak ignored by its annotation.
- Default Rust `cargo test`: 184 passed, 0 failed, 1 existing evidence-only
  soak ignored. The all-target feature command includes 8 feature-only binary
  tests but omits 16 doctests; default includes those doctests and omits the 8.
- `cargo fmt --check`: PASS.
- strict all-target `cargo clippy -- -D warnings`: PASS.
- Six deterministic gzip artifacts: original and compressed bytes/SHA-256,
  decompression, and exact recompression verified.
- Closed checksum inventory: 201 entries; package before the checksum file:
  201 files and 516,267,489 bytes; no file exceeds 100 MiB.
- Attempt-5 complete source binding and both rebuilt release binary hashes:
  exact match.

## Final conclusion

STREAM CREDIT WINDOW ACCEPTED AND RETAINED
