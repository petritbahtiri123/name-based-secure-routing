# Native2048 split guest-core diagnostic

PARTIAL_FAILED_REPEAT: same release1c103518, 2048 live bundles at100 offered/s,
two source shards, existing1s QUIC keepalive, private-memory observer enabled.
Source guestCPU0 and destination guestCPU2 advertise distinct socket/core pairs;
physical host placement is NOT_PROVEN. No binary, timeout or production change.

Three attempted trials:2 PASS_FUNCTIONAL /1 FAIL_RETAINED. The two passes complete
4096 total authenticated connections/1024-byte round trips; both final eleven
ownership counters zero. Six owned PIDs absent before container shutdown.
The failed third trial has1773 source materialized observations,3 HandshakeTimeout
outcomes and0 recorded completed round trips. Materialized rows are partial,
not all terminal admission outcomes. Cancellation killed both owned groups;
failed-trial final ownership NOT_MEASURED. All outcomes remain in raw evidence.

Failed-trial source has2048 live socket inodes and0 drops; destination has1 UDP
socket and617 cumulative drops. Snapshot does not locate event times or prove
which timeout a drop caused. Last5s contained process CPU estimates are0.894
source/0.940 destination effective guest cores (91.7% of the two allocated cores).
These tick-quantized estimates exclude unowned observer/kernel work, are not
strict lower bounds and do not establish a physical hardware or NBSR ceiling.

Private resident phase medians in the two successful trials (MiB):

|Trial|Source active|Destination active|Destination cooldown|
|---|---:|---:|---:|
|n2048-r1|801.494141|618.828125|619.265625|
|n2048-r2|811.523438|627.523438|627.835938|

These are diagnostic process totals, not isolated bytes/connection/session/channel.
Two successful repeats do not meet the minimum3 valid-repeat acceptance gate;
no stable2048 claim, no qualified CV or throughput/admission boundary. Source
cooldown and failed-trial final ownership are unmeasured. Observer neutrality
and per-timeout CPU/socket attribution remain unresolved. Do not advance4096.

Replay: `python -B evidence/performance/v2/native-live2048-split-1c103518/analyze.py C:/NBSR-build/native-live2048-split-1c103518`.
Analyzer verifies exact cohort, release/binary hashes, sealed indexes, placement,
PID epochs, monotonic CPU samples, success ownership and measured drop totals.
Fresh scoped read-only review found no important issues. Raw run/setup scripts,
configs, commands, telemetry and failed cleanup are retained and checksummed.
Next diagnostic: same workload/placement without the optional memory observer;
a non-counterbalanced off cohort cannot qualify observer neutrality or causation.
