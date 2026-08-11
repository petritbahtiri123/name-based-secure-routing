# P2B Stream-Establishment Profiling Design

## Scope

P2B profiles the frozen new-Application-Stream lifecycle only. It does not alter protocol, security, replay, admission, StreamGate, audit, concurrency, serialization, Quinn, Tokio, buffers, or production behavior. P2A and all earlier evidence remain immutable. The existing accepted rates are reused: Direct 2,375 and 4,275 operations/second; Rust NBSR 843.75 and 1,518.75 operations/second.

## Measurement architecture

Extend the disabled-by-default `benchmark-harness` feature with a fixed-cardinality aggregate profiler. It has a closed phase enum, count/total/min/max/log2 histogram buckets, success/failure counts, and no identifiers, payloads, keys, tickets, or retained object references. Disabled calls execute the existing path without timing. Enabled calls time source orchestration, destination control/admission, internal `authorize_stream_open` subphases, Quinn open/accept, first exchange, and cleanup. Snapshots are emitted once per process.

The profiler records phase wall time, not exclusive CPU time. Existing Windows process sampling supplies measured-window CPU and memory. CPU categories are derived only where phase ownership is explicit; no stack-sample precision is claimed. WPR is installed, but no WPA/xperf/PerfView analyzer is available. Allocation counts/bytes and allocating stacks are therefore unavailable unless a safe existing mechanism emerges during implementation; no allocator replacement or invasive profiler will be introduced.

## P1F-safe profile windows

Each Transport Session shard carries at most 8,000 successful lifecycle operations, below the accepted 10,000 replay cap. A logical 180-second profile run is the aggregate of consecutive shards. Direct uses the same operation-count shard boundaries and lifecycle semantics. Session setup is reported separately and excluded from lifecycle phase totals. No `OverCapacity` result is expected or accepted.

## Runs

First run a 30-second instrumentation smoke. Observer effect uses three disabled/enabled paired 30-second logical cells per path at 50% load, with identical sharding. It passes when median throughput degradation is at most 3%, median p99 degradation at most 5%, and additional errors are zero.

Authoritative profiles use three 180-second logical runs for Direct and NBSR at 50% and 90%. Up to two repeats are permitted only when attribution conflicts or noise prevents a conclusion. Payload remains 1 KiB and the existing session/channel reuse plus new-stream lifecycle is unchanged.

## Attribution and serialization

Source ordering is preparation/authorization, control write, serialized admission wait/read/decode/confirm, Quinn `open_bi` and ID validation, first exchange, release. Destination ordering is control read/decode, session binding/replay/sequence/channel checks, `prepare_open` including StreamGate and P1F preflight, audit, replay/state commit, response construction/confirm/write, Quinn `accept_bi` association, exchange, release/state removal.

The runner records in-flight behavior and source/destination task structure. The current benchmark has one source loop and one destination control consumer per session; this is measured/documented, not changed.

## Integrity

Tests prove the phase registry is closed, disabled mode has no records, timer pairs reconcile, success/failure counts remain distinct, snapshots contain no sensitive/high-cardinality fields, manifests freeze the lifecycle model, and Direct/NBSR outcomes are unchanged. Evidence is additive under `evidence/performance/stream-establishment-profile-p2b/` with raw shard output, manifests, observer evidence, analysis, report, and checksums.

## Alternatives

1. WPR ETL sampling: rejected as primary because the environment lacks a supported analyzer and allocation-stack workflow.
2. Per-operation trace events: rejected because cardinality and I/O observer effects would be high.
3. Aggregate feature-gated timers plus existing process sampling: selected because it is bounded, auditable, and supports the observer-effect gate.
