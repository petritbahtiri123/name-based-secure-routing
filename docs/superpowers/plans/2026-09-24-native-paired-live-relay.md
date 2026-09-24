# Short native paired live relay

Extend the accepted short source observer to destination memory without combining
host clocks. Keep 20-second paced diagnostics and all existing deadlines. This is
not yet a qualified observer, near-ceiling reference or long-duration soak.

1. Add a bounded private management ledger for interleaved source progress/final
   records. Reuse ProgressValidator. Only after source readiness transfer may
   source progress arrive; final must precede source completion. Forward accepted
   records to destination over existing ordered management input. Reject duplicate,
   malformed, out-of-order, post-final and unbounded telemetry; EOF remains failure.
2. Start the destination's existing Linux sampler only inside native peer ownership.
   Stop/join before reap and on exceptions. Retain its samples in peer evidence.
   Endpoint-local receipt events and LocalLiveGuard remain outside the sealed peer
   because NBSR can exit before final management telemetry arrives. ACK requires
   complete telemetry, without altering NBSR ACK/send semantics.
3. Bind opt-in paired mode through coordinator, endpoint and peer metadata. Independently
   replay destination local events, match forwarded source records exactly and join
   resource records to retained owned-peer samples. Preserve numerical gate failures
   as diagnostics and fail on invalid accounting/control/ownership.
4. Literal RED tests, focused verification, one review and atomic commit. Exercise
   five counterbalanced Direct/NBSR pairs plus bounded cancellation/control-failure
   cases. Preserve every attempt, verify indexes, update checkpoint.

Ruling: management progress is benchmark-only diagnostic traffic, never protocol
wire or trusted runtime authority. No remote timestamp is used as a local receipt
clock. Observer impact requires its own matched qualification after integration.

Review finding: Manager.send previously pumped incoming events while waiting for
its write. New forwarding callbacks made that reentrant, allowing a second writer
to overtake the first. A literal delayed-writer RED produced second/first order.
The minimal fix defers pumping until the current send returns; the existing bounded
wait still checks cancellation/deadline and the reader queue remains bounded.
No locks or worker fanout were added and no timeout was extended.

Implementation/review status: ledger, observer, endpoint and replay RED cases
preceded implementation. Focused review identified the delayed-writer issue;
literal RED/GREEN and scoped re-review close it. Full affected-suite and actual
Docker diagnostic/cancellation validation follow before evidence acceptance.
