# Task 4l: elevated ETW correlation

**PARTIAL / UNRESOLVED:socket-delivery-to-first-reply. No optimization justified.**

## Capture integrity and workload

The user ran the prepared Administrator command against source
`77bab17ff72abf73c0e8a551dec05b8a24122f96`. Capture root:
`C:\NBSR-build\b4b-task4l-etw-20260905-141214`.

The 2,651,848,704-byte merged trace has SHA-256
`4a838f5bdfc85e92462ff4b4665837d5a1c3cbbe6a7e2c69909534e262d24f87`.
The hash and both original workload checksum manifests were freshly verified.
Trace statistics report zero lost buffers and zero lost events over
2026-09-05 12:17:53.1268971–12:23:32.9106558 UTC.

Both rates used five unprofiled controls followed by five ETW repeats, release
binaries, two source shards, 512 independent client lifecycles, 30-second
established forwarding, and two-second warmup. Source/binary/workload equivalence
passed the wrapper comparison. All 20 records were valid, with zero errors and
timeouts, exact terminal evidence, zero ownership residue, and exited processes.
No Rust, Go, protocol, deadline, security, or workload code was changed.

## Measured diagnostics and rejected observer gates

| Offered/s | Observer | Repeats | Median actual/s | Median handshake p99 ms |
|---:|---|---:|---:|---:|
| 200 | None | 5 | 180.309 | 14.753 |
| 200 | ETW | 5 | 137.996 | 52.696 |
| 250 | None | 5 | 111.801 | 1016.643 |
| 250 | ETW | 5 | 61.139 | 3008.872 |

Both absolute observer gates failed. Admissions/s changed 23.47% at 200/s and
45.31% at 250/s; established goodput changed 9.92% and 9.16%. Block order also
confounds host drift. Trace timings cannot be transferred to controls or used
to claim a production/host capacity or a causal explanation of the unprofiled
collapse. Controls independently show the 250/s progression problem.

## Network and runtime observations

Two bounded windows were exported: first ETW repeat at each rate, not a
whole-trace or all-repeat packet analysis. Installed xperf uses **microseconds**
for `-range`; the preliminary `0 15` export contained only startup metadata and
is not a handshake observation. Final export ranges are 2,000,000–15,000,000 us
and 169,000,000–185,000,000 us relative to the trace origin.

Each final window contains 512 source-port flows for the admission listener.
Source and destination PIDs and listener ports come from that repeat's command
and resource records. UDP endpoint tuples identify flows; logical client IDs
are not invented. First TCP/IP receives do not prove successful socket enqueue
or application reads. Repeated 1200-byte sends are not decoded QUIC packet numbers
and are not asserted to be retransmissions.

Selected longest first-reply gaps:

| Offered/s | Listener/client UDP port | First TCP/IP receive delay | First reply delay | Destination main TID | Matched main CPU during gap | Other runtime progress |
|---:|---|---:|---:|---:|---:|---|
| 200 | 56842 / 57302 | 130 us | 1.030034 s | 17156 | 0.372888 s | 1366 destination UDP sends |
| 250 | 51046 / 51204 | 104 us | 3.025882 s | 21388 | 1.907223 s | 7069 destination UDP sends |

The corresponding first source-send times (trace-relative us) were
7,332,618 / 8,361,581 at 200/s and
173,680,717 / 174,682,353 / 174,682,387 / 176,705,673 at 250/s.
The destination first replied at 8,362,652 and 176,706,599 us respectively.
Main-thread maximum matched off-CPU intervals within these gaps were about
30.8 ms and 30.5 ms. Matched CSwitch intervals are lower-bound CPU observations;
missing boundary intervals are not filled in.

These observations exclude a continuous one/three-second whole-destination
runtime stall in these selected profiled intervals. They narrow the unanswered
question to why a particular initially received datagram produces no first reply
while other connections progress. They do **not** distinguish socket queue/drop
from endpoint handling or establish the unprofiled root cause.

Readable Rust profile symbols include Quinn connection timeout handling and UDP
receive, while many kernel frames remain unresolved. Timer events were not
decoded by the installed xperf exporter. No timer or syscall-level attribution
is claimed. No buffer enlargement, sharding, or timeout adjustment was made.

## Smallest next diagnostic

The locally installed `Microsoft-Windows-Winsock-AFD` manifest exposes event 1033,
`AfdDatagramDropWithAddress`, including Endpoint, BufferLength, Address and Reason.
Events 1000 and 1030 provide socket creation/process identity and bind address.
The new WPR profile filters to precisely those three event IDs, with no kernel
provider, CPU samples, context-switch stacks, or per-packet receive/send stream.
This uses Microsoft's documented [WPR event-ID filters](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/eventfilters).

A non-elevated attempt to start even the drop-only provider returned
`Access is denied (0x5)`. The next capture therefore requires Administrator.
WPR profile parsing, Python contracts, and PowerShell syntax have been verified;
the elevated AFD capture itself has not run. It will use the same matched
five-repeat controls and record observer gates before any causal use.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bajra\OneDrive\Documents\NBSR\scripts\capture_b4b_task4l.ps1" -DatagramDropsOnly
```

The wrapper owns a unique WPR instance, preserves its trace on workload failure,
and refuses existing evidence directories. Return the printed `CAPTURE_READY`
path. AFD endpoint/drop correlation and reason decoding must precede any fix.
Raw system traces remain external and require scoped privacy extraction before
sharing; unrelated socket events are not public NBSR evidence.

## Reproducibility and evidence

```powershell
xperf -i C:\NBSR-build\b4b-task4l-etw-20260905-141214\kernel.etl -tle -o <fresh-200-export.csv> -a dumper -range 2000000 15000000
xperf -i C:\NBSR-build\b4b-task4l-etw-20260905-141214\kernel.etl -tle -o <fresh-250-export.csv> -a dumper -range 169000000 185000000
python scripts/analyze_b4b_task4l_etw.py --capture C:\NBSR-build\b4b-task4l-etw-20260905-141214 --output <fresh-analysis-directory>
```

The analyzer expects `window-200-r1-us.csv` and `window-250-r1-us.csv` under the
capture root. Existing exports are immutable; use those directly or create a
fresh capture-copy root for reproduction. `external-inputs.json` pins original
trace, workload analyses, metadata, observer comparison and both CSV inputs by
path, size and SHA-256. `analysis.json` includes every selected flow and matched
gap-progress derivation. Prior packet and benchmark evidence remains unchanged.

The final funding package, B3-v2, soak, B1-v2, external validation and
ISP/Federation remain pending. **MORE CLOSURE REQUIRED.**

## Verification

Literal RED covered the missing network analyzer, missing filtered WPR profile,
and missing bounded gap CPU calculation. Final GREEN: 9 focused tests passed;
Ruff, PowerShell parse, WPR profile enumeration, dependency/privacy checks, and
diff checks passed. One focused independent review found no Important/Critical
issue. The original trace and workload checksum manifests verified successfully.
No production code or dependency changed, so Rust/Go suites, fmt, Clippy and vet
were not rerun for this offline analysis/capture-preparation stage.
