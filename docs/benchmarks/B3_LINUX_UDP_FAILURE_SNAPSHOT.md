# B3 Linux failure-only socket attribution

At2a30272e, three independent1024 live-bundle controls pass and all three2048
attempts fail. Namespace UDP RcvbufErrors deltas are118/41/151 versus
6425/13055/21244. Namespace counters establish dropped datagrams but cannot
identify the affected socket, its timing, or all handshake failures' cause.
No receive-buffer or production optimization is justified from correlation alone.

The Linux B3 backend now captures one bounded UDP socket snapshot after a
workload failure and before terminating its owned children. PID/start-time
continuity and owned FD socket inodes filter the namespace UDP/UDP6 tables.
The snapshot retains only live socket queue/drop fields; closed sockets and
exact drop timestamps remain unavailable. Kernel pointers are omitted. Missing,
exited, changed or inaccessible processes produce explicit UNAVAILABLE diagnostics.
No capture runs in the successful workload path; failure and cleanup gates stay
unchanged. Source manifests include the helper. Windows behavior is unchanged.

Literal RED: six absent-helper failures, then a real Linux fixture exposed the
UDP6 remote_address header spelling; its regression also failed before correction.
A later syntax mistake was caught and retained. Final real non-root loopback
fixture maps1 owned UDP receiver and1907 deliberately induced receive drops.
Final focused verification:47 Python tests pass, one existing platform skip; Ruff passes.
This is fixture correctness evidence, not NBSR performance. Raw validation:
C:/NBSR-build/b3-udp-failure-ec508ef6. Actual NBSR failure snapshots are pending.
