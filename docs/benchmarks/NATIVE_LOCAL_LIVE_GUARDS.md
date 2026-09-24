# Native local live-guard prerequisite

`scripts.performance.linux_native_live.LocalLiveGuard` is a bounded, single-thread
helper for future native paced endpoints. It does not launch a workload, sample a
process, forward control messages, qualify an observer or accept a sustained run.

Create one guard per owned endpoint role with explicit progress/resource bounds
and payload size. Feed `resource()` samples from that host's owned process, using
its local monotonic `timestamp_ns` and measured `private_resident_bytes`. Never
feed remote resource timestamps into this guard. Zombie memory remains missing,
not zero. Process identity/ownership and sampler failures remain caller duties.

Feed validated source progress via `progress(record, received_ns=LOCAL_RECEIPT)`.
The helper independently validates grouped accounting. On the destination this
must be the destination's receipt timestamp, not the source's clock value.
Forwarding delay makes the inferred phase origin approximate; this cannot prove
precise synchronized phases. Feed available local samples before each progress
record. Only samples actually evaluated at a steady window count toward resource
coverage; late samples wait for a subsequent steady window.

The existing goodput/p99 drift and private-growth predicates are unchanged.
Detected failures remain in `qualification()['failures']`; the caller must not
ignore them or convert them into PASS. Accounting/final/clock/bound failures raise
and must invalidate the run. `finish()` validates final accounting and closes all
input. The helper never certifies source/shape/reference matching or soak duration.

Qualification reports coverage and explicitly retains `NOT_ESTABLISHED` for
sustained capacity and observer qualification even when no failure was seen.
Integration must additionally validate offered/completed ratio, requested cleanup,
relay cancellation, process ownership, current reference, live observer effect and
the genuine 60/120-minute run. None of those is completed by synthetic unit tests.

The finite native coordinator now accepts optional `source_live_guard: true`
alongside `diagnostic_rate` and `post_close_reports: true`. It enables the observer
only on the source. The workload remains 3-second warmup and 20-second issue
duration, with unchanged 120-second controller bounds. Both Direct and NBSR use
the same observer when selected; cohort identity includes this mode.

Source sampling uses the existing Linux private-resident sampler every 0.5 seconds.
The source retains `live-events.ndjson`, `live-observed-stdout` and
`live-result.json`; pair verification replays these records and verifies the
observed stdout equals original stdout. Sampling stops before the child is reaped.
Failures in sampling/framing/accounting invalidate the run; measured drift/growth
failures remain visible as diagnostic results. Numerical success is not stability.

Destination memory and live cross-host progress forwarding remain unimplemented.
The observer effect has not been qualified. Do not combine observed and unobserved
cells into one supposedly equivalent performance cohort.
