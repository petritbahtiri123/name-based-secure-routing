# Task 4e: ETW attribution

Classification: **PARTIAL / UNRESOLVED** for the 128-to-256 handshake collapse.
No production limit, runtime saturation, or sharding benefit established.
Benchmark source baseline: `9274ffc56a7d7d3d8651a599a123bfa41ac3a060`.
Only profiling orchestration, extraction, tests, and evidence changed.

## Integrity and observer effect

Capture: `C:\NBSR-build\b4b-task4e-20260903-210049`.
Kernel and network lost events: **0 / 0**. Both Rust binaries have readable
symbols. Windows kernel/system frames mostly remain unresolved addresses;
zero event loss does not imply complete symbolic attribution.
Raw ETLs and exports remain external, indexed by SHA-256 and byte size in
`external-trace-manifest.json`. Raw control/profile manifests are also stored here.

One matched control/profile pair per cell, not an authoritative capacity sweep.

| Clients | Control admitted | Profile admitted | Control admissions/s | Profile admissions/s | Rate overhead |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 128 | 128 | 37.815 | 37.887 | -0.19% |
| 256 | 201 | 253 | 37.549 | 28.763 | 23.40% |
| 512 | 272 | 258 | 49.534 | 45.139 | 8.87% |

256 and 512 profile rates are rejected for low-observer-overhead performance
claims. Their zero-loss scheduling observations remain diagnostic only.
The 256 profiled cell admitted more clients but finished more slowly: profiling
materially changed the outcome. Do not transfer its timing directly to control.
Control handshake p99 (successful handshakes only): 3032.01 / 3108.67 / 3330.94 ms.
Timeouts are censored and excluded from these successful-handshake percentiles.

## Thread and wait observations

The highest-CPU threads map to the current-thread runtimes. CPU values below
cover each process's sampled lifetime, including idle/cleanup; they are not
instantaneous handshake-phase CPU saturation measurements.

| Clients | Source PID/TID | Destination PID/TID | Source cores | Destination cores | Source switches | Destination switches |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 128 | 15320/8452 | 3652/33544 | 0.223 | 0.109 | 497 | 406 |
| 256 | 35140/25860 | 28636/19504 | 0.177 | 0.117 | 1087 | 1048 |
| 512 | 14900/29188 | 10776/22500 | 0.395 | 0.140 | 1678 | 855 |

Each admission process peaked at five threads. Source handles: 212/345/609;
destination: 84 at every cell. Full resource samples are in the raw manifests.

Matched wait/ready totals, milliseconds:

| Clients | Source wait | Source ready | Destination wait | Destination ready |
| ---: | ---: | ---: | ---: | ---: |
| 128 | 2578.562 | 16.712 | 3715.502 | 11.342 |
| 256 | 7196.567 | 37.704 | 8340.849 | 40.247 |
| 512 | 3646.999 | 71.036 | 22988.627 | 26.535 |

Missing/unmatched wakeups remain unresolved (source 48/108/126;
destination 23/65/51 intervals). These totals are lower-bound attributed times,
not complete blocked-time percentages. Terminated threads have an open final
switch-out interval; that is not evidence of a live leaked thread.
The xperf `cswitch -thread` summary reports CPU **microseconds**, not counts.
Actual counts above come from raw CSwitch events.

Sampled hotspots at both 128 and 256 include unresolved kernel/NTDLL frames,
NTFS/filter activity, TCP/IP, cryptographic arithmetic, and Quinn timeout handling.
There is no unique new dominant named CPU function proving the handshake cause.
WrQueue is the most common waiting reason on the destination; a wait reason is
not a diagnosis of a particular Quinn task, lock, or socket failure.

## Handshake attribution

The control reproduces 55 timeouts at 256 versus none at 128. The profiler changes
this to three timeouts. Small measured ready totals do not support scheduler
ready-queue starvation as the demonstrated cause. Low lifetime CPU averages do
not prove or disprove short event-loop stalls. Per-connection packet/timer
correlation and resolved blocking stacks are still needed to distinguish QUIC
timer/retry behavior, socket loss, synchronous work, and runtime scheduling.
No socket-error or ephemeral-port-exhaustion attribution is made merely because
the network trace has zero losses. Pending-client telemetry remains coarse;
per-handshake attempt timestamps are not available for every failed client.

## Separate 512 cleanup investigation

Both 512 runs exceed the existing 15-second destination cleanup bound.
The source terminal evidence is exact; source ownership counters return to zero.
Destination cleanup cannot be declared clean after forced termination.

Destination TID 22500 has a 19,148,034-us off-CPU interval from ETW timestamp
31,221,384 to 50,369,418 us, with wait reason Executive. At timestamp 31,221,209
(175 us before this interval), its stack contains:

`std::sys::stdio::windows::write -> StderrLock::write_str -> _eprint -> run -> Tokio current_thread::block_on`.

The harness creates destination stderr as `subprocess.PIPE` and reads it only
after waiting for exit/kill (`scripts/run_b4b_mixed_connections.py`, destination
spawn and cleanup). The destination synchronously prints each handshake failure
inside its runtime (`wp8_interop_server.rs`, concurrent lifecycle accept loop).
The profiled failure record contains a 4087-character stderr portion (after
Python text-mode newline normalization), ending mid-message; the control has
the same truncated ending. The native pipe capacity was not measured.
These observations strongly support unread-stderr backpressure as the cleanup
mechanism. The exact blocking syscall lacks a fully resolved switch-out stack,
so this is not promoted to complete syscall-level attribution.
It does not establish the cause of the earlier 256-client handshake failures.

## Recommendation and stop boundary

Do not shard or add workers on this evidence. The smallest supported cleanup
candidate is harness-only continuous draining of destination stderr (or direct
file redirection), preserving every byte and existing deadlines. It is **not
implemented**. For handshake attribution, resolve system symbols and correlate
the existing per-connection network trace with deadlines before requesting a
runtime optimization. No production, protocol, wire, security, ACK, limit, or
frozen-authority change was made. Task 4e remains PARTIAL; B3-v2 not started.

## Reproduction and verification

Run elevated: `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/capture_b4b_task4e.ps1`.
Export raw events (set `_NT_SYMBOL_PATH` to the capture's release binary directory):

```powershell
& 'C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit\xperf.exe' -i C:\NBSR-build\b4b-task4e-20260903-210049\task4e-kernel.etl -symbols -o C:\NBSR-build\b4b-task4e-20260903-210049\kernel-events.csv -a dumper -stacktimeshifting
python scripts/analyze_b4b_task4e.py --capture C:/NBSR-build/b4b-task4e-20260903-210049 --output <fresh-output-directory>
```

Focused RED: 2 analyzer tests fail with missing module; GREEN: 2 pass.
Complete focused check: `python -m pytest tests/performance/test_b4b_task4e_profile.py tests/performance/test_b4b_task4e_analysis.py tests/performance/test_b4b_task4c_profile.py -q` — **9 passed**.
Pytest exit cleanup additionally reports an existing `pytest-current` WinError 5;
no test failed. Ruff on the new Python files and `git diff --check` pass.
Rust/Go/fmt/clippy not rerun: no Rust/Go, benchmark implementation, manifests,
dependencies, or authority files changed. Capture built release binaries; hashes
are recorded in both raw manifests. Original Task 4c evidence is unchanged.
