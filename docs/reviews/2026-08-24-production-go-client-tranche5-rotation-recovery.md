# Production Go client Tranche 5 rotation/recovery closure review

## Outcome

Implementation and local verification pass. Final tranche outcome is BLOCKED
only on missing real two-generation Go→Rust rotation evidence.

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

The first live-verifier invocation was INCONCLUSIVE because the verifier
expects prebuilt binaries and launch failed with `WinError 2`. Exact-source
Rust and Go binaries were then built in the required external layout; the fresh
rerun passed all seven cases.

## Residual limitation

The live harness has only a single pre-established Transport Session adapter.
It cannot exercise production-manager A→B rotation without a concrete
multi-generation Go QUIC connector/opener. Unit/race evidence proves the local
state machine, and real-process evidence proves unchanged wire behavior, but
those two facts are not represented as end-to-end real rotation proof.

No protocol decision is required and no wire semantics were invented. Closure
must remain blocked until that concrete transport adapter and real lifecycle
case exist.
