# WP4 Task 3 report: independently gated multi-stream TCP channels

## Status

Implemented independently gated reliable application streams over the Task 2
active-channel registry. The implementation remains origin-free and in-memory;
it adds no exporter, lifecycle, drain, resume, UDP, or origin-forwarding behavior.

## RED/GREEN cycles

1. **General stream IDs and exact control binding**
   - RED: `cargo test ... --test multi_stream` failed 2/2 because stream ID 8
     was rejected by the WP3 hard-coded ID 4 check and mismatched
     request/session `STREAM_ACCEPT` envelopes returned `Ok(())`.
   - GREEN: generalized Source-Edge bidirectional ID validation and retained
     exact request/session binding; 2/2 passed.
2. **Per-channel state, quotas, release, and sibling isolation**
   - RED: `cargo test ... --lib channel_streams` failed to compile because the
     wished-for internal `ChannelStreams` API and `OverCapacity` rejection did
     not exist.
   - GREEN: added the internal channel/stream registry, global stream-ID replay
     history, 64-stream channel limit, 1 MiB stream and 8 MiB channel
     accounting, checked reservation arithmetic, byte/stream release, and
     scoped failures; 4/4 passed initially and 5/5 after the pre-accept sibling
     containment regression was added.
3. **ControlSession and actual Quinn stream confirmation**
   - RED: the focused application loopback failed to compile because explicit
     `ControlSession` stream-control methods and Quinn session-stream acceptance
     did not exist.
   - GREEN: routed `STREAM_OPEN`, `STREAM_ACCEPT`, and actual Quinn stream-ID
     confirmation through the session-owned `ChannelStreams`; the focused
     application test passed 1/1.
4. **Real two-channel multi-stream loopback**
   - Harness RED: Quinn timed out accepting an idle control stream because no
     bytes had made stream ID 0 visible.
   - GREEN: sent and received a valid bounded control envelope, then activated
     two independently signed routes in one real `ControlSession`; stream IDs
     4, 8, and 12 echoed only their bound in-memory payloads, including the exact
     4 KiB boundary.

## Files

- `crates/nbsr-transport/src/channel_streams.rs` (new)
- `crates/nbsr-transport/src/stream_gate.rs`
- `crates/nbsr-transport/src/session.rs`
- `crates/nbsr-transport/src/quinn_adapter.rs`
- `crates/nbsr-transport/src/lib.rs`
- `crates/nbsr-transport/tests/application_stream.rs`
- `crates/nbsr-transport/tests/multi_stream.rs` (new)
- `.superpowers/sdd/2026-07-31-wp4-reusable-multi-service-transport/task-3-report.md` (new)

## Verification

The required non-OneDrive Cargo target was used throughout:
`C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target`.

- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test multi_stream`:
  5 passed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --lib channel_streams`:
  5 passed, 2 filtered out.
- Required integration regression command (`application_stream`, `stream_gate`,
  `multi_channel`, `control`, `route_context`, `admission`, `multi_stream`):
  19 passed.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check`:
  passed.
- `cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings`:
  passed.
- `git diff --check`: passed; Git emitted only the checkout's existing LF/CRLF
  conversion notices.

## Self-review

- Channel and stream bindings remain private and cannot be mutated through a
  raw registry API.
- Used stream IDs survive release, so release frees capacity/bytes without
  enabling ID reuse.
- Failed reservations calculate both checked totals before mutating counters.
- Wrong binding, replay, pre-accept payload, capacity, and ordinary stream
  failures do not mutate or block a sibling channel.
- All Quinn connection and stream operations remain in `quinn_adapter.rs`.
- WP3 regressions retain pre-accept reset, `b"nbsr-lab"`, exact 4 KiB success,
  and oversized reset evidence.

## Commit

`feat(wp4): multiplex isolated tcp streams`

## Concerns

None. This is bounded in-memory transport evidence only; it does not establish
origin forwarding, production readiness, exporter binding, lifecycle/drain,
resume, UDP, or cross-edge continuity.
