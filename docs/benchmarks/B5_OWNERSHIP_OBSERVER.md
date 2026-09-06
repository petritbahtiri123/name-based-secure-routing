# Optional grouped-soak ownership observation

Status: implemented and unit-tested; live observer qualification pending.
Use `--ownership-sampling` on `scripts/run_b5_v2.py` to request periodic NBSR
ownership evidence. Direct remains explicitly NOT_MEASURED for runtime ownership.
Compare NBSR sampling off/on with identical binaries, shape, rate, affinity and
progress cadence before accepting performance timing with observation enabled.

The source publishes one process-global snapshot after all groups are ready and
then at independent one-second intervals. Its elapsed timestamp is read at actual
observation time; callback/output failures invalidate the run. Destination files
use their existing one-second sampler and ten-record buffering. The destination
checks successful open/write/nonempty sampler completion before publishing PASS.
No production protocol or security path changes.

The controller tails each original file at most once per second, in at most
sixteen 64 KiB chunks per poll, bounds partial lines and sample counts, rejects
file replacement/truncation and malformed counters, and retains receipt metadata.
Original source/destination files remain authoritative. Only sixty projected
snapshots per role are held for growth analysis. Process-local clocks remain
separate; receipt timestamps do not establish exact cross-process phase alignment.

Predeclared growth gate: after twelve snapshots, strictly increasing medians of
three consecutive thirds of the retained window abort as a sampled-growth
diagnostic. This examines eleven current ownership counters and emitted retained
capacities, not cumulative creates/inserts or high-water counts. A single setup
step followed by a plateau does not trigger. An abort is not proof of a leak.
Qualification requires every role, at least twelve samples per role, no snapshot
gap over three seconds, and local time coverage within two seconds of issue
duration. Separate post-close reports must still show all eleven counters zero.

For fresh long-soak trials, predeclare thirty-second progress windows. At 2,000
completed operations/s with stride 64 this gives about 937–938 latency samples
per window, compared with 31–32 at one second. The p99 drift threshold stays 20%,
goodput threshold stays 5%, and pacing windows remain ten milliseconds. The first
three-window drift comparison occurs around ninety seconds. Offered rate, issue
duration, security and timeout budgets are unchanged. The earlier seven-second
abort at one-second cadence remains FAIL/DIAGNOSTIC in b5-controller-live-3644c324.

These gates establish sampled coverage only. Thermal data, allocator attribution,
graceful internal thread joins on failure, and server/WAN performance remain
outside this observation's claims. Long repeated soaks are still pending.
