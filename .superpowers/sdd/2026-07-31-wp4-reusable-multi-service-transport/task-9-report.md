# Task 9 report: bounded native QUIC DATAGRAM UDP channels

## Status

Complete. Core v0.2 candidate sessions can carry isolated UDP application
datagrams over RFC 9221 QUIC DATAGRAM after fresh signed route admission,
correlated acceptance, and live exporter binding. The implementation is
bounded, fail-closed, and does not add fragmentation, retransmission, ordering,
MASQUE, HTTP/3, origin forwarding, or a Core v0.1 change.

## RED/GREEN cycles

1. Exact closed UDP frame
   - RED: the focused test failed to compile because `DatagramFrame`, its
     encoder/decoder, and exact peer-cap calculation did not exist.
   - GREEN: added the closed canonical numeric-key CBOR profile and rejection
     of unknown, missing, duplicate, reordered, non-preferred, tagged, float,
     indefinite, bool-as-int, wrong-type/length, zero, trailing, oversize, and
     peer-maximum-invalid inputs. The first GREEN exposed a one-byte empty-frame
     overhead error; calculating the complete encoded length fixed it.
2. Bounded Quinn-free gate
   - RED: tests failed to compile on the missing per-channel gate, sequence,
     token, queue, receive result, and typed audit mutations.
   - GREEN: added independent inbound/outbound 100-per-second token buckets
     with burst 200 and retained integer millitoken remainder, outbound
     sequence allocation, inbound high-water replay rejection, and queue 64.
3. Signed transport authority
   - RED: `RouteGrantClaims` had no decoded `allowed_transports`, and UDP route
     admission could not express or enforce signed UDP authority.
   - GREEN: Core v0.2 ROUTE_OPEN accepts exactly `tcp` or `udp`; signed grants
     accept a unique bounded subset of those exact values, and requested
     transport must be present. Existing frozen TCP bytes remain unchanged.
4. Native Quinn adapter path
   - RED: the real loopback test failed to compile on missing DATAGRAM buffer,
     maximum-size, send, receive, and pop operations.
   - GREEN: Quinn operations were confined to `quinn_adapter.rs`, buffers were
     bounded, and APIs were bound to the exact authenticated connection and
     session-owned gate. One native DATAGRAM carries one complete CBOR frame.
5. Real authenticated loopback behavior
   - RED: the first run was rejected at HELLO because test constants did not
     match the signed control-vector session inputs; after correcting those,
     the cap+1 expectation assumed a peer cap even when the negotiated path
     permitted the full 1200-byte profile cap.
   - GREEN: the signed inputs now match exactly, and cap+1 expects the precise
     profile or peer-cap rejection. Two UDP services and one TCP service share
     one authenticated connection without cross-delivery.
6. Lifecycle and signed negative path
   - RED: focused additions failed to compile against a guessed drain method
     name and then exposed missing lifecycle denial assertions.
   - GREEN: the existing `begin_session_drain` path immediately denies new UDP;
     target revoke clears its queue/gate, sibling UDP and TCP remain usable,
     and a signed TCP-only grant cannot authorize UDP or create a candidate.
7. Typed audit evidence
   - RED: the queue-drop audit lookup used a reverse iterator guarantee the
     public iterator does not expose.
   - GREEN: the assertion uses ordered filtering and verifies exact channel,
     service, denied outcome, action, and `DatagramQueueFull` reason.
8. Static quality and encapsulation
   - RED: Clippy found a test helper with too many arguments and a useless
     temporary vector; both were test-only findings.
   - GREEN: a small test specification struct and fixed slice removed both
     warnings. The datagram gate and audit callback types were made
     crate-private, and a compile-fail doctest freezes that boundary.

## Exact wire bytes and counts

- Empty payload, channel `11` repeated 16 times, sequence 1:
  `a40001501111111111111111111111111111111102010340` (25 bytes).
- A 1200-byte payload at sequence 1 is exactly 1227 encoded bytes: 27 bytes of
  map/field framing plus 1200 payload bytes.
- At peer maximum 49, the exact sequence-1 payload cap is 23 bytes; a 24-byte
  payload is rejected. At peer maximum 24, no complete frame fits.
- Body version is exactly 1; channel ID is exactly 16 nonzero bytes; sequence
  is 1 through `u64::MAX`; payload is 0 through 1200 bytes.
- Receive queue accepts exactly 64 payloads. Sequence 65 is audited and dropped
  when full, advances replay high-water, does not consume a receive token, and
  cannot be resurrected after a pop.
- Each direction starts with exactly 200 tokens. Attempt 201 at the same
  monotonic millisecond is rejected; 9 ms remains denied and 10 ms admits one
  token. Backwards time and checked-arithmetic boundaries do not mutate state.
- `u64::MAX` outbound sequence is emitted once and never wraps.

## Real-loopback evidence

- One mutually authenticated Quinn connection carries two freshly admitted,
  accepted, and exporter-bound UDP services plus one authorized TCP service.
- The negotiated UDP capacity is computed from Quinn's maximum and the exact
  next-frame encoding. This environment admitted the full 1200-byte inner
  payload; 1201 was rejected by the profile before transport mutation.
- Complete `alpha` and `bravo` payloads reached only their intended queues.
- Sixty-five native frames to one service produced exactly one typed queue
  drop while leaving the other UDP queue untouched.
- Revoking the loaded target cleared and disabled only that channel. A later
  `survives` datagram on the UDP sibling and a `tcp-sibling` stream echo both
  succeeded on the same connection.
- All awaits use bounded two-second loopback timeouts. The test makes no
  reliability or ordered-delivery claim.

## Dependency decision

Quinn's public `Connection::send_datagram` accepts `bytes::Bytes`, so the crate
adds direct exact-pinned `bytes = "=1.12.1"`. Version 1.12.1 was already in the
lockfile; the locked/offline resolution added only the root package's direct
dependency entry and changed no unrelated dependency version.

## Commands and results

All Cargo commands used the required non-OneDrive target
`C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target`.

- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test datagram`
  - PASS: 5 passed, 0 failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test core_v02_vectors --test admission --test multi_channel --test multi_stream --test channel_binding --test channel_lifecycle --test drain --test resumption --test datagram`
  - PASS: 54 passed, 0 failed across all nine required targets.
- `python -m pytest tests/protocol/test_registry.py tests/protocol/test_schemas.py tests/protocol/test_states.py tests/protocol/test_vectors.py -q`
  - PASS: 62 passed, 0 failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml`
  - PASS: 100 unit/integration tests plus 10 compile-fail doctests; 0 failed.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check`
  - PASS.
- `cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings`
  - PASS.
- `git diff --check`
  - PASS (Git emitted only the checkout's existing LF-to-CRLF warnings).

## Files

Created:

- `crates/nbsr-transport/src/datagram_gate.rs`
- `crates/nbsr-transport/tests/datagram.rs`
- `docs/protocol/core-v0.2-udp-datagram-schema-proposal.md`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-9-report.md`

Modified:

- `crates/nbsr-transport/Cargo.toml`
- `crates/nbsr-transport/Cargo.lock`
- `crates/nbsr-transport/src/admission.rs`
- `crates/nbsr-transport/src/audit.rs`
- `crates/nbsr-transport/src/channel_registry.rs`
- `crates/nbsr-transport/src/config.rs`
- `crates/nbsr-transport/src/core_v02.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/tests/admission.rs`
- `crates/nbsr-transport/tests/channel_lifecycle.rs`
- `crates/nbsr-transport/tests/multi_channel.rs`
- `docs/protocol/core-v0.2-session-route-schema-proposal.md`

Core v0.1 artifacts, generated artifacts, and `.codex-test-temp-w4/` were not
modified or staged.

## Commit

Subject: `feat(wp4): carry isolated udp datagrams`

The immutable commit object ID is returned in the task handoff after this
report is included in that commit.

## Self-review

- Admission remains fresh and signed; a requested transport cannot exceed the
  exact grant list, and a gate exists only for a live exporter-bound UDP
  channel.
- Gate mutation is audit-first. Audit failure preserves sequence, token,
  high-water, queue, and payload state.
- Payload bytes do not appear in `Debug`, audit events, or error strings.
- Replay high-water survives pop, quota drop, and deactivation; queued payloads
  do not survive drain/revoke/close.
- Queue and token state are per channel and per direction. Target failures do
  not mutate sibling gates.
- Quinn configuration, negotiated-cap lookup, native send, and native receive
  remain in `quinn_adapter.rs`; framing and quota logic import no Quinn type.
- The public surface exposes framed payload operations and typed outcomes, not
  the internal gate or raw connection.
- Existing TCP, exporter-binding, lifecycle, drain, multi-channel, multi-stream,
  resumption, frozen vectors, and protocol fixtures remain green.

## Concerns

No implementation blocker remains. QUIC DATAGRAM remains loss-permitted and
unordered; production scheduling or delivery guarantees require a separate
design and are not implied.

## Review round 1 of 5: audit containment and inbound adapter bounds

### Findings and RED/GREEN evidence

1. Per-channel audit isolation
   - RED: after 24 queued records for channel A, the 25th record incorrectly
     returned `Ok` and consumed a global queue/sequence slot.
   - GREEN: `AuditLog` now checks the exact channel scope before global,
     sequence, timestamp, or mutation work; the 25th A record is
     `AuditUnavailable`, B receives sequence 25, an unscoped lifecycle record
     receives sequence 26, and popping one A record returns one A slot.
2. Aggregate session reserve
   - RED: 32 channels at 24 events correctly occupied 768 records, but a 769th
     scoped record for channel 33 was incorrectly admitted.
   - GREEN: an exact aggregate 768 channel-scoped counter prevents any set of
     channel IDs from entering the reserved 256 slots. Exactly 256 unscoped
     events then fill the unchanged 1024-event total, and event 1025 fails
     closed. Counts decrement with the corresponding popped channel event.
3. Outbound-only Quinn maximum on receive
   - RED: the adapter had no local-profile decoder and production receive used
     `Connection::max_datagram_size`, which Quinn documents and implements as
     an outbound peer/path limit.
   - GREEN: the private read path decodes against the exact local maximum of
     1235 bytes (23 fixed + 9 sequence + 3 payload length + 1200 payload) after
     `read_datagram`. A 1235-byte canonical frame succeeds and 1236 fails.
4. Raw native malformed/replay containment
   - RED: the adapter-internal test failed to compile because no private raw
     read/decode seam existed.
   - GREEN: a `cfg(test)` module inside `quinn_adapter.rs` accesses the private
     Quinn connection and private read helper without adding a public hook. A
     non-preferred sequence encoding is rejected as `InvalidFrame`; the same
     valid sequence delivered twice is rejected as `Replay` by the target
     gate; UDP B and a bidirectional TCP stream remain usable afterward.
5. Real 24-event service containment
   - RED: the original 64/65 native UDP loopback reached the new A audit cap,
     proving audit retention and payload queue state had been conflated in its
     fixture.
   - GREEN: the queue test now pops audit records independently while retaining
     all 64 payloads. A separate authenticated loopback fills exactly 24 A
     records, proves A's next valid send is `AuditUnavailable` without adding
     an event or mutating its gate, then proves UDP B and TCP C traffic and an
     unscoped session-drain audit still succeed. After A's audit records are
     released, A sends and receives normally.
6. Cross-module audit semantics
   - RED: lifecycle, multi-stream, and resumption fixtures that intentionally
     queued more than 24 records for one channel failed at the new boundary.
   - GREEN: stream/UDP quota fixtures pop audit independently of application
     state; lifecycle tests now exhaust the exact target partition and prove
     sibling/session containment; resume tests distinguish 24-event
     channel-scoped exhaustion from true 1024-event unscoped exhaustion.
     Resume purge remains atomic when the global reserve is full.

### Exact containment properties

- Total queued audit capacity remains 1024.
- One `channel_id` can retain at most 24 queued events.
- All channel-scoped events together can retain at most 768 queued events,
  independent of how many distinct candidate/rejected channel IDs are used.
- At least 256 queue slots are therefore outside channel-scoped consumption.
- Admission, binding, stream, UDP, quota, channel lifecycle, and
  channel-scoped resume events all pass through the same `AuditLog::record`
  checks; the rule is not UDP-specific.
- Both the per-channel and aggregate checks run before the global capacity,
  audit sequence, timestamp, event queue, and protected channel mutation.

### Asymmetric Quinn configuration evidence

The pinned Quinn 0.11.11 / quinn-proto 0.11.16 configuration does not support
the proposed one-way test mode. Setting local
`datagram_receive_buffer_size(None)` makes Quinn's send path return
`SendDatagramError::Disabled` before considering peer support; the same local
receive option controls both the advertised receive capability and Quinn's
local send enablement. The attempted asymmetric behavior run captured that
exact `Disabled` result. The implementation nevertheless no longer uses the
outbound maximum for inbound validation, and the exact local bound has direct
plus real native-read coverage.

### Review-round commands and results

All Cargo commands used the required non-OneDrive target directory.

- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test datagram`
  - PASS: 6 passed, 0 failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test core_v02_vectors --test admission --test multi_channel --test multi_stream --test channel_binding --test channel_lifecycle --test drain --test resumption --test datagram`
  - PASS: 55 passed, 0 failed across all nine required targets.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml`
  - PASS: 105 unit/integration tests plus 10 compile-fail doctests; 0 failed.
- `python -m pytest tests/protocol/test_registry.py tests/protocol/test_schemas.py tests/protocol/test_states.py tests/protocol/test_vectors.py -q`
  - PASS: 62 passed, 0 failed.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check`
  - PASS.
- `cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings`
  - PASS.
- `git diff --check`
  - PASS (Git emitted only the checkout's existing LF-to-CRLF warnings).

### Review-round files

Modified:

- `crates/nbsr-transport/src/audit.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/tests/channel_lifecycle.rs`
- `crates/nbsr-transport/tests/datagram.rs`
- `crates/nbsr-transport/tests/drain.rs`
- `crates/nbsr-transport/tests/multi_stream.rs`
- `crates/nbsr-transport/tests/resumption.rs`
- `crates/nbsr-transport/tests/support/mod.rs`
- `docs/protocol/core-v0.2-session-route-schema-proposal.md`
- `docs/protocol/core-v0.2-udp-datagram-schema-proposal.md`
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-9-report.md`

No dependency, Core v0.1, generated artifact, or `.codex-test-temp-w4/`
change was made.

### Review-round commit

Subject: `fix(wp4): contain channel audit failures`

The immutable commit object ID is returned after this report is included in
the review-round commit.

### Review-round concerns

No review-round blocker remains. Quinn's receive-enable setting cannot express
a send-enabled/receive-disabled asymmetric endpoint in the pinned version, so
that optional live configuration is not claimed. The outbound-independent
inbound bound, raw native malformed/replay behavior, and sibling containment
are verified directly. DATAGRAM delivery remains unreliable and unordered by
design.
