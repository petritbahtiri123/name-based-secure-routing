# Task 7 report: closed lifecycle bodies and bounded drain

## Status

Complete. Core v0.2 codes 12-14 now have closed deterministic-CBOR bodies,
Service Channels and local Transport Sessions have bounded drain state, and
deadline enforcement is confined to the Quinn adapter. Frozen Core v0.1
behavior remains unchanged.

## RED/GREEN cycles

1. Closed lifecycle bodies and fake-clock deadline bounds
   - RED: `tests/drain.rs` failed to compile because `DrainDeadline`,
     `DrainReject`, typed lifecycle bodies/accessors, and message variants did
     not exist (seven compiler errors).
   - GREEN: implemented strict protocol-2 decoding for codes 12, 13, and 14,
     typed accessors, and saturating injected-monotonic deadlines. The first
     three drain tests passed.
2. Channel drain state and deadline enforcement
   - RED: the focused test failed to compile on the missing channel drain
     handler, deadline accessors, and adapter enforcement APIs (six compiler
     errors).
   - GREEN: `Active -> Draining` immediately denied new work, kept release of
     already accepted reliable streams available, and transitioned to
     `Closed` exactly at the effective deadline.
3. Revoke and close controls
   - RED: focused tests separately failed to compile on missing
     `accept_route_revoke` and `accept_route_close` handlers (two errors in
     each cycle).
   - GREEN: revoke became immediate and terminal during drain; close retained
     replay/tombstone state; wrong bindings and replays failed without
     consuming the request ID or source sequence.
4. Real target-stream reset
   - RED: after pre-deadline completion and immediate rejection of new work,
     the live target stream timed out at the deadline instead of observing a
     reset.
   - GREEN: the adapter gained cancellation-aware tracked application streams;
     channel enforcement resets only the target channel's live streams.
5. Local session drain
   - RED: the focused test failed to compile because session drain state,
     start, deadline, and enforcement APIs did not exist (seven errors).
   - GREEN: the fake clock stayed pending at 29 seconds and closed at 30;
     loopback enforcement reset session streams and closed only that QUIC
     connection while an unrelated session remained usable.
6. Earlier authority deadline
   - RED: the focused test failed to compile on the missing constructor that
     accepts an injected session deadline.
   - GREEN: the effective channel drain deadline became the minimum of the
     requested drain, grant remaining lifetime, and session deadline.

Audit-exhaustion coverage was added as a regression after the fail-closed
audit behavior existed. It passed on its first run and is not represented as a
RED cycle.

## Exact wire fixtures and counts

- `ROUTE_DRAIN` is protocol-2 message code 12. Its closed six-key body encodes
  to a 124-byte complete `ControlEnvelope` in the literal fixture.
- `ROUTE_REVOKE` is protocol-2 message code 13. Its closed five-key body
  encodes to a 121-byte complete envelope in the literal fixture.
- `ROUTE_CLOSE` is protocol-2 message code 14. Its closed five-key body
  encodes to a 121-byte complete envelope in the literal fixture.
- The decoder rejects unknown, missing, or duplicate keys; non-preferred or
  indefinite encodings; booleans used as integers; floats; tags; trailing
  bytes; wrong fixed lengths; zero channel/route IDs; timestamps above
  `253402300799`; drain values above 30; and envelope protocol versions other
  than 2.
- No Core v0.1 registry, schema, state, or vector fixture was changed.

## Fake-clock and real-loopback evidence

- Fake-clock coverage exercises requested drain values 0, 1, 29, and 30,
  rejects wire value 31, checks the exact boundary, and verifies saturating
  addition near `u64::MAX`.
- The effective deadline cannot exceed the grant or injected session
  authority deadline.
- Audit exhaustion before start preserves `Active`; audit exhaustion at forced
  closure returns typed audit-integrity failure while authorization remains
  denied and adapter reset/close still occurs.
- Revoke during drain is immediate and terminal. Close/revoke replays and
  wrong grant bindings fail closed. Closing one channel preserves its active
  sibling.
- Real Quinn loopback tests prove an accepted TCP stream can finish before the
  boundary, new post-drain streams are reset, a remaining target stream is
  reset at the channel deadline, and session deadline closure does not affect
  another connection.

## Commands and results

All Cargo commands used the required non-OneDrive target directory:
`C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target`.

- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test drain`
  - PASS: 9 passed, 0 failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test core_v02_vectors --test control --test multi_channel --test multi_stream --test application_stream --test channel_binding --test channel_lifecycle --test drain`
  - PASS: 30 passed, 0 failed across the eight requested targets.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml`
  - PASS: 76 unit, integration, and documentation tests; 0 failed.
- `python -m pytest tests/protocol/test_registry.py tests/protocol/test_schemas.py tests/protocol/test_states.py tests/protocol/test_vectors.py -q`
  - PASS: 62 passed, 0 failed.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check`
  - PASS.
- `cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings`
  - PASS after replacing an eight-argument test helper with a grouped binding.
- `git diff --check`
  - PASS.

## Files

Created:

- `crates/nbsr-transport/tests/drain.rs`
- `docs/protocol/core-v0.2-channel-lifecycle-schema-proposal.md`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-7-report.md`

Modified:

- `crates/nbsr-transport/Cargo.toml`
- `crates/nbsr-transport/src/admission.rs`
- `crates/nbsr-transport/src/audit.rs`
- `crates/nbsr-transport/src/channel_lifecycle.rs`
- `crates/nbsr-transport/src/channel_registry.rs`
- `crates/nbsr-transport/src/channel_streams.rs`
- `crates/nbsr-transport/src/core_v02.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/src/session.rs`

`Cargo.lock`, Core v0.1 protocol artifacts, generated artifacts, and
`.codex-test-temp-w4/` were not modified or staged.

## Commit

Subject: `feat(wp4): bound channel and session drain`

The immutable commit object ID is returned in the task handoff after this
report is included in that commit.

## Self-review

- The wire decoder is closed and version-gated; it introduces no new message
  code and does not use an all-zero channel sentinel for session drain.
- Every received lifecycle control is bound to the exact session, channel,
  route, grant digest, unique request ID, and strictly advancing source
  sequence before mutation.
- Drain is not authority: deadline calculation only shortens existing
  lifetimes, and all new route, stream, application-stream, reservation, and
  binding work is denied immediately.
- Audit is committed before state mutation. At a forced deadline, audit failure
  is surfaced through `AuditIntegrity` while safety enforcement still resets
  or closes through the adapter.
- Quinn reset/stop and connection-close operations remain in
  `quinn_adapter.rs`; lifecycle/session modules contain policy and state only.
- Channel reset is scoped by channel ID and the sibling-isolation regression
  passed. Session close is scoped to one `TransportConnection` and the
  unrelated-session loopback regression passed.
- Replay and tombstone state survives close/revoke; revocation takes precedence
  over drain.

## Concerns

No Task 7 blocker remains. Deadline progression is intentionally driven by
callers supplying monotonic seconds to the enforcement APIs; integrating those
calls into a production scheduler is outside this task's prototype scope.

## Review round 1 of 5: authority and teardown corrections

### Findings and root causes

1. Session drain stored only its requested/session deadline. It did not map each
   active grant's Unix expiry into the injected monotonic clock, so adapter
   enforcement could leave an accepted channel alive until the 30-second
   session boundary.
2. `ROUTE_REVOKE` and `ROUTE_CLOSE` were public `ControlSession` transitions.
   They removed logical stream state but bypassed the connection-owned tracked
   Quinn streams, so a live target was not reset.

### RED/GREEN evidence

- RED: the completed loopback regressions failed to compile with 13 intended
  missing-API errors: the trusted Unix-plus-monotonic session-drain signature
  was absent at three call sites and adapter-bound revoke/close methods were
  absent at ten call sites. The test fixtures otherwise compiled.
- GREEN: focused `drain` passed 11/11. A requested 30-second session drain now
  resets a preaccepted target at its one-second grant deadline while the
  session remains `Draining` until second 30.
- GREEN: real adapter tests preaccept target streams for revoke and close.
  Connection mismatch, wrong digest, and audit exhaustion do not reset or
  consume the controls. After an audit slot is available, the exact same valid
  controls commit and immediately reset only the target; the live sibling
  completes normally after both operations.

Two fixture-only failures occurred while reaching GREEN and did not require
production changes: generated stream request IDs initially collided with route
request IDs, and the first layout exceeded the configured two-concurrent-bidi
limit and assumed reusable one-message Application Streams. The final test uses
independent IDs and sequences real streams within both transport contracts.

### Implementation and ordering review

- `begin_session_drain(monotonic_now, unix_now, requested_seconds)` prepares a
  bounded snapshot of every active channel's earliest grant, existing channel,
  and session deadline. The session-start audit occurs before the snapshot is
  committed, so audit failure leaves session and channel deadlines unchanged.
- Session enforcement deterministically enumerates due channels, commits their
  logical deadline transition, and resets each exact tracked channel before
  separately enforcing the later session close.
- Public revoke/close entry points now belong to `AuthenticatedConnection`.
  They reject connection mismatch first, then delegate validation, audit, and
  logical commit to crate-private session handlers, and call `reset_channel`
  only after success. Invalid and audit-failed controls cannot trigger reset.
- Replay/tombstone retention, terminal revoke precedence, sibling isolation,
  adapter confinement, and frozen Core v0.1 behavior remain intact.

### Files changed in review round 1

- `crates/nbsr-transport/src/channel_registry.rs`
- `crates/nbsr-transport/src/admission.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/tests/drain.rs`
- `docs/protocol/core-v0.2-channel-lifecycle-schema-proposal.md`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-7-report.md`

### Verification

- Focused drain: 11 passed, 0 failed.
- Required eight-target Rust matrix: 32 passed, 0 failed.
- Full Rust unit/integration/doctest suite: 78 passed, 0 failed.
- Frozen Core v0.1 Python protocol suite: 62 passed, 0 failed.
- Formatting, clippy with warnings denied, and staged diff checks: required
  before the review-round commit.

### Commit and concerns

Commit subject: `fix(wp4): enforce lifecycle transport teardown`.

No blocker remains. Enforcement still uses caller-supplied trusted clock values
and explicit scheduling, consistent with the prototype boundary documented
above.

## Review round 2 of 5: public boundary and audit-integrity aggregation

### Findings and root causes

1. `ControlSession::revoke_channel` and `ControlSession::close_channel` remained
   public direct logical mutators after the received-control handlers were
   moved behind `AuthenticatedConnection`. A caller could therefore bypass the
   connection-owned tracked-stream reset.
2. `AuthenticatedConnection::enforce_session_drain` reset each due channel but
   discarded that channel's `DrainEnforcement::Enforced` audit-integrity field.
   If the audit log was exhausted, safety reset still occurred but the public
   result incorrectly reported ordinary pending state with no typed failure.

### RED/GREEN evidence

- RED public boundary: two new `compile_fail` examples compiled successfully
  against the old public mutators, so doctests failed 2/8 while the six existing
  boundary examples passed.
- RED aggregation: focused drain failed to compile because the wished-for
  `SessionDrainEnforcement` typed public result did not exist.
- GREEN public boundary: doctests pass 8/8. The logical revoke/close helpers are
  crate-private and used only behind exact-connection adapter operations; the
  former external lifecycle regression now sends a closed `ROUTE_REVOKE`
  envelope through `AuthenticatedConnection`.
- GREEN aggregation: focused drain passes 12/12. With the audit log filled by
  the session-start record, a one-second due channel returns
  `SessionDrainEnforcement::Pending { audit_integrity: Failed }`; the adapter
  still resets the target, the session stays draining, and deterministic due
  channel order is preserved.

The safe-path test migration initially reused a request ID from its existing
audit-fill range and correctly received `Replay`; moving lifecycle fixture IDs
outside that range resolved the test-only collision without a production
change.

### Implementation and self-review

- `SessionDrainEnforcement` distinguishes pending from session-enforced state
  while carrying aggregate `AuditIntegrity` in both variants. This prevents a
  per-channel failure from being misrepresented and avoids treating
  `Pending { Failed }` as authority to close the whole connection early.
- Session enforcement starts at `Recorded`, folds every sorted due-channel
  result to `Failed` if any forced audit fails, resets every enforced target,
  then folds the session-deadline result. Connection close occurs only for the
  session-level `Enforced` variant.
- Received revoke/close handlers validate and audit first, call crate-private
  logical mutators, commit replay/sequence state, and return to the adapter;
  only adapter success triggers `reset_channel`.
- Obsolete revoked-to-closed external plumbing was removed from production
  admission state. Registry-only terminal transition coverage remains confined
  to unit tests, while public regressions exercise the supported wire/adapter
  path.

### Files changed in review round 2

- `crates/nbsr-transport/src/channel_lifecycle.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/src/admission.rs`
- `crates/nbsr-transport/src/channel_registry.rs`
- `crates/nbsr-transport/tests/drain.rs`
- `crates/nbsr-transport/tests/multi_stream.rs`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-7-report.md`

### Verification

- Focused drain: 12 passed, 0 failed.
- Safe-path multi-stream regression: 3 passed, 0 failed.
- Public-boundary doctests: 8 passed, 0 failed.
- Full Rust unit/integration/doctest suite: 81 passed, 0 failed.
- Frozen Core v0.1 Python protocol suite: 62 passed, 0 failed.
- Formatting, warning-denied clippy, and staged diff checks are required before
  the round-two commit.

### Commit and concerns

Commit subject: `fix(wp4): preserve lifecycle enforcement integrity`.

No blocker remains. `AuditIntegrity::Failed` is an aggregate fail-closed signal;
it does not reopen work, suppress target reset, or accelerate the later session
connection close.
