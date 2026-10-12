# Deterministic offline authority timer — 2026-10-10

Implemented a bounded, explicitly polled injected-clock adapter over the existing
mock connector model. It consumes only `SimulatedAuthorityEvent` test inputs;
it does not construct trusted receipts or bypass threshold packaging. The approved
connector profile's effective-time/revision/dependency dispatch and accepted
F93/lifetime separation supply the semantics; no new policy was needed.

## Behavior and boundaries

One timer attaches to one exact model owner/session and fixture context/dependency
set. Explicit fixture revision and a maximum 1..64 lifetime event-ID inventory
are required; the bound is a local test limit, not a wire allocation. Exact
duplicates are inert, conflicting IDs reject, and the inventory never evicts.
At serialized dispatch, owner/session, revision and DependencyIndex effects are
rechecked. Events are ordered by effective time then ID for deterministic tests.
These labels/digests/revisions are fixture associations, not authenticated lineage.

Each explicit poll samples the original injected clock once. Attaching replaces
the model clock with that snapshot: callers must poll before each simulated
operation after advancing time. There is no background wakeup, real clock,
scheduling-latency guarantee, concurrency or runtime integration. Multiple timers
cannot attach to the same model. Invalid/rolled-back time latches closed, with
failed cleanup retaining visible ownership. This cannot resurrect via later time.

The only incremental model API change is an optional validated `effective_at`
for fixture enforcement. Delayed deny-new anchors grace at the original cause
time, never at observation. Repeated drain cannot extend the deadline; termination
overrides grace. Registration lease expiry starts drain but preserves already
admitted work until its independent request/authority/grace bound. No universal
lease-based transfer timeout, new active-work policy or grace constant was added.

## Measured validation

- Final scoped suite: **432 passed, zero failed/skipped/deselected**, 3.61s pytest,
  5.25s supervised. Includes 31 timer tests, signed-authority 43, existing model,
  adapter, registration vectors, CBOR, state, revocation, authorization and outage.
- Initial red: one missing-effective-argument assertion failure plus 16 missing
  module setup errors. This records API absence, not 17 behavioral defects.
- First green 105 passes (17 timer + 88 model); boundary run 28 passes.
- Independent review found two clock sampling paths: timer30/model29 lost an
  event on exception; timer19/model20 left a due event unapplied. Both scripted
  regressions failed before fix; 118 timer/model tests passed afterward.
- Final independent rereview clear. Reviewer did not rerun tests. A misplaced
  assertion tail was caught during editing and corrected before final execution.
- Final Ruff lint/format and `git diff --check` pass. An earlier direct format
  check reported one test file needing formatting; fixed before final checks.
  That diagnostic was tool-visible, not separately archived.
- All eight supervised run records/stdout/stderr retained, including both failed
  runs. Exact commands, final source snapshots and incremental model patch are
  adjacent to this manifest. Intermediate red source snapshots were not captured.
- Python3.14.6 with existing pytest8.4.2/cryptography45.0.7/Ruff0.11.13; no dependency
  download. This is not full Python-version, hosted CI or live interoperability
  validation. Previous signed-authority source/test/dependency hashes, except the
  explicitly modified model, were checked unchanged. Historical manifests remain
  snapshots; their old model/doc hashes are not current-source gate claims.

## What is now possible offline, and the remaining boundary

Existing pieces can exercise registration vectors, real COSE checks on pinned
public deterministic signed fixtures, model ownership/cleanup and explicit
effective-time event scheduling without new policy. Further pure fixture
composition or Go/Rust test-adapter porting remains code-only development work;
it does not inherently need new credentials, network access or protocol policy.
This slice does not join them into a live authenticated provider.

The real revocation-receipt producer remains blocked on the **unfrozen transport
packaging/threshold boundary** identified in the approved connector profile.
That needs reviewed semantic/package approval before implementation can claim
authenticated delivery; a caller boolean or test event is not a substitute.
Installing actual clock/provider callbacks into the Go/Rust live coordinator,
and exercising them with live sockets/credentials, additionally needs explicit
authorization for that live scope. No such work, key generation, network provider,
registry change or runtime trust is included here. Stage 3 remains partial;
stages 1-2 remain 2/10 complete.

Every supervised run obeyed offline/two-job settings, 95s work and 120s cleanup
bounds, >=8GiB starting disk, 6GiB floor, stricter 256MiB growth bound and 2GiB RAM
reserve. No resource abort; every direct child reaped. Final read-only process
check found no Python/Cargo/rustc/Go workers. No sockets/containers were created.
No commit, push, staging, cleanup deletion or alteration of unrelated work.
