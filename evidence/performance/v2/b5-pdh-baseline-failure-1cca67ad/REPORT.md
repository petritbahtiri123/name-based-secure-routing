# Failed PDH-observer baseline diagnostic

**INVALID PARTIAL DIAGNOSTIC. Observer NOT_EVALUATED; drift cause UNRESOLVED.**
The first off-arm cell at `1cca67ad092292acec85f622c7d2825c47654a67`
failed the existing live p99 drift guard at the third progress window, about 90 s
into a planned 120 s measurement. One baseline was attempted, zero PDH arms ran,
and zero cells qualified. No typeperf process was launched by this driver.

This is historical fixed-load NBSR-only Windows loopback evidence:
421624000000/150013467 operations/s, one physical-core pool on logical0/mask1,
one group, eight 16 KiB streams, depth 1, warmup 3 s and progress 30 s. Periodic ownership
sampling was off. The inactive parser default `percent=70` in environment.json
is not used in diagnostic mode: this load is not 70% of current capacity.

| Window | Goodput MB/s (decimal) | p99 ms | Goodput / window 1 | p99 / window 1 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 88.832074 | 3.0628 | 1.000000 | 1.000000 |
| 2 | 90.075179 | 3.0306 | 1.013994 | 0.989487 |
| 3 | 89.565972 | 3.7199 | 1.008262 | 1.214542 |

The existing three-window guard compares first and last windows. Goodput did
not trigger its 5% decline rule; p99 exceeded its 1.20 ratio limit. These are
retained window metrics with bounded sampled latency, not a completed soak or
pooled-operation latency distribution. Reported zero errors/timeouts in these
three progress records do not convert the controller abort into a valid run.

The baseline failure demonstrates that PDH presence was unnecessary for this
particular failure. It identifies neither the cause nor unrelated applications,
IRQ/DPC contribution, thermal behavior, memory leaks, hardware limits or an
observer effect. An off/on observer comparison was never reached.

Resource samples retain role/PID and absolute monotonic times, but the original
controller convention uses first-progress *receive time minus elapsed_ns*.
That receive anchor was not serialized. Per-window process CPU cannot therefore
be reproduced under the original convention; no shifted-clock approximation is
substituted. Raw resource records remain available for suitably scoped analysis.

There is no successful source final and no final ownership snapshot in this
aborted cell. The controller's failure/cleanup path and retained partial logs are
not proof that all eleven runtime ownership gauges reached zero. Both verified
process affinity observations were mask1. No failed row is replaced or hidden.

Integrity: independently verified all 20 top-level indexed artifacts and all 14
nested controller entries (overlapping, not 34 unique artifacts), plus all 8
preparation entries. Source/driver/prebuild/binary bindings match. The exact
parent console, prebuild console and prepared manifest sit outside the raw
root index; their actual-byte hashes and paths are separately listed in
external-inputs.json. Raw binaries/logs remain external. Preparation driver,
fixtures and both RED/GREEN stages are copied compactly here; no tests or builds
were rerun during packaging. Canonical checksums cover canonical bytes and are
separate from byte-preserved external checksum indexes.
