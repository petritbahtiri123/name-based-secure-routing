# Production Go client Tranche 5 rotation/recovery closure review

## Outcome

TRANCHE 5 COMPLETE AND VERIFIED.

## Reviewed boundary

The single focused review covered generation count/current uniqueness, draining
admission, descendant binding, replay reset/reuse, application replay, stale
authority activation, trigger escalation, B failure with A draining, finite
drain ownership, pending/orphan state, bounded recovery, lock/I/O boundaries,
teardown races, and prohibited resolver/Synthetic-IP scope.

It found one Critical and four Important defects:

- concurrent cross-key rotations could commit the same generation;
- rotation state capacity omitted stream bytes and lacked a final recheck;
- pending SC creation survived handoff/teardown;
- `FailTransportSession` did not escalate the pending trigger;
- cancellation during SC authority commit could double-close completion state.

Literal regressions reproduced each defect. The fixes add final generation and
state barriers, cancelable generation-local pending channels, trigger
escalation, and post-authority-commit ownership revalidation. The one scoped
re-review found the last commit-race issue; its fix passed focused and race
tests. No further review cycle was run. No Critical/Important finding remains
in the reviewed local boundary.

## Fresh validation

- Go client full tests: PASS.
- Go client UCRT full race: PASS.
- Go client vet: PASS.
- Rust P1F replay focus: 14 passed, 1 ignored soak.
- Rust application stream: 4 passed.
- Rust P2D integration/vectors: 7 + 5 passed.
- Python P2D: 21 passed.
- Existing real Go→Rust P1F/P2D live verifier: 7 cases PASS; artifact at
  `C:\NBSR-build\tranche5-final\live-run\live-result.json`.
- Real Go→Rust A→B rotation verifier: PASS; artifact at
  `C:\NBSR-build\tranche5-closure-b124939\rotation-run\rotation-evidence.json`.

The first live-verifier invocation was INCONCLUSIVE because the verifier
expects prebuilt binaries and launch failed with `WinError 2`. Exact-source
Rust and Go binaries were then built in the required external layout; the fresh
rerun passed all seven cases.

## Final connector/evidence review

The focused review of the new connector and lifecycle evidence found four
Important issues: post-commit SC failure handling, retained connector state,
unsynchronized handle access, and assertion-only pinning/replay evidence. The
fix preserved the committed TS handoff, made SC creation generation-local and
lazy, synchronized handles, purged exact connector ownership, and moved the A
payload exchange after B activation. The scoped re-review found one remaining
Important deadline-cleanup race; the final fix makes transport teardown purge
the cached handle under the connector/handle lock order and adds a deadline
regression. No Critical/Important finding remains after that scoped fix.

## Real lifecycle evidence

A used `[::]:65206->127.0.0.1:65204`; B used the distinct real QUIC transport
`[::]:65208->127.0.0.1:65205`. The manager observed
`1:DRAINING -> 2:CURRENT`, never more than two generations, and rejected C
while A drained. New SC/credit/stream work resolved only to B and every
new-work probe against A was rejected. An A stream admitted before rotation
performed its single payload exchange after B became current, remained pinned
to its original StreamID/connection, and was then closed. A teardown removed
all generation-local state and identity; B remained current and completed a
final payload exchange.

Rust A recorded one correct operation; Rust B recorded two correct operations,
with zero errors. Those exact counts plus post-handoff A I/O demonstrate that
no A application payload was replayed on B. The artifact binds source commit
`b124939de0dc43b1605959421535070b718e8553`, source tree, binaries, readiness,
peer state, and Rust results.

## Residual limitation

Replay-cap replacement was not forced through the real harness because that
would require an impractical cap-sized campaign. Existing focused Go/P1F proof
remains authoritative. No wire semantics were changed, and no Synthetic IP,
resolver, DNS, or proxy work was started.
