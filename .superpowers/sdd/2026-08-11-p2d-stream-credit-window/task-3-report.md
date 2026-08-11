# P2D Task 3 report: same-stream Quinn admission and payload quarantine

## Scope and baseline

- Branch: `codex/nbsr-perf-p2d-stream-credit-window`.
- Task baseline: `30caefe` (`Harden credited stream commit authority`).
- Implemented live `AuthenticatedConnection::open_credited_session_stream` and
  `AuthenticatedConnection::accept_credited_session_stream` on the existing
  Task 1 codec and Task 2 session/window/P1F authority.
- The existing Core v0.1/v0.2 legacy `open_session_stream` and
  `accept_session_stream` implementations were not changed. No control-envelope
  bytes, numeric meanings, RouteGrant schemas, benchmark evidence, protected
  refs, or remote refs were changed.

## Literal RED

The live integration tests were created before either Quinn API existed and
before the existing profile selector was exposed to the runtime caller.

Command from `crates/nbsr-transport`, with
`CARGO_TARGET_DIR=C:\Users\bajra\.codex\targets\nbsr-p2d-task3`:

```text
cargo test --test stream_credit_integration
```

Result: exit 1 with nine expected compile errors: one `E0624` for the private
`select_stream_credit_profile` method and eight `E0599` errors for the missing
`open_credited_session_stream` / `accept_credited_session_stream` methods. No
fixture, syntax, or environment error occurred.

A second literal RED isolated the bounded reader before its extraction:

```text
cargo test stream_credit_adapter_tests
```

Result: exit 1 with the expected `E0432` unresolved import for the missing
`read_bounded_stream_credit_wire` helper. After the helper was implemented, the
same command passed 2 tests, 0 failed.

## GREEN implementation

- Source verifies the exact connection capability, opens one Quinn bidi stream,
  obtains its transport-owned stream ID, atomically allocates the next local
  credit and ordinary stream/P1F entry under `ControlSession`, encodes and writes
  only the bounded deterministic preface, and waits for exactly one response
  byte. Only `0x00` returns an `ApplicationStream`; EOF, `0x01`, or any other byte
  fails closed.
- Destination accepts one bidi stream and reads the QUIC varint prefix without
  allocation. Length zero and lengths over 128 reject immediately. At most an
  8-byte prefix plus a fixed 128-byte body representation is used; truncated
  reads reject. Only after the complete bounded item is buffered does the path
  derive authenticated session/channel/generation/transport-ID context, decode,
  and call `ControlSession::authorize_credited_stream`.
- Destination writes exact `0x00` only after credit, P1F replay history, ordinary
  stream state, and audit have committed. Safe failures write exact `0x01`, stop
  the receive side, and finish/reset only that bidi stream.
- Source allocations are terminal after transport or peer failure. Failure
  cleanup releases ordinary live stream state while retaining the consumed
  credit and P1F stream-ID history; later unused credits remain allocatable.
- A shared preparation helper keeps credited capacity, P1F, audit-denial, and
  typed rejection mapping identical between source allocation and destination
  authorization. Neither credited path reads or mutates a control-envelope
  request ID, monotonic sequence, or shared pending-admission queue.

## Focused evidence

All commands used the target directory above.

```text
cargo test --test stream_credit_integration
cargo test --test application_stream
cargo test session_tests::
cargo test stream_credit::lifecycle_tests
cargo test stream_credit_adapter_tests
cargo clippy --test stream_credit_integration -- -D warnings
```

Observed results:

- live credited Quinn integration: 5 passed, 0 failed;
- unchanged legacy application streams: 4 passed, 0 failed;
- live session credit authority/P1F/expiry/revocation/audit: 7 passed, 0 failed;
- bounded refill/current-draining/race/abuse lifecycle: 7 passed, 0 failed;
- zero/oversized/truncated/unsupported/payload-boundary reader cases: 3 passed, 0 failed;
- strict scoped Clippy: exit 0, no warnings.

The live integration tests prove no `STREAM_OPEN`/`STREAM_ACCEPT` exchange is
needed for credited admission; source payload APIs are unavailable while the
open future waits for the same-stream decision; distinct slots admit on streams
4 and 8; two concurrent source views proposing the same slot yield exactly one
destination and one source success; malformed early queued bytes and a wrong
channel reject without destination admission; a rejected source allocation is
not reused while the next credit remains valid; and revocation after the
preface is queued but before decision rejects and releases live state while P1F
history remains terminal.

The bounded-reader tests independently cover length zero, a shortest-form
length of 129, truncation, an unsupported profile body, and a valid preface with
already-queued payload. The latter proves that the destination reader consumes
only the exact preface and leaves all payload quarantined inside the receive
stream; the destination constructs and returns no `ApplicationStream` until
after authorization commit and its ACCEPT write. Existing Task 1
vectors continue to cover wrong channel, generation, session, actual stream,
epoch, and slot, while Task 2 authority tests cover expiry, revocation,
capacity, audit, replay cap, current/draining overlap, same-slot serialization,
refill transition, and cleanup without mutation on rejection.

## Fresh final verification

```text
cargo test
cargo fmt --check
cargo clippy --all-targets -- -D warnings
git diff --check
```

All commands exited 0. The full suite reported exactly 174 passed, 0 failed,
and 1 ignored. The ignored test is the pre-existing P1F evidence-only ten-minute
bounded-memory soak. Formatting, strict all-target Clippy, and whitespace checks
passed without errors; Git emitted only the repository's line-ending conversion
notices during the diff check.

## Self-review

- The only heap allocation on the admitted wire path is the existing bounded
  encoder result on the source. Destination prefix/body parsing is fixed stack
  storage and rejects before semantic state or audit work.
- The actual Quinn `SendStream::id()` is authoritative on both endpoints. The
  source cannot provide an expected-result label or caller-selected stream ID;
  destination decoder context also uses the transport-observed ID.
- Credit allocation/consumption and `used_stream_ids` remain separate, retained
  one-time authorities. Ordinary live stream release never removes P1F history.
- The source holds no application stream handle before ACCEPT, so the public API
  cannot send speculative application payload. Destination parsing reads only
  the exact bounded preface and does not read, expose, or forward an
  already-queued payload byte before commit and ACCEPT. A malformed raw early
  control-frame probe is rejected and reset without admission before a following
  valid credited stream succeeds.
- The credited methods track successful streams in the existing per-connection,
  per-channel tracker. Revoke/close therefore use the unchanged scoped reset
  behavior; failures before return never enter the tracker.
- Profile selection remains explicit before activation. Legacy selection and all
  legacy application-stream tests remain byte/behavior compatible.

## Concerns and non-claims

- Task 3 does not add a new refill control-envelope wire format. It consumes the
  compact Task 2 source/destination window APIs; automatic refill transport and
  performance evidence remain later task scope.
- Invalid peer bytes are injected live for the zero-length/early-payload and
  wrong-channel cases. Oversized, truncated, unsupported, and the remaining
  binding mutations are exercised at the exact bounded reader/decoder/session
  boundaries without adding a production raw-stream escape hatch solely for
  tests.
- QUIC exposes one ordered byte stream, not a trustworthy sender wall-clock
  marker after the preface. The receiver therefore does not use a racy
  one-poll/timing oracle to guess when an already-buffered byte was sent. The
  deterministic invariant proved here is zero application-payload read,
  exposure, or forwarding before commit plus ACCEPT; conforming source code
  cannot obtain the stream handle or send payload before receiving ACCEPT.
- This is loopback interoperability evidence, not a throughput improvement,
  live-platform result, production-readiness claim, or Task 4 acceptance result.
- The controller-owned untracked normative protocol and implementation-plan
  documents were neither modified nor staged.

## Fix round 1: cancellation ownership and unlocked transport I/O

This section supersedes the initial report where the two conflict.

### Corrected claims

- The original concurrent test used two independent `ControlSession` copies,
  so it did not prove same-session serialization and its "same slot commits
  once" wording was overstated. Task 2's state-level race test remains the
  same-slot proof. The live replacement uses one cloneable shared session and
  proves that a second, distinct credit reaches ACCEPT while the first stream's
  peer deliberately withholds its decision.
- The original revocation test proved that the preface was queued before
  revocation, not that destination parsing had completed. It is now named
  `revocation_before_destination_commit_rejects_and_retains_source_replay`.
  A separate exact phase test encodes and decodes the preface, revokes after
  parsing, then proves the commit authority recheck rejects it.
- Pending credited streams are now tracked internally immediately with their
  session commit so revoke/close can reset a stalled admission. They are still
  private and are never returned to application code before ACCEPT. This
  replaces the initial report's statement that only successful streams enter
  the tracker.

### Literal RED

From `crates/nbsr-transport`, using the same external target directory:

```text
cargo test --test stream_credit_integration
```

Result: exit 1 with the expected `E0432` unresolved import for the missing
`SharedControlSession`; after correcting two test-only `Debug` assumptions,
there were no fixture, syntax, or environment failures.

```text
cargo test session_tests::dropping_destination_admission_before_accept_releases_live_but_retains_credit_and_p1f
```

Result: exit 1 with the expected missing `SharedControlSession`,
`CreditedAdmissionCleanup`, and `release_credited_stream_terminal` APIs.

### Ownership and lock boundaries

- `SharedControlSession` owns one `ControlSession` behind a private synchronous
  mutex. Its `inspect` and `update` closures cannot return a borrow, so callers
  cannot retain `&mut ControlSession` across an await. Ordinary poisoned-state
  access fails closed. Only the private terminal cleanup path recovers the
  mutex, and that path can remove only an ordinary live-stream entry.
- Source lock sections are limited to exact-connection inspection, atomic
  credit/P1F/live allocation plus internal tracking, and the final live-entry
  validation. Quinn `open_bi`, preface write, and decision read all run without
  the session lock.
- Destination lock sections are limited to exact-connection/context snapshot,
  atomic credit/P1F/live commit plus internal tracking, and terminal cleanup.
  Quinn `accept_bi`, bounded preface read, REJECT write, and ACCEPT write all run
  without the session lock. Decode uses a snapshot, while commit rechecks all
  live authority after peer-controlled I/O.
- An armed RAII owner is created in the same uninterrupted poll immediately
  after either source allocation or destination commit. Future drop, timeout
  abort, explicit I/O error, peer rejection, expiry, or closing invokes the
  terminal cleanup. Cleanup is idempotent, releases ordinary live capacity,
  and deliberately retains the consumed credit and P1F stream ID. Existing
  revoke/close authority remains terminal and may already have removed the
  ordinary entry or credit window; P1F history remains untouched.
- Internal pre-admission stream tracking lets concurrent revoke/close wake and
  reset stalled Quinn I/O. Application payload APIs remain inaccessible until
  same-stream ACCEPT, and the exact bounded reader/quarantine behavior is
  unchanged.

### GREEN evidence

```text
cargo test --test stream_credit_integration
cargo test session_tests::
cargo test --test application_stream
cargo test stream_credit::lifecycle_tests
cargo test stream_credit_adapter_tests
cargo clippy --test stream_credit_integration -- -D warnings
```

Observed results were respectively 5/5 live credited Quinn tests, 12/12
session tests, 4/4 unchanged legacy application-stream tests, 7/7 Task 2
lifecycle tests, 3/3 bounded-reader tests, and strict focused Clippy clean.

The spawned live cancellation test waits for the first source allocation to
become observable, gives that stream to a peer that withholds its decision,
observes a real timeout, aborts and awaits the task, and then proves the stream
permit/live entry is gone. During the stall, a second credit under the same
shared session completes on stream 8, proving no session-wide head-of-line
wait; the cancelled stream ID 4 remains a P1F duplicate. Because the credited
future is spawned, the test also enforces that no non-`Send` synchronous mutex
guard crosses its Quinn awaits.

Destination cancellation is covered in both the exact ownership unit and live
Quinn paths. A source transport with a zero receive window deterministically
blocks the destination's one-byte ACCEPT write after a real destination
credit/P1F/live commit. The test observes the committed live entry, times out,
aborts and awaits the actual destination future, and proves the live entry is
gone while the slot bitmap remains consumed and stream ID 4 remains a
duplicate; the source admission is reset. Dropping the same RAII owner directly
at the commit/ACCEPT boundary independently pins its terminal semantics.
Separate tests prove cleanup still removes the entry after session drain begins
and after the hard session deadline expires, even though public
`release_stream` correctly rejects in those states.

Fresh full `cargo test` after this fix round reported exactly 179 passed,
0 failed, and 1 ignored. The ignored case remains the pre-existing P1F
evidence-only ten-minute soak. No benchmark, throughput, live-platform, or
production-readiness claim is added.
