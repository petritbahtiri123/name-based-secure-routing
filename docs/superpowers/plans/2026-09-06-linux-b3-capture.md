# Linux B3 capture and analysis

Scope: add explicit per-run Linux capture/placement to the existing Rust B3
lifecycle controller. Preserve Windows defaults, source planning, all barriers,
deadlines, report/release order and eleven-counter cleanup. No transport changes.

1. Add literal RED tests for Linux capture identity continuity, missing live data,
   exact role sums without Windows aliases, taskset prefix, and final-cooldown
   backend propagation before release. Implement a per-cell backend, no globals.
2. Add explicit `--platform linux --cores 1|2|4` selection and Linux executable
   suffix. Record lscpu/inherited affinity, cgroup limits and tool/platform details.
   Prefix both source/server commands before launch/readiness. Capture all live
   processes with PID/start checks across every phase; missing telemetry aborts
   before active/report release and retains the partial prefix.
3. Add a separate Linux analyzer with literal RED tests. Require same-process
   cycle identity/count, complete phases and cleanup; preserve residency/resource
   scopes and 3-valid/5-if-CV-over5 gates. Name private-resident, RSS/PSS, hugepage,
   FD/thread metrics explicitly. Do not alias Windows commit or infer leaks.
4. Run focused existing/new B3 tests and scoped Ruff, then parent review. Docker
   compatibility is separately coordinated after tests; no new image/build. Any
   older retained binary is labelled separately from current Python source SHA.

This stage supplies Linux single-host capture, not remote orchestration, dedicated
hardware qualification, B4/B5 portability or performance acceptance.

## Completion status

Implementation and focused review: COMPLETE. Original review identified expected
bundle-source exit and unbound analyzer pooling; both received focused RED/GREEN
fixes and scoped parent rereview PASS with no further Important findings.
Final agent suite69 PASS/1 opt-in liveSKIP; parent independently63 PASS/1 liveSKIP
(omitting six unchanged Windows analyzer tests). Ruff and diff checks PASS.
Docker/runtime compatibility: NOT_RUN; separately coordinated after quiet measurements.
Canonical evidence: `evidence/performance/v2/linux-b3-capture-dc4de434/`.
