# One physical core: current fixed-shape forwarding ladder

MEASURED Windows loopback, 16 KiB, one stream, one endpoint group, one shared physical-core pool for both processes; no SMT sibling. This is a particular closed-loop workload, not the maximum of all stream/group shapes or a WAN/server capacity claim.

| Outstanding operations | Direct median Gbit/s | Direct classification | NBSR median Gbit/s | NBSR classification |
|---:|---:|---|---:|---|
| 1 | 0.624863 | STABLE | 0.611685 | STABLE |
| 2 | 0.986758 | STABLE | 0.870949 | UNRESOLVED |
| 3 | 0.943938 | DEGRADED | 0.947627 | DEGRADED |
| 4 | 0.828101 | SATURATED | 0.881301 | SATURATED |
| 8 | 1.114484 | SATURATED | 1.136810 | SATURATED |
| 16 | 1.093011 | SATURATED | 1.161223 | SATURATED |

Every cell has three valid repeats, five when either matched path exceeded 5% CV. All 48 repeats are retained with successful cleanup and zero errors/timeouts. NBSR depth 2 remains UNRESOLVED at 6.268% CV despite lower median p99; it is not promoted to stable capacity. NBSR observed peak 1.174746 Gbit/s remains DIAGNOSTIC.

NBSR depth 1: 2333.394 operations/s, sampled CPU 383689 ns/op, effective CPU 0.895 cores. At depth 16: 4429.715 operations/s, sampled CPU 220084 ns/op, 0.975 cores, median p99 5.791 ms versus depth-1 reference 1.049 ms. The allocated physical core is measured busy at high depth; this is not a machine-wide hardware ceiling or production hotspot attribution. Allocation counts, syscalls and context switches were NOT_MEASURED.

Analysis uses scripts/performance/physical_core_analysis.py. It binds the lowest-load p99 reference to all six depths and preserves every unfavorable valid repeat. Refinement source SHA differs only in non-execution work: binaries, both retained execution scripts, topology/placement, warmup and duration were compared and match. Full source identities remain in environments.json; no exact-SHA identity is invented.

Each cell used 3 s warmup and 30 s measurement. Source and destination process affinity share mask 0x1, selected from the verified four-physical/eight-logical topology. Process CPU is sampled every 0.5 s over the final measured-duration window; boundary fragments and host interrupt work are excluded, so CPU ns/op is a sampled estimate.

Environment qualification: the user reported starting Docker Desktop near the end of refinement. Its launch timing and resource impact were not separately instrumented. All refinement results remain retained; a quiet-environment confirmation is required before final funding freeze if this disturbance could affect a load-bearing claim. No Docker image build or test suite ran during the ladder; Docker API inventory was read only.

Raw roots and complete 185/97-entry checksum indexes are retained externally and verified. Repository records are normalized JSON, not byte-identical raw copies. Source/binary artifacts remain external. This is an intermediate campaign package, not the final maximum-throughput or multi-core result.
