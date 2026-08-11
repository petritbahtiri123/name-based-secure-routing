# P2C final report

## Executive summary

Outcome B — IMPLEMENTED THEN REVERTED. The eligible bounded pipeline used actual silent Quinn stream reservations and ordered source admissions while destination authorization stayed sequential. Window 2 was the smallest candidate. Three 8,000-operation pairs measured +23.64% median lifecycle throughput and +41.68% median p99, with zero errors. The fixed p99 limit was +5%, so the production change was reverted and no soak was run.

## Semantic and security result

Existing request/session and echoed stream/channel/route fields provide exact response correlation. Strict source/destination monotonic sequences, request replay, stream replay, P1F, channel capacity, RouteGrant and Service Channel binding, audit, revocation, downgrade, and federation paths were not changed in the final tree. The candidate used actual Quinn IDs rather than prediction and never exposed a reserved stream as an application stream without the existing exact permit.

## Measurements

The corrected sweep produced window 1/2/4/8/16 throughput of 3641.08/4522.58/5146.21/5557.26/5567.90 ops/s. Corresponding p99 was 0.391/0.569/0.948/1.701/3.479 ms. Benefit saturated by window 8, but latency grew monotonically. Window 2 was selected as the smallest candidate exceeding the 10% throughput target.

The three window-1 throughputs were 3591.28, 3668.30, and 3658.06 ops/s (CV 1.15%). Window-2 values were 4489.96, 4539.50, and 4522.96 ops/s (CV 0.56%). Median p99 changed from 0.394 ms to 0.5582 ms. Three pairs were sufficient because both CVs were below 5% and the p99 failure was 36.68 percentage points beyond the limit.

## Phase interpretation

Individual admission RTT did not need to shrink: multiple ordered admissions overlapped, raising aggregate throughput. Destination authorization remained the approximately 9 us/op P2B owner and Quinn `open_bi` remained sub-microsecond in P2B. The new cost was queueing between neighboring admissions and the point where a silent reserved Quinn stream becomes peer-visible. That tail-latency tradeoff failed the tranche gate.

## Acceptance gate

- Security semantics in final tree: PASS (candidate reverted; affected regression required fresh verification).
- Candidate actual-ID reservation, exact basic correlation, and bounded window: PASS in RED/GREEN candidate tests before reversion.
- Full candidate pending-concurrency P1F/capacity/failure-isolation matrix: NOT COMPLETED; the candidate was reverted immediately after the decisive performance failure, so this is also not a KEEP pass.
- Median throughput improvement at least 10%: PASS (+23.64%).
- Median p99 regression at most 5%: FAIL (+41.68%).
- Unexpected errors: PASS (zero in sweep and pairs).
- Soak/resource-leak gate: NOT RUN because short acceptance failed.
- Final KEEP decision: FAIL; production optimization reverted.

## Fresh verification

- Focused Rust security/lifecycle set: 43 passed, 0 failed.
- `cargo test --all-targets --features benchmark-harness`: exit 0; 140 tests listed, with the evidence-only ten-minute P1F soak ignored by its existing annotation.
- P2C and P2B Python tests: 8 passed, 0 failed.
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets --features benchmark-harness -- -D warnings`: exit 0.
- P2C checksum inventory: 30 entries, 0 mismatches.
- Prior performance evidence diff: 0 changed paths.

## Git boundaries

Work occurred on `codex/nbsr-perf-p2c-pipelined-stream-open` from exact base `e82b7cfa7b3c4dc14bdae605caf1eeded0dacaa7`. Remote `main` remained `1938154d498b32d81a3564319969430644e8a688`; remote accepted product branch `codex/nbsr-v3-wp0-wp1` remained `4e25ee026618a502327331f352d90e26d29284e3`. No push, pull, merge, or rebase occurred.

## Final conclusion

OPTIMIZATION NOT ACCEPTED

## Recommended next task

Define a protocol-owner decision for whether an accepted application stream may be materialized independently of the ordered control-loop handoff, with an explicit lifecycle-tail-latency objective. Do not implement it as part of P2C.
