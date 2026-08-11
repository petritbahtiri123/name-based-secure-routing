# Task 4 report: benchmark harness, evidence, and acceptance

## Result

**DONE — Outcome A — ACCEPTED AND RETAINED.** Final authority is
`evidence/performance/stream-credit-window-p2d/attempt-4-final/`.

At selected concurrency 64, three matched 60-second BEFORE/AFTER pairs
measured median throughput 5,077.88 -> 18,967.29 operations/second (+273.53%)
and median p99 12.8990 -> 3.2660 ms (-74.68%). Sample throughput CV was 4.412%
BEFORE and 3.038% AFTER. Every pair was on the passing side of both fixed
thresholds and all six cells had zero errors, so the exact three-pair stopping
rule applied.

The conditional soak ran 300.1691775 seconds, completed 5,704,000 correct 1
KiB operations at 19,002.62 operations/second, p99 3.1729 ms, with zero errors,
89,125 ordered refills, active-epoch high-water 2, and replay 8,000/10,000.
All mandatory gates are PASS.

## Scope and Git boundary

- Branch: `codex/nbsr-perf-p2d-stream-credit-window`
- Starting commit: `4225a545845e36034066a0e527d7471f92926f1b`
- Local `main` before commit: `1938154d498b32d81a3564319969430644e8a688`
- `origin/main` observed before commit: `1938154d498b32d81a3564319969430644e8a688`
- No push, pull, merge, rebase, branch switch, or protected-ref mutation.
- Evidence is additive only under
  `evidence/performance/stream-credit-window-p2d/`; no P1A-P2C evidence path
  changed.
- The controller-authored normative document and implementation plan that were
  initially untracked are included in the scoped commit as directed.

## Literal RED -> GREEN

### Python benchmark/evidence contract

Command:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
```

Literal RED first produced `ModuleNotFoundError` for the absent
`scripts.performance.p2d_stream_credit` module. After adding only a skeleton,
the ten pinned tests failed on missing/wrong behavior. The tests pin the exact
concurrency tuple `(1,2,4,8,16,32,64)`, matched 1 KiB manifests,
nearest-rank percentile/median/sample-CV math, the three-or-five stopping rule,
gate precedence, exact 20%/5% boundaries, zero errors, at least ten refill
windows, bounded credits/epochs/replay with exact limit 10,000, saturation
selection, and checksum closure.

Final GREEN: `10 passed in 0.41s` (earlier pre-refactor fresh run:
`10 passed in 0.33s`).

### Rust live refill API and transport

RED command:

```powershell
$env:CARGO_TARGET_DIR='C:\codex-target\nbsr-p2d'
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test stream_credit_integration ordered_live_refill_follows_exhaustion_and_synchronizes_bounded_epochs -- --exact --nocapture
```

Literal RED failed to compile with 11 missing live refill/snapshot/control API
errors. The minimum implementation added bounded typed session refill state
and request/grant operations on the existing ordered Quinn control stream.

Exact fixed frame: one shortest QUIC length byte `0x1e` plus a closed 30-byte
body (`NSCR`, version 1, request/grant kind, 16-byte channel ID, nonzero
big-endian u64 epoch). Exact full request/grant vectors for channel
`404142434445464748494a4b4c4d4e4f`, epoch 2 are:

```text
1e4e5343520101404142434445464748494a4b4c4d4e4f0000000000000002
1e4e5343520102404142434445464748494a4b4c4d4e4f0000000000000002
```

GREEN commands/results:

```powershell
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib refill_control_vectors_pin_exact_bounded_request_and_grant_bytes -- --nocapture
# 1 passed, 0 failed

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test stream_credit_integration ordered_live_refill_follows_exhaustion_and_synchronizes_bounded_epochs -- --exact --nocapture
# 1 passed, 0 failed
```

The live test exercises actual Quinn endpoints through all 64 credits, a 65th
exhaustion rejection, ordered request/grant, current+draining high-water 2,
retirement to 1, and a successful stream in the new window.

Fresh focused final-source verification:

```powershell
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib stream_credit
# 11 passed
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test stream_credit_vectors
# 5 passed
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test stream_credit_integration
# 6 passed
```

Total focused Rust result: 22 passed, 0 failed.

## Implementation summary

- Actual Quinn BEFORE path retains legacy `STREAM_OPEN` plus application echo.
- Actual Quinn AFTER path uses `open_credited_session_stream` /
  `accept_credited_session_stream` and actual 1 KiB echo payloads.
- Allocation automatically records one refill at 16 remaining credits without
  blocking use of those credits. Refill does not create or renew a RouteGrant.
- One current and at most one draining epoch are recognized; pending refill is
  singular and epoch wrap/stale/duplicate/third-epoch transitions fail closed.
- Source and destination session shards both use the existing exact P1F
  `ReplayHistoryLimit(10000)` and at most 8,000 operations per shard.
- The final benchmark helper parameter-struct refactor is private,
  benchmark-only, and mechanical; it was required for strict Clippy and does
  not change wire or session behavior.
- Rust `Instant` supplies the Windows high-resolution QPC timing source;
  process CPU/working-set/private-byte sampling is observed by the Windows
  runner at 20 ms intervals.

## Measurement ladder and corrections

All commands used the release benchmark binaries and the same local host,
Transport Session/Service Channel lifecycle, build/environment/source binding,
and 1 KiB semantics:

```powershell
$env:CARGO_TARGET_DIR='C:\codex-target\nbsr-p2d'
python scripts/run_p2d_stream_credit.py --suite all --output <attempt-path> --security-gate PASS --pair-seconds 60 --soak-seconds 300
```

### Attempt 1 — rejected, non-authoritative

Output: `attempt-1-rejected-unbounded-replay-harness/`. Observed runner wall
duration: 866.2 seconds. Initial metrics would otherwise have passed
(+267.40% median throughput, -72.81% median p99, zero errors), but the live
cells reported replay limit 4,294,967,295. The resource gate was therefore
invalid. No value was relabeled; the original analysis/raw evidence is
retained with an explicit rejection status.

Correction 1 configured both benchmark endpoints with exact P1F limit 10,000
and hardened live-cell/resource validation to require exactly 10,000.

### Attempt 2 — valid but superseded

Output: `attempt-2-bounded-replay/`. Runner wall duration: 864 seconds. It
measured +266.40% median throughput, -73.03% median p99, zero errors, and a
300.0633676-second soak with 5,536,000 operations and exact replay bounds.
Subsequent rustfmt changed source bytes, so this attempt is not used for
final-source acceptance.

Correction 2 applied required formatting and reran the full ladder.

### Attempt 3 — valid but superseded

Output: `attempt-3-rustfmt-clean/`. Artifact wall interval was approximately
864 seconds. It measured +268.97% median throughput, -73.50% median p99, zero
errors, and a 300.0270172-second soak with 5,584,000 operations. All source and
binary hashes matched. Strict final Clippy then found only five
benchmark-helper `too_many_arguments` warnings.

Correction 3/3 mechanically grouped benchmark helper parameters into private
structs. Focused tests, rustfmt, and strict Clippy passed before source freeze.

### Attempt 4 — final authority

Output: `attempt-4-final/`. Runner wall duration: 865 seconds. It is bound to
exact measured source SHA-256
`9db03d84162a55fcfcc6bae461d97fa4ac0f81db53ac0ab319b43c5e3d2729cf`
and release binaries:

- source: `19db8113b87ca4f3af80e069d334b0ee94896494171a46dba495ef4d532fb752`
- server: `7d4a7b8696c56fcf4c7e4e1f2cdc7af13fe6774dab3535cc274d283079e67053`

All eight frozen source/doc/runner hashes and both current binary hashes match
their attempt-4 bindings. All three permitted evidence-driven corrections are
consumed; no mandatory attempt-4 gate failed.

## Final observed cells

Smoke at concurrency 64 completed 192 operations in each mode. BEFORE was
5,276.35 ops/s, p99 12.0796 ms. AFTER was 18,216.15 ops/s, p99 2.6645 ms,
three windows/refills, three deliberate exhaustion observations, epoch
high-water 2, replay 192/10,000, and zero unexpected errors.

Sweep (`concurrency: BEFORE ops/s / AFTER ops/s`, with AFTER p99):

- 1: 3,737.24 / 5,163.24; 0.2975 ms
- 2: 4,568.21 / 7,751.49; 0.4127 ms
- 4: 5,118.62 / 10,777.81; 0.5134 ms
- 8: 5,260.17 / 14,311.07; 0.6994 ms
- 16: 5,289.33 / 14,882.64; 1.7563 ms
- 32: 5,280.36 / 17,075.38; 2.0079 ms
- 64: 5,296.20 / 17,666.20; 3.0355 ms

Concurrency 64 is the smallest point within 98% of the AFTER maximum.

Raw pairs (`BEFORE ops/s, p99 ns -> AFTER ops/s, p99 ns`):

1. `5454.679989, 11953600 -> 18032.892168, 4628400`
2. `5040.756297, 13416900 -> 18967.290614, 3266000`
3. `5077.883544, 12899000 -> 19058.939410, 3138800`

Continuity completed 1,024 operations, 16 windows/refills, p99 2.8817 ms,
epoch high-water 2, replay 1,024/10,000, zero errors.

The soak contains 713 bounded periods/shards. First/last/median shard
throughput was 19,645.51 / 18,661.34 / 19,057.23 ops/s; first/last/median p99
was 3.0295 / 3.4628 / 3.0790 ms. Working set/private-byte observations and the
clearly labeled static thousands-channel estimate are in
`resource-analysis.md`.

Replay audit: 24 aggregate cells, 1,270 shards, 2,540 source/destination shard
endpoints, required replay limit 10,000, zero violations.

## Final gates

| Gate | Result | Final evidence |
|---|---|---|
| throughput >=20% | PASS | +273.53% median |
| p99 regression <=5% | PASS | -74.68% median |
| unexpected errors | PASS | zero |
| security | PASS | focused state/vector/live Quinn matrix |
| refill | PASS | live ordered request/grant, multiple refills, bounded epochs |
| continuity | PASS | 16 windows >=10 |
| soak | PASS | 300.1691775 s, correct payload, zero errors |
| resource | PASS | CPU measured; epoch HWM2; exact replay cap; stable process state |

## Compression, inventory, and final verification

Five JSON artifacts larger than 100 MiB were losslessly, deterministically
gzip-compressed with level 9, mtime 0, and empty filename header. The package
records original/compressed SHA-256, byte counts, schema, source binding, and
successful decompression/recompression verification. Current package before
the checksum file: 161 files, 416,431,368 bytes; largest file 22,146,271 bytes;
no file exceeds 100 MB. No LFS rule was added.

Final commands/results:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
# 10 passed, 0 failed

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check
# PASS

cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
# PASS

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness
# 173 passed, 0 failed, 1 existing evidence-only ten-minute P1F soak ignored

cargo test --manifest-path crates/nbsr-transport/Cargo.toml
# 181 passed, 0 failed, 1 existing evidence-only ten-minute P1F soak ignored
```

The 173 and prior Task-3 179 counts are from different commands. The
all-target feature command includes 8 feature-only tests but omits 16
doctests. Default `cargo test` includes the 16 doctests and omits those 8,
giving 181 now. Task 3's comparable default count was 179; Task 4 added exactly
the refill codec unit test and ordered live refill integration test.

Closed checksum inventory: 161 entries generated and independently verified;
zero missing, unlisted, or mismatched files. `git diff --check` and staged-scope
checks are also run immediately before the local commit.

## Non-claims

This is observed single-host Windows loopback evidence, not a multi-host, WAN,
adversarial-network, memory-attribution, production-capacity, rollout, or
production-readiness claim. The thousands-channel table is an explicit static
estimate and does not substitute for any mandatory observed gate.
