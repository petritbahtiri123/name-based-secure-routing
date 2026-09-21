# Native lifecycle shared/split guest CPU diagnostic

The 1024/200 finite cohort completes five times but has approximately one-second
cold-handshake p99 and high dispersion. Both Rust roles select guest CPU 0.
Their separately sampled activation CPU is substantial; differing intervals do
not yet prove simultaneous core saturation. Test CPU placement before attributing
the delay to production or changing the implementation.

Smallest harness extension: optional explicit per-role logical CPU pool, checked
against inherited availability and the existing physical/NUMA selector. Keep the
controller/observer affinity unchanged. Defaults and all workload/security gates
remain unchanged; do not pin entire containers, which would confound observer
placement with child placement. Reject unavailable CPUs, duplicates, bools and
SMT siblings masquerading as distinct physical cores.

RED/GREEN, focused tests/review and atomic implementation commit precede the new
exact-SHA release build. Compare 1024 bundles at 200/s, two shards, 1 KiB, native
local fixtures and unchanged two-second hold: shared source/destination [0]/[0]
versus split [0]/[1]. Verify actual resource affinity. Use five counterbalanced
pairs with the same private test fixture bytes within each pair and fresh
namespaces per cell. Preserve every failure, stop for cleanup failure or less
than 5 GiB disk reserve. No concurrent workload/capture campaign.

This is a guest allocation sensitivity diagnostic, not one-versus-two verified
host physical cores, sustainable admission, production optimization or hardware
ceiling proof. No timeout/keepalive/packet/authority change. The existing socket
observer and gates are identical between arms. Final timing remains diagnostic
and all unfavorable outcomes/dispersion remain visible.

Remain under this turn's absolute 27% account usage ceiling; reserve checkpoint
space and retain any incomplete cohort rather than manufacturing completion.
