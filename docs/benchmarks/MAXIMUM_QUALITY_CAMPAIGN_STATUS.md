# Maximum-quality campaign: current state

Working status, 2026-09-06. **NOT a final evidence freeze.** Technical outreach must retain the historical/diagnostic qualifications below. Repository branch: `codex/nbsr-v3-wp0-wp1`; protected `main` and `origin/main`: `1938154d498b32d81a3564319969430644e8a688`. No push or main integration is authorized.

| Area | State | Evidence and next gate |
| --- | --- | --- |
| Historical forwarding | DONE / HISTORICAL | Accepted strict-stable 2.185 Gbit/s, latency-degraded 2.942 Gbit/s, saturated observed peak 3.040 Gbit/s; Windows loopback only. Current production-buffer SHA requires fresh matched measurements before calling these current. |
| Historical admission | DONE / HISTORICAL | 125 offered/s: 119.813 actual/s strict-stable in its accepted stage; 150 degraded, 200 saturated. Two-shard scheduling improved the saturated 200/s cell but did not move boundaries. |
| Windows UDP receive buffer | DONE / MEASURED, scoped | Production and Direct listener buffer raised to bounded 1 MiB on Windows, based on captured insufficient-local-buffer drops. Paired five-repeat 250/s p99 improved, but admission dispersion remains high and p50 worsened. Post-fix captured workload recorded no AFD datagram drops. This is not a general capacity proof. |
| Residual handshake progress | UNRESOLVED / PLATFORM_DIAGNOSTIC_LIMIT | ETW, AFD and accept-pump observers failed matched distortion gates. Task 4n preserves 20 valid clean runs and 201 verified artifacts; no further implementation optimization follows from these profiles. |
| Invalid comparisons | INVALID for causal attribution | SHA-mismatched capture remains diagnostic only; all failed observer comparisons and unfavorable valid repeats remain preserved. |
| Physical-core forwarding | PARTIAL / MEASURED | One-core fixed-shape package remains accepted separately. Current exact-SHA 2/4-core ladders preserve 90 valid records and 786 verified raw artifacts. Four-core NBSR strict-stable: 2.306118 Gbit/s, five repeats, CV 0.908%; observed 3.666140 peak is DIAGNOSTIC only. Two-core baseline remains UNRESOLVED by dispersion. See physical-core-multicore-53468db4. Endpoint-group controls are preserved at physical-core-group-controls-fe755be0. One-core 1KiB/64-stream depth1 measured 0.866384 Gbit/s; two-core baseline remains dispersed. Fresh cbdca987 one-core calibration now preserves 46 valid records / 271 raw hashes: 16KiB/8 depth1 1.052536 Gbit/s STABLE, depth2 DEGRADED, depth4/8 SATURATED; 1KiB/64 depth1 0.865859 STABLE, depth2 DEGRADED, depth4 SATURATED. Sampled baseline CPU is 0.968/0.983 effective cores in the one-core allocation. See physical-core-calibration-cbdca987. Other useful multicore shapes and final source-compatible soak calibration remain pending. Earlier process cleanup is not a two-sided ownership proof; see P2A_POST_CLOSE_OWNERSHIP.md and p2a-ownership-observer-564df326. |
| Sustainable admission after buffer change | PARTIAL / fresh finite-batch MEASURED | admission-fresh-1917b195 preserves 27 valid repeats / 254 verified raw artifacts: 125 offered/s gives 119.920 actual/s STABLE; 150 gives 138.887 DEGRADED; 200 gives 176.182 SATURATED by achieved/offered ratio. All 13,824 admissions succeed, errors/timeouts zero. 25/50 remain DEGRADED by forwarding dispersion. This 512-client batch is not a sustained admission soak or physical-core capacity proof; source ownership is terminal/process scope. |
| B3 memory/lifecycle | PARTIAL / substantial MEASURED scale | 35 clean b29054b9 cells span 32..2048 materialized streams across 32 fixed channels, five repeats/count, all 11 final ownership counters zero on both roles; 325 raw hashes verified. Earlier a6d46796 has five same-process 50-cycle repeats, source per-cycle and both final ownership zero, unchanged cooldown handles. Combined wide-stream active-private slope is DERIVED 40,473.34 bytes/stream including runtime/fixture costs. Separate 512-bundle cohort passed five repeats; 1024 setup stalled. Private-retention cause remains INCONCLUSIVE. See b3-wide-streams-b29054b9 and b3-materialized-scale-a6d46796; their independent raw analysis already verifies11 fields beyond the old8-field runner gate. The Rust runner now enforces11 exact-integer-zero fields at c6b2db86, with42 literal RED cases,85 focused tests and12 retained Linux cell replays. All failed attempts remain retained. |
| B5 near-ceiling soak | NEEDS_RERUN / bounded live controls PASS | Grouped controller, periodic ownership, strict output/resource bounds and final eleven-counter cleanup are live. Three Direct/NBSR 120-second light-load controls pass at aec0a989 (168 verified raw artifacts; fifteen NBSR cleanup reports). This is DIAGNOSTIC integration, not near-ceiling capacity or an authoritative soak. Earlier short-window drift abort remains retained. At cbdca987, the 16KiB/8 one-core 70% finite-ceiling periodic observer comparison retained two valid 120-second diagnostics and an observed-repeat abort around90 seconds: goodput fell5.417%, p99 rose2.275x, tracked CPU remained about0.75 core. Its62 raw hashes are preserved at b5-observer-drift-cbdca987. Observer causality and long stability remain INCONCLUSIVE; no thresholds were relaxed. A later fixed historical-load off-arm at1cca67ad aborted around90s on p99 ratio1.214542 with goodput ratio1.008262; PDH was never launched and remains NOT_EVALUATED (b5-pdh-baseline-failure-1cca67ad). The missing receive-origin serialization is corrected at8c612c87 with32 controller tests; old timestamps remain unavailable. Final source-compatible calibration, successful observer qualification and60/120-minute repeated soaks remain pending. |
| B1 packet delta | DONE / SCOPED ACCOUNTING | Twenty captures, five matched pairs for each of two workloads, pass readiness/loss/inventory gates. Setup relay UDP-payload delta is consistently positive; established and whole-PCAP deltas cross zero. No stable-sign data overhead or phase-aligned IP/L2 claim. See `evidence/performance/v2/b1-packets-e2c75b59/REPORT.md`; all 200 raw checksums and canonical package blobs verified. |
| Security regression | PARTIAL / CURRENT SCOPED GATES PASS | Adversarial refresh bf53b8d4:13 executable fail-closed scenarios PASS, zero FAIL,45 raw hashes verified; its direct-origin case remains INCONCLUSIVE. The prior b7df259b report is retained. Separate accepted ISP isolation package f831c9bb closes the scoped client/ISP-A reachability case with three genuine Docker network lifecycles. Final quality/dependency/privacy closure remains pending. |
| ISP private-origin isolation | DONE / SCOPED MEASURED | Three lifecycles at f831c9bb denied four direct-origin probes, then returned the exact authorized body with exactly one accepted origin request. Destination process completed and all campaign containers/networks/volumes returned to zero. See evidence/security/isp-isolation-f831c9bb. Shared fixture bootstrap material, unmeasured runtime ownership counters and no live federation remain explicit limitations. |
| Federation | NOT_PROVEN for live runtime | Admission preflight and secure-route isolation must be reported separately from live runtime federation. No legacy demo evidence substitution. |
| External validation | EXTERNAL_HARDWARE_REQUIRED / PARTIAL definition | No suitable external host has been established. The Linux loopback runner and seven synthetic tests are committed; Linux Docker compatibility now passes six valid repeats at 3644c324 after the proven zombie FD sampler repair; all twelve terminal process samples preserve identity and CPU. See linux-compatibility-3644c324. This is VM compatibility, not physical-server capacity or runtime-ownership proof. Benchmark-only explicit IPv4 binds now pass36 focused tests and four actual loopback-address diagnostics; see external-native-bind-cbdca987. A syntax-checked finite two-host runbook is AUTHORED/UNEXECUTED. Bounded Linux private-resident sampling is committed at10a51bee with49 focused tests and restricted-container identity/zombie compatibility evidence (linux-resource-sampling-bf53b8d4). B3 backend/orchestration compatibility now has12 accepted restricted-container runs (streams16/32,16bundles,3same-process cycles;3repeats each),33 independently verified11-field raw cleanup reports, and all process joins. It uses controller1cca67ad with unchanged3644c324 Rust binaries and remains DIAGNOSTIC_BINARY_SOURCE_MISMATCH; CLI live NOT_RUN. The first empty evidence-transfer attempt is INVALID and retained (linux-b3-compatibility-1cca67ad). Linux B4 integration is committed at 0aecf156. Compatibility evidence preserves six valid rows then an FD permission failure; a separately declared five-attempt diagnostic did not reproduce that denial (linux-b4-compatibility-c62b1165, linux-b4-fd-attribution-9397429f). Cause remains UNRESOLVED; older Rust image evidence is diagnostic only. Linux B5 finite reference and strict loader are implemented at 96f6b902 with 74 focused tests, but the sustained Linux runtime backend remains NOT_IMPLEMENTED. Full admission/memory/soak/wire execution is not yet defined by a validated portable runner. |
| Administrator validation | IN PROGRESS ledger | See `ADMIN_REQUIRED_FINAL_VALIDATION.md`. No new mandatory elevated command established; previously supplied traces have been analyzed. |

## Latest 96f6b902 / d12e38c9 stages

Fifty finite calibration repeats and 597 indexed artifacts are preserved in
`windows-b5-sampler-stop-96f6b902`. One-core 1KiB/64-stream NBSR depth1 is
0.873115 Gbit/s STABLE; depths2/4 are DEGRADED/SATURATED. The four-core,
four-group 64-stream shape has no strict-stable baseline (dispersion); depth8
is saturated. These are exact-stage finite results, not production maxima.

The 120-second ownership observer cohort stopped after three complete pairs
and one invalid sampler-stop cell; it is not qualified. Failure-only context
retention was added at d12e38c9 (71 focused tests). A separate diagnostic then
completed one accounting run below 95% achieved/offered operations and aborted on goodput
drift in the next. See `b5-sampler-attribution-d12e38c9`; no replacement.
The sampler lookup cause and longer-run paced stability remain UNRESOLVED.
The candidate benchmark destination exit/ACK mismatch was independently
reproduced and corrected with an optional post-cleanup hold used only by B5;
see `b5-destination-hold-a1ec0649`. Live process sampling now passes on both
paths. This does not prove the exact earlier sampler failure cause or resolve
goodput drift. Fresh benchmark qualification remains required.
No near-ceiling 60/120-minute soak has qualified.

At 70dea630, a fresh 18-repeat reference with ownership reports measured
one-core NBSR 0.873913 Gbit/s STABLE (depth2 DEGRADED, depth4 SATURATED).
Three after-hold fixed-load diagnostics passed, but the separate matched
observer comparison aborted on private-memory growth while eleven live
ownership gauges remained constant. Measured large benchmark latency-vector
allocations are now removed through two prepared reusable buffers; see
`b5-window-reuse-70dea630`. Live memory/observer/soak effects remain pending;
no leak fix or production speedup is claimed.

## Protected boundaries

No frozen protocol, wire format, authentication, authorization, crypto, replay, admission-security, ACK/send-completion, authority or fail-closed semantics have been relaxed. A measured improvement that requires such a change is `BLOCKED_ARCHITECTURAL`; other independent work continues.

Accepted historical P1D rotation analysis describes a missing production authority-refresh/session-pool contract. It is not authorization to invent one for this campaign. Any future soak/session-rotation implementation must stay within approved current semantics and report fixture session replacement distinctly from production transparent rotation.

## Infrastructure

Last inspected disk free space was approximately 11.69 GiB. No build-cache cleanup has been performed in this continuation. Exact owned Docker test resources were removed after evidence retention; unrelated Docker resources were untouched. Authoritative raw runs, ETL/PCAP and binary/source provenance remain retained. The two Linux compatibility images and shared build-cache records remain retained; no cache prune has been performed.

Git commits succeed, but automatic maintenance reports permission denial for stale worktree metadata at `.git/worktrees/nbsr-name-routing`. Its ownership/state has not been established; it has not been deleted or repaired destructively. This does not authorize changing branches or history.

Final recommendation remains **MORE ENGINEERING REQUIRED** until the outstanding gates are executed or explicitly classified under the authorized stop conditions.

## Latest 2d7525f3 qualification

See `evidence/performance/v2/b5-qualification-2d7525f3/REPORT.md`. The 32-stream
1 KiB one-core finite reference is STABLE at 0.812138 Gbit/s NBSR; depths 2/4
are saturated. The separate 64-stream reference is saturated and retained.
Three ownership observer pairs pass the 5% gate. Direct ten-minute pacing
fails the 95% achieved/offered gate (20.17%, 0.114662 Gbit/s). Separate NBSR
completes one ten-minute run at 0.555331 Gbit/s, 97.68%, with final eleven
counts zero, then repeat 2 aborts on source private growth at 30 seconds.
No replacements; no stable long-soak claim. Causes remain UNRESOLVED.
All 470 indexed artifacts across six roots were verified for this stage.

Task8 now has the requested machine-readable server matrix and companion
`funding-grade-v2-server-linux-validation.md`, with two RED/GREEN contract
tests and four verified CLI-help entrypoints. This closes the missing workload
definition files, not portable execution: Linux sustained/wire/full-matrix
backends remain explicitly PARTIAL_REQUIRED_PORTING. No server results.

Linux B5 now has an optional nonreaping exit-observation primitive/controller
injection (54 focused tests, three actual Linux terminal-state cases). See
`linux-b5-exit-85e706fc`; full sustained backend remains NOT_IMPLEMENTED.

Linux terminal-source sampler opt-in now preserves one validated zombie CPU/
identity snapshot while the destination continues (84 focused tests, actual
restricted Linux fixture). See `linux-b5-terminal-648c8acd`. Full B5 runtime
composition/clock wiring and observer qualification are still outstanding.

B5 live guards now have explicit Linux clock/private-resident metric selection
(60 focused tests); terminal null memory cannot establish live stability.
Full Linux sustained orchestration and observer qualification remain pending.

A new deferred ADMIN_REQUIRED item is now established specifically for Direct
paced CPU attribution: WPR CPU start fails0xc5585011 in the current process.
The final admin ledger contains one matched five-pair capture command; its
syntax and non-admin refusal pass, elevated execution remains NOT_RUN.

Explicit Linux B5 adapter now connects those primitives to shared run_one:
55 focused tests and an actual two-child Linux lifecycle fixture PASS.
`linux-b5-backend-c6bb0e9f` is lifecycle-only; current Rust execution, sustained
CLI/provenance wiring and observer-qualified benchmark remain pending.

The Linux sustained CLI is now AUTHORED/PARTIAL (`linux_b5_campaign`), with
strict current reference/build binding,3-to5 paired repeats, p99/goodput CV
and failed-prefix preservation.59 focused tests and Ruff PASS. Actual current
Rust/QUIC execution and observer qualification remain NOT_RUN; no stable soak.

## Current-source Linux execution at edc0f96d

Native release build and binary hashes PASS. Actual Linux B5 CLI compatibility
stops on Direct p99 drift. Finite reference first exposed missing build-root
vectors; mounting the unchanged captured tree restores NBSR execution. The
corrected cohort retains5 valid rows then an NBSR /proc/230/fd PermissionError.
All6 post-close reports have11 zero counters, but missing telemetry still
invalidates the cohort. No accepted Linux reference or soak. See
`linux-current-edc0f96d` (365 indexed raw files) and NEXT_SESSION_HANDOFF.md.
