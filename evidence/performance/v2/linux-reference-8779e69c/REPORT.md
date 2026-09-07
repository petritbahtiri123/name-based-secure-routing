# Linux finite reference at 8779e69c

MEASURED, scoped Docker Desktop Linux VM loopback. Source
8779e69cfd7fe5cb244aba2f3e96e785c3dd47eb, clean detached runtime checkout,
Rust 1.97.1 release. Both peers share one selected guest-core representative;
one group/worker per role, 32 streams, 1 KiB request/response, 3-second warmup,
30-second measurement. This is not dedicated host physical-core or NIC capacity.

| Path | Depth | Median Gbit/s | Median p99 | Repeats | Classification |
| --- | ---: | ---: | ---: | ---: | --- |
| Direct | 1 | 1.415431 | 0.729134 ms | 5 | UNRESOLVED: CV 6.98% |
| Direct | 2 | 1.737643 | 1.089160 ms | 3 | DEGRADED |
| Direct | 4 | 2.033175 | 1.818095 ms | 3 | SATURATED |
| NBSR | 1 | 1.822417 | 0.482626 ms | 5 | STABLE: CV 0.663% |
| NBSR | 2 | 2.165110 | 0.850445 ms | 3 | DEGRADED |
| NBSR | 4 | 2.432145 | 1.513480 ms | 3 | SATURATED |

All 22 attempts are valid and retained, with zero errors/timeouts and required
cleanup. The finite classifier uses bounded in-flight work, latency relative to
the same-path baseline, dispersion and clean drain; it is not an externally
rate-controlled sustainable-capacity classifier. Direct's unresolved baseline
prevents a strict-stable Direct/NBSR capacity-delta claim.

The explicit finite exit-transition fix did not produce a telemetry failure in
this cohort. That does not retrospectively validate the old invalid run or prove
its cause. Production Rust code is unchanged from edc0f96d. A fresh release build
completed in 32.49 seconds using the retained generated cache; all three binary
hashes equal the old release binaries. Build and runtime fixtures remain bound
to /work, with unchanged source/vector archives. Runtime peers run as UID65532.

The 248 inner reference hashes were independently verified. The enclosing raw
index additionally binds build logs, archives, update bundle, runtime preparation
and commands. See raw-evidence.json for the retained root and index checksum.
Git emitted inaccessible /root/.config default-ignore/attributes warnings after
the runtime dropped privileges; source checks succeeded and this did not occur
inside timed peer work. Later preparation uses a process-local XDG config path.

The NBSR depth-one cell can supply a 70% paced target through the strict loader.
This does not qualify the smaps or ownership observer, paced achieved/offered
ratio, long-run memory behavior, or sustained stability. B5 validation remains
separate and pending. No server, WAN, physical-core scaling or hardware ceiling
claim follows from this VM reference.
