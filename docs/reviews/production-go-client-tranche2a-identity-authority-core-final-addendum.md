# Production Go client — Tranche 2A final closure addendum

## Authority and lineage

This append-only addendum supersedes the implementation-SHA reference and the
final evidence-lineage statement in the earlier closure packaging. It does not
rewrite the prior evidence records.

| Record | Commit |
| --- | --- |
| Approved plan baseline | `0b15dc3a54698854badec99dd55d2ff051c68e82` |
| Original implementation/closure parent | `530e19e4001a13e601d60405085e48709b9a3bbf` |
| Original GREEN closure | `900735078c514d50a690e23ec1242db2b922d981` |
| Retained RED evidence | `785ed81768d87414a67b9287dba852a53fed5746` |
| Closure handoff packaging | `3451b61500f38b14ee44fa440875e11594df1f86` |
| **Corrected final implementation baseline** | **`f4e4b60f0caf76658a3ad64a2347c739d2562353`** |
| Protected local and remote `main` | `1938154d498b32d81a3564319969430644e8a688` |

The commit containing this addendum is the externally reported final evidence
commit. Its SHA is intentionally not embedded in its own content, avoiding an
impossible self-reference.

## Final whole-review finding, fix, and re-review

The whole-branch review found two authority-boundary defects after the original
closure:

1. Raw `CheckpointClaims` could cross the authority-verification boundary
   instead of requiring a non-forgeable, sealed `VerifiedCheckpoint` produced
   only after freshness-evidence verification.
2. Completed idempotency records could retain a reservation reference after
   consume, release, quarantine, or invalidation. That broke invariants and
   could turn duplicate terminal requests into false ambiguity.

Commit `f4e4b60f0caf76658a3ad64a2347c739d2562353` fixed both findings. It seals,
copies, and canonicalizes checkpoint state behind private fields and value-only
accessors; rejects the zero checkpoint; carries the real sealed checkpoint
through publication, verification, and restart; and converts completed request
links to a bounded terminal state whenever their reservation terminates.

This addendum is the post-fix re-review. Every exact Task 12 acceptance gate
below passed against `f4e4b60f0caf76658a3ad64a2347c739d2562353` with a clean
worktree before the addendum was created. No further defect was observed in
this bounded acceptance matrix.

## Execution environment

Every Go command used this process-local PATH prefix:

```powershell
$env:PATH = 'C:\msys64\ucrt64\bin;C:\msys64\usr\bin;' + $env:PATH
```

The exact `gofmt` glob command was run through MSYS Bash so the four globs were
expanded exactly as written:

```powershell
gofmt -w internal/corestate/*.go internal/identity/*.go internal/authority/*.go internal/retry/*.go
```

Result: PASS, exit 0, and no source diff.

## Go acceptance evidence

| Command/gate | Exact observed result | Result |
| --- | --- | --- |
| `go test ./... -count=1` | authority `0.835s`; corestate `0.582s`; identity `0.639s`; retry `0.520s` | PASS |
| Supplemental `go test -json ./... -count=1` count | authority 321; corestate 150; identity 20; retry 41; **532 total passing test events** | PASS |
| `go test -race ./... -count=1` | authority `2.011s`; corestate `1.440s`; identity `1.663s`; retry `1.292s` | PASS |
| `go vet ./...` | Exit 0; no diagnostics | PASS |
| Focused identity selector | identity `0.536s` | PASS |
| Focused authority selector | authority `0.620s` | PASS |
| Ten-second `FuzzAuthorityLifecycle` | 166 baseline inputs; 4,159 executions; 1 new interesting input; 167 total; package `11.720s` | PASS |
| Three-run `BenchmarkBaselineOnly` | Command and both packages exited 0 | PASS |

The focused commands were exactly:

```powershell
go test ./internal/identity -run 'Test(Purpose|Signer|Identity|Workload|TSProof|LocalState)' -count=1
go test ./internal/authority -run 'Test(Verify|Cache|Consumed|Ambiguous|Freshness|Generation|Floor|ColdStart|Coalesc|Pending|Request|NoProviderCall|NoDurableAPI)' -count=1
go test ./internal/authority -run '^$' -fuzz '^FuzzAuthorityLifecycle$' -fuzztime=10s
go test ./internal/authority ./internal/retry -run '^$' -bench '^BenchmarkBaselineOnly' -benchmem -count=3
```

## Baseline-only benchmark observations

`BASELINE ONLY — NOT ACCEPTANCE CAPACITY`. These measurements are not targets,
capacity evidence, throughput claims, or production-performance claims.

```text
ValidityCheck:    45.41, 43.35, 42.98 ns/op; 0 B/op; 0 allocs/op
CacheLookup:      178.7, 180.6, 178.9 ns/op; 0 B/op; 0 allocs/op
GenerationCheck:  29.39, 26.39, 26.35 ns/op; 0 B/op; 0 allocs/op
FreshnessLookup:  26.91, 26.85, 26.87 ns/op; 0 B/op; 0 allocs/op
RetryDecision:    12.98, 12.95, 12.97 ns/op; 0 B/op; 0 allocs/op
```

Host observation: Windows/amd64, Intel Core i5-10210U, benchmark suffix `-8`.

## Repository, scope, and protected-boundary evidence

| Gate | Exact observed result | Result |
| --- | --- | --- |
| `git diff --check` | Exit 0 | PASS |
| Plan commit lookup | `0b15dc3a54698854badec99dd55d2ff051c68e82` | PASS |
| `git diff --name-only $planCommit` | Only Tranche 2A identity, authority, retry, and prior closure-review paths; includes the final `authority/final_boundary_test.go` | PASS |
| Protected-path `git diff --exit-code` | Empty for corestate, Go interop/federation, Rust transport, protocol, vectors, and evidence | PASS |
| Prohibited implementation-token scan | Only the in-memory test `MemoryRegistry` identifiers and one `"quic"` test literal; no networking/platform implementation import | PASS |
| Tranche 2B marker scan | Marker present in the original GREEN closure record | PASS |
| Focused Python safety tests | **32 passed in 3.39s** | PASS |
| `python -m ruff check .` | `All checks passed!` | PASS |
| `git rev-parse main` / `origin/main` | Both `1938154d498b32d81a3564319969430644e8a688` | PASS |

The protected comparison remained anchored to the approved plan commit and
covered:

```text
client/nbsr-go-client/internal/corestate
interop/nbsr-go-peer
verifiers/federation-go
crates/nbsr-transport
docs/protocol
vectors
evidence
```

## Non-claims and remaining gaps

This is local deterministic package/test evidence. It is not proof of live ACP
or enrollment transport, HTTP/1.1 or HTTP/2 wire behavior, ACP schema/registry
approval, checkpoint/response COSE exchange, server idempotency storage, push
or revocation delivery, resolver/DNS, Synthetic-IP interception, QUIC/TLS TS,
SC or Stream Credit/P2D wire changes, rotation, platform adapters, TPM/OS
keystores, federation negotiation, operator routing, WAN/demo readiness,
capacity, or production readiness.

Those Tranche 2B and later gaps remain excluded and require separate protocol
approval and fresh evidence. The clean matrix here closes only the corrected
Tranche 2A identity/authority/retry boundary at the named implementation SHA.

## Final lineage clarification

This clarification supersedes the earlier handoff's statement that
`3451b61500f38b14ee44fa440875e11594df1f86` is the externally reported final
packaging commit. That commit remains the historical pre-fix handoff;
`f4e4b60f0caf76658a3ad64a2347c739d2562353` is the corrected implementation;
and `e097027335465db56d22c8a7b45600f44a35cded` is the post-fix acceptance
evidence. The commit containing this clarification is the final local
documentation-packaging commit and is reported externally as the final
local/published SHA. Its SHA is not embedded here, avoiding self-reference.
