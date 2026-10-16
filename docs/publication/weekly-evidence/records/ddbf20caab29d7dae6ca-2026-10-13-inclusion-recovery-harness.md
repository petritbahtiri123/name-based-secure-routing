# Test-only inclusion recovery composition

Implemented the approved surviving-controller composition with deterministic
storage/disposal inputs. No production provider or security policy changed.
Published ancestor is ad77d59754651fee449bb1d9c14a946f9f3b2d15; the local handoff
inventory binds the actual sources and retained input package bytes.

`scripts/inclusion_recovery_harness.py` retains an independently supplied context,
expected snapshot digest and exact fake worker owner. It blocks recovery until
that owner's exact disposal attempt succeeds. Failure keeps ownership and requires
explicit retry; stale or repeated completions cannot release a successor. Recovery
calls the existing `Repository.load`, including its lineage, retention, expectation
and uncertain-repair rules. Every explicit retry opens a new repository under the
same controller expectation. The controller survives throughout this experiment.

The recovered fake worker holds a snapshot and `registration=None`. It has no
authority, transport, readiness or application-work API. Ordinary outage, scoped
revocation and bounded ongoing-work semantics are unchanged.

## Fixture boundary

Tests read the first retained inclusion package and check its recorded SHA-256.
They preserve its full canonical record bytes while constructing explicitly
assumed-accepted storage snapshots with synthetic event bindings. They do not
invoke `make_fixture`, signing or credential generation. The snapshot assumption
is not independently verified signed acceptance. No new signature or production
authority is inferred from codec success. Reusing `Repository.load` is appropriate
for storage recovery; it is not a substitute for `verify_package` on new authority.

Four deterministic states represent before/after watermark and primary replacement.
Two additional tests inject failure before/after primary repair. These are memory
states and callback exceptions, not actual process termination or disk writes.

## Validation

- Initial red: one collection error because the harness module was absent.
  This is API-absence evidence, not a behavioral assertion failure.
- Initial green: 10 passed; expanded interruption/negative matrix: 18 passed.
- Independent review found reentrant restoration could publish an inner worker
  and then overwrite it without disposal. Regression red: 1 failed, 18 deselected.
- Minimal correction: controller-level in-progress guard, reset in `finally`,
  around repository construction/load and publication. Per-repository guards
  alone cannot protect separate instances created by recursive callbacks.
- Final scoped run: 125 passed, no skips/deselections (19 harness, 10 outage,
  96 connector-model). Pytest 1.31 seconds; supervised 2.62 seconds. Ruff check
  and format check passed for both new Python files.

All supervised direct children were reaped with no resource abort. Final disk
free stayed 13,967,360,000 bytes and RAM free was 6,062,829,568 bytes. Existing
fixed cumulative disk baseline and resource/deadline guards were retained.
Python 3.14 is locally permitted; this does not establish a version matrix.
Intermediate red logs are retained; not every intermediate source was snapshotted.

Changed paths: harness, its focused tests, this report and root AGENTS.md.
Existing inclusion code, vector bytes and original dirty checkout sources are
unchanged. No CI selection or runtime activation was added. The signing-dependent
inclusion suite was deliberately excluded from this no-signing task.

## Remaining gate

Actual killed-worker/filesystem interruption and owned-resource disposal need
a separately bounded execution scope. Windows private-writer ACL effects still
require action-time exact-root authorization. Local reap alone cannot confirm
remote/backend disposal. Controller loss, hostile-process identity, concurrency,
production authority provenance, reboot durability and runtime registration
integration remain outside this synchronous test-only harness. No Docker, SSH,
SPHERE, sockets, heavy builds, signing, publication or security settings changed.
