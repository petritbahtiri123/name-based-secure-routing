# Task 4i — rate-controlled admission capacity

**PASS / highest strict-stable cell 125 offered admissions/s; SATURATED at
200/s with host headroom and an unattributed admission-lifecycle backlog.** This is a
Windows-loopback benchmark result, not a production, WAN, server-class, or
hardware-capacity claim.

## Method and scope

Capture base: `fa46af05db7923a4aa7bb6e4d9c5af8dcb17e5b7`, branch
`codex/nbsr-v3-wp0-wp1`. Release binaries, Windows 11, Intel i5-10210U,
4 physical cores / 8 logical processors, 16,942,501,888 bytes RAM. Each cell
used 512 independently authenticated transport connections, `ControlSession`s,
routes, streams, ownership records, and cleanup states while the unchanged
established-forwarding pair ran for 30 seconds after a 2-second warmup.

The benchmark-only async gate schedules logical client `i` at `i/rate` seconds.
The connection future and unchanged handshake deadline are constructed only
after release. The concurrent benchmark destination creates its matching
`accept_one()` future at the same planned rate so the existing five-second
listener deadline is not pre-armed before a client is scheduled. No timeout
value, connection-close behavior, production code, protocol, wire format,
security rule, or frozen authority changed. Simultaneous Task-4h release remains
a separate burst-stress diagnostic and is not mixed into this capacity result.

Three repeats were required, extended to five when CV exceeded 5%. All 25
authoritative records were valid and terminal evidence plus final ownership
cleanup was exact. There were 12,799 successful admissions from 12,800 attempts:
one valid 50/s repeat admitted 511/512 and recorded one handshake timeout. It is
preserved and makes that cell SATURATED under the zero-error rule.

## Results

| Offered/s | Actual admissions/s | Achieved/offered | Admitted | Admission p99 | Handshake p99 | Forwarding Gbit/s | Forwarding p99 | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 25 | 24.811 | 99.24% | 512/512 | 10.135 ms | 3.759 ms | 0.624 | 0.384 ms | BASELINE |
| 50 | 49.037 | 98.07% | 2559/2560 total | 14.533 ms | 5.144 ms | 0.606 | 0.406 ms | SATURATED (1 timeout; 15.30% CV) |
| 75 | 72.819 | 97.09% | 512/512 | 20.869 ms | 6.784 ms | 0.595 | 0.425 ms | STABLE |
| 100 | 96.397 | 96.40% | 512/512 | 27.683 ms | 9.826 ms | 0.612 | 0.423 ms | STABLE |
| 125 | 119.813 | 95.85% | 512/512 | 32.250 ms | 10.446 ms | 0.596 | 0.444 ms | STABLE |
| 150 | 139.511 | 93.01% | 512/512 | 46.360 ms | 11.740 ms | 0.609 | 0.455 ms | DEGRADED |
| 200 | 138.958 | 69.48% | 512/512 | 883.194 ms | 222.134 ms | 0.609 | 0.463 ms | SATURATED |

The requested primary statement is therefore:

> On this host, NBSR sustained approximately **120 new admissions/s** while
> maintaining approximately **0.596 Gbit/s** established forwarding under the
> tested workload.

This uses the highest strict-stable cell: 125 offered/s, 119.813 actual/s.
The isolated 50/s timeout makes the observed ladder non-monotonic; it is not
silently averaged away and the 125/s statement applies only to its own three
zero-error repeats, not to an assertion that every lower-rate cell was stable.
At that cell median tracked-process usage was 1.468 effective cores, peak
working set 69,586,944 bytes, peak private bytes 42,356,736, 19 threads, and
346 handles. Whole-host median CPU was 23.67%, processor queue median zero,
and available memory median 7,955,456,000 bytes. Cleanup ownership was zero.

## Saturation and backlog

At 200/s, actual throughput no longer increased over 150/s (138.958 versus
139.511 admissions/s), achieved/offered fell to 69.48%, admission p99 rose to
883.194 ms, and handshake p99 rose to 222.134 ms. The destination ownership
high-water marks rose from 10 live transport sessions / 10 QUIC connections at
150/s to 107 / 120 at 200/s; live service channels rose from 6 to 76 and live
application streams from 5 to 50. This is measured admission-lifecycle backlog.
Tracked-process usage at 200/s was 1.485 effective cores, 167,501,824 bytes peak
working set, 146,432,000 peak private bytes, 19 threads, and 547 handles.

Median whole-host CPU remained 23.27%, processor queue median zero, and median
available memory 8,022,872,064 bytes at 200/s. Consequently this is not a proven
hardware limit. The exact owner of the backlog—source scheduling, destination
runtime/accept scheduling, QUIC progression, or control-session work—remains
unattributed without a separate low-distortion profile. No tuning is justified
from these counters alone.

`peak_pending_clients` in the inherited raw schema is process-level (512 while
the source process is live), not an instantaneous client queue depth. It is not
used for classification. The lifecycle high-water counters above are the
defensible bounded-backlog evidence.

## Rejected preliminary campaign

The first campaign is preserved separately under
`b4b-task4i-rejected-prearmed-accept-fa46af05db79`. It exposed a benchmark
defect: all destination accept futures started their unchanged five-second
deadlines at process startup, so 25/s admitted about 125 clients before the
remaining pre-armed accepts expired. Those runs are invalid for rate capacity
and are not included above. The correction paces future construction; it does
not extend or alter the deadline.

## Reproduction and integrity

```powershell
$env:CARGO_TARGET_DIR = 'C:\NBSR-build\b4b-task4i'
python -u scripts/run_b4b_task4i.py --output C:\NBSR-build\task4i-new-run --duration-seconds 30 --warmup-seconds 2
python scripts/analyze_b4b_task4i.py --root C:\NBSR-build\task4i-new-run
```

Exact commands, toolchains, hashes, and host metadata are in
`environment.json`; raw records and host samples are under `raw/`;
`analysis.json` and `telemetry-summary.json` are mechanically derived.
`checksums.sha256` covers every retained artifact. Raw evidence was not edited.

Final review added fail-closed repeat aggregation, default non-benchmark cfg
coverage, omission of the disabled destination-rate environment variable, and
offline telemetry/reporting. None changes the rate-controlled executable path
used for the retained raw runs. The measured binary hashes and captured source
identify that campaign; derived analysis was rerun against the unchanged raw
records and removed no measured data.
