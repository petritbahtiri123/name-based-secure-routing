# Tranche 5 Transport Session Rotation and Recovery Design

## Scope and authority

Tranche 5 extends the production Go client's accepted Transport Session,
Service Channel, Stream Credit, and Application Stream ownership hierarchy. It
adds generation rotation, deterministic draining, and bounded recovery without
changing frozen TS/SC/P1F/P2D wire semantics. Synthetic IP, DNS interception,
resolver/proxy integration, application-level retry, stream migration, and
automatic application-data replay remain out of scope.

The existing `AuthorityBarrier` remains the local authorization boundary.
Creating a replacement captures and validates current authority, the full reuse
key, the generation-specific proof key, and current device/policy state. Before
publication, rotation repeats those checks and verifies that the same authority
and rotation attempt still own the commit. A stale or revoked attempt closes
its unowned transport and cannot publish a new current generation.

## Generation state machine

For each exact reuse key, the manager owns at most two committed generations:
one `CURRENT` and optionally one `DRAINING`. It also owns at most one bounded,
coalesced replacement attempt. A rotation establishes B outside the ownership
lock. Its successful commit is one locked transition from A=`CURRENT` to
A=`DRAINING`, B=`CURRENT`. No observer can see two current generations or an
ambiguous current generation.

A third committed generation is rejected until the draining generation has
been removed. A failed B leaves A current only if the trigger did not itself
make A ineligible for new work and the final authority barrier still validates
A. Otherwise A becomes no-new-work and the reuse key has no current generation.
An uncommitted B is always closed.

Concurrent requests for the same reuse key join the same pending attempt and
receive its exact result. Pending rotations, joiners, replacement attempts,
retry counts, timers, and drain tracking are bounded by configured limits.
Network operations and waiting never occur while the manager ownership lock is
held.

## Triggers and recovery

The production coordinator accepts only repository-backed local triggers:
explicit rotation, detected authority-generation or proof-generation
replacement, current transport failure, revocation/invalidation, and a typed
replay-cap exhaustion signal from the existing transport boundary. These
triggers select whether A may remain current after a failed replacement and
whether existing admitted streams may drain or must fail immediately. No new
protocol message or wire value is introduced.

Recovery makes a bounded number of replacement attempts with bounded backoff
and cancellation. Transport failure immediately prohibits new work on the
failed generation and resolves pending creations deterministically. Shutdown
cancels replacement work, closes any uncommitted transport, and leaves no
orphan generation. Exhausted recovery fails closed rather than reconnecting
indefinitely.

Replay-cap recovery never clears or weakens replay history within A. A becomes
no-new-work/draining, and only a fresh B has fresh generation-local replay
state. If the current adapter cannot expose the already-defined replay-cap
condition without new wire semantics, the integration remains typed at the
local transport boundary and no wire contract is invented.

## Generation-local descendants and draining

Service Channels, Stream Credits, and Application Streams retain immutable TS
generation ownership. After B becomes current, all new authority-dependent
work resolves to B. A rejects new SC creation, credit refill/new-work
reservation, and Application Stream admission. Existing accepted streams on A
remain pinned to A and may drain only where current authority policy allows.

Unused credits and pending refill state on a no-new-work generation are
invalidated. Pending SC and stream admissions that have not committed at the
handoff barrier fail deterministically. Bytes sent or partially sent on A are
never copied, queued, or resent on B. Failure is surfaced through the original
Application Stream.

When A has no admitted descendants, or when shutdown/security policy requires
immediate closure, teardown atomically removes A and all generation-local
handles, credits, pending state, and stream ownership before closing network
resources outside the lock. Deadline-based draining is bounded and repeated
teardown is safe.

## Restart lifecycle

Session ownership remains entirely ephemeral. A newly constructed manager has
no TS, SC, credit, stream, pending rotation, or routing state. The existing
authenticated identity and authority-floor stores load with `Ready=false`;
fresh ACP validation is required before any new TS is created. Pre-restart
generation identifiers are neither restored nor rebound.

## Verification and closure

Implementation proceeds through literal RED tests for atomic handoff,
two-generation capacity, coalescing, authority races, trigger-specific failure,
drain/teardown, descendant pinning, replay-cap replacement, restart, bounded
recovery, cancellation, and no application-data replay. Focused package tests
precede the complete Go suite, race suite under UCRT, and `go vet`.

A focused real Go-to-Rust lifecycle will establish A, use an owned SC/credit/
Application Stream, rotate to B, prove new work uses B while A work remains
pinned or fails under policy, close A, and prove no A-owned state remains. The
existing relevant Rust transport, P1F, P2D, protocol-vector, and interop
regressions remain unchanged and are rerun. Closure includes one focused
correctness/security review, fixes only confirmed Critical/Important findings,
and performs one scoped re-review.

Documentation records measured test results and local-loopback evidence without
claiming WAN, physical-NIC, server-class, or broad production readiness.
