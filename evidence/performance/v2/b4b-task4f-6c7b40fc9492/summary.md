# Task 4f — destination stderr drain

**Cleanup intervention: PASS. Workload: SATURATED at 256/512. Handshake cause: UNRESOLVED.**
15/15 valid runs, five repeats at each of 128, 256, and 512 clients.
Windows loopback only. No production-limit claim or sharding recommendation.

## Change and invariants

One dedicated Python reader thread continuously consumes the admission
destination's binary stderr pipe. It writes raw bytes to an exclusive-created
file, flushes/fsyncs/closes it, then joins before validating evidence. No text
decoding or newline conversion occurs in the evidence path. Error prose may
decode a separate copy; the raw file is authoritative.
The child retains identical logging, runtime, authorization, connection/session
independence, wire/security behavior, and handshake/cleanup deadlines.
The established forwarding pair is unchanged. No sharding or Rust changes.

The reader has a 64 KiB chunk bound. A write failure marks capture invalid but
continues draining/discarding to prevent deadlock; discarded bytes cannot count
as valid evidence. A read/flush/close failure also invalidates capture.
Shutdown consumes only the remaining original 15-second destination wait budget.
Existing forced-kill/reap bounds remain unchanged. A blocked reader is daemonized
and cannot prevent interpreter exit; it cannot make an invalid run valid.
The legacy and V2 analyzers reject failed captures explicitly.

## Before / after

Medians across five repeats; timeouts are totals across those repeats.
Before = accepted Task4d; after = Task4f. Comparisons are sequential host runs,
not randomized simultaneous controls. Successful-handshake percentiles exclude
failed/censored handshakes. See `comparison.json` for full precision and CVs.

| Clients | Admitted before → after | Admissions/s | Handshake p95 ms | Handshake p99 ms | Timeouts |
| ---: | --- | --- | --- | --- | --- |
| 128 | 128 → 128 | 38.65 → 52.05 | 1108.25 → 1077.42 | 3026.25 → 1089.00 | 0 → 0 |
| 256 | 226 → 223 | 42.39 → 41.78 | 3148.96 → 3148.69 | 3150.33 → 3150.06 | 177 → 145 |
| 512 | 296 → 294 | 52.98 → 52.55 | 3339.47 → 3408.27 | 3343.87 → 3410.27 | 1004 → 1100 |

| Clients | Forwarding Gbit/s | Forwarding p99 ms | Effective cores | Private MiB | Handles |
| ---: | --- | --- | --- | --- | --- |
| 128 | 0.657 → 0.690 | 0.354 → 0.373 | 1.36 → 1.35 | 82.3 → 82.6 | 459 → 460 |
| 256 | 0.670 → 0.564 | 0.371 → 0.454 | 1.38 → 1.37 | 123.4 → 125.4 | 592 → 591 |
| 512 | 0.681 → 0.565 | 0.398 → 0.487 | 0.87 → 1.43 | 213.9 → 209.2 | 855 → 856 |

Four benchmark processes and median peak 19 benchmark threads remain unchanged.
The additional reader runs in the Python orchestrator, outside those benchmark
process totals: one extra orchestration thread, not per-client fan-out. Host
telemetry includes the orchestrator; per-process benchmark totals do not.
After-run host CPU medians: 23.02%, 25.61%, 26.24% at 128/256/512.
CPU comparison at 512 is confounded by removal of the old long blocked cleanup
interval from the elapsed-time denominator; not a CPU-efficiency speedup claim.

Lower forwarding goodput and higher p99 at 256/512 are preserved. These runs do
not establish whether the difference is host variability or an intervention
effect. No performance-regression cause is asserted or hidden.

Existing workload classification: 128 STABLE; 256/512 SATURATED. This is not a
strict low-variance ceiling claim: after five repeats admission-rate CV is
34.23%, 2.63%, 9.23%; forwarding CV is 1.40%, 9.79%, 6.45% respectively.
The historical zero-client baseline is reused only for classification ratios;
no new zero-client measurement was run, as only 128/256/512 were authorized.

## Primary result: cleanup

Task4d 512: **5/5 destination cleanup overruns**, followed by forced termination.
Task4f 512: **0/5 overruns**, all processes exited normally, all eight reported
ownership counters returned to zero, exact per-client terminal evidence.
The same cleanup result holds for all 128/256 runs.
Connections, transport sessions, channels, streams, tasks, queues, and replay
entries are represented separately in each raw record's cleanup counters.

Destination stderr at 512: **13,680; 11,514; 14,421; 10,659; 12,426 bytes**.
All captures passed byte-count/SHA-256 verification and flush/join checks.
Unlike the old truncated stderr, complete error logs exceed the former pipe
backpressure region while the destination proceeds to zero-resource shutdown.
This controlled harness-only change closes the observed 512 cleanup failure.

`destination_cleanup_wait_seconds` is the residual wait at the existing
post-forwarding cleanup check, **not end-to-end connection teardown latency**.
Destinations had already exited by that check: median residual waits were about
31/29/28 microseconds at 128/256/512, versus old 512 waits exceeding 15 seconds.
Do not present these residual waits as total cleanup duration.

## Remaining handshake problem

256 and 512 still have timed-out handshakes despite successful stderr draining
and clean ownership termination. This confirms the handshake problem is not
resolved by the cleanup fix; it does not identify its cause. No production limit,
hardware limit, runtime serialization, or sharding benefit is inferred.
Next recommended step: bounded handshake-specific attribution with resolved
system symbols and connection/timer/network correlation. No optimization yet.
B3-v2 and driver sharding are not started.

## Reproduction / provenance

Raw execution base: `6c7b40fc9492b326058e37fa0341f5adaedf4b5b`, plus the harness
changes captured by this atomic commit. `environment.json` records dirty state,
host/toolchains, source/binary hashes, release build, command and workload.
Each measurement uses 20 seconds plus 2-second warmup, matching Task4d.
Three repeats are extended to five if either admission-rate or goodput CV >5%.

```powershell
$env:CARGO_TARGET_DIR='C:\NBSR-build\b4b-task4e-profile'
python scripts/run_b4b_task4f.py --output <fresh-evidence-directory>
python scripts/analyze_b4b_task4f.py --before evidence/performance/v2/b4b-task4d-361c315038bb --after <fresh-evidence-directory> --output <fresh-evidence-directory>/comparison.json
```

Raw results are unedited. The comparison script verifies every captured stderr
file against its recorded byte count and SHA-256. `checksums.sha256` covers this
evidence directory, excluding itself.

## Verification

- Literal RED: three missing-drain tests; then V2 validity gate failed (1 FAIL,
  3 PASS); legacy analyzer rejection failed before correction.
- GREEN: `python -m pytest tests/performance -q` — **245 PASS**.
- After adding read-failure coverage: `python -m pytest tests/performance/test_stderr_drain.py tests/performance/test_mixed_connections.py -q` — **22 PASS**.
- `python -m pytest tests/protocol/test_dependencies.py tests/federation/test_repository_safety.py tests/federation/test_independent_peer_dependency_boundary.py -q` — **12 PASS**.
- `python -m ruff check scripts/performance/stderr_drain.py scripts/run_b4b_task4f.py scripts/analyze_b4b_task4f.py scripts/run_b4b_v2.py scripts/run_b4b_mixed_connections.py scripts/performance/mixed_connections.py tests/performance/test_stderr_drain.py` — PASS.
- `git diff --check` — PASS.
- Pytest's exit cleanup emits the pre-existing `pytest-current` WinError 5; test
  commands exit zero. No tests overlap authoritative measurements.
- Focused diff review: binary pipe capture, deadline accounting, failure gates,
  raw evidence flush/join and production dependency boundary inspected.
- No Rust/Go or dependency changes; their suites/fmt/clippy were not rerun.
  Existing release benchmark binaries were rebuilt/reused through the normal
  harness build command; raw environment records their hashes.
