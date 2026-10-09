# Explicit owned sends: first-stage contract

Status: owned-send stage 1 and the subsequently approved borrowed-send guard are
implemented and verified; this six-file package is approved for publication to
`codex/nbsr-v3-wp0-wp1`. Further cancellation-path work remains separate.
Base: bcd5f5df7c4cca64007943011c2c7cc338b1f32d. Historical stage-1 failures below are
retained as evidence; see the later guard validation for the current outcome.

## Intent and rationale

Pause waiting without losing progress or duplicating a prefix; keep explicit abort
and reset for terminal failure. No background sender and no wire changes.

The retained loopback diagnostic observed clean EOF after 64/4096 bytes when a
borrowed send future and stream were dropped. Its normal-completion control passed.
That is evidence about abandonment, not permission to reset every dropped stream.

Sources: `docs/architecture/nbsr-transport-profile.md` (standard QUIC graceful close
and stream-scoped reset); `docs/protocol/wp4-reusable-multi-service-transport-decision.md`
(1 MiB stream / 8 MiB bidirectional channel accounting and terminal revocation);
`quinn_adapter.rs` (`send_payload`, `wait_for_send_ack`, `echo_once`); the demo's
absolute deadline in `wp8_interop_server.rs::relay_demo_backend_until`.
Pinned Quinn `write` is cancel-safe; `write_all` may consume a prefix before Pending;
SendStream Drop ordinarily sends FIN. Existing timeout callers must not silently
continue after declaring failure.

## Additive API

`ApplicationStream::begin_owned_send(&mut self, payload: Vec<u8>) -> Result<OwnedSendOperation<'_>, TransportError>`
creates an operation but sends nothing. `OwnedSendOperation::drive(&mut self)` is
async and can be dropped/recreated to pause/resume. `abort(self)` consumes the
operation and resets an unfinished stream. Drop of an unfinished operation does
the same; Drop after successful drive does not reset. No blanket ApplicationStream
Drop change. A repeated drive after completion is an idempotent local success.

The operation object is the opaque, non-Clone token, bound by an exclusive mutable
borrow to one stream. It has no replace-payload or cross-stream retry method; its
kind is owned payload, not echo. The borrow prevents concurrent send, receive,
echo, benchmark framing, ACK wait, or another begin on the same stream while it
exists. A first-stage begin is rejected after any legacy application write attempt
or any prior owned operation, or with an unfinished receive operation. Internal credit
prefaces are not payload writes. The later borrowed-send guard below refines its
marker to accepted payload progress or FIN; zero-progress cancellation does not
block a subsequent owned begin. Echo and framing guards are unchanged.

One immutable payload is moved into stream-associated operation state with offset,
phase (Pending/Completed/Aborted), and its quota reservation. A weak registration
lets revocation clear paused state without waiting for the async stream lock.
The operation owns the strong state reference. No unbounded operation registry.

## Progress, memory and lifecycle

- Validate <=1,048,576 payload bytes and reserve within 8,388,608 channel bytes
  before installing the operation; errors send no bytes and release reservations.
- Each cancel-safe write commits its returned accepted-byte count synchronously.
  Resume sends only the suffix at that offset. A fixed <=16 KiB temporary chunk
  avoids holding a synchronous state mutex across an await; no extra full copy.
- FIN is issued only after the entire payload is accepted. Successful completion
  transfers the reservation to existing completed outbound ownership; explicit
  `release_buffered_payloads` still releases only completed ownership.
- Pause retains payload/quota. Explicit abort, unfinished owner Drop, revocation,
  and terminal write/connection errors invalidate progress, clear reservations,
  and reset/stop only that stream where transport state permits. Reset cannot undo
  bytes already observed by a peer; no application-level delivery guarantee.
- Completion means accepted by transport plus FIN, not ACK or application processing.
  Drop the completed operation to release its stream borrow, then use existing ACK
  waiting if desired. A broken connection can prevent delivery or acknowledgment.
- No timer task is created. A caller timeout around drive means pause; to enforce
  an absolute operation deadline the owner calls abort/drops the operation at that
  deadline. Resuming must not extend an existing caller deadline. Paused state stays
  quota-accounted until explicit completion/abort, revocation, or owner Drop.

## Compatibility and later stages

The original first stage did not migrate borrowed `send_payload`, echo, composite
methods, or demo timeout callers, and its legacy abandonment diagnostic remained
red. The later approved guard below fixes borrowed-send abandonment; historical
first-stage results are not relabeled.

Later echo migration must retain receive/send phase, response bytes and both quota
directions; restarting echo must never reread input after its response exists.
Later `send_and_receive` migration must retain Sending/Receiving phase so resuming
a response wait cannot resend the request. Existing caller deadlines and explicit
abort intent must be preserved. Each migration needs its own reviewed tests/docs.

## First-stage evidence

Deterministic authenticated loopback with 64-byte test windows: repeated pause/resume
returns exactly one 1024-byte payload; explicit abort and unfinished Drop produce
stream error, normal completion remains clean EOF; quota stays charged while paused
and is released by abort/revoke or transferred on completion. Also cover zero bytes,
oversize/channel exhaustion, rejected mixing, revocation without repolling, and
completed operation Drop. No throughput or delivery-guarantee claims.

Test-budget ruling: a 4096-byte positive resume case reached 3840 bytes at the
two-second cutoff under 64-byte windows. The positive case uses 1024 bytes with
the same three proven pauses and unchanged cutoff. The original 64/4096 legacy
failure and 4096-byte abort cases remain unchanged. No throughput claim follows.


## Final validation and review record

Commands use the existing cached target, `--locked --offline --features
benchmark-harness --jobs 2`, the 95-second work cutoff, and disk/RAM guards.
Local evidence logs are named `control-read-owned-send-<label>.stdout.log` and
`.stderr.log`; raw logs and machine-specific paths are excluded from this package.

| Actual run label | Passed | Failed | Ignored | Test duration |
| --- | ---: | ---: | ---: | ---: |
| api-red | — | compile error: absent begin_owned_send API | — | no tests ran |
| first-green | 3 | 1 (positive resume timeout) | 0 | 2.43 s |
| resume-diagnostic | 0 | 1 (3840/4096 at cutoff) | 0 | 2.07 s |
| focused-green | 4 | 0 | 0 | 1.01 s |
| complete-focused | 6 | 0 | 0 | 1.18 s |
| library-check | 88 | 1 (legacy diagnostic) | 1 | 4.50 s |
| ordering | 8 | 0 | 0 | 1.26 s |
| final-credit | 11 | 0 | 0 | 1.09 s |
| final-library | 90 | 1 (legacy diagnostic) | 1 | 4.65 s |

The final library run includes all eight owned-send tests after strengthening
cleanup assertions to precede operation Drop. No diagnostic was ignored, deleted,
or relaxed. The one ignored test is the existing ten-minute soak.
`final-clippy`: all-target Clippy with `-D warnings` passed (11.57 s).
Final `cargo fmt --check` and `git diff --check` are recorded separately by the
local validation command; no full repository suite or benchmark was run.

Independent read-only review found no blocking production issue. Its coverage
suggestion was addressed with a `cfg(test)` hook immediately after FIN and before
reservation transfer, while the operation state mutex is held. The test starts
revocation, waits for its cancellation flag, then allows transfer and verifies
zero quota/empty outbound ownership before operation Drop. No timing-based race
probability is used to reach that boundary. A separate completion-first control
verifies exact clean EOF, idempotent drive, one completed reservation, transport
ACK retaining quota, then explicit release or revocation returning quota to zero.
The hook does not exist in production builds.

## Historical next-slice recommendation (subsequently approved for the guard only)

Address existing borrowed-send abandonment and its timeout callers before expanding
into echo/composite state machines. Preserve the borrowed API's documented terminal
abandonment intent: a send-scoped cancellation guard should reset only an unfinished
send, retain normal FIN after success, and make the original 64/4096 test pass.
Do not silently make a borrowed call retain its input or automatically retry it.
At callers that intentionally pause, adopt an explicit owned operation outside the
cancellable wait and resume that same object under the original absolute deadline.
At callers that declare terminal timeout, explicitly abort/drop it. First inventory
those call sites and write before/after timeout, zero-progress, partial-progress,
normal-FIN, sibling-isolation and quota tests; implement only that bounded slice.
Then migrate echo and send-and-receive separately using retained phase and payload
identity, so response waits cannot resend a request or reread an echo input.


## Approved borrowed-send guard: contract and rationale

`send_payload(&[u8])` retains its signature and borrowing behavior. The implementation
uses cancel-safe `write` calls and arms a small local guard synchronously after the
first nonzero accepted write. It never stores the caller's payload for later resume.

- Dropping an unpolled call or cancelling before its first accepted payload byte
  releases this call's quota and leaves an otherwise healthy stream usable. This
  includes waiting for the stream mutex or transport credit. No application-write
  marker is set until accepted progress (or an empty payload's FIN).
- After any accepted payload byte, cancellation is terminal: the guard marks only
  this application stream cancelled, resets its send direction, stops its receive
  direction, and releases stream-owned quota. Subsequent payload APIs reject it.
  Sibling streams and the connection remain usable. There is no blanket stream-Drop
  reset. Already observed bytes cannot be retracted.
- A terminal write/FIN error also arms cleanup. Successful FIN disarms it and keeps
  completed outbound quota until explicit release, revocation, or final stream Drop.
  Empty payloads preserve successful FIN. ACK remains transport acknowledgment only.
- The guard is declared before the async stream-lock guard, so the latter is dropped
  first during cancellation/return. Cleanup can then acquire it to reset immediately.
  If revocation already marked the stream, Drop completes reset even when no payload
  byte was accepted and the notification was never repolled.
- Notify is enabled before waiting for the mutex and checking cancellation, closing
  the check-versus-notification gap. The cancelled flag is checked before each write,
  before FIN, and after quota transfer. The final check prevents a reservation from
  surviving if revocation released completed ownership just before that transfer.
  Revocation after transfer releases it itself. An in-flight reservation remains
  owned by the borrowed future until that future is polled to termination or dropped;
  this slice does not add a shared paused-state registry for borrowed calls.

Compatibility: partial cancellation now produces a stream error rather than false
successful truncation. Ordinary zero-progress cancellation remains reusable and now
also permits owned begin; neither case silently starts a resumable borrowed operation.
The original 64/4096 regression is unchanged. Its same-connection normal completion
control also proves future connection use. Separate tests cover retained failed stream
rejection, unaffected sibling FIN/ACK, normal/empty FIN and quota, no-progress retry,
and revocation while waiting or while a zero-progress write is pending.

Call-site inspection found the demo response timeout in
`wp8_interop_server.rs::relay_demo_backend_until`, direct sends in that binary and
`perf_rust_source.rs`, and the `send_and_receive` delegation. No call site was migrated
and no deadline changed. The send phase of `send_and_receive` inherits this guard,
but the composite is not a resumable phase machine: cancelling its later receive
phase and restarting the whole method is not supported. `echo_once` still has its
separate outbound write path and needs its own phase-aware migration and regression.
Benchmark frame writes are also outside this payload-send fix. Use explicit owned
operations for deliberate pause/resume; audit/migrate each caller separately.


### Borrowed guard validation record

All commands used the existing cache, locked/offline dependencies, two jobs and
unchanged disk/RAM/time guards. Labels below map to
`control-read-<label>.stdout.log` in the local evidence workspace
and `.stderr.log`. Counts are per actual run, not additive unique test counts.

| Actual run label | Passed | Failed | Ignored | Test duration |
| --- | ---: | ---: | ---: | ---: |
| borrowed-send-red | 0 | 2 | 0 | 0.16 s |
| borrowed-send-green | 2 | 0 | 0 | 0.27 s |
| borrowed-send-original-green | 1 | 0 | 0 | 0.15 s |
| borrowed-send-revoke-drop-red | 0 | 1 | 0 | 2.19 s |
| borrowed-send-final-focused | 5 | 0 | 0 | 0.63 s |
| borrowed-send-final-library | 96 | 0 | 1 | 5.09 s |
| borrowed-send-neighbors1: application_stream | 4 | 0 | 0 | 0.74 s |
| borrowed-send-neighbors1: stream_credit_integration | 11 | 0 | 0 | 1.16 s |
| borrowed-send-neighbors2: drain | 12 | 0 | 0 | 1.11 s |
| borrowed-send-neighbors2: multi_stream | 3 | 0 | 0 | 0.56 s |

The initial red cases exposed an early application-write marker and missing partial
cancellation reset. Independent review then identified zero-progress revocation/drop
without repolling; its new regression timed out before the fix and passes after Drop
also checks the cancelled flag. Final independent review found no remaining blocker.
The final library run includes all eight owned-send tests unchanged and the original
64/4096 regression without assertion weakening. The only ignored case remains the
existing ten-minute soak. No full repository suite, demo, or benchmark was run.
The follow-up changes only quinn_adapter.rs, control_read_tests.rs, this spec and
its plan; owned_send.rs and lib.rs are unchanged from stage 1. Publication was
subsequently authorized only for the complete six-file package on the named branch.

Final borrowed-guard checks: all-target Clippy with warnings denied passed (11.56 s); cargo fmt --check and git diff --check both passed.
