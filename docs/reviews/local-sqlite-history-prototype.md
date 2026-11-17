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
