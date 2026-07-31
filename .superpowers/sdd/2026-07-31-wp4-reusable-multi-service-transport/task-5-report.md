# Task 5 report: Live Quinn/rustls Service Channel binding

## Status

Complete. Accepted Service Channels now require an opaque binding derived from
the live authenticated Quinn connection before `STREAM_OPEN`, `STREAM_ACCEPT`,
or application-byte authorization. The live exporter call uses only Quinn's
public API and remains confined to `quinn_adapter.rs`.

## RED evidence

### Live exporter RED

Command:

```powershell
$env:CARGO_TARGET_DIR='C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target'
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test channel_binding
```

Observed before implementation: compilation failed at both peer calls because
`AuthenticatedConnection::export_channel_binding` did not exist. These were the
expected missing-live-exporter failures.

### Mandatory session-binding RED

Command:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test multi_stream
```

Observed before implementation: compilation failed on the missing
`AuthenticatedConnection::bind_channel` operation and missing
`SessionReject::ChannelBindingRequired` result. This was the expected absent
mandatory-binding gate.

After the gate was added, the unmigrated application-stream regression exposed
the old implicit path: `application_stream` ran 1 passed and 2 failed, both at
`authorize_stream_open` with `ChannelBindingRequired`. Migrating those tests to
the live operation produced 3 passed.

### Sibling-reuse RED

The focused registry test initially failed compilation because the opaque live
binding constructor had no originating `channel_id`. The minimal change tagged
the opaque value internally and made installation reject a sibling channel
without mutating it.

## GREEN evidence

- Both authenticated loopback peers derive equal opaque values from the same
  handshake and context.
- A second TLS handshake using the same PKI and identical NBSR context derives
  a different value.
- Mutating each variable context input (session, either edge, channel, route,
  grant digest, service, transport, port, policy, client nonce, or edge nonce)
  changes the live binding. Task 4 retains the independently verified fixed
  profile/version, label, output-length, ordering, type, and invalid-context
  coverage.
- Pending, rejected, unknown, unbound, wrong-peer, wrong-handshake, and sibling
  binding attempts fail without making the affected channel usable.
- The pre-binding `STREAM_OPEN` failure does not consume its request; the same
  request succeeds after live binding. Bound sibling channels retain independent
  multi-stream behavior.
- `ChannelBinding` has no public constructor or byte accessor, and its `Debug`
  output is exactly `ChannelBinding([REDACTED])`.

## Public API decision

`AuthenticatedConnection::export_channel_binding` performs the fixed public
Quinn exporter call and returns a comparable but otherwise opaque
`ChannelBinding`. It accepts the already frozen Task 4 context type, but the
returned value has no public activation path.

The only public activation operation is
`AuthenticatedConnection::bind_channel(&mut ControlSession, channel_id)`. It
asks the session for a crate-private owned request assembled from verified
HELLO, admission, policy, and correlated `ROUTE_ACCEPT` state; checks the live
connection role and authenticated peer against the request; derives the fixed
binding; and installs it through crate-private methods. There is no
`attach_binding(bytes)`, no public registry, no public binding constructor, and
no public byte read. Task 4's separate fixture-only `ServiceChannelBinding`
remains readable for conformance vectors and cannot be supplied to a session.

## Commands and counts

All Cargo commands used the required non-OneDrive target:
`C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target`.

```text
cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test channel_binding
  PASS: 4 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test exporter_vectors --test handshake --test control --test multi_channel --test multi_stream --test application_stream --test channel_binding
  PASS: 28 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml
  PASS: 53 unit/integration tests plus 6 compile-fail doctests (59 total)

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
  PASS

cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
  PASS

git diff --check
  PASS
```

## Files

- Modified `crates/nbsr-transport/src/channel_binding.rs`.
- Modified `crates/nbsr-transport/src/quinn_adapter.rs`.
- Modified `crates/nbsr-transport/src/session.rs`.
- Modified `crates/nbsr-transport/src/admission.rs`.
- Modified `crates/nbsr-transport/src/channel_registry.rs`.
- Modified `crates/nbsr-transport/src/lib.rs`.
- Added `crates/nbsr-transport/tests/channel_binding.rs`.
- Modified `crates/nbsr-transport/tests/multi_channel.rs`.
- Modified `crates/nbsr-transport/tests/multi_stream.rs`.
- Modified `crates/nbsr-transport/tests/application_stream.rs`.
- Added this report.

## Self-review

- The canonical context is hashed before the exporter call. The label and
  32-byte output length are private constants, and the sole
  `export_keying_material` invocation is in `quinn_adapter.rs`.
- Established session state retains only the verified non-secret HELLO inputs.
  Active admission retains the exact RouteGrant digest, not complete grant
  wire bytes; the verified service policy supplies the policy hash.
- Registry activation and live binding are distinct: correlated
  `ROUTE_ACCEPT` moves candidate metadata active, while every stream and byte
  operation requires the binding option to be present. Failed installation
  never replaces an existing value.
- The live binding carries its originating channel ID privately so even a
  crate-internal attempt to reuse it for a sibling is rejected. Equality still
  compares the exporter value, so channel-context mutation tests do not pass
  merely because of that internal tag.
- No OriginSet, Origin Endpoint, NameRelay, lifecycle, drain, resume, UDP,
  cross-edge continuity, 0-RTT, HTTP/3, MASQUE, Core v0.1, dependency, lockfile,
  or public-document claim was changed.

## Commit

Commit subject: `feat(wp4): bind channels to tls exporter`.
The immutable Git object ID is returned in the task handoff after this report
is included in that commit.

## Concerns

- Task 5 proves both peers' exporter agreement locally but adds no new wire
  field carrying the binding or a cross-peer confirmation value; existing Core
  v0.2 message bodies remain unchanged.
- `ServiceChannelBinding::as_bytes` intentionally remains public only for the
  frozen Task 4 fixture conformance API. It is a different type and cannot
  activate or bind a live `ControlSession`.

## Review round 1/5: exact originating connection

### Finding and correction

The initial implementation retained only authenticated peer name and role in
`ControlSession`. Before any binding existed, a fresh connection with the same
PKI, role, and peer name could therefore install its own exporter result into a
session created from another handshake. The earlier report statement that
"wrong-handshake" attempts fail was too broad: the original test attempted the
replacement only after the originating handshake had installed a different
value, so it proved replacement protection but not exact session provenance.

`AuthenticatedConnection` now receives one adapter-private
`ConnectionBindingCapability` after Quinn authentication. The capability is an
`Arc` allocation around a private marker; only the adapter can construct it.
`ControlSession::new` clones that opaque capability, keeping the allocation
alive for the complete session lifetime, and `bind_channel` requires
`Arc::ptr_eq` before it reads a binding request or invokes the exporter. A
fresh connection cannot acquire the same live allocation identity, while the
capability has no public type export, constructor, accessor, or debug output.

Source and destination peers now use separate `ControlSession` instances,
each created from that peer's own exact authenticated connection. HELLO peer
checks are orientation-aware: a Source session authenticates the destination
edge, and a Destination session authenticates the source edge. Both retain the
same verified source/destination transcript values for exporter context.

### TDD evidence

The first focused RED moved the same-PKI replacement before any legitimate
binding. The assertion expected `ConnectionMismatch` but observed `Ok(())`,
reproducing the finding exactly. After expressing the required two-session
orientation, a second RED failed source-side `CLIENT_HELLO` with
`ControlRejected`, proving the prior session model was destination-oriented
only.

After the capability and orientation changes, the focused test proves:

- session A rejects same-PKI/same-name/same-role connection B with
  `ConnectionMismatch` before any binding;
- the channel remains unbound and rejects the same `STREAM_OPEN` request;
- originating connection A then binds and authorizes that unchanged request;
- source A and destination A each bind through a session created from their own
  exact connection; and
- wrong-name, pending, unknown, sibling, and stream-isolation checks remain
  intact.

### Review-round verification

```text
cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test channel_binding --test multi_stream
  PASS: 6 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test exporter_vectors --test handshake --test control --test multi_channel --test multi_stream --test application_stream --test channel_binding
  PASS: 28 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml
  PASS: 53 unit/integration tests plus 6 compile-fail doctests (59 total)

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
  PASS

cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
  PASS

git diff --check
  PASS
```

Review-fix commit subject: `fix(wp4): bind session to exact quinn connection`.
The immutable Git object ID is returned in the review handoff after this report
append is included in that commit.
