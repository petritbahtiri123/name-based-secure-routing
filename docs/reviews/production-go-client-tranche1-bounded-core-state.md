# Production Go Client Tranche 1: Bounded Core State Closure

## Closure result

**PASS** for the bounded Tranche 1 scope at commit `e64565de6fb9335b431a374eb68b886d14fe5479`.

This is a closure result for the in-memory `client/nbsr-go-client/internal/corestate` package, not a production-readiness result. Benchmarks are local observations only: **BASELINE ONLY — NOT ACCEPTANCE CAPACITY.**

The tranche does not implement or claim QUIC, TLS, RouteGrant acquisition, NBSR Authority Control Plane transport, resolver/DNS integration, Synthetic-IP OS allocation, TUN, WFP, eBPF, packet interception, proxy listeners, platform adapters, Transport Session establishment, Service Channel wire admission, Stream Credit framing, P2D changes, rotation, active/standby behavior, revocation-feed transport, key enrollment, live-state persistence, UDP/IP, cross-edge migration, or performance optimization.

## RED closure evidence

The review was first created with a pending result on every command and semantic gate. The exact Task 9 PowerShell RED check exited `1`; a separate direct `rg` invocation printed 32 pending occurrences. No acceptance command had been run when that RED state was recorded.

## Acceptance command record

### Go module gates

Run from `client/nbsr-go-client` with Go `1.26.5` at `C:\Program Files\Go\bin`; the race gate additionally used GCC `16.2.0` at `C:\msys64\ucrt64\bin`.

| Command | Observed result |
| --- | --- |
| `gofmt -w internal/corestate/*.go` | **PASS.** The exact plan command text was executed under Git Bash, which expanded the wildcard, and exited `0`. For shell-specific evidence, the same text under PowerShell did not expand the wildcard and exited `2` with `CreateFile internal/corestate/*.go: The filename, directory name, or volume label syntax is incorrect.` A separate sorted PowerShell enumeration of the exact 19 `.go` files also exited `0`. Neither successful invocation produced a corestate diff. |
| `go test ./... -count=1` | **PASS**, exit `0`: `ok nbsr.local/client/nbsr-go-client/internal/corestate 0.544s`. The package lists 92 top-level tests. |
| `go test -race ./... -count=1` | **PASS**, exit `0`: `ok nbsr.local/client/nbsr-go-client/internal/corestate 1.652s`. |
| `go vet ./...` | **PASS**, exit `0`, no diagnostics. |
| `go test ./internal/corestate -run 'Test.*(Capacity\|Bytes\|Teardown\|Lifecycle\|Invariant\|Handle\|Duplicate\|Conflict\|Isolation)' -count=1` | **PASS**, exit `0`: `ok nbsr.local/client/nbsr-go-client/internal/corestate 0.500s`; the regex selects 46 top-level tests. |
| `go test ./internal/corestate -run '^$' -fuzz '^FuzzBoundedLifecycle$' -fuzztime=10s` | **PASS**, exit `0`: 165 baseline inputs, 9,510 executions, 2 new interesting inputs, package time `11.648s`; no panic or reported invariant failure. |
| `go test ./internal/corestate -run '^$' -bench '^BenchmarkBaselineOnly' -benchmem -count=3` | **PASS**, exit `0`: six baseline-only benchmarks, three observations each, package time `23.666s`. |

### Repository integrity gates

Run from repository root with Python `3.14.6` and Ruff `0.11.13`.

| Command | Observed result |
| --- | --- |
| `git diff --check` | **PASS**, exit `0`, no diagnostics. |
| `git status --short` | **PASS**, exit `0`; before final review update it listed only `?? docs/reviews/production-go-client-tranche1-bounded-core-state.md`. `gofmt` changed no Go source. |
| `$planCommit = git log -1 --format=%H -- docs/superpowers/plans/2026-08-14-production-go-client-tranche1-bounded-core-state.md; if ([string]::IsNullOrWhiteSpace($planCommit)) { throw "plan baseline is not committed" }` | **PASS**, exit `0`; derived `10f6b72382d95a1ef4967479145eda17f497b9d0`. |
| `git diff --name-only $planCommit` | **PASS**, exit `0`; committed changes are `client/nbsr-go-client/go.mod`, the 19 `internal/corestate/*.go` files, and the Task 6 generation-ownership supplement. The untracked closure review is additionally reported by `git status`. |
| `git diff --exit-code $planCommit -- interop/nbsr-go-peer crates/nbsr-transport docs/protocol vectors evidence` | **PASS**, exit `0`, no output. |
| `python -m pytest tests/performance/test_session_rotation_model.py tests/test_p2d_stream_credit.py -q` | **PASS**, exit `0`: `32 passed in 4.93s`. |
| `python -m ruff check .` | **PASS**, exit `0`: `All checks passed!` |
| `git rev-parse main` | **PASS**, exit `0`: `1938154d498b32d81a3564319969430644e8a688`. |
| `git rev-parse origin/main` | **PASS**, exit `0`: `1938154d498b32d81a3564319969430644e8a688`. |

## Changed-path and protected-authority audit

- The plan-derived baseline is `10f6b72382d95a1ef4967479145eda17f497b9d0`.
- The two post-plan non-client commits are the human-authorized documentation exceptions `290fd030cb48d391c55cedabd7eaaa95ed835763` and `fd1664f1903d875e23bd59a2c7bbc6dd08809107`. Both modify only `docs/superpowers/specs/2026-08-14-production-go-client-task6-close-generation-ownership-supplement.md`.
- The original immutable plan and the Task 6 supplement have no working-tree diff.
- `interop/nbsr-go-peer`, `crates/nbsr-transport`, `docs/protocol`, `vectors`, and `evidence` have no diff from the plan baseline.
- Local and remote `main` are equal at the required protected SHA. The working branch remains `codex/nbsr-v3-wp0-wp1`; no branch switch, commit, merge, rebase, or push was performed for this closure run.

## Semantic acceptance

- **PASS — bounded entries and logical bytes.** Generation, mapping, service, and stream entry tests cover one below, exact, and one above; mapping, service, and stream byte tests cover the same boundary. Checked arithmetic and configured field lengths fail closed.
- **PASS — mapping lifecycle.** Typed conflict rejection, exact expiry, acquisition/release, live-reference rejection, removal, ID exhaustion/non-reuse, copied ownership, observer ordering, and exact accounting are covered by the full suite.
- **PASS — service handles.** `ServiceHandle` is a four-byte `uint32` with zero invalid. Generation-local namespaces start independently, allocation is monotonic, removed handles are not reused, failed inserts do not consume a handle, and `MaxUint32` transitions to fail-closed exhaustion.
- **PASS — digests are not authority.** Services are keyed by generation-local handle and reverse-indexed by generation plus `ChannelID`; tests prove stable service and RouteGrant digests neither collapse nor authorize distinct bindings.
- **PASS — streams remain pinned.** The key is the exact `(TSGeneration, ServiceHandle, StreamID)` tuple. `StreamID` remains opaque, including valid zero, and tests cover generation/service pinning and key isolation.
- **PASS — atomic typed duplicate decisions.** Mutations and duplicate checks occur under the store mutex and return typed `StateError` codes; concurrent duplicate testing observes one winner with exact accounting under the race detector.
- **PASS — teardown.** Service and generation teardown remove owned streams and reverse-index state, reconcile counters and bytes, preserve unrelated services and mappings, reject stale generation use, and do not resurrect state.
- **PASS — deterministic and concurrent stress.** The full suite includes the deterministic property corpus and exact 4,096-operation population, while the race run covers bounded concurrent mapping, service, stream, and teardown interactions.
- **PASS — fuzz.** The required ten-second fuzz invocation reported no panic, accounting underflow/overflow, handle reuse, resurrection, or capacity breach.
- **PASS — bounded implementation surface.** Production state consists of limit-checked maps. The temporary mapping-expiry removal slice is bounded by `MaxMappings`; invariant scratch state is bounded by `MaxServices`. Production contains no goroutine start, queue, worker, retry list, or cleanup backlog.
- **PASS — logical bytes are not heap bytes.** Each registry has deterministic logical-cost accounting that reconciles against `Usage`; package documentation explicitly states that these values are not heap allocation limits.
- **PASS — excluded surfaces absent.** The Go module has no external dependency declarations and the production package contains only local state/lifecycle behavior. Narrow source search found no excluded network, OS interception, persistence, rotation, or migration implementation.
- **PASS — benchmark claim boundary.** All six benchmark names begin `BenchmarkBaselineOnly`; each exercises a fixed bounded fixture and sets no target, threshold, or acceptance assertion.

## Local benchmark observations

These values are measurements from this Windows/amd64 host only. They are not acceptance targets, capacity claims, production estimates, or cross-host comparisons.

| Benchmark | Three observed ns/op | B/op | allocs/op |
| --- | ---: | ---: | ---: |
| Mapping lookup | 50.87, 51.02, 50.34 | 16 | 2 |
| Mapping insert/remove | 518.9, 522.5, 525.3 | 32 | 4 |
| Service lookup | 66.77, 67.28, 66.56 | 16 | 1 |
| Service insert/remove | 1122, 1120, 1130 | 192 | 3 |
| Stream lookup | 58.75, 58.71, 58.84 | 0 | 0 |
| Stream insert/remove | 1115, 1110, 1118 | 0 | 0 |

Environment emitted by Go: Windows/amd64, Intel Core i5-10210U CPU @ 1.60GHz.

## Final closure

All Task 9 acceptance commands and semantic gates are recorded above from fresh local execution. There is no product-test failure or inconclusive gate. No Tasks 1–8 behavior changed during closure, and no Task 10 work was started.
