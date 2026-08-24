# Production Go client Tranche 5 implementation status

Status: TRANCHE 5 COMPLETE AND VERIFIED.

## Generation rotation

`internal/session.Manager` now owns one bounded rotation operation per exact
reuse key. Replacement connection runs outside the ownership lock. Its final
barrier repeats authority, proof, generation uniqueness, and total state-byte
checks before one atomic commit changes A from `CURRENT` to `DRAINING` and
publishes B as the only `CURRENT` generation.

The committed maximum remains two generations per reuse key. Cross-key
replacement generations are globally unique at both reservation and final
commit. B failure while A drains never promotes A. A third generation is
rejected until the draining slot is removed; afterward a fresh generation may
be established from current valid authority.

## Trigger and recovery behavior

Explicit, authority/proof replacement, replay-capacity, transport-failure, and
revocation triggers are local typed inputs and add no wire values. Coalesced
triggers escalate monotonically. `FailTransportSession` also escalates an
already-pending replacement, so a benign request cannot mask a later
no-new-work condition.

Replacement attempts, waiters, backoff, pending state, and sessions are
configured and bounded. Teardown cancels a pending replacement. Failed benign
rotation retains A only while A remains locally eligible; stale authority or a
strong trigger leaves no current generation. No lock is held across transport
connection or channel-opening I/O.

## Draining and descendants

Every draining generation receives a finite runtime-configured drain timeout.
Expiry recursively closes streams, channels, pending work, and the transport,
then releases the generation slot. The production interop adapter configures
the existing 30-second local drain duration; the protocol defines no timeout
constant.

SCs, credits, and Application Streams remain generation-local. Handoff blocks
new SC, refill, credit, specific-credit, and stream admission on A, cancels
pending A channel creation, invalidates unused credits, and leaves accepted
streams pinned until explicit close or deadline teardown. No handle,
`channel_id`, credit, or StreamID is rebound. Application bytes written on A
are never copied or sent on B.

Replay-cap replacement marks A no-new-work without clearing its replay state.
Fresh replay state belongs only to B. The accepted Rust P1F hard cap and
rejection precedence are unchanged.

## Restart

A reconstructed manager begins with zero TS, SC, credit, stream, pending
rotation, or routing ownership. Existing authority runtime tests continue to
prove `Ready=false` until fresh ACP validation. A fresh post-restart TS uses a
new generation-specific proof; no prior live object is restored.

## Verification

Fresh results on tested source commit `b124939de0dc43b1605959421535070b718e8553`:

- production Go client `go test ./... -count=1`: PASS;
- UCRT `go test -race ./... -count=1`: PASS;
- `go vet ./...`: PASS;
- focused session race tests: PASS;
- P2D Python regressions: 21 passed;
- Rust replay-history tests: 14 passed, 1 evidence-only soak ignored;
- Rust Application Stream tests: 4 passed;
- Rust Stream Credit integration: 7 passed;
- Rust Stream Credit vectors: 5 passed;
- real Go→Rust two-generation rotation:
  `python scripts/verify_tranche5_rotation.py --build-root
  C:\NBSR-build\tranche5-closure-b124939`: PASS;
- A was `[::]:65206->127.0.0.1:65204`; B was the distinct QUIC v1/TLS
  1.3/`nbsr-quic-1` connection `[::]:65208->127.0.0.1:65205`;
- the observed handoff was `1:DRAINING -> 2:CURRENT`, with a maximum of two
  committed generations and C rejected while A occupied the draining slot;
- an A stream admitted before rotation completed its sole 1024-byte echo only
  after B became current. Rust A recorded exactly one operation and Rust B
  exactly two, all payload-correct with zero errors, proving no implicit replay;
- all attempted new SC, credit, refill, and Application Stream work on A was
  rejected; new and final usability work completed on B;
- closing A removed its transport identity, cached handle, SC/credit/stream and
  pending ownership. B remained current and usable.

The machine-readable artifact is
`C:\NBSR-build\tranche5-closure-b124939\rotation-run\rotation-evidence.json`.
It binds the tested source commit and tree plus Go/Rust binary SHA-256 values,
readiness data, peer evidence, and both Rust results.

## Residual limitations and nonclaims

The real closure case exercises explicit production rotation and deterministic
A drain/teardown. Replay-cap replacement remains proven by focused P1F and Go
manager regressions rather than an impractically large real interop campaign.
No protocol message, field, or constant was added. Synthetic IP, DNS
interception, resolver/proxy integration, application retry, migration, and
automatic payload replay remain unimplemented.
