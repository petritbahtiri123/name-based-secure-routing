# NBSR Performance Task P1E — Active/Standby Session Rotation

## Executive summary

**Outcome C — CODE-LEVEL PROTOCOL BLOCKED.** Production code did not change. No fix was kept or reverted, replay memory is not hard-bounded, and no performance impact was measured.

The approved ownership model resolves who should own rotation, but the repository has no production Go client/agent to implement it in and no existing live fresh-RouteGrant acquisition contract to reuse. The only wire-capable Go component is the explicitly standalone interoperability/benchmark peer; it reads pre-generated RouteGrant-bearing CBOR files. Core v0.2 has no grant-acquisition exchange. Inventing a new production API or wire exchange is outside the frozen semantics and triggers the P1E implementation stop.

## Git boundaries

- Branch: `codex/nbsr-perf-p1e-active-standby-session-rotation`
- Base SHA: `611e8287e9785513cbd021aefedeee0364353745`
- P1D base: `a13ead66e65896260a44da19da0ae27b0c98cd96`
- Final SHA: recorded in the final handoff because a commit cannot contain its own SHA
- Remote `main`, pre/post: `1938154d498b32d81a3564319969430644e8a688`
- Remote accepted branch `codex/nbsr-v3-wp0-wp1`, pre/post: `4e25ee026618a502327331f352d90e26d29284e3`
- Push/force-push/pull/merge/rebase: none
- Final status: required clean after local Outcome-C commit

## Architecture implemented

No production architecture was implemented.

The approved target remains:

- Go client/agent owns fresh RouteGrant acquisition, ACTIVE/PREPARING/READY/DRAINING generations, atomic new-flow selection, retry, and cross-generation revocation.
- Rust destination owns session-local replay enforcement and the hard replay cap.

The current repository instead contains only:

- `interop/nbsr-go-peer`, a standalone test/benchmark peer that consumes filesystem fixtures and sequentially opens configured connections; and
- `verifiers/federation-go`, an offline Federation package verifier.

No production Go cache/session owner, authority provider, or application-facing selector exists.

## Security contract

Existing frozen behavior is unchanged:

- committed stream replay remains rejected for the full Transport Session;
- old RouteGrant, channel, request, sequence, resume, exporter, and connection authority cannot authorize a fresh session;
- same numeric stream IDs may recur only in independently authorized sessions;
- revocation remains terminal under existing channel/session rules;
- existing capacity errors remain fail closed;
- failed pre-commit stream admission causes no replay commit or application payload exposure.

The requested cross-generation behavior was not implemented, so no claim is made for atomic cutover, multi-generation revocation, failed rotation, or capacity-triggered fresh-session retry.

## Configuration

- Client proactive rotation threshold: not added.
- Destination hard replay limit: not added.
- Validation rules/defaults/benchmark overrides: not added.

Choosing values before an implementable production ownership/authority path exists would create configuration for an incomplete mechanism.

## Production files changed

None.

Added files are limited to the P1E plan, read-only feasibility evaluator, its tests, and additive evidence.

## TDD evidence

- RED: `python -m pytest tests/performance/test_p1e_implementation_gate.py -q` failed collection with `ModuleNotFoundError` because the gate evaluator did not exist.
- GREEN: 4/4 P1E gate tests passed after the minimal repository evaluator was added.
- Combined P1C/P1D/P1E model/gate suite: 22 passed, 0 failed.

The P1E tests derive results from actual Go module/file inventory, Go QUIC calls, fixture reads, Core message constants, and Rust admission/error symbols.

## Server hard-bound proof

Not implemented and therefore not proven.

- Configured limit: none
- Maximum observed entries/capacity: not measured
- Over-limit rejection/no mutation/no upstream effect: existing insertion point traced, not implemented
- Malicious non-rotating client: not run

The safe insertion point is `ChannelStreams.prepare_open`, using existing `StreamReject::OverCapacity` before commit. This does not require a wire change, but a Rust-only cap is not the authorized coordinated production fix.

## Go rotation proof

Not eligible.

- Generations/cutovers/drains: 0
- Fresh authority acquisitions: 0
- Failed candidate tests: not applicable
- Selector proof: absent

The interoperability peer's sequential lifecycle connections are benchmark orchestration, not ACTIVE/STANDBY production ownership.

## BEFORE vs AFTER

No AFTER implementation existed; all five pairs were ineligible.

| Pair | Throughput | p50/p95/p99 | CPU | WS/private | Replay entries/capacity | Errors | Rotations |
|---:|---|---|---|---|---|---|---|
| 1 | N/A | N/A | N/A | N/A | N/A | N/A | 0 |
| 2 | N/A | N/A | N/A | N/A | N/A | N/A | 0 |
| 3 | N/A | N/A | N/A | N/A | N/A | N/A | 0 |
| 4 | N/A | N/A | N/A | N/A | N/A | N/A | 0 |
| 5 | N/A | N/A | N/A | N/A | N/A | N/A | 0 |

Paired deltas: not measured. No baseline value is extrapolated into an AFTER claim.

## Long-session validation

Not run because short validation was ineligible. Duration, operations, rotations, simultaneous generations, replay high-water, process-memory shape, errors, and cleanup are all unmeasured. Current replay growth remains history-linear within one long-lived session and releases when `ControlSession` is destroyed.

## Security/regression tests

Fresh results:

- P1C/P1D/P1E Python models/gates: 22 passed, 0 failed in 4.43 seconds.
- P1E gate alone: 4 passed, 0 failed.
- Independent Go wire peer: 41 passed, 0 failed; all six tested packages passed; `go vet ./...` passed.
- Focused Rust replay/session/channel/stream/drain/resumption: 61 passed, 0 failed.
- Broader serial Rust suite: 142 passed, 0 failed.
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets -- -D warnings`: exit 0.
- Federation Go verifier: 72 passed, 1 failed (`TestCheckedInPackage`: `untrusted manifest digest`). The identical failure reproduced in the untouched P1D worktree and is baseline drift; no frozen manifest or verifier constant was changed.
- One orchestration command initially found no Python tests because it ran from the nested Go module; corrected root/module-specific commands produced the results above.

## Acceptance gate

### Security

- All replay tests pass: PASS for unchanged production/model.
- Cross-generation authority tests pass: NOT IMPLEMENTED.
- Revocation tests pass: PASS for existing single-session behavior; cross-generation NOT IMPLEMENTED.
- No replay false accepts: PASS for existing behavior/model.
- No invalid authority resurrection: PASS for existing behavior/model.
- Server fail closed at new hard limit: FAIL, no new limit.

### Memory

- Entries cannot exceed configured hard bound: FAIL.
- Non-rotating client cannot break new bound: FAIL/not tested.
- Go client releases old replay state: FAIL/not implemented.
- No retired-session accumulation: INCONCLUSIVE.
- Long run bounded/sawtooth: INCONCLUSIVE.

### Performance

- Throughput regression <=5%: INCONCLUSIVE.
- p99 regression <=5%: INCONCLUSIVE.
- Zero unexpected protocol errors: PASS only for unchanged focused suites.
- No unexplained CPU regression: INCONCLUSIVE.
- Material memory-safety benefit: FAIL.

### Correctness

- Relevant independent Go peer tests: PASS.
- Relevant Rust tests: PASS.
- Full relevant regression has no new failures: PASS; the only Go verifier failure is reproduced at P1D.

Overall KEEP gate: **FAIL / no implementation eligible**.

## Evidence integrity

- Evidence root: `evidence/performance/active-standby-session-rotation-p1e/`.
- P1A tree unchanged: `74caa77ae79cbcb4e0b4a53d95352df3c198aaf1`.
- P1B tree unchanged: `8b8893dd5347338c8e220b7ede278ba7b15abdbe`.
- P1C tree unchanged: `5fad03f39f242ce70141f6e2b35e4e7a4795d21b`.
- P1D tree unchanged: `63446f0dd6190bf116afd662f809c5baa10fee34`.
- P1E checksums cover all evidence files except the checksum manifest itself.
- No P1E large/raw artifacts were generated; no new Git LFS object is required.

## Remaining risks

1. No production Go client/agent component exists in the repository.
2. No live fresh-RouteGrant acquisition API or Core exchange exists.
3. Application ownership scope, authority-provider trust boundary, and revocation feed remain undefined at code level.
4. Rust destination replay memory remains unbounded by committed history within one session.
5. Federation Go verifier contains pre-existing checked-in manifest digest drift.

## Final conclusion

**NOT ACCEPTED.** The original Rust destination replay-memory problem is not fixed or hard-bounded. The coordinated implementation cannot be expressed from current repository interfaces without inventing the production Go authority acquisition contract or a new wire exchange.

## Recommended next task

Define and freeze exactly one **production Go client/agent package plus local fresh-RouteGrant authority-provider API**, including TS-specific key binding, expiry/revocation, cancellation, retry, and application ownership scope. Prefer a local API contract if authority already exists outside the transport; allocate new wire semantics only in a separately approved protocol task.

Do not start implementation or further replay optimization until that contract is frozen.
