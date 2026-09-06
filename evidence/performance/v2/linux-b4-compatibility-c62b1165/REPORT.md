# Linux B4 compatibility with older binaries

**INVALID PARTIAL DIAGNOSTIC.** Controller c62b1165 ran immutable-image Rust
binaries built at 3644c324. This is DIAGNOSTIC_BINARY_SOURCE_MISMATCH, not current
Linux CLI acceptance, a capacity result or an observer-qualified comparison.

Six repeats completed: three at 125 admissions/s and three at 200/s. Each admitted
all 512 independent clients with zero recorded errors/timeouts and passed the
existing terminal/process and destination cleanup gates. Independent raw checks
verified all 512 source success IDs and all eight existing destination counters
at zero for both destination roles in each completed repeat.

| Offered/s | Completed valid repeats | Admission-rate CV | Forwarding-goodput CV | Required repeats |
| --- | ---: | ---: | ---: | ---: |
|125|3|3.9436%|2.4572%|3|
|200|3|5.2764%|0.9933%|5|

The 200/s fourth repeat failed with PermissionError on `/proc/74/fd`; fifth was
not run and no replacement was attempted. Consequently the expanded200/s cohort
is incomplete. The125/s STABLE classifier label remains diagnostic and cannot be
promoted to a hardware or production ceiling. Linux observer cost is NOT_QUALIFIED.

PID 74 was admission-destination. Its last successfully captured state was S.
The failing sampling round retained established-peer observations about 108 ms
later. The failed repeat already retained 512 source success records and the
admission destination's PASS/connections 512 result. The established workload
was still active. This locates the failure in late admission-destination resource
observation, not a recorded admission rejection. Failure-time stat and traceback
were not retained, so the cause remains UNRESOLVED. The same-identity zombie
recheck existed; no accepted Z outcome was produced on the propagated error
path. This does not justify suppressing live permission errors or modifying
sampling semantics. A separate failure-only diagnostic repair is pending.

Definition: 512 clients, one connection each, two source shards, eight-stream
1 KiB established load for 30 s after 2 s warmup. All four owned peers shared one
selected guest logical CPU. Existing deadlines and repeat/classification gates
were unchanged. Source shard CPU is NOT_MEASURED (non-Windows OS thread IDs are
zero); full source runtime ownership is not established by terminal markers.

The existing image was reused without build or pull, with network none, UID/GID
65532, read-only root, dropped capabilities, no-new-privileges, one CPU quota,
1 GiB memory and 128-PID bound. This is Docker Desktop Linux VM loopback evidence;
no external-host or physical-server result is implied. The 236 staged controller
files came from the exact committed archive; unrelated untracked B5 work was
excluded and separately inventoried in the external stage definition.

All 107 captured raw artifact hashes were verified. A complete nonempty tar was
copied and verified before releasing the wrapper; it then exited 1 as expected.
Only the exact stopped owned container was removed, after evidence preservation.
Raw image/inspect/console/archive/removal receipts remain externally indexed.
No image, volume, source archive or unrelated resource was removed. No code or
runtime fix was applied in this evidence closure.
