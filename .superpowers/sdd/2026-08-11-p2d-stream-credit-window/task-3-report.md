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
