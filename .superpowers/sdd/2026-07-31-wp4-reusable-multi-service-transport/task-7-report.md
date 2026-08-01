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
