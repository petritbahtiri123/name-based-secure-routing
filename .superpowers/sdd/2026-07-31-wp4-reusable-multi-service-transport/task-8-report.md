# Task 8 report: fail-closed same-edge channel resumption

## Status

Complete. WP4 now has a bounded internal same-edge resume store that can
correlate one normally closed eligible channel with a fully fresh,
independently authorized channel on a newly authenticated Transport Session.
It restores no authority or channel state, adds no wire message, and leaves
Core v0.1 unchanged.

## RED/GREEN cycles

1. Bounded input types
   - RED: the focused test failed to compile because `TrustProfileId`,
     `ResumeHandle`, and their typed validation errors did not exist.
   - GREEN: added bounded validated trust-profile identifiers and exact
     32-byte nonzero opaque handles whose `Debug` output is redacted.
2. Explicit authenticated scope
   - RED: session construction rejected the new required trust-profile
     argument because authenticated sessions had no caller-approved profile.
   - GREEN: `ControlSession` now requires and retains the explicit profile and
     the live connection's negotiated ALPN; neither value is inferred.
3. Store and happy path
   - RED: the focused test failed to compile on the missing manager, issuance,
     preflight, consume, correlation, and replay result.
   - GREEN: implemented bounded policy-mediated issuance and adapter-mediated
     single-use consume returning only old/new channel IDs.
4. Fresh-authority separation
   - RED: a new channel that reused the old exact grant digest was incorrectly
     accepted.
   - GREEN: consume now requires a different connection capability, session
     ID, channel ID, grant digest, route ID, grant nonce, client nonce, edge
     nonce, and live exporter binding, while matching the exact reuse scope,
     service, policy, and client-key thumbprint.
5. Cross-edge preflight
   - RED: audit types had no resume rejection action or cross-edge reason.
   - GREEN: the adapter rejects either-edge mismatch as `CrossEdgeDenied`
     before channel allocation, audits it, preserves the handle, and permits a
     later exact same-edge attempt.
6. Retention boundaries
   - RED: expired issuance did not leave the required resume rejection as the
     final audit event.
   - GREEN: retention is bounded by the minimum of 30 monotonic seconds, prior
     grant expiry, session authority deadline, and channel authority deadline;
     second 30 is valid and second 31 consumes expiry terminally.
7. Adapter and replay audit boundaries
   - RED: wrong-adapter, consumed-handle replay, and unbound-new-channel
     attempts returned typed errors without appending rejection audit events.
   - GREEN: all three paths audit before any resume-store or channel mutation.

Two deliberate mutation checks validate important negative boundaries:

- Making direct manager consume public caused its compile-fail doctest to fail
  exactly as intended; restoring `pub(crate)` returned all doctests to green.
- Reducing capacity from 4096 to 4095 made the exact capacity test fail;
  restoring 4096 returned the focused test to green.

## Exact scope and API

- The exact reuse key is `(source_edge_id, destination_edge_id,
  trust_profile_id, ALPN, protocol_version)` with ALPN `nbsr-quic-1` and
  protocol version 2.
- `TrustProfileId::new` accepts only validated 1..64-byte lowercase NBSR
  identifiers. It is required during safe authenticated session construction.
- `ResumeHandle::new` accepts exactly 32 supplied nonzero bytes. The caller is
  the CSPRNG boundary; the store does not generate handles.
- `SameEdgeResumeManager::issue` is the only public mutation on the manager.
  Direct preflight and consume operations are crate-private.
- `AuthenticatedConnection::preflight_same_edge_resume` and
  `consume_same_edge_resume` enforce the exact live connection capability and
  keep Quinn-owned checks at the adapter boundary.
- `ResumeCorrelation` exposes only the old and new channel IDs.
- Records retain correlation, exact scope, service/policy/client identity,
  non-secret freshness comparators, deadlines, and eligibility state. They do
  not retain exporter values, TLS secrets, complete grants, payloads, Origin
  Endpoints, DNS data, or stream state.
- Mismatches do not consume the handle. Successful use and expiry do.
- This is an origin-free in-process policy/store API. It introduces no resume
  wire body and makes no independent interoperability, cross-edge handover,
  replica-state, 0-RTT, or production claim.

## Counts and behavioral evidence

- Capacity is exactly 4096 retained records; the 4097th issuance is rejected
  without eviction.
- Retention accepts the exact 30-second boundary and rejects/consumes at 31;
  shorter grant, session, and channel authority deadlines win.
- Audit capacity remains Task 6's exact 1024 events. Exhaustion rejects issue
  and otherwise valid consume before resume-store mutation.
- Eligibility covers only a normally closed channel that was previously
  active and live-exporter-bound. Candidate, active, unbound, draining,
  revoked, forced-close, expired, and audit-integrity-failed channels are
  ineligible.
- Real loopback coverage uses two independent Quinn handshakes and proves
  unequal live exporters, fresh sessions/channels/grants/routes/nonces, atomic
  replay rejection, no old-state copying, and sibling isolation.
- Failure coverage includes same connection/session/channel/grant digest/route/
  nonce, wrong service/policy/client key/trust/either edge/role/peer/adapter,
  expired authority, unbound new channel, replay, capacity, and audit
  exhaustion.

## Commands and results

All Cargo test and Clippy commands used the required non-OneDrive target:
`C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target`.

- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test resumption`
  - PASS: 10 passed, 0 failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test channel_binding --test channel_lifecycle --test drain --test multi_channel --test multi_stream --test application_stream --test resumption`
  - PASS: 39 passed, 0 failed across all seven requested targets.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml`
  - PASS: 83 unit/integration tests plus 9 compile-fail doctests; 0 failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --doc`
  - PASS: 9 passed, 0 failed.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --all -- --check`
  - PASS.
- `cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings`
  - PASS.
- `git diff --check`
  - PASS (Git emitted only the checkout's existing LF-to-CRLF warnings).

## Files

Created:

- `crates/nbsr-transport/src/resumption.rs`
- `crates/nbsr-transport/tests/resumption.rs`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-8-report.md`

Modified:

- `crates/nbsr-transport/src/admission.rs`
- `crates/nbsr-transport/src/audit.rs`
- `crates/nbsr-transport/src/channel_registry.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/tests/application_stream.rs`
- `crates/nbsr-transport/tests/drain.rs`
- `crates/nbsr-transport/tests/multi_channel.rs`
- `crates/nbsr-transport/tests/multi_stream.rs`

`Cargo.lock`, Core v0.1 artifacts, generated artifacts, and
`.codex-test-temp-w4/` were not modified or staged.

## Commit

Subject: `feat(wp4): resume channels on the same edge`

The immutable commit object ID is returned in the task handoff after this
report is included in that commit.

## Self-review

- A handle is correlation only. Fresh HELLO/session establishment, signed
  RouteGrant admission, proof/nonces, ROUTE_ACCEPT, and live exporter binding
  all precede consume.
- Audit records issue, consume, and every rejection before mutation. Queue
  exhaustion cannot create, remove, or consume resume authority.
- Terminal channel snapshots retain only resume-safe metadata. No binding or
  exporter value crosses into the closed-channel record or resume store.
- The manager has no public direct consume path; the compile-fail boundary
  forces callers through the connection-owned adapter.
- Successful consume removes the record atomically and returns correlation
  only. It does not restore streams, counters, audit sequence, replay entries,
  bindings, drain state, or tombstones.
- Exact scope and authority mismatches preserve the handle, while expiry and
  success consume it. Cross-edge denial happens before allocation.
- Quinn operations remain confined to `quinn_adapter.rs`; policy/state logic
  contains no transport operations.
- Existing lifecycle, drain, channel-binding, multi-channel, multi-stream, and
  application-stream regressions all pass.

## Concerns

No Task 8 blocker remains. The prototype intentionally relies on
caller-supplied unpredictable handles and trusted monotonic clock values, and
keeps correlations in process memory. A future wire-carried handle,
cross-process store, or production scheduler requires a separate design and
schema gate; none is implied here.

## Review round 1 of 5: audited retention, live sessions, and gated admission

### Findings and RED/GREEN evidence

1. Expired records could capacity-lock the manager.
   - RED: the strengthened 4096-record regression returned `Replay` when an
     expired handle was reused at second 31 instead of purging the complete
     expired set. The first RED also lacked a typed purge audit action.
   - GREEN: a valid issue attempt computes at most 4096 expired handles,
     records one `ResumePurged` audit before mutation, removes their associated
     preflights, then evaluates replay and capacity. With the audit queue full,
     all 4096 records remain and no new record is issued; after an audit slot is
     available, the expired handle is reusable and only the new record remains.
2. Target-session and exact-Quinn liveness were incomplete.
   - RED: a target session whose authority deadline equaled `monotonic_now`
     returned `Ok`, and both peer/local closed Quinn connections returned `Ok`
     from preflight. A consume mutation that removed the adapter liveness gate
     incorrectly returned a successful correlation after peer close.
   - GREEN: preflight, resume admission, and consume all require the exact
     session-owned connection capability and `Connection::close_reason() ==
     None`. Session authority deadline equality is terminal `Expired` with an
     `Expired` audit reason; draining/closed sessions are `Ineligible`. Real
     loopback covers peer-closed consume and adapter-local-close preflight while
     a second `ControlSession` remains logically active.
3. Fresh RouteGrant expiry was not terminal.
   - RED: after an expired fresh grant was audited, the manager still retained
     one record and a later fresh attempt could reuse it.
   - GREEN: audit exhaustion still preserves the handle; once the expiry audit
     succeeds, the handle and all associated preflight state are removed before
     returning `Expired`, and later use returns `Replay`.
4. Cross-edge no-allocation was advisory because ordinary route admission
   could precede a later consume call.
   - RED: the focused success test failed to compile because no
     resume-specific admission method existed and preflight returned `()`.
   - GREEN: `ResumePreflight` is an opaque, redacted, non-cloneable capability
     backed by a bounded one-per-handle manager record. It is bound to the
     handle, exact reuse key, target session ID, authenticated role/peer, and
     exact connection capability. `AuthenticatedConnection::
     accept_route_open_for_resume` validates it before calling ordinary fresh
     RouteGrant admission and then associates only that admitted channel.
     Consume requires the same capability and channel association.

### Capability and bypass properties

- Duplicate preflight for one handle is `Replay`; the number of retained
  preflights cannot exceed the 4096 retained handles, and expiry/purge/success
  removes associated preflight state.
- Preflight issuance adds `ResumePreflightIssued` before mutation. An
  intentional audit-order mutation made the strengthened audit-exhaustion test
  fail with `Replay`; restoring audit-before-insert returned it to green.
- A capability used with another exact session/connection is rejected before
  route allocation. The cross-edge target remains at zero active channels.
- An ordinary channel admitted after preflight cannot be relabeled: consume
  returns `FreshAuthorizationRequired` because only the resume-specific route
  path can associate a channel with the capability.
- Successful correlation removes the handle and preflight together after the
  consume audit. Reuse of the capability is `Replay`.
- Direct manager consume remains crate-private. Temporarily making the current
  capability-shaped signature public caused exactly the intended compile-fail
  doctest to fail (8/9); restoring `pub(crate)` returned 9/9 to green.
- No resume wire message, closed ROUTE_OPEN change, cross-edge handover, 0-RTT,
  state restoration, or independent interoperability claim was introduced.

### Files changed in review round 1

- `crates/nbsr-transport/src/audit.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/src/resumption.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/tests/resumption.rs`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-8-report.md`

`Cargo.lock`, Core v0.1 artifacts, generated artifacts, and
`.codex-test-temp-w4/` were not modified or staged.

### Verification

All Cargo commands used the required non-OneDrive target directory.

- Focused resumption: 13 passed, 0 failed.
- Required seven-target matrix: 42 passed, 0 failed.
- Full crate: 86 unit/integration tests plus 9 compile-fail doctests passed;
  0 failed.
- Explicit doctests: 9 passed, 0 failed after restoring the visibility
  mutation.
- Formatting: the first final check reported one line-wrap-only difference;
  rustfmt was applied and the repeated check passed.
- Clippy with all targets and warnings denied: passed.
- `git diff --check`: required before the review-round commit.

### Commit and concerns

Commit subject: `fix(wp4): gate same-edge resume admission`.

No review-round blocker remains. Capabilities and correlations remain bounded
in-process prototype state using caller-supplied trusted clock values; future
wire transport or cross-process persistence remains a separate schema and
design gate.

## Review round 2 of 5: exact preflight authority and deadline semantics

### Findings and RED/GREEN evidence

1. Reused transport/session authority reached post-admission validation.
   - RED: after adding candidate-count observations, the same exact Quinn
     connection produced a successful preflight instead of
     `FreshAuthorizationRequired`.
   - GREEN: preflight now compares the retained old context with the current
     target scope before minting a capability. Exact connection-capability
     reuse, session-ID reuse, local-role mismatch, or authenticated-peer
     mismatch is audited and rejected. Real loopback assertions keep candidate
     and active channel counts at zero and preserve all three handles.
2. Sequential preflight IDs were not manager-specific capabilities.
   - RED: manager A's first token was accepted by manager B because both
     managers independently minted ID 1, allocating an active channel.
   - GREEN: every manager owns a private process-local `Arc` marker and every
     token carries that marker plus its ID. Validation requires exact pointer
     identity before allocation. Manager A's token is `Replay` at manager B,
     candidate/active counts remain zero, and manager B's own token remains
     valid through fresh admission, binding, and consume.
3. A shared inclusive expiry comparison extended old authority at equality.
   - RED: a record capped by an old session authority deadline of 130 still
     consumed successfully at monotonic second 130.
   - GREEN: handle TTL and prior RouteGrant expiry retain their documented
     inclusive semantics (`now > expiry`), while old session/channel authority
     is due at `now >= deadline`. The same predicate is used by issue purging,
     preflight, and capability validation. A 4096-record regression rejects
     consume at exact equality, removes that expired record, then proves one
     audited purge of the remaining 4095 unlocks capacity for a fresh record.
     The exact +30 and prior-grant boundaries remain valid.
4. An audited post-admission mismatch left its capability reusable forever.
   - RED: after a successful mismatch audit, retrying the same capability
     returned `Mismatch` again instead of `Replay`.
   - GREEN: a successfully audited post-admission authority or binding
     mismatch removes only that preflight association and retains the handle.
     Audit exhaustion returns `AuditUnavailable` without mutation; after an
     audit slot is available the mismatch retires the capability, its reuse is
     `Replay`, and a fresh preflight plus a fresh valid channel can consume the
     retained handle.

### Scope and self-review

- All four old/new authority comparisons happen during preflight, before the
  resume-specific path can call ordinary RouteGrant admission.
- `ResumePreflight` remains opaque, redacted, non-cloneable, and usable only
  with the manager instance that minted it. The private marker is not derived
  from a counter or caller-controlled value.
- Inclusive correlation/grant retention and exclusive monotonic authority
  deadlines are represented separately instead of collapsing them into one
  scalar expiry.
- Every new state mutation remains after its corresponding audit. In
  particular, audit exhaustion cannot retire the mismatched preflight or
  consume its handle.
- No resume wire body, cross-edge handover, 0-RTT, state restoration, or
  independent interoperability claim was added.

### Files changed in review round 2

- `crates/nbsr-transport/src/admission.rs`
- `crates/nbsr-transport/src/channel_registry.rs`
- `crates/nbsr-transport/src/resumption.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/tests/resumption.rs`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-8-report.md`

`Cargo.lock`, Core v0.1 artifacts, generated artifacts, and
`.codex-test-temp-w4/` were not modified or staged.

### Verification

All Cargo commands used the required non-OneDrive target directory.

- Focused resumption after all changes: 17 passed, 0 failed.
- Required seven-target matrix: 46 passed, 0 failed.
- Full crate: 90 unit/integration tests plus 9 compile-fail doctests passed;
  0 failed.
- Explicit doctests: 9 passed, 0 failed.
- Formatting check: passed after applying rustfmt.
- Clippy with all targets and warnings denied: passed.
- `git diff --check`: passed before staging; the staged check is required
  immediately before commit.

### Commit and concerns

Commit subject: `fix(wp4): bind resume authority before admission`.

No review-round blocker remains. Correlations and manager markers remain
bounded process-local prototype state using caller-supplied trusted clock
values. Future wire transport, cross-process persistence, or production
scheduling remains a separate schema and design gate.
