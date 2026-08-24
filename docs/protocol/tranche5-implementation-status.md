# Production Go client Tranche 5 implementation status

Status: IMPLEMENTED AND LOCALLY VERIFIED; REAL ROTATION INTEROP CLOSURE BLOCKED.

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

Fresh results on the working branch:

- production Go client `go test ./... -count=1`: PASS;
- UCRT `go test -race ./... -count=1`: PASS;
- `go vet ./...`: PASS;
- focused session race tests: PASS;
- P2D Python regressions: 21 passed;
- Rust replay-history tests: 14 passed, 1 evidence-only soak ignored;
- Rust Application Stream tests: 4 passed;
- Rust Stream Credit integration: 7 passed;
- Rust Stream Credit vectors: 5 passed;
- real Go→Rust accepted P1F/P2D regression: 7 cases PASS.

## Closure blocker and nonclaims

The existing real Go peer constructs one `streamclient.OwnedChannel` around one
already-established QUIC connection. It has no concrete production adapter that
can establish a second QUIC TS and feed both generations through the same
`session.Manager`. The current real-process run therefore proves unchanged
P1F/P2D interoperability, not a real A→B rotation lifecycle.

Adding that adapter requires additional production transport integration, but
no new protocol message or wire rule. Until a real two-generation Go→Rust run
proves A use, B activation, B-only new work, A drain/failure, and A teardown,
Tranche 5 cannot honestly be marked complete. Synthetic IP, DNS interception,
resolver/proxy integration, application retry, migration, and automatic
payload replay remain unimplemented.
