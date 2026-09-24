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
