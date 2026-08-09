# Loopback Benchmark Completion Design

## Status and scope

This design closes only the three scientific blockers that keep the extended
unoptimized loopback benchmark at `PARTIAL_BASELINE`:

1. capacity discovery and formal-load reproduction are inconsistent;
2. post-warm-up memory stability is `INCONCLUSIVE`; and
3. unsupported 640-stream failures lack typed raw request evidence.

The work continues on `codex/nbsr-v3-wp0-wp1` from
`e4492c4fc4b5124e71e218c56efd16114c147238`. It does not optimize NBSR,
redesign the protocol, change protocol or resource limits, or add cloud,
same-region, cross-region, WAN, HTTP/3, or demo scope.

## Immutable evidence boundary

The original 300,000-sample baseline, extended 2,530,000 formal headline
samples, lifecycle results, 20-service results, payload results, five-run
reproducibility results, existing supported concurrency through 320 streams,
and all prior manifests and checksums remain byte-for-byte unchanged.

Completion evidence is written under a new additive evidence root. Its
manifest identifies the prior partial evidence root as historical input and
records checksums for every new authoritative or explanatory artifact. The
new verifier reads the prior evidence only to verify its frozen checksums and
to cite previously accepted results; it never regenerates or overwrites it.

## Frozen sustainable-capacity rule

Capacity remains path-specific for Direct QUIC, Rust-to-Rust NBSR, and
Go-to-Rust NBSR. A sustainable point must satisfy all of the following during
a formal 600-second steady-state window after at least 60 seconds of warm-up:

- success rate at least 99.9%;
- no unexpected protocol rejection;
- no unexpected protocol or resource-limit violation;
- destination CPU at most 85% of assigned capacity;
- no sustained unbounded memory growth; and
- p99 no greater than twice that path's idle p99.

The historical 5,500/s Direct, 2,500/s Rust, and 500/s Go points are retained
as superseded candidates. They are not accepted capacities unless they pass
the repeated method in this design.

## Capacity discovery and acceptance

Each path is searched independently. The harness starts from known passing
and failing regions, conducts a bounded coarse search, records a passing and
failing bracket, narrows it with finer points, and tests conservative points
near the boundary. Search decisions and every attempted point are raw
evidence, including failed points.

A candidate cannot be accepted from discovery alone. Acceptance requires at
least three independent 60-second warm-up plus 600-second steady-state
confirmations at the same rate. Every confirmation must pass every frozen
criterion. A single failing confirmation invalidates the candidate; failures
are not averaged with passes. The harness moves downward and starts a new
three-run confirmation set.

## Formal-load validation

After a path has an accepted capacity, its 25%, 50%, 75%, and 90% cells are
calculated from that same path's accepted value. The machine-readable record
stores the accepted-capacity evidence identifier and calculation for each
cell. No capacity is shared between paths.

The formal cells use at least 60 seconds of warm-up followed by 600 seconds of
steady state. The 90% cell must satisfy the same p99-to-idle rule. A repeated
90% failure invalidates the accepted capacity and returns that path to
discovery and confirmation; the report cannot average or waive the failure.

## Open-loop and backlog integrity

Scheduled arrival time remains the authority for offered load. The driver
continues scheduling arrivals against absolute deadlines even when workers
are delayed. It records offered, accepted, queued, active, completed, failed,
timed-out, and rejected counts together with scheduler lag, send lag, receive
lag, and observable queue or backlog depth where available.

Every offered sample reaches a terminal raw record. Evidence-writer overflow,
sample loss, or offered/terminal count mismatch fails the run. A saturated
implementation therefore remains visibly saturated instead of becoming a
healthy-looking closed-loop test.

Authoritative latency records contain only instrumentation shown by focused
measurement not to materially distort latency. If deeper decomposition of
the prior Rust 90% p99 result is needed, it runs separately and is labeled
`EXPLANATORY — NOT AUTHORITATIVE LATENCY`. Explanatory observations may
distinguish scheduling, queueing, send, receive, application, transport wait,
timeout, and rejection, but cannot replace authoritative cells.

## Memory-stability experiments

Six primary memory experiments run after final capacity acceptance:

- Direct at approximately 50% and 75%;
- Rust-to-Rust at approximately 50% and 75%; and
- Go-to-Rust at approximately 50% and 75%.

All six use the same explicit warm-up rule and fixed sampling cadence. Each
has at least 30 minutes of steady-state observation after warm-up. The 90%
cell is not primary memory evidence.

Each sample records monotonic time, warm-up or steady-state phase, process
identity, working set, private bytes, peak working set, CPU, processed request
count, active concurrency, and available queue or backlog observations. Go
samples additionally preserve `HeapAlloc`, `HeapSys`, `HeapIdle`,
`HeapInuse`, `HeapReleased`, `NumGC`, `TotalAlloc`, mallocs, frees, and GC
pause information when the existing runtime endpoint exposes them. Rust uses
process-level authoritative evidence; allocation-specific instrumentation is
permitted only in separately labeled explanatory experiments.

Memory collection is fail-closed. Expected cadence points, collected points,
and gaps are explicit. Missing samples, a stopped sampler, or corrupt records
invalidate the affected run rather than disappearing from analysis.

## Memory trend method

Warm-up samples are excluded by an explicit phase boundary recorded before
the run. Trend analysis uses only steady-state samples. For working set and
private bytes it reports full post-warm-up, second-half, and final-quarter
slopes; start/end values; peaks; residual variation; and slope normalized by
processed requests where the request counter advances.

Classification compares both loads for the same path and correlates memory
with time, processed requests, CPU, queue/backlog, and Go GC activity:

- `PASS` requires defensible evidence of bounded allocator retention or
  stable post-warm-up working set/private bytes at both stable loads;
- `FAIL` requires reproducible sustained post-warm-up growth correlated with
  time or processed requests that is not explained by bounded warm-up,
  allocator steps, cache settling, GC sawtooth, allocator retention, or OS
  page behavior; and
- `INCONCLUSIVE` remains mandatory when noise, duration, missing samples, or
  allocator/runtime behavior prevents that distinction.

No isolated allocator step, retained heap, GC sawtooth, or working-set change
is automatically classified as a leak.

## Typed 640-stream evidence

The supported result through 320 concurrent streams remains unchanged. The
640-stream test remains an unsupported operating point and is not made to
succeed by changing limits.

Every attempted request produces a raw record with run ID, implementation,
scenario, requested concurrency, configured or supported limit, service and
channel identity, request or sample ID, scheduled and start times where
meaningful, final result, typed rejection or failure, timeout category,
pre-admission or post-admission phase, expected-fail-closed flag, and
supported or unsupported operating-point classification.

Rust `AuditUnavailable` and Go no-recent-network-activity timeout remain
distinct typed outcomes. They are also distinct from protocol correctness
failures. Evidence-integrity `PASS` at 640 streams requires explicit
fail-closed behavior and one terminal record for every attempt; it does not
require successful admission or payload completion.

## RED-first integrity contract

Before harness implementation changes, focused tests must fail for the
missing behavior and then pass after minimal changes. Tests cover:

1. no candidate acceptance from one run;
2. one failing confirmation invalidates a candidate;
3. each 90% cell derives from the same path's accepted capacity;
4. a failed 90% cell forces re-evaluation;
5. absolute open-loop offered load remains visible under backlog;
6. scheduler lag and backlog are measurable;
7. memory samples cannot silently disappear;
8. warm-up exclusion follows the frozen phase rule;
9. memory trends use only post-warm-up samples;
10. allocator steps are not automatically leaks;
11. every 640-stream attempt emits typed raw evidence;
12. unsupported-limit outcomes differ from protocol correctness failures;
13. all failed requests remain represented;
14. summaries regenerate from raw evidence;
15. checksum verification detects mutation; and
16. existing protocol and security semantics remain untouched.

Tests assert behavior through generated raw records and regenerated summaries,
not source-text presence.

## Reporting and classification

The existing performance report and machine-readable analysis are updated by
an additive completion report that clearly separates prior accepted evidence,
new evidence, superseded candidates, accepted capacities, formal cells,
explanatory backlog observations, memory classifications, and typed 640-stream
outcomes. Raw counts and paths are explicit.

`COMPLETE_LOOPBACK_BASELINE` is emitted only when all three independent
capacities have reproduced, all formal cells are valid, the 90% criterion
reproduces, all three paths have defensible `PASS` or `FAIL` memory results,
typed 640-stream integrity passes, and the full evidence, security, and
regression verification succeeds. Any unresolved condition retains
`PARTIAL_BASELINE` with the exact blocker.

## Non-optimization boundary

The tranche cannot optimize queueing, scheduling, allocation, GC, Rust or Go
memory use, F75, federation, channel or stream admission, QUIC, serialization,
batching, caching, or concurrency limits. It cannot change frozen protocol or
security behavior. A benchmark-driver correctness defect may be fixed only
when a RED test demonstrates that the measurement method is scientifically
wrong. Observed bottlenecks are reported under `Candidate optimization
opportunities — NOT IMPLEMENTED` and remain unmodified.

## Validation boundary

After focused RED/GREEN cycles and evidence generation, validation includes
the full Python suite, focused performance tests, Rust tests, Rust formatting,
Clippy with `-D warnings`, Go tests, Go vet, Go module verification,
federation tests, interoperability and conformance, security regressions,
Ruff, raw-to-summary evidence regeneration, manifest and checksum
verification, prior-evidence immutability verification, and `git diff
--check`. Rust builds use a writable `CARGO_TARGET_DIR` outside OneDrive.

No push, merge, rebase, or `main` modification is part of this design.
