# Benchmark V2 Task 3 Stage 3: shared destination profiling

Classification: **PASS / HARNESS-LIMITED: shared destination QUIC listener/endpoint-driver runtime**

The matched 16 KiB, one-stream, outstanding-four controls reproduce the lack of useful 1/2/4-group scaling. The unprofiled destination process stays at approximately one effective core while aggregate throughput plateaus or falls. ETW context-switch accounting identifies one destination main thread consuming 94.6% to 97.1% of one core in every Direct and NBSR cell. Additional per-group application-handler threads together consume only 18.5% to 22.1% of one core. This proves that all independently authorized groups still serialize through the shared destination listener/endpoint-driver runtime.

| Path | Groups | Control Gbit/s | Control destination cores | Control p99 ms | Main thread core | Handler cores | Main-thread ready events |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct | 1 | 2.333 | 0.967 | 0.698 | 0.948 | 0.221 | 6,796 |
| Direct | 2 | 2.269 | 0.965 | 1.651 | 0.969 | 0.191 | 516 |
| Direct | 4 | 2.139 | 0.957 | 4.257 | 0.946 | 0.193 | 190 |
| NBSR | 1 | 2.363 | 0.859 | 1.158 | 0.969 | 0.000 | 712 |
| NBSR | 2 | 2.390 | 0.957 | 1.512 | 0.971 | 0.185 | 392 |
| NBSR | 4 | 2.121 | 0.972 | 4.673 | 0.957 | 0.202 | 198 |

NBSR control throughput changes by +1.1% from one to two groups and -10.2% from one to four groups; p99 rises 4.0x by four groups. Direct changes by -2.7% and -8.3%, with p99 rising 6.1x. Both paths therefore show the same destination serialization pattern. The earlier NBSR-versus-Direct +34.85% cell is not generalized.

Destination sampled CPU is dominated by kernel/socket/network processing (58.5% to 66.2%), followed by cryptography (6.2% to 9.7%) and visible Quinn endpoint/connection-driving stacks (3.5% to 5.1%). NBSR lock/synchronization samples remain only 0.4% to 0.8%, so lock contention is not the measured primary limit. ReadyThread wakeups for the destination main thread fall as group count rises because the thread becomes continuously runnable rather than sleeping between events.

The ETW profiler reduced throughput by 6.9% to 35.7%. Profiled throughput is therefore not used as a capacity measurement. Attribution remains defensible because the unprofiled controls independently show destination utilization near one core, while ETW supplies thread and stack identity. The trace contains zero lost events and readable symbols for all three Rust binaries.

The smallest recommended harness-only experiment is one independently bound destination QUIC endpoint/listener and current-thread runtime per group, using distinct loopback UDP ports and identical Direct/NBSR topology. No production runtime, protocol, security, stream cap, trust, authorization, or ACK change is recommended or authorized here.

The 635 MB merged ETL, 627 MB raw ETL, and 3.46 GB ReadyThread export remain outside Git under `C:\NBSR-build\max-throughput-v2-stage3-20260902-211248`. Their sizes and SHA-256 digests are pinned in `external-trace-manifest.json`.
