# Native host-local live guards

Prerequisite for native paced orchestration: evaluate progress and private-memory
growth using each endpoint's own monotonic clock. Never compare source and
destination monotonic timestamps. Reuse ProgressValidator, live_drift_failure
and private_growth without changing thresholds.

Implement a bounded guard for one owned role. Progress records carry source
elapsed durations; receipt time and resource timestamp must both be supplied by
the local endpoint. Approximate phase origin is first local receipt minus source
elapsed duration, explicitly including relay delay uncertainty. This is not a
clock synchronization scheme or precise phase attribution. Reject malformed,
reordered, oversized or post-final input. Copy accepted inputs so caller mutation
cannot rewrite retained state. Preserve every detected drift/growth failure.

Literal RED tests cover clock-offset invariance, growth and latency failures,
insufficient sampling, wrong role, local clock reversal, input bounds, malformed
progress, final ordering and retained-input mutation. Focused tests and one review
precede commit. This helper does not launch a run or grant a stable-capacity PASS.
Integration, observer qualification, relay failure tests and long-run execution
remain separate; no timeout/protocol/security changes are permitted here.

Ruling: use the existing pure drift/growth predicates directly rather than import
the Windows controller and its platform-specific dependencies. This keeps the
native helper portable while preserving the same numerical gates.

Review integration constraint: deliver available local resource samples before
each steady progress record. Late samples must not count as evaluated coverage.
A literal RED proves late delivery previously inflated the availability flag;
the helper now reports only the number actually passed to the growth predicate.
Late data remains retained but requires another steady window for evaluation.
