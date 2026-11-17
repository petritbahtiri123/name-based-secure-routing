# Local SQLite history prototype: coverage and limits

This adapter is local conformance only, not a production authority/history
provider. It consumes the existing Storage/Repository interface and normal-v2
signed-fixture verifier. No wire, registration, enrollment, threshold or active
work enforcement changes are made. The offline milestone baseline remains 2/10;
this prototype does not close Stage 3.

## Scope

Explicit create refuses overwrite; reopen never bootstraps a missing database.
SQLite BEGIN IMMEDIATE serializes cooperating connections and commits primary
and watermark together. Trusted private directory and correct SQLite/OS behavior
are preconditions. This is not hostile-path hardening or a process-wide lease.
External expected digest, identity and time remain synthetic caller inputs.
Rolling back both database and expectation is intentionally shown undetectable.
Restore is not fresh admission. Local persistence is not independent provenance,
complete/current source history, clone exclusivity or Byzantine protection.

## Coverage

The 23 SQLite cases cover signed successor/restart, context substitution,
fixture freshness/anchor/policy refusals, idempotent typed-effect preservation,
external digest mismatch/whole-store rollback limitation, missing storage,
explicit bootstrap, exception atomicity and competing connections. The 8 newer
cases exercise commit-before/after failures, rollback failure and retained lock,
corrupt primary/watermark, exact-expectation repair and missing-watermark refusal.
Failure injection wraps a real SQLite connection; it does not simulate power loss.
Latch assertions disable injected faults and prohibit SQL, preventing a repeated
fault from masking a missing latch. After-commit state is compared with an exact
successor independently computed using the canonical coordinator in another DB.

Controller/emergency runtime, Source Operator/ENROLL, active-work cleanup,
real provisioning/clock/expectation providers, SQLite page corruption, disk-full,
process crash and power-loss recovery are not established by these tests.
Snapshot-byte corruption is not SQLite-file corruption. Instance-local failure
latches are not durable independent rollback protection.

## CI integration and reproduction

The python-core profile explicitly selects SQLite plus canonical memory-neighbor
tests on both existing CI OS targets, and includes targeted lint. The existing
memory-only command remains unchanged. The selection regression lives in
tests/ci/test_sqlite_history_selection.py, already reached by python-core's
tests/ci selection. Federation selection also sees the portable test module;
that duplicate coverage is not another authority mode.

From the repository root with provisioned dependencies:

```sh
python -B -m pytest --collect-only -q -p no:cacheprovider tests/federation/test_local_history_sqlite.py
python -B -m pytest -q -p no:cacheprovider tests/federation/test_local_history_sqlite.py tests/federation/test_inclusion_persistence.py tests/ci/test_sqlite_history_selection.py
python -B -m ruff check --no-cache scripts/local_history_sqlite.py tests/federation/test_local_history_sqlite.py tests/ci/test_sqlite_history_selection.py
```

## Retained validation record, 2026-11-17

Initial isolated version: 15 passed in 1.42s. Revised canonical-layout collection:
23 collected in 0.98s. First integrated execution failed 71/75 because a tracked
registry was sparse-excluded; this setup failure was retained, not discarded.
After materializing exact registry dependencies: 75 passed in 3.06s, targeted Ruff
passed. All execution used bounded Windows Jobs with empty final membership,
reaped parents and closed handles. No sockets/services were started.

That run used the original checkout as a fallback for sparse helper modules,
so it is not standalone-checkout evidence. Subsequent standalone validation: 77
passed in 3.23s with only this checkout on PYTHONPATH; scoped lint passed. Both independent review findings were closed; no new source blocker found. Hosted CI for the preceding 7595e8d
commit is separate evidence and does not validate this patch.

## Process-exit successor

Two additional cases terminate a fixed child after the watermark write before
commit, or after the canonical Repository commit returns. Reopen must preserve
the exact predecessor/successor respectively and reject the other digest.
Child output is one fixed marker; the child starts no descendants or sockets,
waits are bounded and failure cleanup kills/reaps it. This is process-exit
simulation, not power loss or independent provenance. The existing whole-file
CI selection includes these cases without a new workflow.

Local successor validation: 25 SQLite cases collected in 0.67s; the complete CI
contract suite plus SQLite and canonical persistence neighbors passed 140 tests
in 8.96s. Scoped Ruff and diff-check passed. This remains local evidence; hosted
CI must be checked separately for the successor commit.

## Mock connector decision boundary (local validation)

Six parameter cases compose real SQLite restore, the canonical local-v2 verifier,
and the existing synchronous connector control model. A successful load restores
history only. The positive case additionally supplies an independent mock Permission
and revalidates the signed fixture at the decision callback. Negative cases cover
no Permission, expired Permission, stale evidence, wrong expected digest and
new_use=False. The positive case also withdraws new-use eligibility before renewal
and checks that unchanged history cannot restore admission. History bytes remain
unchanged in all cases; explicit stop releases the mock transport ownership.

The Binding and Permission are declared synthetic inputs, NOT identity mappings
or authorization derived from the persisted revocation record. No source-completion
producer, Option C runtime conversion, live registration, concurrent atomic barrier,
real clock or active-child cleanup is implemented. The existing whole-file SQLite
CI command and lint select these cases. On isolated exact-base sources at
81257cc47d2c9c05d45693c78d225f62196278cc, Windows Python 3.14.6 collected
31 SQLite cases, including all six boundary cases. SQLite, canonical persistence,
connector model and CI-selection regressions passed 179 tests in 5.79s after
review hardening; scoped Ruff passed. Hosted CI for this successor remains pending.

Independent review identified that Model's intentional verifier-exception refusal
could hide assertion failures in negative tests. The callback now records results
and errors; checks outside Model require SnapshotRejected only for the wrong
expectation, explicit REJECT/ERR_AUTHORITY for stale evidence, and exception-free
IDEMPOTENT verification for Permission and renewal cases. Binding, session and
unchanged-history observations are checked outside the swallowed-exception boundary.

## Restore and halted connector lifecycle

Two deterministic cases extend the mock decision boundary through Permission or
evidence-freshness loss at renewal, ownership release, idempotent stop, denial of
a new attempt with unchanged history, and a separate positive control requiring
a new session and decision. The original halted model cannot resume even after
fixture inputs recover. Retry delay is zero in these cases, so cooldown cannot
mask a missing halted latch. Assertions remain outside verifier callbacks.

On source materialized from exact 78f442e84efaad6e93d2686c4671262a28578ded
Git tree/blob identities, the SQLite, persistence, connector and CI-selection
suites passed 181 tests in 8.27s; targeted Ruff passed. The existing whole-file
SQLite CI selection includes both cases. An earlier provisional predecessor run
passed 181 tests, but review found the cooldown masking gap; the latest-source
result above includes that correction. This remains synchronous mock coverage,
not real authority provenance, active-child cancellation or Stage 3 completion.
