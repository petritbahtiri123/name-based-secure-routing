# Task 4 report: benchmark harness, evidence, and acceptance

## Result

**DONE — Outcome A — ACCEPTED AND RETAINED.** Final authority is
`evidence/performance/stream-credit-window-p2d/attempt-5-final-security-review/`.

At selected concurrency 64, three matched 60-second BEFORE/AFTER pairs
measured median throughput 4,979.12 -> 18,704.12 operations/second (+275.65%)
and median p99 14.0123 -> 3.4331 ms (-75.50%). Sample throughput CV was 4.064%
BEFORE and 0.962% AFTER. Every pair was on the passing side of both fixed
thresholds and all six cells had zero errors, so the exact three-pair stopping
rule applied.

The conditional soak ran 300.2110533 seconds, completed 5,576,000 correct 1
KiB operations at 18,573.60 operations/second, p99 3.5048 ms, with zero errors,
87,125 ordered refills, active-epoch high-water 2, and replay 8,000/10,000.
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

### Attempt 4 — valid but superseded

Output: `attempt-4-final/`. Runner wall duration: 865 seconds. It is bound to
exact measured source SHA-256
`9db03d84162a55fcfcc6bae461d97fa4ac0f81db53ac0ab319b43c5e3d2729cf`
and release binaries:

- source: `19db8113b87ca4f3af80e069d334b0ee94896494171a46dba495ef4d532fb752`
- server: `7d4a7b8696c56fcf4c7e4e1f2cdc7af13fe6774dab3535cc274d283079e67053`

All eight then-frozen source/doc/runner hashes and both binary hashes matched
their attempt-4 bindings, and no mandatory attempt-4 gate failed. A later
consolidated security/evidence-integrity review required corrected source and
a new full Attempt 5 ladder, so Attempt 4 is not final authority.

## Historical Attempt 4 observed cells (superseded)

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

## Historical Attempt 4 gates (superseded)

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

## Historical pre-security compression, inventory, and verification

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

## Consolidated security and evidence-integrity correction

Final review identified six new integrity findings after Attempt 4. This is a
new correction set rather than another correction for an earlier performance
failure. Literal RED observations were:

```powershell
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib draining_and_current_accept_old_new_reordering_but_never_a_third_epoch -- --nocapture
# RED: request_refill returned Ok(3) while epoch 1 was draining; expected
# Err(DrainingEpoch), with pending state remaining None.

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib draining_epoch_retirement_waits_for_reordered_old_stream_terminal_cleanup -- --nocapture
# RED: premature epoch-1 retirement returned Ok(()) while one reordered old
# stream remained live; expected Err(StreamCredit(InvalidState)).

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib refill_grant_revalidates -- --nocapture
# RED: both full-channel and exhausted-P1F cases returned Ok(()); expected
# typed OverCapacity/ReplayCapacity without window mutation.

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test stream_credit_integration ordered_live_refill_follows_exhaustion_and_synchronizes_bounded_epochs -- --exact --nocapture
# RED: a second control-stream open succeeded; expected ControlStreamFailed.

python -m pytest tests/test_p2d_stream_credit.py -q
# RED at collection: recursive replay-limit validation and complete source
# binding APIs did not exist.
```

The minimum GREEN implementation:

- rejects a refill request before setting pending state whenever a draining
  epoch exists;
- keeps two compact assigned-stream counters in the fixed window state and the
  epoch number in each existing ordinary stream entry, with no per-credit heap
  object;
- decrements only after successful ordinary terminal removal and refuses to
  retire a draining epoch with any assigned stream outstanding;
- atomically claims exactly one control stream on each authenticated Quinn
  connection, reusing it for lifecycle and refill frames and rejecting every
  second open/accept;
- revalidates live per-channel stream headroom and exact per-session P1F replay
  headroom before any grant mutation, recording the existing quota-denial audit
  and reserving no stream, replay ID, byte quota, or RouteGrant;
- recursively checks every measured source/destination endpoint, making any
  replay-limit violation a FAIL; and
- binds every Rust source file, Cargo manifest/lock, imported orchestration and
  analysis module, relevant runtime vector, Python project manifest, and the
  normative protocol document, plus exact bound-input status/worktree/index
  diff identities.

Focused GREEN observations before final formatting and the full suite:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
# 12 passed

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib stream_credit -- --nocapture
# 11 passed

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --lib refill_grant_revalidates -- --nocapture
# 2 passed

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test stream_credit_integration -- --nocapture
# 6 passed
```

Attempt 4 is superseded for final-source acceptance. Attempt 5 is run only
after the corrected source passes focused/full tests, rustfmt, and strict
all-target Clippy, is committed locally, and has an empty bound-input diff.

Two existing integration tests used a second `open_control_stream()` call as a
raw application-stream escape hatch. The singleton correctly failed those
calls. Their original security assertions remain intact without weakening the
invariant: the pre-accept test now keeps the sole control stream and sends on a
bound application-stream permit without transmitting `STREAM_ACCEPT` to the
destination; the drain test opens stream 12 through a bound application permit
and observes the draining destination reset it. Focused reruns passed.

Fresh pre-Attempt-5 freeze verification:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
# 12 passed, 0 failed; 3.974 s wrapper duration (1.90 s pytest duration)

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness
# 176 passed, 0 failed, 1 existing evidence-only P1F soak ignored; 37.790 s

cargo test --manifest-path crates/nbsr-transport/Cargo.toml
# 184 passed, 0 failed, 1 existing evidence-only P1F soak ignored; 66.582 s

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
# PASS

git diff --check
# PASS (line-ending notices only)

cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
# PASS; 3.180 s
```

The corrected all-target feature count is 176: the prior 173 plus three new
library regression tests (premature epoch retirement and two grant-headroom
cases). Default is 184 because it includes 16 doctests and omits the 8
feature-only binary tests. These are command-shape differences, not missing
coverage.

## Attempt 5 — final corrected-source authority

Frozen fix commit:
`8cc935e1a08de20eaab1abd814906d1854da9bc8`. Before the timed run, Git status
was empty. All 35 bound inputs recorded zero-byte status, worktree-diff, and
index-diff identities with the exact empty SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
The complete measured-source SHA-256 is
`e32e8b4c4b2187c2fb1412909fcdc2449b771e2b096c763175ade7e2396c2cb3`.
The generic `repository_dirty` field is true only because the immutable output
directory was created before repository-wide status capture; the separately
recorded complete bound-input identity is clean.

Command:

```powershell
$env:CARGO_TARGET_DIR='C:\codex-target\nbsr-p2d'
python scripts/run_p2d_stream_credit.py --suite all --output evidence/performance/stream-credit-window-p2d/attempt-5-final-security-review --security-gate PASS --pair-seconds 60 --soak-seconds 300
```

Observed runner wall duration: 886.090 seconds. Exact rebuilt binaries:

- source: `4f0cbd64b3fd6111790faaddcc0bff1262c631413e98a3bc2b3e6e31def57c51`
- server: `2d30d6118d6417c775824a85956cae40bc0cd596933449bf44407fa7a6fe9df4`

The seven-point sweep selected concurrency 64. Three-pair stopping applied:

1. `5324.058646, 13200700 -> 18704.122884, 3433100`
2. `4979.123779, 14012300 -> 18454.956823, 3642300`
3. `4954.324122, 14268600 -> 18803.032642, 3294900`

Median throughput improved 4,979.123779 -> 18,704.122884 operations/second
(+275.65%); median p99 fell 14.0123 -> 3.4331 ms (-75.50%). Throughput CV was
4.0638% BEFORE and 0.9615% AFTER. All six cells had zero errors and every pair
passed both fixed thresholds.

Continuity completed 1,024 operations, crossed/refilled 16 windows, measured
p99 2.9711 ms, held epoch high-water 2, and had zero errors. The soak ran
300.2110533 seconds, completed 5,576,000 correct 1 KiB operations at
18,573.599935 operations/second, aggregate p99 3.5048 ms, zero errors, 87,125
windows/refills, epoch high-water 2, and replay 8,000/10,000.

The soak contains 697 periods/shards. First/last/median periodic throughput was
19,965.101003 / 18,618.927117 / 18,922.997592 operations/second. The worst
periodic throughput was 11,548.015856 at period 190. First/last/median periodic
p99 was 2.9748 / 3.0320 / 3.1500 ms; worst periodic p99 was 5.7913 ms at period
38. These extrema are observations alongside, not replacements for, aggregate
acceptance metrics.

The recursive replay audit covered every nested measured endpoint: 24
aggregate cells, 1,252 shards, and 2,504 source/destination endpoints. Every
`replay_limit` was exactly 10,000; violations: zero. The analyzer classifies
any future measured violation as FAIL, not INCONCLUSIVE.

Attempt 5's sole JSON above 100 MiB was compressed only after the runner
completed. Exact lossless identity:

- original: 107,929,076 bytes,
  `dee80e84f7bc84f7a8cba04f220c5821f23f66e2e7e2cf2e213d654daf8c850f`
- gzip: 15,898,996 bytes,
  `721dd7ccac9bad09abdf5054e9b44dd9f7c50f75e91109c87833abfa9326a8a1`

All six retained compressed artifacts were decompressed to the exact original
byte count/SHA-256 and independently recompressed with gzip level 9, mtime 0,
and empty filename header. Every recompressed byte stream and SHA-256 exactly
matched the stored gzip.

Final package inventory before regenerating `checksums.sha256`: 201 files,
516,267,489 bytes; largest file 22,146,271 bytes; zero files exceed 100 MiB.
The closed checksum file contains exactly 201 entries and is independently
verified after generation.

Fresh post-Attempt-5 verification against the unchanged frozen source:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
# 12 passed, 0 failed; 1.423 s wrapper duration (0.76 s pytest duration)

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
# PASS

git diff --check
# PASS (line-ending notices only)

cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
# PASS; 0.412 s

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness
# 176 passed, 0 failed, 1 existing ignored; 41.654 s

cargo test --manifest-path crates/nbsr-transport/Cargo.toml
# 184 passed, 0 failed, 1 existing ignored; 40.995 s
```

## Source-binding correction round 2

Attempt 5 remains valid performance evidence but is superseded for final
source-identity acceptance. Its selected-path binding omitted tracked
transitive inputs such as `scripts/performance/resources.py`,
`authorities.py`, and `driver.py`, and it captured repository-wide status only
after creating the output directory. This new correction changes source
identity only; prior security findings 1-5 remain closed.

Literal RED command/result:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q -k "source_binding or runtime_audit"
# 4 failed: missing head_tree, source_binding(root) unsupported for both a
# tracked transitive edit and untracked import shadow, and no runtime audit API.
```

The minimal GREEN binding:

- captures `HEAD` commit and `HEAD^{tree}` before creating the attempt output;
- requires exact empty `git status --porcelain=v2 --untracked-files=all`, a
  clean index, clean tracked worktree, and `git write-tree == HEAD^{tree}`;
- makes the commit plus complete Git tree object authoritative for every
  tracked/transitive input, while retaining explicit SHA-256 for key benchmark
  entrypoints and release binaries;
- after output creation, permits untracked paths only beneath that exact output
  root and rejects any tracked/index/HEAD change or other untracked path; and
- audits at every live cell boundary and records post-output, post-build, and
  final runtime repository identities.

Focused GREEN:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q -k "source_binding or runtime_audit"
# 4 passed, 11 deselected

python -m pytest tests/test_p2d_stream_credit.py -q
# 15 passed
```

Attempt 6 is run only after this source/report/test tree is committed, the full
Rust/Python/fmt/Clippy matrix passes, and the authoritative pre-output status
is empty. If this same source-binding failure mode recurs, one correction
remains.

Pre-freeze verification:

```powershell
python -m ruff check scripts/run_p2d_stream_credit.py tests/test_p2d_stream_credit.py
python -m ruff format --check scripts/run_p2d_stream_credit.py tests/test_p2d_stream_credit.py
# PASS

python -m pytest -q
# Existing branch-wide result: 1,790 passed, 1 skipped, 37 failed in 323.33 s.
# Every failure is outside this three-file correction and arises from existing
# locked Core/F75/federation/dependency/vector authority drift; first failure:
# modified original core-v0.2 baseline-lock digest. The scoped P2D suite is
# independently GREEN at 15 passed. This repository-wide failure set is not
# used to weaken or relabel any P2D mandatory gate.

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
git diff --check
# PASS

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness
# 176 passed, 0 failed, 1 existing ignored; 42.605 s

cargo test --manifest-path crates/nbsr-transport/Cargo.toml
# 184 passed, 0 failed, 1 existing ignored; 43.421 s

cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
# PASS; 0.441 s
```

## Final source-binding correction

Attempt 6 completed smoke, the complete concurrency sweep, three matched
60-second pairs, continuity, and the 300-second soak, but exited 1 after 881
seconds while finalizing its runtime repository audit. The runner had already
exclusive-created `runtime-repository-audit.json` as `IN_PROGRESS` and then
incorrectly called the same exclusive-create writer for the final `PASS`
document. That raised `FileExistsError`. Attempt 6 is preserved additively but
is non-authoritative; its `analysis.json` Outcome A is not accepted.

Literal finalizer RED:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q -k "runtime_audit_finalizer"
# 6 failed: the finalizer API did not exist.
```

The tests require the finalizer to replace only the exact canonical known
`IN_PROGRESS` audit file at the fixed filename inside the exact attempt root.
They reject a missing target, wrong state, already-finalized target, actual
file symlink, and escaped attempt root. The success test observes that the old
audit file remains intact until a fully flushed and fsync'd same-directory
temporary file reaches `os.replace`, and proves another raw evidence file is
byte-identical afterward.

Minimal finalizer GREEN:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q -k "runtime_audit_finalizer"
# 6 passed, 15 deselected

python -m pytest tests/test_p2d_stream_credit.py -q
# 21 passed
```

Attempt 6's 108,710,706-byte soak JSON was losslessly compressed to a
15,439,839-byte deterministic gzip (level 9, mtime 0, empty filename header).
Decompression reproduced SHA-256
`6b0aca8a55257531f72f8882e30dc97219fc07bf7ba9b9a00f9e7145b4be263f`;
exact recompression reproduced stored gzip SHA-256
`47d17db0d22db076c9295347e8fa1b6aee48247129539062e423c98ece4803c0`.

Final correction pre-freeze verification:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
# 21 passed in 4.12 s

python -m ruff check scripts/run_p2d_stream_credit.py tests/test_p2d_stream_credit.py
python -m ruff format --check scripts/run_p2d_stream_credit.py tests/test_p2d_stream_credit.py
cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
git diff --check
# PASS

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness --quiet
# 176 passed, 0 failed, 1 existing ignored

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --quiet
# 184 passed, 0 failed, 1 existing ignored

cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
# PASS

python -m pytest -q
# 1,796 passed, 1 skipped, 37 failed in 310.53 s. The same pre-existing
# branch-wide Core/F75/federation/dependency/vector authority failures remain;
# the six added passing finalizer tests account for the increase from the
# preceding 1,790-pass run. No P2D mandatory gate is weakened or relabeled.
```

## Authoritative Attempt 7

The final correction/evidence commit before measurement was
`100b871db011ba514bd45f0354714e1f698ebdd5`. Its clean pre-output identity
was:

- `HEAD^{tree}` and index tree:
  `6d84e897b29e358c716c6c83b2ad6efc2ec445fa`;
- tracked files: 2,069;
- measured-source SHA-256:
  `921d4276f4aa28d7747c78622bb0a785a3333e3020188a8f45bc1b38483e7cb4`;
- pre-output porcelain-v2 status: zero bytes / exact empty SHA-256;
- release source binary SHA-256:
  `4f0cbd64b3fd6111790faaddcc0bff1262c631413e98a3bc2b3e6e31def57c51`;
- release server binary SHA-256:
  `2d30d6118d6417c775824a85956cae40bc0cd596933449bf44407fa7a6fe9df4`.

Command:

```powershell
$env:CARGO_TARGET_DIR='C:\codex-target\nbsr-p2d'
python scripts/run_p2d_stream_credit.py --suite all --output evidence/performance/stream-credit-window-p2d/attempt-7-final-atomic-audit --security-gate PASS --pair-seconds 60 --soak-seconds 300
# exit 0; 879.4 s wall time
# Outcome A — ACCEPTED AND RETAINED
```

All mandatory gates passed. At selected concurrency 64, three matched pairs
measured median throughput 5,056.57 -> 18,936.28 operations/second (+274.49%)
and median p99 13.9433 -> 3.2508 ms (-76.69%). Throughput CV was 3.338%
BEFORE and 0.228% AFTER; errors were zero. Continuity crossed/refilled 16
windows in 1,024 operations with zero errors.

The 300.2411631-second soak completed 5,568,000 operations at 18,545.09
operations/second with aggregate p99 3.8604 ms, 87,000 windows/refills, zero
errors, active-epoch high-water 2, and replay state 8,000/10,000. Its worst
periodic throughput was 8,109.91 operations/second and worst periodic p99 was
6.8864 ms, both at period 241. These extrema are observations and do not
replace the aggregate gates. All 2,514 nested source/destination endpoints in
1,257 shards across 24 cells reported replay limit exactly 10,000.

`runtime-repository-audit.json` finalized atomically to PASS. Pre-output was
empty; post-output, post-build, every cell boundary, and the final capture
retained the exact commit/HEAD/index tree, allowed only the exact Attempt 7
root, and reported zero disallowed changes.

Attempt 7's 107,774,853-byte soak JSON was losslessly compressed to a
15,872,609-byte deterministic gzip. Decompression reproduced original
SHA-256 `29ca69c804fa67923c4ef5c0dae234d162259abba7aa7883a565805d2c809c02`;
exact recompression reproduced stored gzip SHA-256
`72de500e21e63ea55901934861db97a5111869e4688ec118ffed00d8017f719c`.
All eight package gzip artifacts passed the same decompression and exact
recompression verification.

Final package inventory before the evidence commit: 282 closed checksum
entries, 283 files including the checksum file, 717,058,062 bytes total, and a
largest stored artifact of 22,372,470 bytes. All 248 stored `.json` files parse;
the earlier Attempt 6 inventory counts are superseded by this final
closed-inventory verification.

Final post-Attempt-7 verification against the unchanged measured source:

```powershell
python -m pytest tests/test_p2d_stream_credit.py -q
# 21 passed in 5.00 s

python -m ruff check scripts/run_p2d_stream_credit.py tests/test_p2d_stream_credit.py
python -m ruff format --check scripts/run_p2d_stream_credit.py tests/test_p2d_stream_credit.py
cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
git diff --check
# PASS

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness --quiet
# 176 passed, 0 failed, 1 existing ignored

cargo test --manifest-path crates/nbsr-transport/Cargo.toml --quiet
# 184 passed, 0 failed, 1 existing ignored

cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
# PASS; complete concise matrix 100.4 s

python -m pytest -q
# 1,796 passed, 1 skipped, same 37 pre-existing authority/vector failures;
# 390.40 s under parallel validation load.
```
