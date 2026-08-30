# Funding-Grade Benchmark V2: B2 Plateau Profiling

## Scope

This Task-1 result profiles the current source baseline on one Windows loopback host. It does not change production code or benchmark semantics and does not establish a WAN, NIC, server-class, or production ceiling.

The release benchmark uses one outstanding request/response operation per active stream. Direct was swept at 1, 2, 4, 8, 16, 32, 64, 128, and 256 streams. The unchanged NBSR destination accepts only 1, 8, or 64 streams; its rejection of other counts is retained as a harness limitation rather than bypassed.

## Processor topology and affinity

Windows `GetLogicalProcessorInformationEx(RelationProcessorCore)` reported four physical cores and eight logical processors. Each physical core has two SMT siblings:

- core 0: logical mask `0x03`
- core 1: logical mask `0x0c`
- core 2: logical mask `0x30`
- core 3: logical mask `0xc0`

The primary comparison selected one logical processor from each distinct physical core. Exact server and client masks were set and read back for every repeat:

- 1 core: `0x01`
- 2 cores: `0x05`
- 4 cores: `0x55`

These are physical-core-separated logical-processor selections. They are not a claim of exclusive core isolation: Windows and unrelated host work were not isolated from the selected cores.

## Workloads and controls

Both Direct and NBSR used release binaries from source SHA `0c5e6ae41251b21d0d9d6e659a1b15a9da5dc2e0`, a 3-second warmup, a 10-second measured interval, and at least three repeats. Cells above 5% throughput CV were extended to five repeats. Bad-but-valid dispersion was preserved.

The representative cells were 1 KiB/64 streams and 16 KiB/8 streams. Raw results include application goodput, operations/s, p95/p99, process CPU time, effective cores, memory, errors, exact affinity requests, and exact observed affinity masks.

## Profiling capability and observer overhead

Windows Performance Recorder 10.0.26100 is installed, but `wpr.exe -start CPU -filemode` failed with `0xc5585011` because the host did not permit enabling the system-performance profiling policy. No `wpaexporter.exe`, `xperf.exe`, or `PerfView.exe` was installed. No system software or policy was changed.

Consequently no reliable CPU stack/wait trace exists and profiling overhead cannot be measured. The run does not substitute aggregate CPU utilization for stack attribution.

## Classification

The throughput plateau reproduced while effective CPU consumption remained below the allocated physical-core-separated processor count. Direct and NBSR showed the same broad scaling shape at their matched supported cells. However, the data cannot distinguish one-outstanding request/response serialization from scheduler wakeups, QUIC/runtime waits, copying/allocation, lock contention, or another software/harness owner.

Classification: **Evidence PARTIAL / System UNRESOLVED**.

No production optimization is justified by this task. Before optimization, obtain readable CPU-stack/blocked-time evidence and a separately approved harness-only diagnostic that can vary outstanding depth and NBSR stream counts without changing workload accounting or transport semantics.

## Reproduction

```powershell
$env:CARGO_TARGET_DIR = 'C:\NBSR-build\b2-v2-profile'
python scripts/profile_b2_v2.py --output evidence\performance\v2\b2-profile-0c5e6ae41251 --warmup-seconds 3 --duration-seconds 10 --repeats 3 --streams 1,2,4,8,16,32,64,128,256
python scripts/profile_b2_v2.py --output evidence\performance\v2\b2-profile-0c5e6ae41251 --analyze
```

The analysis command regenerates derived files and checksums from stored raw repeat JSON. It also repeats the non-mutating WPR capability probe.
