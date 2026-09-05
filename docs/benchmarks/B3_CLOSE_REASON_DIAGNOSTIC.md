# B3 failure-only transport close diagnosis

The512-bundle materialized trials at100/s and125/s failed after early connections
had been held near the destination10-second idle bound. Existing errors mapped
the stream failure to ApplicationStreamRejected/ApplicationStreamFailed, hiding
the underlying connection state. Idle expiry remained an inference.

The benchmark-harness feature now exposes a read-only, fixed-category view of
Quinn's current close reason: not_closed, timed_out or other_closed. It returns
no peer reason text, identity, key or address. Non-benchmark builds do not expose
this method. No timeout, protocol, authority or error-handling path is changed.

Materialized B3 parents log the category only when a stream task fails, before
connection teardown. Three local elapsed timestamps capture preparation, release
and failure. Source origin is its connection attempt; destination origin is its
lifecycle handler entry. Source logical_client_id and destination accept_ordinal
are different namespaces: concurrent accepts can reorder. Never pair peers by
those ordinals or subtract clocks with different origins.

Literal RED: release unit test failed with missing category helper. GREEN: fixed
category test PASS; default-library and benchmark-library/source/server release
Clippy with-D warnings PASS. The diagnostic does not recover or convert failed
operations into successes. Focused independent review found and resolved the
destination ordinal-label ambiguity. Live diagnosis follows this commit.

Any future confirmed timeout result qualifies the specific failed B3 workload;
it does not establish a memory leak, host-memory ceiling or production admission
ceiling. Retained stream/connection handles alone do not prove open transports.
