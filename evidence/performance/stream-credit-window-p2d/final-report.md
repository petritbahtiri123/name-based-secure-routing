# P2D final report

## Decision

Outcome A — ACCEPTED AND RETAINED.

The authoritative exact-final-source campaign selected concurrency 64. Three
matched 60-second pairs measured median throughput rising from 5,077.88 to
18,967.29 operations/second (+273.53%) and median p99 falling from 12.8990 ms
to 3.2660 ms (-74.68%). Both throughput CVs were below 5%, every pair was on
the same passing side, and all six cells reported zero errors, so the approved
stopping rule ended at three pairs.

## Live refill and continuity

The smoke used actual Quinn paths at concurrency 64 for 192 operations. AFTER
crossed and refilled three windows, deliberately observed three exhaustion
rejections, reached active-epoch high-water 2, and ended with zero unexpected
errors. The separate continuity cell crossed 16 windows in 1,024 operations,
also with zero errors and active-epoch high-water 2.

The conditional soak ran 300.1691775 seconds and completed 5,704,000 correct
1 KiB echo lifecycles at 19,002.62 operations/second with p99 3.1729 ms, zero
errors, and 89,125 ordered refills. Its 713 bounded session shards each ended
at replay 8,000/10,000. The first and last shard throughput were 19,645.51 and
18,661.34 operations/second; median shard throughput was 19,057.23. First and
last shard p99 were 3.0295 and 3.4628 ms; median was 3.0790 ms.

## Mandatory gates

| Gate | Result | Evidence |
|---|---|---|
| throughput improvement >=20% | PASS | +273.53% median |
| p99 regression <=5% | PASS | -74.68% median |
| unexpected errors | PASS | zero across smoke, sweep, pairs, continuity, soak |
| security | PASS | focused state/vector/live Quinn matrix |
| refill | PASS | ordered live request/grant, multiple refills, bounded epochs |
| continuity | PASS | 16 windows, requirement >=10 |
| soak | PASS | 300.1691775 seconds, correct payloads, zero errors |
| resource | PASS | epoch HWM 2; replay exact 10,000 cap; measured CPU/process state |

## Correction and evidence authority

Attempt 1 is retained but explicitly rejected and non-authoritative because
its live sessions exposed replay limit 4,294,967,295. Correction 1 configured
the benchmark's actual source and destination sessions
with exact P1F limit 10,000 and hardened validation to require it. Attempt 2
was valid bounded-replay evidence, but rustfmt then changed source bytes.
Correction 2 reran the full ladder against rustfmt-clean source. Strict Clippy
then found only benchmark-helper argument-count warnings. Correction 3 grouped
those parameters into private structs, passed strict Clippy, and reran the
complete ladder. In authoritative attempt 4, all 24 aggregate cells and all
2,540 source/destination shard endpoints reported exactly 10,000, and all
eight frozen source bindings plus both release binary hashes match. All three
permitted corrections are consumed.

The five JSON artifacts larger than 100 MiB were deterministically gzip
compressed with mtime 0 and no filename header. Original/compressed hashes and
byte counts plus decompression verification are in
`compressed-artifacts.json`. No LFS rule or prior evidence changed.

## Boundaries and non-claims

The evidence is an observed single-host Windows loopback result using release
Rust binaries, actual Quinn streams, persistent Transport Sessions and Service
Channels, and matched 1 KiB semantics. It is not a multi-host, WAN,
adversarial-network, memory-attribution, production-capacity, or rollout claim.
The thousands-channel table is explicitly an estimate and is not substituted
for an observed gate.

## Fresh verification

- P2D Python contract: 10 passed, 0 failed.
- Focused Rust state/vector/live Quinn suites: 22 passed, 0 failed.
- Rust all targets with `benchmark-harness`: 173 passed, 0 failed, 1 existing
  evidence-only ten-minute P1F soak ignored by its annotation.
- Default Rust `cargo test`: 181 passed, 0 failed, 1 existing evidence-only
  soak ignored. Task 3's comparable count was 179; Task 4 added the refill
  codec test and live refill integration test. The all-target feature command
  reports 173 because it includes 8 feature-only tests but omits 16 doctests.
- `cargo fmt --check`: PASS.
- strict all-target `cargo clippy -- -D warnings`: PASS.
- Five deterministic gzip artifacts: original bytes and SHA-256 verified after
  decompression; no evidence file exceeds 100 MB.
- Closed checksum inventory: 161 entries, 0 missing, unlisted, or mismatched.
- Attempt-4 frozen source and both release binary hashes: exact match.

## Final conclusion

STREAM CREDIT WINDOW ACCEPTED AND RETAINED
