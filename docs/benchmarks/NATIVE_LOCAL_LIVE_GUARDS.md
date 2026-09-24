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

The source-only option leaves destination memory unmeasured. The observer effect
has not been qualified. Do not combine observed and unobserved cells into one
supposedly equivalent performance cohort.

## Paired short diagnostic

The finite coordinator also accepts `paired_live_guards: true`, requiring
`source_live_guard: true`, `post_close_reports: true` and `diagnostic_rate`.
Only the endpoint adapter may launch this mode. Source progress/final records are
validated and forwarded in order over the private management stream. The manager
does not dispatch further callbacks while a control write is pending, preventing
reentrant writes from reordering records; deadlines/cancellation remain active.

Each destination records receipt time on its own monotonic clock. Its sampler
starts inside owned-peer lifetime and stops before reaping (or when source final
arrives first). NBSR may naturally exit before final telemetry; endpoint evidence
therefore joins late telemetry outside the already-sealed peer directory. This
management join does not alter NBSR ACK/send completion semantics. The endpoint
refuses its management ACK until the source telemetry final is validated.

Pair collection checks both observer modes, retained/live source control equality,
source stdout equality, destination resource identity/counters and exact agreement
between owned samples and local receipt events. Both guards retain numerical
failures. `PAIRED_DIAGNOSTIC` is still not a capacity, observer-neutrality or soak
qualification. The workload and deadlines remain the original short diagnostic.
Reference-bound long-duration execution and matched observer qualification remain
separate unfinished requirements.

## Explicit longer diagnostics

The native finite coordinator additionally accepts `diagnostic_seconds` equal to
60, 3600 or 7200 when `diagnostic_rate` and post-close reports are enabled. Omit
the field for the unchanged 20-second workload. Direct and NBSR use the same
duration. Example extension to a complete native coordinator configuration:

```json
{
  "diagnostic_rate": [1000, 1],
  "diagnostic_seconds": 60,
  "post_close_reports": true,
  "source_live_guard": true,
  "paired_live_guards": true
}
```

This is a diagnostic mode, not reference-bound B5 acceptance. The 60-second option
is a functional preflight; 3600/7200 declare a genuinely different workload.
Their control budget is duration plus the existing 120-second allowance. Existing
short-mode 120-second, readiness-transfer 30-second, child cleanup and transfer
deadlines remain unchanged. There is no automatic retry or timeout extension.

One bounded contract controls command duration, process/management budgets,
resource counts, telemetry framing and independent replay. Sampling remains
0.5 seconds and progress windows remain 5 seconds. Final duration must exactly
match the declared workload; a short transcript cannot pass as a long run.
Synthetic two-hour replay verifies framing/ownership joins, not two hours of
actual execution. Reference binding, observer timing qualification and a genuine
near-ceiling soak remain separate open gates.
