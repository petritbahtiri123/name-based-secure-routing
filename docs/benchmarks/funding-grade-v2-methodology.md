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

## Task 2 harness-only baseline transition

Task 2 changes only code compiled behind the `benchmark-harness` feature. The historical baseline computed SHA-256 over every payload inside the timed operation. The new baseline retains the same payload lengths, operation counts, latency boundaries, error rules, and frame length, but moves full-payload SHA-256 validation to preflight, postflight, and every 1024th timed operation. The remaining operations validate a deterministic tag and eight bounded payload probes. Direct and NBSR use the same framing and outstanding-work accounting.

The diagnostic stream range is now 1 through 64. `--p2a-outstanding-per-stream` accepts 1 through 64 and defaults to 1. The production 64-stream-per-channel limit is unchanged. The benchmark rejects a completion that is not the oldest outstanding sequence and records the configured and maximum observed outstanding depth.

This is a new V2 benchmark baseline. Comparisons with the earlier full-SHA baseline measure removal of benchmark interference; they are not production NBSR speedup claims. The pre-fix profiler trace and results remain under `historical-task1b/`.

### Matched release sweep

All authoritative Task-2 cells used Windows affinity mask `0x55`, which was previously verified as four physical-core-separated logical processors. The exploratory sweep covered 1 and 16 KiB payloads, 1, 2, 4, 8, 16, 32, and 64 streams, and outstanding depths 1, 2, 4, and 8. Selected stable, peak, and degraded cells then ran five 10-second repeats after a 3-second warmup. All 112 exploratory and 80 authoritative result records were valid with zero benchmark errors or timeouts.

The stable NBSR ceiling observed for 1 KiB was 1.997 Gbit/s at 64 streams and one outstanding operation per stream (CV 1.4%, p99 0.804 ms). For 16 KiB it was 2.290 Gbit/s at one stream and four outstanding operations (CV 0.4%, p99 0.645 ms). Larger outstanding queues did not establish a higher stable ceiling and increased tail latency. These are Windows-loopback harness ceilings, not host hardware or production ceilings.

At the selected 16 KiB stable cell, Direct measured 2.312 Gbit/s and NBSR 2.290 Gbit/s, a measured NBSR delta of approximately -0.95%. At the selected 1 KiB stable cell, Direct measured 2.027 Gbit/s and NBSR 1.997 Gbit/s, approximately -1.48%. Derived values and every repeat are stored in `analysis.json` and `authoritative/`.

### Post-transition profiling

The post-transition ETW trace had zero lost events and readable Rust symbols. Its observer overhead was explicitly measured at 7.26% for Direct and 8.23% for NBSR, so its throughput values are rejected as authoritative. The trace is retained for qualitative stack attribution only. The matched unprofiled controls remain authoritative.

SHA-256 no longer dominates the sampled stacks. The next visible benchmark owner is the single-thread runtime boundary: all three benchmark binaries use Tokio `current_thread`, and at the stable peaks each source and destination process consumed approximately 0.9 effective core despite affinity mask `0x55`. QUIC packet processing, encryption, polling, and Windows networking are visible below that boundary. This supports **Evidence PASS / System HARNESS-LIMITED** for Task 2, but it does not justify a production optimization or identify a host hardware ceiling.

### Task 2 reproduction

```powershell
$env:CARGO_TARGET_DIR = 'C:\NBSR-build\b2-v2-profile'
python scripts/profile_b2_v2.py --output <output> --warmup-seconds 3 --duration-seconds 10 --repeats 5 --max-repeats 5 --streams 1,2,4,8,16,32,64 --payloads 1024,16384 --paths direct,nbsr --affinities 4 --p2a-outstanding-per-stream 1,2,4,8
python scripts/analyze_b2_v2_optimization.py --evidence-root evidence\performance\v2\b2-optimization-8721b95177bd --historical-root evidence\performance\v2\b2-optimization-8721b95177bd\historical-task1b\control --historical-root evidence\performance\v2\b2-profile-0c5e6ae41251
```
