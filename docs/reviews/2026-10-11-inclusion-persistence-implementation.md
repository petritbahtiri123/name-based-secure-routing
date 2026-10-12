# Inclusion persistence implementation: local memory scope

INCLUSION-PERSISTENCE-01 was approved for implementation and local tests that
do not change Windows permissions. Implemented `scripts/inclusion_persistence.py`
and `tests/federation/test_inclusion_persistence.py`; no filesystem backend exists.
The coordinator calls the real approved inclusion verifier, stores exact original
R bytes, and retains canonical event bindings, markers and checkpoint floor.
The existing federation snapshot schema and private writer are unchanged.

The closed separate codec binds profile/amendment, injected configuration
reference, transaction predecessor and full safety state. It reuses the existing
snapshot byte ceiling and aggregate record bound. Repository operations require
backend ownership, exact independently supplied restore digests, and complete
watermark-first then primary replacement. Write or post-write ownership-release
failure latches the instance unavailable. Re-entrant callbacks cannot reset that
latch. Reopening requires a fresh instance and the exact permitted candidate;
hashes and local ordering never establish fresh authority.

## Measured results

Final focused run: **255 passed**, no skips or deselections, 5.47 seconds pytest
time (6.85 seconds supervised). Breakdown: 51 persistence, 76 inclusion-v2,
123 neighboring conformance/witness/transparency/revocation tests, three pure
store tests, and two CI-selection checks. The explicit `inclusion-persistence-local`
CI command selects the memory suite. This is not a hosted CI result.

Ruff check passed for both new files plus the touched CI source/tests; both new
files formatted. Historical inclusion implementation and vectors were not edited.
Independent scoped review found one lock-release failure boundary, fixed after
three failing regressions. A further same-instance re-entrancy regression failed
before the tracking guard was added. Final independent review found no blocker;
the reviewer did not independently rerun tests.

Retained failed/intermediate runs: missing-module RED collection error; first
implementation run 13 passed, one failed request-order comparison and four pytest
setup errors caused by an oversized auto-generated parameter ID on Windows;
corrected stable parameter IDs and canonical returned ordering; 16 passed;
expanded 47 passed; release RED three failed/47 deselected; release GREEN 51
passed including one CI check; re-entrancy RED one failed/50 deselected; final
255 passed. Initial lint found four E731 lambda assignments in test code; corrected
to functions. These outcomes are retained, not counted as successful validation.

## Evidence limits and next gate

The memory backend models atomic replacement and deterministic before/after
replacement failure. Tests cover malformed encoding, missing/corrupt/oversized
copies, recovery repair, retained bindings, terminal rejection, capacity rejection,
cooperating-instance exclusion, stale ownership and joint-file rollback against
an independent expectation. They deliberately also demonstrate that a supplied
old expectation allows an old internally valid snapshot: no malicious-host
rollback resistance is claimed.

No filesystem, ACL, real lock-file, flush/fsync, partial disk write, reparse/alias
validation or power-loss tests ran. The storage protocol describes a future
adapter; memory faults are not evidence of those operating-system behaviors.
Existing writer helpers were not called or monkeypatched. No keys were generated,
no sockets/containers started, no installation, activation, commit or push.

Next integration gate is an explicitly authorized fresh temporary-root filesystem
adapter/test slice under the action-time ACL proposal in the approved design.
No root has been created or ACL action requested in this iteration. Production
trust/provenance and power-loss durability remain separate unresolved gates.
Runtime/live remain false; Stage 3 remains partial. Source snapshots, exact
commands, resource limits/results, review and cleanup are in the adjacent manifest.
