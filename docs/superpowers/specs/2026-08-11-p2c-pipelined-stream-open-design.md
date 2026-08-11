# P2C Bounded Pipelined STREAM_OPEN Design

## Scope and eligibility

Core v0.2 already permits a source-initiated bidirectional QUIC stream to exist before its matching `STREAM_ACCEPT`; it forbids application bytes before acceptance. Responses are independently and unambiguously correlated by the envelope `request_id` and `session_id` plus echoed stream, channel, and route identifiers. Source and destination control sequences remain strictly increasing in their respective wire order, and the destination continues to prepare, audit, and commit each admission sequentially.

The implementation is eligible without a wire change if it reserves actual Quinn streams rather than predicting identifiers. A reserved stream is silent until accepted. Holding its real Quinn handles makes its ID exclusive even if another opener uses the connection. Rejection, cancellation, timeout, revoke, or connection close resets/drops that reserved stream and removes its bounded pending entry.

## Design

Add a bounded `PendingStreamAdmissions` source coordinator and a `ReservedApplicationStream` transport handle. The coordinator has a validated deterministic window in `1..=16`, is keyed by request ID, rejects duplicate request IDs and stream bindings, and never contains more entries than its window. Reservation calls Quinn `open_bi`, records the actual ID, and emits no application bytes. Activation requires a normal `ApplicationStreamPermit` whose connection capability and exact stream ID match the reservation; only then is the stream tracked and exposed as an `ApplicationStream`.

The lifecycle benchmark processes operations in batches no larger than the configured window. The source reserves actual streams, constructs and locally authorizes the existing frozen `STREAM_OPEN` envelopes for those IDs, sends them in monotonic sequence order, receives responses in wire order, verifies exact correlation, and activates accepted reservations. The destination reads, authorizes, commits, and responds to the batch sequentially, then accepts and services the corresponding application streams. No destination authorization work runs concurrently.

Window 1 follows the current order. Windows 2, 4, 8, and 16 change only how many independently authorized admissions may be outstanding. Existing per-channel stream capacity and P1F replay limits remain enforced by the existing destination `ChannelStreams::prepare_open` then `commit_open` sequence; no production limit changes.

## Failure and cleanup

Each pending entry owns one silent reserved stream. Exact response mismatch fails only that entry and resets it. A reject removes and resets only the correlated entry. Timeout/cancellation drops the entry and releases the window permit. Channel revoke removes applicable entries; connection shutdown clears all entries. Accepted neighbors remain independently valid. Replay and capacity decisions stay in existing session code and retain their current precedence and audit behavior.

## Verification and decision

Literal RED tests cover windows, exact correlation, mixed accept/reject isolation, cleanup paths, actual stream-ID binding, replay/sequence/capacity/revocation invariants, and safe diagnostics. Short matched loopback measurements select the smallest useful window. The production change is kept only if median lifecycle throughput improves at least 10%, p99 regresses no more than 5%, errors remain zero, resource state is bounded, focused/broader tests pass, and formatting/Clippy are clean. Otherwise production changes are reverted while safe design/tests/evidence are retained.
