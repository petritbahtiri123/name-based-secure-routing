# Tranche 2A closure — retained literal RED evidence

## Provenance and limitation

This is an append-only, tracked preservation of the literal RED closure table
that was created before Task 12 acceptance execution. It was retained in the
ignored SDD workspace while the acceptance commands ran and is committed only
after the GREEN closure. It therefore proves the recorded execution order and
the exact template used, but **does not establish prior Git immutability**.

The task environment date was 2026-08-15. The original terminal capture did
not retain a wall-clock timestamp for the RED command; its order is known to be
before every Go acceptance command and before the closure commit whose author
time is `2026-08-15 01:10:47 +0200`.

## Exact pre-execution table/template

The following table is reproduced verbatim in substance and state from the
pre-execution closure record: every acceptance gate was initially marked
`FAIL — not yet executed`, with no prefilled success count.

| Gate | Expected | Observed | Result |
| --- | --- | --- | --- |
| Full Go suite | `go test ./... -count=1` exits 0 with exact package counts | Not executed. | FAIL — not yet executed |
| Race Go suite | `go test -race ./... -count=1` exits 0 | Not executed. | FAIL — not yet executed |
| Go vet | `go vet ./...` exits 0 | Not executed. | FAIL — not yet executed |
| Identity focused tests | Required purpose/signer/identity/workload/TS-proof/local-state tests pass | Not executed. | FAIL — not yet executed |
| Authority verification | Frozen valid fixture passes; malformed and stale inputs fail closed | Not executed. | FAIL — not yet executed |
| Candidate sealing | No exported API or boolean convention seals a provider candidate | Not executed. | FAIL — not yet executed |
| Cache isolation | Full cache key prevents cross-service and cross-TS reuse | Not executed. | FAIL — not yet executed |
| Cache limits | Entry and logical-byte below/exact/above capacity tests pass | Not executed. | FAIL — not yet executed |
| Pending limits | Pending entry/byte and waiter below/exact/above tests pass | Not executed. | FAIL — not yet executed |
| Terminal grant states | Consumed, ambiguous, revoked, expired, stale-checkpoint, and stale-generation grants do not resurrect | Not executed. | FAIL — not yet executed |
| Exact freshness boundary | `now == FreshUntil` fails | Not executed. | FAIL — not yet executed |
| Hot path isolation | Local validation performs no provider call, I/O, wire parse, or background work | Not executed. | FAIL — not yet executed |
| Update ordering | Generation/revocation update rejects stale work under race detection | Not executed. | FAIL — not yet executed |
| Request IDs | 128-bit IDs, conflict rejection, bounded retention, and ambiguity quarantine hold | Not executed. | FAIL — not yet executed |
| Retry | Finite attempts/deadline/backoff/jitter/circuit behavior; no payload retry | Not executed. | FAIL — not yet executed |
| Generation floor | Monotonic signed floor; equal-identical idempotent; equal-conflicting/lower reject | Not executed. | FAIL — not yet executed |
| Cold start | Fresh enrolled-ACP validation required; no live-authority restore | Not executed. | FAIL — not yet executed |
| Durable API boundary | No prohibited authority/transport/cache types accepted | Not executed. | FAIL — not yet executed |
| Fixture provider | Finite deterministic pre-signed input only; cannot mint authority | Not executed. | FAIL — not yet executed |
| Observer privacy | Bounded-cardinality events expose no keys, raw grants, service names, or payload | Not executed. | FAIL — not yet executed |
| Lock callbacks | No provider/verifier/observer/store callback under authority mutation lock | Not executed. | FAIL — not yet executed |
| Bounded resources | No unbounded collection, retry loop, goroutine, or cleanup list | Not executed. | FAIL — not yet executed |
| Fuzz | Ten-second lifecycle fuzz has no panic, breach, resurrection, rollback, or invariant failure | Not executed. | FAIL — not yet executed |
| Benchmarks | Baselines are labelled `BASELINE ONLY — NOT ACCEPTANCE CAPACITY`; no throughput claim | Not executed. | FAIL — not yet executed |
| Corestate freeze | No plan-baseline diff; full tests green | Not executed. | FAIL — not yet executed |
| Protected paths | Interop, federation verifier, Rust, protocol, vectors, and P1F/P2D evidence have no diff | Not executed. | FAIL — not yet executed |
| Scope/import guard | No excluded live wire, resolver, platform, federation, TPM, or WAN/demo implementation | Not executed. | FAIL — not yet executed |
| Repository safety | Diff check, changed-path audit, focused Python tests, and Ruff pass | Not executed. | FAIL — not yet executed |
| Main refs | Local and remote `main` equal `1938154d498b32d81a3564319969430644e8a688` | Not executed. | FAIL — not yet executed |
| Tranche 2B marker | Required marker exists for excluded checkpoint/wire work | Not executed. | FAIL — not yet executed |

## Exact RED command and observed result

```powershell
if (rg -n 'FAIL — not yet executed' docs/reviews/production-go-client-tranche2a-identity-authority-core.md) { exit 1 }
exit 0
```

Observed result: exit code **1**. The PowerShell `if` condition consumed the
`rg` standard output, so the preserved terminal result contains no separately
printed marker lines; the true conditional and exit code are the direct RED
evidence. The marker-bearing table above is the exact state that satisfied the
predicate. No later GREEN result is represented as if it were pre-execution
evidence.

## Execution order

1. Create the closure document with the all-FAIL table above.
2. Run the exact RED command; observe exit 1.
3. Run formatting, Go acceptance, repository, Python, and Ruff gates.
4. Replace pending statuses with observed GREEN evidence and commit the closure
   as `900735078c514d50a690e23ec1242db2b922d981`.
5. Commit this retained evidence append-only after the GREEN closure.
