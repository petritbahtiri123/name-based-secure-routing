# Native post-close observer qualification

REJECTED_OBSERVER_GATE. Exact source ac40740c, unchanged release binaries,
NBSR 16 KiB / eight streams / depth one, 3 s warmup and 20 s measurement,
both Rust peers on guest CPU 0 in separate Docker/WSL namespaces.
The existing pre-run ownership diagnostics plus post-close reports were toggled
on both roles. Five uninterrupted counterbalanced on/off pairs are available.

MEASURED: all twelve individual cells passed payload/accounting, process exit,
independent pair integrity and exact-PID absence before fixture stop. All requested
NBSR post-close reports satisfy eleven zero live/entry counters. In the five
uninterrupted pairs, median paired goodput change is -5.3273%, p99 change +63.0342%;
off/on throughput CV 25.36% / 32.28%. Both five-percent effect and repeatability
gates fail. High background variance prevents assigning these changes solely to
the observer, and no production bottleneck or optimization is justified.

Pair 3 was interrupted between off and on by the predeclared five-GiB disk reserve.
It remains fully retained and reported. One predeclared sixth pair supplies the
fifth uninterrupted comparison. Across all six pairs, median changes are -3.3592%
goodput / +40.8428% p99; off/on CV 23.20% / 29.06%. No unfavorable run was discarded.

NOT_PROVEN: observer-free strict-stable reference, physical-core/host ceiling,
causal NBSR overhead, external/server performance, long-run retention or soak.
The functional cleanup mode remains useful, but these timing results cannot
qualify a native B5 ceiling. Existing historical scores are not replaced.

Safe disk maintenance used cargo clean on five inactive, explicitly verified
C:/NBSR-build Cargo targets. Immediate measured free-space increase was
4,635,074,560 bytes, from 5,997,096,960 to 10,632,171,520 bytes. Earlier independent
low-space observation was 4,065,542,144 bytes; do not attribute the intervening
change to cleanup. Source, Git, authoritative evidence and private fixtures remain.

Reproduce: `python evidence/performance/v2/native-post-close-observer-ac40740c/analyze.py`.
All raw cells, interruption/resumption/extension scripts, commands and cleanup
inventory are retained by raw-evidence.json. Resource CPU fractions are lifetime
sample-interval diagnostics, not steady CPU ns/op. Checksums are not signatures.
