# Task 4g — bounded shared-memory observer

**PARTIAL / UNRESOLVED. Both observer gates rejected.** No causal attribution,
ETW, optimization, sharding or B3-v2 follows this result.

## Provenance and scope

Branch: `codex/nbsr-v3-wp0-wp1`.
Capture base: `e4ce037ebaf4024609497aec5fc594720812386e`, dirty benchmark-only
instrumentation explicitly recorded in `environment.json`. Capture began
2026-09-03 20:06:24 UTC. Windows 11, i5-10210U, 4 physical cores / 8 logical
processors, 16,942,501,888 bytes RAM; inherited affinity, release builds.
Compiler/runtime versions, exact commands and binary/source SHA-256 are stored.

This is Windows loopback with the existing established-forwarding pair and
independent client connections to the existing concurrent admission destination.
No production, frozen-authority, protocol, ACK, deadline or trust change.
Shared memory is observation only. Source process exit remains the admission
measurement endpoint. No logical client shares another client's record or session.

Five OFF/ON pairs at each of 128 and 256 clients; alternating order; 20-second
forwarding window, 2-second warmup. Both groups required five repeats due to CV.
All 20 results are valid captured runs; all show zero cleanup ownership and exact
terminal evidence. All 20 original ON mapping snapshots were decoded again and
matched their stored JSON. Checksums cover original logs, binary mappings,
environment, source snapshots and derived summaries.

## Observer gate

| Clients | OFF / ON admitted median | OFF / ON admissions/s | OFF / ON Gbit/s | Absolute success shift | Result |
|---|---:|---:|---:|---:|---|
| 128 | 128 / 128 | 38.731 / 73.582 | 0.618359 / 0.638170 | 0 pp | REJECT |
| 256 | 237 / 226 | 44.176 / 41.516 | 0.598026 / 0.592558 | 4.296875 pp | REJECT |

128-client median differences: admissions/s 89.98%, forwarding p99 10.14%,
admission p99 58.12%, handshake p99 65.33%. 256-client differences: admissions/s
6.02%, forwarding p99 12.21%, handshake p50 58.74%. These violate the absolute
5% guard, including apparent improvements; the 256 success shift also violates
the 1-percentage-point guard. Exact values are in `timeline-analysis.json`.

Admission-rate CV OFF/ON was 41.03%/9.66% at 128 and 8.51%/21.17% at 256.
Median sampled process CPU divided by complete observed run elapsed time was
1.347/1.335 effective cores at 128 and 1.395/1.399 at 256. This includes harness
setup/observation and is not a thread saturation measure. Host/resource samples
remain in each raw record. No host-limit claim is made.

The comparison does not isolate intrinsic instrumentation cost from host/run
variability. It fails the pre-approved comparability gate regardless; no speedup
or exact observer-cost attribution is claimed.

## Timeline observations — rejected for causal attribution

Pooled ON source records: 128 clients yielded 640 admitted observations; 256
yielded 1,138 admitted and 142 timed-out observations. Successful connect-future
interval p99 was 1.054 s versus 3.316 s. Connected-to-control-hello p99 was
1.193 s versus 3.815 s. The 256 timeout interval from first connect poll had
median 5.008 s. These describe the instrumented runs, not an accepted explanation
of the original collapse. Failed clients were not discarded from timeline data.

**Exact delay cause and handshake-timeout mechanism: NOT ESTABLISHED.** Timing
and poll counts cannot distinguish Windows network delay, Quinn timers, source
scheduling, destination scheduling, admission serialization or another cause.
Destination accept slots remain unmatched to source IDs. No speculative
cross-process correlation was performed. ETW correlation quality: NOT AVAILABLE
because the timeline-only gate failed; ETW was intentionally not collected.

## Integrity and review corrections

`capture-source/` preserves exact sources used during measurement, verified
against environment source hashes. The measured binaries are identified by hash,
not retroactively represented as binaries from the final commit.

After capture, one focused review and scoped re-review caused correctness-only
changes: require every gate metric and required repeat count; retain local cleanup
timestamps after failed consuming close calls without changing failure outcomes;
preserve mappings on exceptional runner exit when child exit is confirmed;
reject the reserved error-code field; add Windows mapping/overflow tests and
non-Windows compile guards. Captured-source versus final code differences remain
explicit. No second authoritative campaign was run after gate rejection, and
final-code observer overhead is not claimed to pass. Existing raw files were not
edited. Offline revalidation still accepts every original mapping.

If the OS cannot terminate a child within existing cleanup bounds, the run is
INVALID. A mapping is not serialized while that child remains live merely to
obtain evidence; such a failure may lack a post-exit snapshot. Handles still have
scoped parent ownership. No deadlines were extended to cover this exceptional case.

## RED / GREEN and exact commands

RED: missing parent implementation/validation initially failed; three Rust stage
tests failed with an empty recorder; clock-reversal regression failed; review
regressions failed 2 tests (missing metric acceptance and close-error cleanup).
GREEN: targeted Python timeline/gate tests 9/9; Rust timeline tests 5/5 in each
binary. Native test covers real mapped slot isolation, duplicate/unknown claims
and counter overflow; Python child-exit test verifies parent retention and final
named mapping disappearance. Endpoint-preservation test guards source-exit timing.

Final commands executed:

```powershell
$env:CARGO_TARGET_DIR = 'C:\NBSR-build\b4b-task4g'
python -m pytest tests/performance tests/protocol/test_dependencies.py tests/federation/test_repository_safety.py -q
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source --bin wp8_interop_server
cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check
cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source --bin wp8_interop_server -- -D warnings
git diff --check
```

Results: Python 264 PASS; Rust 25 + 12 PASS; fmt, clippy, dependency/privacy
tests and diff check PASS. Python emitted a non-fatal pytest temporary-symlink
cleanup `WinError 5` after passing; this is separate from NBSR ownership cleanup.

Reproduce new collection (new output directory required):

```powershell
python scripts/run_b4b_task4g.py --output C:\NBSR-build\task4g-new-run
python scripts/analyze_b4b_task4g.py --root evidence/performance/v2/b4b-task4g-e4ce037ebaf4
```

The second command derives summaries from preserved original raw files, not from
edited prose. `capture-source/` plus the recorded base/lockfiles identifies the
historical executable-dependent variant; current code contains the review fixes.

## Recommendation

Stop here. Do not infer a runtime, network, handshake or production bottleneck
from these rejected observations. Any redesigned observer or further profiling
requires a separate approved step; no tuning/sharding recommendation is justified.
