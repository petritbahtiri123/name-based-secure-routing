# Bounded offline reconnect verification

This is a characterization of existing mock behavior, not a runtime fix or
durable restart implementation. Published ancestor:
`ad77d59754651fee449bb1d9c14a946f9f3b2d15`; exact local sources and test delta
are retained in the corresponding local handoff inventory.

## Contract and scope

The connector profile requires fresh authentication and acceptance on reconnect,
exact service/session binding, cleanup before replacement and no automatic
takeover or application replay. The lifetime model separately bounds admission,
ongoing authority, request deadline and completion grace. Deny-new preserves
only independently authorized bounded work; terminate-active cancels it.

The federation adapter explicitly excludes reconnect and durable trust.
Constructing a fresh mock Model is not restoring a revocation floor. Persistent
authority provenance, restart recovery and cross-process cleanup remain separate
gates; a new model must not be presented as proof that those gates are settled.

## Measured results

- Existing connector model: 88 passed.
- Added characterization: 8 passed, 88 deselected. Reconnect and fresh-model
  construction each reject stale, expired, revoked and other-service permission.
  Each checks a fresh session, another verifier call, rejection of the old ticket,
  no admitted work, closed candidate and zero remaining model ownership.
- Final focused suite: 133 passed, no skips or deselections (96 model, 13 state,
  24 revocation), pytest 1.12 seconds, supervised elapsed 2.21 seconds.
- Ruff check and format check passed for the changed test file.

The existing suite also covers stale-ticket/successor isolation, session changes,
failed cleanup retaining ownership, explicit cleanup retry, revocation reconnect
latching, finite grace, authority expiry and request-bound work renewal. These
were rerun rather than duplicated. No defect reproduced, no red test and no
implementation fix. No new policy, fallback, keys, signing, sockets or builds.

One command launch encountered an exec transport disconnection. A subsequent
read-only check found neither final-run evidence nor a visible Python process;
only then was the same permitted command retried. The successful run reaped its
direct child with no resource abort. Disk free stayed 13,963,649,024 bytes; final
available RAM was 6,102,085,632 bytes. Existing fixed cumulative disk baseline
and supervisor guards were retained. Python 3.14 is within package metadata;
this is not validation of the broader Python version matrix.

## Limits and next gate

Synchronous fake verifier/transport inputs do not prove authenticated revocation,
durable restart, interrupted real transport shutdown, application continuation
after reconnect or direct-origin routing behavior. No runtime route was exercised
or modified. The next implementation gate is an approved provider/restart contract
for current authority, retained floors and cleanup ownership across process loss;
it must not reconstruct authority from stale registration or a snapshot hash.
The full federation vision and production readiness remain unchanged.

Root guidance was reviewed: no durable commands, limits or semantics changed, so
AGENTS.md needed no edit. The skill's optional writing-good-tests resource could
not be loaded; the main debugging/TDD and verification guidance was available.
Repository-scoped validation was used as instructed; no repository-wide suite ran.
