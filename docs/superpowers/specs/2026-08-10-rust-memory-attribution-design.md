# Rust Retained-Memory Ownership Attribution Design

## Scope

Task P1A is diagnostic only. It starts from
`4e25ee026618a502327331f352d90e26d29284e3` on the isolated branch
`codex/nbsr-perf-p1-rust-memory-attribution`. It does not optimize, repair, tune,
pool, cache, refactor protocol behavior, change allocator behavior, change
limits, or alter security semantics. Existing accepted evidence remains
byte-for-byte unchanged; all P1A evidence is additive.

## Architecture

Add one opt-in Rust diagnostics module containing process-wide aggregate atomic
counters and immutable snapshots. Diagnostics are disabled by default and are
enabled only by the Rust performance peer for P1A. Lifecycle transitions are
recorded at the existing owning boundaries in `ControlSession`, channel and
stream registries, the audit queue, NBSR-owned Tokio tasks, and Quinn wrapper
objects. No diagnostic retains a protocol object, identity, nonce, payload,
ticket, key, endpoint secret, or request identifier.

Counters use mutually exclusive terminal outcomes and conservation equations.
Gauges use checked increment/decrement operations and atomic high-water marks.
Container observations expose only aggregate entry counts and capacities that
the standard collection API already makes available. Unsupported or absent
owners are reported explicitly rather than represented by artificial models.

The benchmark peer emits a bounded diagnostic snapshot at the existing
one-second resource cadence using monotonic nanoseconds. The durable runner
writes these records to a new diagnostic JSONL stream. Sampling does not emit
per-object metric series and does not add unbounded labels.

## Owners and reconciliation

- Transport sessions: created, success terminal, failure/cancel terminal, live,
  and live high-water. `created - success - failure = live`.
- Service channels: created, terminal, live, and live high-water, plus pending,
  active, and terminal registry entry counts/capacities where observable.
- Application streams: opened, success terminal, failure/cancel terminal,
  live, and live high-water. `opened - success - failure = live`.
- Pending and registry state: inserts, removals, current entries, high-water
  entries, and aggregate retained capacity at snapshot time.
- Audit queue: enqueued, processed, dropped/evicted, current entries,
  high-water entries, and retained capacity.
- Replay/nonce state and caches: instrumented only if the accepted Rust workload
  reaches a concrete existing owner; otherwise the final inventory names the
  absent or unobservable layer.
- NBSR-owned Tokio tasks: spawned, completed, aborted/cancelled where distinct,
  live, and live high-water. Runtime-global tasks are excluded.
- Quinn wrappers: NBSR connections and relevant application/control stream
  wrapper counts at existing API boundaries. Quinn internals remain untouched.
- Important buffers/queues: live count and aggregate capacity only where the
  owning type exposes capacity without walking or retaining protocol objects.

Every run records the expected baseline before load, the end-of-load snapshot,
and post-drain snapshot. A nonzero delta is attributed to the narrowest concrete
owner whose lifecycle does not reconcile. Reconciled logical counts and
retained capacity are reported separately.

## Benchmark and evidence flow

The existing accepted Rust capacity remains 1,687.5 operations/second. P1A
reuses its frozen approximately 50% and 75% Rust workload definitions; it does
not conduct capacity discovery. Each attribution run has a 60-second warm-up,
1,800-second measured window, and an explicit post-load drain/observation
period recorded in its manifest. Process memory, CPU, offered/completed/errors,
and diagnostics share the same monotonic timeline.

Evidence is written under a new `evidence/performance/rust-memory-attribution-*`
root with raw JSONL, exact commands, environment/build metadata, analysis,
report, manifest, and SHA-256 checksums. Existing evidence is read-only input.

## Observer-effect gate

Before attribution, run at least five short paired Rust comparisons with the
same configuration and alternating disabled/enabled diagnostics. The gate is:
median throughput degradation at most 3%, p99 degradation at most 5%, and zero
additional protocol errors. A failed gate permits only reducing diagnostic
sampling/accounting overhead, never changing NBSR behavior.

## TDD and validation

Each new accounting primitive and lifecycle integration begins with a focused
test that fails for the missing metric, followed by minimal instrumentation and
a passing rerun. Tests cover conservation, high-water behavior, terminal-state
exclusivity, disabled-by-default behavior, bounded snapshots, privacy-safe
schema, durable output, analysis, and A-E classification. Focused protocol,
authorization, replay, channel-binding, lifecycle, and stream-limit regressions
must remain unchanged.

## Classification

The report emits exactly one of A, B, C, D, or E using the definitions in the
approved task. Correlation alone is not causation. An owner is reproducibly
implicated only when it appears in at least two of the three 75% runs and agrees
with post-drain evidence. No identified defect is fixed in P1A.
