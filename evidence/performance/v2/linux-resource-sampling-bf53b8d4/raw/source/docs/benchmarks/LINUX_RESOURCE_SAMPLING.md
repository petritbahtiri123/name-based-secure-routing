# Bounded Linux resource sampling

`scripts.performance.linux_resources` supplies a process sampler primitive. It does
not port B3/B4/B5 controllers or establish dedicated-server/two-host validation.

`parse_smaps_rollup` requires exactly one each of `Rss`, `Pss`, `Private_Clean`,
`Private_Dirty`, and `Private_Hugetlb`, in nonnegative integer kB. Output bytes use
1024 bytes/kB. Unknown kernel fields are ignored. `private_resident_bytes` is
Private_Clean + Private_Dirty; `private_hugetlb_bytes` is separate. Neither is
Windows private commit, allocator live allocation, or an RSS alias. Huge-page
accounting must remain separately labelled when interpreting memory trends.

`sample_linux_process(pid, cpus)` reuses the existing Linux reader, checking
PID/start identity before and after memory access, each observed thread's affinity,
and unexpected child processes. Missing or denied live `/proc` data fails closed.
An unchanged zombie returns `memory_state=UNAVAILABLE_ZOMBIE` and null memory
values, preserving final CPU evidence; it never invents zero private memory.
The memory, CPU and affinity reads are sequential observations, not an atomic
kernel snapshot. The timestamp is the final process reader's monotonic timestamp.

`LinuxResourceSampler(processes, cpus, interval_seconds=..., max_records=...,
record_sink=...)` is start-once, maintains a hard retained-record cap, checks
per-role identity and monotonic CPU/time, and latches sampling or sink failures.
The sink receives an independent copy after the record is retained. Snapshot
callers likewise receive independent copies. A live sampler treats process exit
or unavailable memory as failure; callers needing final zombie CPU must stop the
live sampler at the expected activity boundary and perform an explicit postflight
read before reaping the child. `stop()` joins with a fixed five-second bound and
cannot turn a failed or empty stream into successful evidence. Python cannot
forcibly cancel a blocked user callback: a join timeout fails and the thread may
remain alive until the callback returns. Sinks must therefore be bounded.

Callers must verify owned PIDs and their intended physical/SMT placement, reserve
sufficient cap for all roles and the full fixed deadline, persist sink records,
poll `check_health(require_running=True)` even during source silence, and retain
`records_snapshot()` on failure. A sink error cannot guarantee disk persistence
of the failing record. Workload-specific Linux memory growth gates, source phase
alignment, ownership histories, final cleanup and partial stdout retention remain
controller obligations. Cgroup limits/guest topology need separate recording.

Verification: literal missing-module RED, then 25 missing-class RED failures with
18 reader tests passing; final 49 focused tests (including existing zombie tests)
and Ruff pass. A restricted existing-image diagnostic observed an owned Python
child's real private-resident memory and same-identity zombie null metrics, then
joined the child and removed only its inspected stopped container. Image:
`sha256:dd08db4a391b16a9d303a251d2693808baf470f2fc4870d8e3c54b7523deed71`.
Network-none, nonroot, read-only root/staged source, no capabilities,
no-new-privileges, 128MiB memory/swap bound, one-CPU quota and 32-PID bound were
applied. This is Linux container compatibility evidence, not performance or
external-hardware qualification. Raw logs, inspect record and tested source hashes:
`C:/NBSR-build/linux-resources-20260906`.
