# Task 6 report: bounded audit, replay, revocation, and containment

## Status

Complete. Channel lifecycle is explicit and session-mediated, audit and replay
state are bounded, revocation is terminal, and lifecycle/audit/quota failures
remain scoped without changing active siblings.

## RED/GREEN cycles

### Cycle 1: hard bounds and safe audit state

RED command:

```powershell
$env:CARGO_TARGET_DIR='C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target'
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test channel_lifecycle
```

Observed before implementation: compilation failed on the missing audit types,
explicit `ChannelState`, fallible policy constructor, audit read/pop operations,
and `AuditUnavailable` rejection. This was the expected missing-feature RED.

GREEN: 3 passed. The tests cover 32/33 authorized services, 4096 accepted replay
entries and 4097 rejection before audit mutation, existing-key replay at
capacity, audit sequences 1 through 1024, the next mutation's rejection with
unchanged candidate state, and safe-field-only debug output.

### Cycle 2: terminal revocation and sibling containment

RED command:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test multi_stream revoked_channel_is_terminal_while_bound_sibling_remains_usable
```

Observed before implementation: compilation failed with 14 expected missing
lifecycle/session API errors for revoke, close, state, tombstone, audit access,
and typed invalid-state rejection.

GREEN: 1 passed through a real authenticated Quinn session. It proves terminal
revoke/close, exact tombstone expiry, post-revoke binding/stream/byte denial,
wrong-channel containment, usable bound sibling state, and audit-full revocation
failure without sibling unbinding or lifecycle mutation.

### Regression correction

The first focused matrix run had 25 passing tests and one existing multi-stream
failure: a pending channel bind returned `InvalidChannelState` instead of the
existing `UnexpectedMessage`. The cause was an overly broad mapping of every
known non-active state. The mapping now preserves the pending-channel contract
while reserving `InvalidChannelState` for terminal/draining states. The complete
multi-stream suite then passed 3/3.

## Exact bounds and counts

- Audit queue: 1024 retained events; event 1025 is rejected without audit,
  lifecycle, stream, quota, or request-replay mutation.
- Audit sequence: starts at 1, is monotonic, reaches `u64::MAX` once, and then
  fails closed without wrapping.
- Replay/tombstone store: 4096 accepted/candidate entries; entry 4097 is rejected
  before candidate or audit mutation, while an existing replay key is still
  reported as replay.
- Authorized service policy: 32 entries accepted, 33 rejected before admission
  state construction.
- Revocation tombstone: `max(grant_expires_at + 30, revoked_at + 30)` with
  saturating arithmetic; the saturation case retains `u64::MAX`.
- Lifecycle: `Candidate -> Active -> Revoked -> Closed`; `Draining` is explicit
  but has no Task 6 transition.

## Public-boundary decisions

- Public lifecycle mutation is available only on `ControlSession` via
  `revoke_channel` and `close_channel`; the registry, replay store, audit log,
  audit insertion, binding installation, and stream transition commits remain
  crate-private.
- `ControlSession` and `DestinationAdmission` expose read-only audit iteration
  plus bounded front-pop access. They expose no arbitrary insertion or mutation.
- `AuditEvent` contains only Unix time, per-session sequence, session ID,
  optional channel ID, validated ASCII `SafeServiceId`, typed action, typed
  outcome, and typed safe reason. It stores no exporter, grant wire/signature,
  payload, Origin Endpoint, hostname/DNS, certificate, or arbitrary error text.
- Stream authorization uses prepare/audit/commit transitions. Audit capacity is
  checked after validation but before request replay, stream gate, quota, or
  lifecycle state is mutated.
- Quinn exporter and stream reset operations remain adapter-confined. No raw
  lifecycle, registry, audit, tombstone, or stream-reset bypass was added.
- `DestinationAdmission` construction is fallible so the 33-service policy is
  rejected before a session or admission registry exists.

## Files

- Added `crates/nbsr-transport/src/audit.rs`.
- Added `crates/nbsr-transport/src/channel_lifecycle.rs`.
- Added `crates/nbsr-transport/tests/channel_lifecycle.rs`.
- Modified `crates/nbsr-transport/src/channel_registry.rs`.
- Modified `crates/nbsr-transport/src/channel_streams.rs`.
- Modified `crates/nbsr-transport/src/stream_gate.rs` for cloneable prepared
  transitions.
- Modified `crates/nbsr-transport/src/session.rs`.
- Modified `crates/nbsr-transport/src/admission.rs`.
- Modified `crates/nbsr-transport/src/lib.rs`.
- Updated focused test callers in `tests/admission.rs`,
  `tests/application_stream.rs`, `tests/multi_channel.rs`,
  `tests/multi_stream.rs`, and `tests/route_context.rs` for fallible policy
  construction and lifecycle containment coverage.
- Added this report.

## Verification

All Cargo commands used the required non-OneDrive target.

```text
cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test channel_lifecycle
  PASS: 3 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test admission --test route_context --test control --test multi_channel --test multi_stream --test application_stream --test exporter_vectors --test channel_binding --test channel_lifecycle
  PASS: 26 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml
  PASS: 60 unit/integration tests plus 6 compile-fail doctests (66 total)

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
  PASS

cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
  PASS

git diff --check
  PASS (Git emitted only the checkout's existing LF/CRLF conversion notices)
```

## Self-review

- Every security-relevant mutation has an audit preflight before the mutation;
  prepared stream transitions avoid partial stream/request state on audit
  failure.
- Revocation drops the target binding and every target stream state, retains
  both replay keys and its tombstone, and cannot be repeated or reversed.
- Candidate, terminal, unknown, wrong-channel, binding-required, replay,
  capacity, and audit-exhaustion paths do not change siblings.
- Replay capacity is checked after existing-key lookup and before audit or
  candidate insertion; no replay or live tombstone entry is silently evicted.
- Audit sequence and tombstone arithmetic use checked/saturating operations and
  have boundary tests.
- No lifecycle wire decode, timed drain, UDP behavior, Origin Endpoint,
  NameRelay, 0-RTT, cross-edge continuity, dependency, lockfile, generated
  artifact, or public product claim was added or changed.

## Commit

Commit subject: `feat(wp4): contain channel lifecycle failures`.
The immutable object ID is returned in the task handoff after this report is
included in that commit.

## Concerns

- Task 6 records and retains tombstone expiry values but intentionally performs
  no timed pruning or drain transition; timed lifecycle behavior remains Task 7.
- Audit and replay state are process-memory session state. Exhaustion is
  intentionally fail-closed and requires bounded event consumption or a new
  session; there is no persistence claim.
