# Native2048 shared guest CPU diagnostic failure

MEASURED release1c103518: first2048 live-bundle attempt fails before the paired active hold.100offered/s,two source shards,existing keepalive1s,memory observer on; both roles pinned the same guest logicalCPU0. Source retains1211 materialized observation rows and10 HandshakeTimeout outcomes; zero recorded completed round trips. Remaining terminal outcomes are incomplete after cancellation. Both owned processes were killed by cleanup and their absence verified; final ownership NOT_MEASURED. No repeats launched after this failure. The result remains a retained failed partial diagnostic, not a valid capacity or memory cell.

DERIVED contained-sample shared guestCPU estimates for the last1/2/5/10seconds before the earlier final resource sample:92.0%,96.5%,97.8%,98.8%. CPU deltas use samples wholly inside each common Docker/WSL monotonic window, sum only the two owned processes, and divide by one allocated guestCPU. These are tick-quantized estimates, not strict mathematical lower bounds. The per-role whole-lifetime means alone (~48% and46%) would hide their shared allocation. Neither the CPU masks nor guest topology prove exclusive physical host cores.

Destination failure snapshot records20 cumulative live-socket UDP drops, without precise drop timing. Source UDP snapshot is UNAVAILABLE because the parser encountered a duplicate inode. Do not invent zero drops or attribute every timeout to either CPU or packet loss. The measured shared guestCPU pressure justifies a separate placement diagnostic using existing cpu_pool configuration: source[0],destination[2]. GuestCPUs0/1 are advertised SMT siblings;0/2 are different reported cores. Workload and timeouts must remain unchanged.

Native control now permits2048 only with explicit live-bundles. Idle1024 cap is unchanged.4096 is still rejected:16384 source markers exceed the existing10000-entry archive limit, while2048 fits with8192 source markers plus metadata. This is a harness export bound, not a production limit. Two literal RED tests, six focused GREEN,360 affected tests/Ruff and39-test scoped independent review PASS. Failure-analysis review corrected lower-bound wording to contained-sample estimates. Rust binaries are unchanged; no production/security/protocol optimization.

Reproduce the retained run.py/setup.py/config/build; replay: python -B evidence/performance/v2/native-live2048-1c103518/analyze.py C:/NBSR-build/native-live2048-1c103518

Safe pip HTTP/index cache cleanup recovered550723584host bytes; no locally built wheels, installed packages, source or authoritative evidence deleted. Exact guard/command/inventory retained.

Classification FAILED_PARTIAL_SHARED_GUEST_CORE_PRESSURE. Sustainable admission, repeatable boundary, physical-hardware ceiling, allocator cause and production bottleneck remain NOT_PROVEN.
