# Native same-process lifecycle cycles

The native bundle coordinator proves one concurrent lifecycle, while the existing Rust benchmark peers already support sequential connections in one process. This is a harness coverage gap, not an attributed production bottleneck.

1. Add a separate bounded sequential workload contract (1, 2, 4, 8, 16 cycles; one session/channel/materialized stream at a time). Preserve the concurrent bundle contract and all transport deadlines. Both peers remain alive across cycles; source has the existing final-release gate. No offered-rate or concurrent-client claim applies.
2. Add cycle-aware private management barriers: start only the next ordinal, verify both active, hold two seconds, release both, verify source ACK, cooldown two seconds before next start. Retain per-cycle socket snapshots and resource samples; do not equate ACK with all background resources already reclaimed.
3. Bind retained events, commands, process epochs, exact cycle completions and final eleven-counter cleanup independently. Reject skipped/duplicate/out-of-order cycles, stale markers, changed process identity and partial collection. Keep bounded cancellation/EOF handling.
4. Focused literal RED/GREEN, affected tests, one review; then current release three actual namespace repetitions, five if relevant CV exceeds 5 percent. Preserve all failures. No physical hardware, qualified memory cost, sustainable admission or leak claim from diagnostic completion alone.

Stage 1 is a prerequisite only. The remote cycle runner is not available until stages 2-4 are completed and verified. Per-axis channel/stream scaling remains subsequent scope.

Prerequisite stage: command contract, local cycle barrier, transcript ledger and abstract driver implemented. Initial RED: 8 command, 13 barrier, 8 ledger failures. Review ordering defect: 2 RED regressions fixed. 114 affected tests, Ruff, scoped review/re-review PASS. Endpoint integration, independent collected-evidence gate and actual current-release runs remain OPEN. No cycle measurements claimed.
