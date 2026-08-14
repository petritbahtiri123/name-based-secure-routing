# Production Go client — Tranche 2A identity/authority core closure

## Literal RED closure record

This record was created before any Task 12 acceptance command was executed.
The literal RED proof then exited 1 as required; the results below replace the
initial pending state only after the commands in the execution log completed.

| Gate | Expected | Observed | Result |
| --- | --- | --- | --- |
| Full Go suite | `go test ./... -count=1` exits 0 with exact package counts | Exit 0; 522 JSON pass events: authority 311, corestate 150, identity 20, retry 41. | PASS |
| Race Go suite | `go test -race ./... -count=1` exits 0 | Exit 0 for authority, corestate, identity, and retry with the requested process-local MSYS2 PATH. | PASS |
| Go vet | `go vet ./...` exits 0 | Exit 0; no diagnostics. | PASS |
| Identity focused tests | Required purpose/signer/identity/workload/TS-proof/local-state tests pass | Exact focused command exited 0 (identity package). | PASS |
| Authority verification | Frozen valid fixture passes; malformed and stale inputs fail closed | Exact focused authority command exited 0. | PASS |
| Candidate sealing | No exported API or boolean convention seals a provider candidate | Exact focused authority command exited 0. | PASS |
| Cache isolation | Full cache key prevents cross-service and cross-TS reuse | Exact focused authority command exited 0. | PASS |
| Cache limits | Entry and logical-byte below/exact/above capacity tests pass | Exact focused authority command exited 0. | PASS |
| Pending limits | Pending entry/byte and waiter below/exact/above tests pass | Exact focused authority command exited 0. | PASS |
| Terminal grant states | Consumed, ambiguous, revoked, expired, stale-checkpoint, and stale-generation grants do not resurrect | Exact focused authority command exited 0. | PASS |
| Exact freshness boundary | `now == FreshUntil` fails | Exact focused authority command exited 0. | PASS |
| Hot path isolation | Local validation performs no provider call, I/O, wire parse, or background work | `TestNoProviderCall` selector passed in exact focused authority command. | PASS |
| Update ordering | Generation/revocation update rejects stale work under race detection | Race suite exit 0; focused generation selector exit 0. | PASS |
| Request IDs | 128-bit IDs, conflict rejection, bounded retention, and ambiguity quarantine hold | Exact focused authority command exited 0. | PASS |
| Retry | Finite attempts/deadline/backoff/jitter/circuit behavior; no payload retry | Full suite and retry benchmark package passed. | PASS |
| Generation floor | Monotonic signed floor; equal-identical idempotent; equal-conflicting/lower reject | Exact focused `Floor` selector passed. | PASS |
| Cold start | Fresh enrolled-ACP validation required; no live-authority restore | Exact focused `ColdStart` selector passed. | PASS |
| Durable API boundary | No prohibited authority/transport/cache types accepted | Exact focused `NoDurableAPI` selector passed. | PASS |
| Fixture provider | Finite deterministic pre-signed input only; cannot mint authority | Exact focused authority command exited 0. | PASS |
| Observer privacy | Bounded-cardinality events expose no keys, raw grants, service names, or payload | Full authority suite passed. | PASS |
| Lock callbacks | No provider/verifier/observer/store callback under authority mutation lock | Full authority suite and race suite passed. | PASS |
| Bounded resources | No unbounded collection, retry loop, goroutine, or cleanup list | Capacity/coalescing/pending focused selectors passed. | PASS |
| Fuzz | Ten-second lifecycle fuzz has no panic, breach, resurrection, rollback, or invariant failure | Exit 0; 145 baseline corpus entries, 7,555 executions, 154 total interesting inputs. | PASS |
| Benchmarks | Baselines are labelled `BASELINE ONLY — NOT ACCEPTANCE CAPACITY`; no throughput claim | Three-run `BenchmarkBaselineOnly` command exited 0; results retained below as baselines only. | PASS |
| Corestate freeze | No plan-baseline diff; full tests green | Protected-path diff exit 0; corestate full and race package tests passed. | PASS |
| Protected paths | Interop, federation verifier, Rust, protocol, vectors, and P1F/P2D evidence have no diff | `git diff --exit-code` from plan baseline exited 0. | PASS |
| Scope/import guard | No excluded live wire, resolver, platform, federation, TPM, or WAN/demo implementation | Import-token scan found only in-memory `MemoryRegistry` identifiers and one `"quic"` test literal; no implementation import. | PASS |
| Repository safety | Diff check, changed-path audit, focused Python tests, and Ruff pass | `git diff --check` exit 0; Python 32 passed; Ruff reported all checks passed. | PASS |
| Main refs | Local and remote `main` equal `1938154d498b32d81a3564319969430644e8a688` | Both resolved to the required SHA. | PASS |
| Tranche 2B marker | Required marker exists for excluded checkpoint/wire work | This review carries the required exclusion marker below. | PASS |

## Execution evidence

The literal RED command found the initial marker and exited 1 before execution.
The source PowerShell form of the prescribed `gofmt -w internal/.../*.go`
command did not expand native executable globs on this Windows host and failed
with `CreateFile .../*.go`. The same four approved directories were then
explicitly enumerated to `gofmt -w`; it exited 0 and changed only the
three-added/one-removed line wrap in
`internal/authority/concurrency_test.go` (no semantic change).

From `client/nbsr-go-client`, all prescribed Go commands exited 0:

```text
go test ./... -count=1
  authority 0.892s; corestate 0.705s; identity 0.754s; retry 0.570s
go test -race ./... -count=1
  authority 2.046s; corestate 1.480s; identity 1.494s; retry 1.337s
go vet ./...
  no output
go test ./internal/identity -run 'Test(Purpose|Signer|Identity|Workload|TSProof|LocalState)' -count=1
  identity 0.545s
go test ./internal/authority -run 'Test(Verify|Cache|Consumed|Ambiguous|Freshness|Generation|Floor|ColdStart|Coalesc|Pending|Request|NoProviderCall|NoDurableAPI)' -count=1
  authority 0.623s
go test ./internal/authority -run '^$' -fuzz '^FuzzAuthorityLifecycle$' -fuzztime=10s
  authority 11.726s
```

The race command used only this process-local prefix:

```powershell
$env:PATH = 'C:\msys64\ucrt64\bin;C:\msys64\usr\bin;' + $env:PATH
```

Supplemental JSON output for the full suite counted 522 passing test events:
authority 311, corestate 150, identity 20, and retry 41. The regular Go test
output reports package results, not individual test totals; the JSON count is
an observation, not a separately specified capacity target.

The three-run baseline command exited 0. `BASELINE ONLY — NOT ACCEPTANCE
CAPACITY`; no throughput or production-capacity claim follows:

```text
ValidityCheck:    42.75, 43.08, 42.07 ns/op; 0 B/op; 0 allocs/op
CacheLookup:      157.0, 157.3, 157.4 ns/op; 0 B/op; 0 allocs/op
GenerationCheck:  24.90, 24.87, 24.94 ns/op; 0 B/op; 0 allocs/op
FreshnessLookup:  25.16, 25.11, 25.11 ns/op; 0 B/op; 0 allocs/op
RetryDecision:    12.96, 12.98, 12.98 ns/op; 0 B/op; 0 allocs/op
```

From the repository root, the plan baseline was
`0b15dc3a54698854badec99dd55d2ff051c68e82`. `git diff --check` and the
protected-path `git diff --exit-code` both exited 0. The focused Python command
reported `32 passed in 4.73s`; `python -m ruff check .` reported `All checks
passed!`. Both `main` and `origin/main` resolved to
`1938154d498b32d81a3564319969430644e8a688`.

The final Tranche 2A implementation baseline, immediately before this
closure-evidence commit, was `530e19e4001a13e601d60405085e48709b9a3bbf`.
The closure commit SHA is intentionally reported by the final handoff after
the evidence record is committed, avoiding a self-referential commit hash.

## Changed-path audit

The plan-baseline changed-path audit contains only the accepted Tranche 2A
identity/authority/retry package paths listed below. This Task adds this review
and the formatting pass changed only the authority test line wrap described
above.

```text
client/nbsr-go-client/internal/authority/{benchmark_test.go,cache.go,cache_test.go,cbor.go,coalesce.go,coalesce_test.go,concurrency_test.go,cose.go,doc.go,errors.go,fixture_provider.go,floor.go,floor_test.go,freshness.go,freshness_test.go,fuzz_test.go,generation.go,generation_test.go,idempotency.go,idempotency_test.go,manager.go,manager_test.go,observer.go,provider.go,restart.go,restart_test.go,types.go,verifier.go,verifier_test.go}
client/nbsr-go-client/internal/identity/{doc.go,errors.go,identity_test.go,signer.go,signer_test.go,store.go,types.go}
client/nbsr-go-client/internal/retry/{doc.go,errors.go,policy.go,policy_test.go}
docs/reviews/production-go-client-tranche2a-identity-authority-core.md
```

The protected set is empty relative to the plan baseline:
`internal/corestate`, `interop/nbsr-go-peer`, `verifiers/federation-go`,
`crates/nbsr-transport`, `docs/protocol`, `vectors`, and `evidence`.

## Non-claims and retained gaps

TRANCHE 2B — REQUIRES SEPARATE PROTOCOL APPROVAL: live HTTP/1.1 or HTTP/2 ACP
transport; enrollment messages; ACP deterministic-CBOR schemas and registries;
live checkpoint/response COSE; idempotency storage; push/revocation delivery;
and production issuer/profile distribution or ACP authentication wire proof.

Tranche 2A makes no claim of live ACP, resolver/DNS, Synthetic-IP interception,
QUIC/TLS TS establishment, SC/credit/P2D/rotation wire work, platform or TPM
keystores, federation negotiation, operator routing, WAN/demo readiness, or
production performance optimization. The evidence is a local deterministic Go
package/test result, not live-platform, interoperability, capacity, or
production-readiness proof. Future changes require independent scope approval
and fresh evidence.
