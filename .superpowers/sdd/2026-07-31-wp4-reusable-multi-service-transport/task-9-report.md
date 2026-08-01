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

No implementation blocker remains. Because the adapter intentionally exposes
neither raw Quinn access nor a malformed-frame injection bypass, malformed and
replayed frames are covered deterministically at the exact codec/gate boundary,
while the native authenticated loopback covers negotiated oversize rejection,
quota/drop containment, target revoke, and UDP/TCP sibling survival. QUIC
DATAGRAM remains loss-permitted and unordered; production scheduling or
delivery guarantees require a separate design and are not implied.
