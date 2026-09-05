# Maximum-quality campaign: current state

Working status, 2026-09-05. **NOT a final evidence freeze.** Technical outreach must retain the historical/diagnostic qualifications below. Repository branch: `codex/nbsr-v3-wp0-wp1`; protected `main` and `origin/main`: `1938154d498b32d81a3564319969430644e8a688`. No push or main integration is authorized.

| Area | State | Evidence and next gate |
| --- | --- | --- |
| Historical forwarding | DONE / HISTORICAL | Accepted strict-stable 2.185 Gbit/s, latency-degraded 2.942 Gbit/s, saturated observed peak 3.040 Gbit/s; Windows loopback only. Current production-buffer SHA requires fresh matched measurements before calling these current. |
| Historical admission | DONE / HISTORICAL | 125 offered/s: 119.813 actual/s strict-stable in its accepted stage; 150 degraded, 200 saturated. Two-shard scheduling improved the saturated 200/s cell but did not move boundaries. |
| Windows UDP receive buffer | DONE / MEASURED, scoped | Production and Direct listener buffer raised to bounded 1 MiB on Windows, based on captured insufficient-local-buffer drops. Paired five-repeat 250/s p99 improved, but admission dispersion remains high and p50 worsened. Post-fix captured workload recorded no AFD datagram drops. This is not a general capacity proof. |
| Residual handshake progress | UNRESOLVED / PLATFORM_DIAGNOSTIC_LIMIT | ETW, AFD and accept-pump observers failed matched distortion gates. Task 4n preserves 20 valid clean runs and 201 verified artifacts; no further implementation optimization follows from these profiles. |
| Invalid comparisons | INVALID for causal attribution | SHA-mismatched capture remains diagnostic only; all failed observer comparisons and unfavorable valid repeats remain preserved. |
| Physical-core forwarding | PARTIAL / MEASURED | One-core fixed-shape package remains accepted separately. Current exact-SHA 2/4-core ladders preserve 90 valid records and 786 verified raw artifacts. Four-core NBSR strict-stable: 2.306118 Gbit/s, five repeats, CV 0.908%; observed 3.666140 peak is DIAGNOSTIC only. Two-core baseline remains UNRESOLVED by dispersion. See physical-core-multicore-53468db4. Endpoint-group controls and other useful shapes remain pending. |
| Sustainable admission after buffer change | NEEDS_RERUN | Progressive rates, complete distributions, five repeats where CV exceeds 5%, ownership and background-resource evidence. Burst remains separate. |
| B3 memory/lifecycle | PARTIAL | Single-process async holds, B3 serial armed accept, response ACK completion and final-report gating are implemented. Five 50-cycle repeats have CLEAN measured ownership and unchanged cooldown handle counts; private-memory cause remains INCONCLUSIVE. See `evidence/performance/v2/b3-cycles50-gated-453d026d/REPORT.md`. Registry/source-handle residency is distinct from two-sided materialized QUIC stream cost, whose opt-in mode passed a live 2-channel/4-stream residency regression. Higher-cardinality and independent-axis closure remain pending. |
| B5 near-ceiling soak | NEEDS_RERUN | Live errors, throughput/p99 drift and sampled private-memory growth guards preserve partial evidence. Resource timestamps now use actual acquisition time. Optional OS power telemetry is default-off pending observer comparison; it does not measure temperature/effective clocks. Current matching load calibration and 60/120-minute soaks remain pending. |
| B1 packet delta | DONE / SCOPED ACCOUNTING | Twenty captures, five matched pairs for each of two workloads, pass readiness/loss/inventory gates. Setup relay UDP-payload delta is consistently positive; established and whole-PCAP deltas cross zero. No stable-sign data overhead or phase-aligned IP/L2 claim. See `evidence/performance/v2/b1-packets-e2c75b59/REPORT.md`; all 200 raw checksums and canonical package blobs verified. |
| Security regression | PARTIAL / CURRENT SCOPED GATES PASS | Adversarial campaign b7df259b: 13 executable fail-closed scenarios PASS, 45 raw hashes verified; its direct-origin case remains historical INCONCLUSIVE in that immutable report. Separate current ISP isolation package f831c9bb closes the scoped client/ISP-A reachability case with three genuine Docker network lifecycles. Final quality/dependency/privacy closure remains pending. |
| ISP private-origin isolation | DONE / SCOPED MEASURED | Three lifecycles at f831c9bb denied four direct-origin probes, then returned the exact authorized body with exactly one accepted origin request. Destination process completed and all campaign containers/networks/volumes returned to zero. See evidence/security/isp-isolation-f831c9bb. Shared fixture bootstrap material, unmeasured runtime ownership counters and no live federation remain explicit limitations. |
| Federation | NOT_PROVEN for live runtime | Admission preflight and secure-route isolation must be reported separately from live runtime federation. No legacy demo evidence substitution. |
| External validation | EXTERNAL_HARDWARE_REQUIRED / PARTIAL definition | No suitable external host has been established. The Linux loopback runner and seven synthetic tests are committed; no Linux live result exists; full two-host/admission/memory/soak/wire execution is not yet defined by a validated portable runner. |
| Administrator validation | IN PROGRESS ledger | See `ADMIN_REQUIRED_FINAL_VALIDATION.md`. No new mandatory elevated command established; previously supplied traces have been analyzed. |

## Protected boundaries

No frozen protocol, wire format, authentication, authorization, crypto, replay, admission-security, ACK/send-completion, authority or fail-closed semantics have been relaxed. A measured improvement that requires such a change is `BLOCKED_ARCHITECTURAL`; other independent work continues.

Accepted historical P1D rotation analysis describes a missing production authority-refresh/session-pool contract. It is not authorization to invent one for this campaign. Any future soak/session-rotation implementation must stay within approved current semantics and report fixture session replacement distinctly from production transparent rotation.

## Infrastructure

Last inspected disk free space was approximately 34.8 GiB after Docker startup and pinned-image bootstrap. No cleanup has been performed in this continuation. Authoritative ETL/PCAP, raw runs and binary/source provenance remain retained.

Git commits succeed, but automatic maintenance reports permission denial for stale worktree metadata at `.git/worktrees/nbsr-name-routing`. Its ownership/state has not been established; it has not been deleted or repaired destructively. This does not authorize changing branches or history.

Final recommendation remains **MORE ENGINEERING REQUIRED** until the outstanding gates are executed or explicitly classified under the authorized stop conditions.
