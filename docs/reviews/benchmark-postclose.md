# Future post-close archive owner adapter (not installed in a campaign)

`finalize_after_owner` is an opt-in adapter for a future reviewed outer owner.
Construction/import is inert. Its caller supplies the bounded owner, run-bound
receipt reader, expected remote unit/cgroup identities and atomic space-reservation
context. The adapter first finishes the owner, rejects unconfirmed terminal state,
then checks parent/capture/remote/publisher closure before reserving and archiving.
It never launches a benchmark, polls a dashboard or deletes/moves original evidence.

The observed RUN1709 task-local parent writes its final receipts while its own
launcher is still alive. Therefore this adapter must be invoked OUTSIDE that
launcher, after its outer owner has actually reaped it. RUN1709 and its source
pins remain untouched. The current outer owner is a tool session, not a tracked
production wrapper, so no campaign hook is installed by this change.

## Explicit caller trust boundaries

The production owner must already implement bounded lifetime and full process-tree
ownership. A guessed PID or booleans copied from an older receipt are not proof.
The receipt reader must bind all bytes to the current immutable run and expected
owner identities, including the separate publisher or explicit no-dispatch proof.
The adapter validates their contents, not authenticated provenance or remote truth.
The reservation context must atomically account historical roots and concurrent
external obligations, hold admitted space throughout execution, and retain/account
actual archive or partial-file usage when releasing the reservation. The adapter
does not implement a cross-process ledger, filesystem disk-free accounting, or a
preemptive compression timeout. The future owner must bound archive execution too.

Fresh admission checks use strict150MiB, observed accounting no older than5seconds,
maximum ZIP bytes, full input-byte restore capacity and explicit metadata capacity.
No compression ratio is assumed. No restore/pruning is performed; the reserve
merely leaves capacity for a separately reviewed restore workflow. Missing or
unconfirmed closure, accounting or publisher evidence prevents an archive attempt.
Static explicit inventory excludes operational databases/WAL/SHM/dashboard,
lock/pending paths and source manifests. Exclusions are conservative path checks,
not a substitute for the caller's closed-file allowlist.

Invalid measurement/exit1 can be archived after confirmed closure. Returned
measurement status remains INVALID_PARTIAL; ZIP success does not promote it.
Source and receipt persistence/cancellation after return remain owner concerns.
Failed archives retain all originals and any partial ZIP for diagnosis.

## Offline verification

28 tests under tests/ci cover real local single-child terminal ordering, invalid
measurement retention, unresolved parent/readers/publisher, remote identity/error,
strict/fresh reservations, protected paths, duplicate archive and injected archive
failure. The child fixture is idle, has no sockets/descendants and uses bounded
wait/kill cleanup. This is not native Windows Job/process-tree qualification.
Cloud tests and scoped Ruff pass; independent review and native platform checks
remain required before deployment. Existing python-core discovers tests/ci;
publication must retain these tests in the same change. No paid API calls.

## 2026-11-18 restore follow-up (offline, unpublished)

The helper now offers `restore_verified_zip`: a separate explicit restoration to
an exclusively created directory, with pinned archive digest, bounded output,
fsynced extracted files and independent reread/hash checks of persisted bytes.
It retains both originals and partial restore outputs. It does not authorize or
perform pruning. Invalid benchmark status and the Performance Lab are unchanged.

All 52 isolated tests pass (14 existing archive, 28 adapter, 10 restore); Ruff
passes. Independent review found no blocker under the documented quiescent writer
and directory contract and requested two regressions, now passing: archive
replacement between validation and reopen creates no destination; corrupting a
restored file before reread produces no success receipt. Native Windows tests,
full repository/hosted CI, real outer-owner/ledger wiring, and archive-backed
Performance Lab download proof remain outstanding. RUN1709 was not modified.

Deletion remains deliberately unavailable until consumer compatibility is proven:
removing a source used by the dashboard or raw download is not safe merely because
its ZIP can be extracted. No actual evidence was pruned by this change.

## Consumer compatibility fixture proof

Two added tests in tools/performance-lab/tests/test_external_archive_lifecycle.py
exercise the existing app in TestClient with temporary directories only. The
first imports a synthetic snapshot, ZIPs/restores its external campaign copy,
removes that test-only campaign copy, and proves unchanged /api/v1/runs and exact
bytes/SHA256 at /api/v1/artifacts/{sha}. The second proves deleting the Lab's own
content-addressed raw file breaks download (404), even with a campaign ZIP.
Therefore any eventual prune allowlist MUST exclude the entire operational Lab
store, inbox and source paths still consumed by readers. ZIP existence does not
make the Lab archive-aware. No dashboard change is necessary for pruning an
independent, already-ingested campaign copy; active source readers must still be
closed. These tests are selected by the existing Performance Lab tests-directory
workflow and do not require importing root scripts into its sparse checkout.

Both fixtures passed on the local cloud runtime (using existing FastAPI/HTTPX;
a Starlette deprecation warning is present). Store implementation was checked
against the current development branch and matches the local source used.
This is not a full pinned-dependency hosted CI pass or a deployed browser test.

Native Windows validation is blocked in the supported Library transfer path:
current library_file_transfer.py invokes os.setxattr, unavailable on Windows.
No helper modification, metadata omission or alternate transfer was used.
Windows execution itself works via the reviewed escalated path; the default
sandboxed MSIX PowerShell launcher fails before command execution. No installation
or security-setting changes were made. The source bundle remains available in
Library. No native test pass is claimed.
