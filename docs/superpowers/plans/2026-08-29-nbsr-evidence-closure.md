# NBSR Evidence Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining NBSR benchmark, stability, security, federation, and outreach evidence gaps without changing frozen protocol or security semantics.

**Architecture:** Reuse the accepted benchmark and secure-route implementations, add only narrowly scoped measurement or orchestration support, preserve raw machine-readable evidence, and derive every report automatically. Each closure task remains an atomic, independently verified commit.

**Tech Stack:** Rust 2024, Tokio, Quinn, Go, Python 3, JSON/NDJSON, Markdown, Windows loopback validation, Docker/Kubernetes where already supported.

**Spec:** User-approved evidence-closure directive dated 2026-08-29, captured by the objectives and constraints below.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; never modify or merge `main`.
- Start evidence work from prerequisite commit `94a1e4a2da528534ce9e2c62bc9d7a6335bd81ab`.
- Do not change frozen wire semantics, authentication, authorization, replay, revocation, trust, cryptographic formats, ACK meaning, or fail-closed behavior.
- Do not weaken security or performance assertions to obtain passing results.
- Use release builds for authoritative measurements.
- Preserve historical evidence; classify code-baseline-dependent measurements rather than rewriting them.
- Store raw evidence and generate summaries automatically.
- Execute only the currently approved task; B4 is approved, and B5 must not begin without approval.

## Post-repair audit snapshot

| Closure item | Status | Current evidence | Gap / rerun rule |
|---|---|---|---|
| B1 exact wire overhead | MISSING | P2A has equivalent established Direct/NBSR traffic and application counters; earlier 6.45–8.59% figures are framing models | No measured isolated bytes/packets or setup/data-plane separation at current SHA |
| B2 CPU efficiency | PARTIAL | P2A contains process CPU and established goodput | Existing raw data predates `94a1e4a`; derived CPU normalization remains useful historically but authoritative current-binary values require rerun |
| B3 memory/session closure | INCONCLUSIVE | Direct and Rust-to-Rust stable windows exist; Go-to-Rust runs retained partial evidence | Go path lacks authoritative closure; all current-binary lifecycle conclusions require a scoped rerun |
| B4 mixed workload | Evidence PASS / scope PARTIAL | Current-SHA same-runtime evidence combines established forwarding with application-stream admissions on one established authorized route | B4b separately tracks new connections, new routes, multiple clients, and saturation beyond 800 admissions/s; it does not block B5 |
| B5 sustained capacity | PASS | Current-baseline 60-minute 1 KiB/64-stream and 30-minute 16 KiB/8-stream established-path soaks both classify PASS / STABLE | This closes bounded Windows loopback sustained behavior; server-class, WAN, and multi-client capacity remain external validation |
| Security campaign | PARTIAL | Extensive protocol, replay, admission, revocation, federation, and fail-closed tests exist | No single reproducible attack/result matrix at current SHA |
| ISP-style federation PoC | PARTIAL | Secure-route demo and federation interoperability are accepted | Existing localhost/process isolation does not prove independent ISP/network-domain isolation |
| Final evidence freeze | BLOCKED | Historical reports and status documents exist | Depends on classification of B1–B5, security, and ISP federation work |

Historical performance evidence remains valid for its recorded commit, host, and methodology. It must not be silently relabeled as current-binary evidence. P2A workload selection and stability findings may guide new cells; headline numerical measurements that depend on executable bytes must be rerun at `94a1e4a` or a descendant B1 commit.

---

### Task 1: B1 Direct-vs-NBSR wire overhead

**Objective:** Measure incremental NBSR transport/network byte and packet cost for equivalent Direct and NBSR workloads.

**Current evidence:** P2A provides matched persistent QUIC/NBSR echo semantics, stable 1 KiB/64-stream and 16 KiB/8-stream cells, release build orchestration, payload validation, and lifecycle-isolation counters.

**Identified gap:** No isolated actual byte/packet measurement exists. `pktmon` is installed but inaccessible without elevation; machine-wide interface counters are unsuitable. Physical Ethernet/L2 bytes and retransmission attribution are unavailable on this host.

**Files expected to change:**
- Create: `scripts/performance/wire_overhead.py`
- Create: `scripts/run_b1_wire_overhead.py`
- Create: `tests/performance/test_wire_overhead.py`
- Create: `crates/nbsr-transport/src/bin/b1_support/mod.rs`
- Modify: `crates/nbsr-transport/src/bin/perf_direct_peer.rs`
- Modify: `crates/nbsr-transport/src/bin/perf_rust_source.rs`
- Modify: `scripts/run_performance_validation.py` (optional client-start callback used to bind relay ownership to the exact process)
- Create: `evidence/performance/wire-overhead-b1-94a1e4a/**`
- Modify: this plan's Task 1 final status

**Interfaces:**
- `UdpFlowCounter(server: tuple[str, int])` forwards one isolated UDP client/server flow and counts UDP payload bytes/datagrams by direction and phase.
- A loopback TCP control endpoint accepts exact phase messages: `setup-complete`, `measurement-start`, and `measurement-stop`.
- `analyze_pairs(records: list[dict]) -> dict` rejects mismatched/invalid pairs and derives medians, ranges, byte ratios, packet ratios, and incremental overhead.

- [x] **Step 1: Write RED tests for counter isolation and phase accounting**
  - Verify deterministic UDP payloads are forwarded unchanged.
  - Verify unknown sources are rejected and cannot contaminate counters.
  - Verify setup and established counters reset/snapshot only after acknowledged control markers.
  - Verify TX/RX bytes and packet counts match known datagram sizes exactly.
- [x] **Step 2: Run `python -m pytest tests/performance/test_wire_overhead.py -q` and observe expected missing-module/interface failures.**
- [x] **Step 3: Implement the minimal single-flow relay/control counter in `wire_overhead.py`.**
- [x] **Step 4: Re-run the focused tests to GREEN.**
- [x] **Step 5: Write RED analysis tests**
  - Reject unequal payload, concurrency, operations, build mode, or phase semantics.
  - Reject errors/timeouts and fewer than three valid repeats.
  - Derive aggregate request+response application bytes, measured UDP payload byte ratios, packet ratios, deltas, medians, and ranges.
  - Mark results INCONCLUSIVE when pair dispersion overlaps the observed Direct/NBSR delta.
- [x] **Step 6: Run the tests and observe the expected missing-analysis failures.**
- [x] **Step 7: Implement the minimal analyzer and Markdown renderer.**
- [x] **Step 8: Re-run focused tests to GREEN.**
- [x] **Step 9: Add benchmark-only phase-control calls to both P2A clients.**
  - Signal setup completion after all persistent streams are established and before warm-up.
  - Signal measurement start immediately before releasing the measurement barrier.
  - Signal measurement stop only after every worker finishes its final response.
  - Do not alter payload framing, stream lifecycle, admission, or timing when the option is absent.
- [x] **Step 10: Run focused Rust process/self-tests and a deterministic one-stream smoke validation.**
- [x] **Step 11: Implement `run_b1_wire_overhead.py` using the existing release P2A binaries, fresh authority, isolated relay, exact metadata, immutable raw JSON, automatic analysis, commands, environment, and checksums.**
- [x] **Step 12: Validate counter correctness with a short 1 KiB/1-stream Direct/NBSR run and prove no unrelated traffic enters the relay.**
- [x] **Step 13: Execute five repeats for 1 KiB/64 streams and 16 KiB/8 streams with identical warm-up, fixed operation count, host, release mode, and protocol configuration.**
- [x] **Step 14: Analyze results, preserve invalid repeats, generate `analysis.json` and `summary.md`, and classify B1 honestly.**
- [x] **Step 15: Run affected Python/Rust tests, formatter, Clippy, safety checks, checksum verification, and `git diff --check`.**
- [x] **Step 16: Review the complete diff and commit one atomic B1 closure commit.**

**Evidence to capture:** Exact command lines; Git/branch/toolchain/OS/CPU/RAM metadata; per-repeat setup and established UDP payload bytes/datagrams by direction; completed operations; aggregate request+response application bytes; errors/timeouts; invalid-repeat reasons; medians/ranges; incremental bytes and percentages; capture limitations; checksums.

**Acceptance criteria:** At least three stable valid equivalent pairs permit a defensible measured UDP-payload statement for both representative workloads. If the difference is within observed pair noise, or only a subset is valid, classify INCONCLUSIVE or PARTIAL. Never describe derived IPv4/UDP or physical L2 estimates as measured.

**Rollback/revert approach:** Revert the single B1 commit. Benchmark-only phase controls are disabled unless explicitly requested, and no production/frozen module is changed.

**Dependencies:** Prerequisite commit `94a1e4a`; existing P2A release binaries and authority generator; loopback UDP/TCP sockets.

**Final status:** INCONCLUSIVE — five valid pairs per cell measured exact isolated UDP payload bytes/datagrams, but established Direct/NBSR deltas changed sign and remained smaller than pair dispersion. Setup/admission cost was measurable; physical L2 bytes and retransmissions remain unavailable on this host.

---

### Task 2: B4 mixed workload

**Objective:** Measure established NBSR forwarding while concurrent route/session admissions are created.

**Current evidence:** Separate P2A established forwarding and lifecycle/admission harnesses.

**Identified gap:** No combined configurable workload or saturation evidence.

**Files expected to change:** `scripts/performance/mixed_workload.py`, `scripts/run_b4_mixed_workload.py`, `tests/performance/test_mixed_workload.py`, benchmark-only P2A branches in `perf_rust_source.rs` and `wp8_interop_server.rs`, `crates/nbsr-transport/src/bin/b4_support/mod.rs`, and `evidence/performance/mixed-workload-b4-e8d61c7/**`.

**Implementation steps:** RED analysis/configuration tests; schedule new application-stream admissions on the same authenticated route/runtime while established streams forward; short release validation; 0/25/50/100/400/800 admissions-per-second sweep; preserve fail-closed saturation; automatic analysis/report; atomic commit.

**Tests:** Focused workload tests, affected Rust/Go tests, failure/backpressure cases, formatter/lint/safety checks.

**Evidence to capture:** Goodput, offered/achieved admissions/s, successes/failures, established and admission latency percentiles, CPU/RSS/private bytes/threads, errors/timeouts, scheduling-lateness backpressure, saturation point, and installed packet-capture capability.

**Acceptance criteria:** Demonstrate whether established traffic remains stable during admissions and preserve the first failure/saturation point.

**Rollback/revert approach:** Revert the isolated B4 commit; no protocol changes.

**Dependencies:** Completed B1 and renewed user approval.

**Final status:** Evidence PASS / scope PARTIAL — the measured same-runtime campaign passes its declared stability limits in all three repeats from 0 through 800 offered application-stream admissions/s. At 800/s, 8,000/8,000 admissions completed; median established goodput was 0.360 Gbit/s (0.965089 of baseline) and median p99 was 1.016646 of baseline, with zero failures or timeouts. No saturation point was observed in the bounded sweep. Two discarded pre-authoritative runs exposed missing benchmark audit consumers; both were fixed by mirroring the established audit-drain lifecycle, and the invalid evidence was preserved outside the repository. This evidence covers new application-stream admissions on one established authorized route.

**B4b future follow-up (non-blocking for B5):** Close mixed load with multiple concurrent clients plus new transport connections and new route admissions, and probe saturation beyond the bounded 800 admissions/s B4 harness ceiling. Status: MISSING / NOT YET VALIDATED.

### Task 3: B5 sustained capacity / soak

**Objective:** Establish 10/30/60-minute stability and cleanup behavior.

**Current evidence:** Historical P2D evidence remains useful for admission/credit/replay continuity (300.387 seconds, 4,832,000 operations, zero errors), P1F remains useful for the exact replay hard-cap result (601.073 seconds and exactly 10,000 committed IDs), and P2A identifies the persistent established-stream workload and stable cells. Those executable-dependent measurements predate the current repaired branch and cannot close B5.

**Identified gap:** No current-SHA authoritative 30/60-minute persistent established-stream run with periodic application/resource/ownership telemetry and post-load cooldown/cleanup classification.

**Files expected to change:** Benchmark-only bounded progress support in `perf_rust_source.rs` and `b5_support/mod.rs`; destination diagnostic cooldown in `wp8_interop_server.rs`; Windows handle sampling in `scripts/performance/resources.py`; `scripts/performance/sustained_capacity.py`; `scripts/run_b5_sustained_capacity.py`; focused tests; and `evidence/performance/sustained-capacity-b5-58b3697/**`.

**Implementation steps:** Audit/reuse P2A and resource/diagnostic infrastructure; RED validation for strict cadence/accounting/cleanup and bounded latency sampling; 60-second shape gates; 10-minute validation; preserve and diagnose the detected unbounded benchmark-sample retention; add a bounded-tail regression; rerun 10-minute validation; run one 60-minute primary 1 KiB/64-stream soak plus one 30-minute secondary 16 KiB/8-stream soak; classify evidence and system behavior independently; atomic commit.

**Tests:** Durable-runner tests, descendant cleanup, affected integration tests, format/lint/safety checks.

**Evidence to capture:** Goodput/latency/CPU/RSS/private bytes/sessions/tasks/errors over time and post-run cooldown.

**Acceptance criteria:** Stable plateau or honest FAIL/INCONCLUSIVE; no uninvestigated growth.

**Rollback/revert approach:** Revert isolated harness changes; preserve raw bad results.

**Dependencies:** B4 stable workload selection.

**Final status:** PASS — the authoritative release-build campaign at base SHA `58b369752dd86811f10c1f52551879a1a861403f` produced 720/720 valid five-second windows over 60 minutes at 1 KiB/64 streams and 360/360 over 30 minutes at 16 KiB/8 streams. The primary completed 156,167,149 operations at 0.734 median Gbit/s with -3.168% early-to-late goodput drift; the secondary completed 5,678,257 operations at 0.853 median Gbit/s with +1.599% drift. Both had zero errors/timeouts, cleanup PASS, and no classified continuous RSS/private-byte growth. Evidence status and system result are independently recorded as PASS / STABLE. One attempted authoritative rerun was preserved outside the repository and rejected as INVALID after Windows Event Log proved a button/lid sleep interrupted the load and caused a post-resume QUIC `CloseTimeout`; the clean replacement run used a process-lifetime Windows execution-state request. The measured scope is release-build Rust-to-Rust persistent established forwarding on this Windows loopback host; it does not establish WAN, multi-client, or server-class capacity.

### Task 4: B3 memory/session closure

**Objective:** Resolve Direct, Go-to-Rust, and Rust-to-Rust memory/session classifications.

**Current evidence:** Direct/Rust bounded windows and incomplete Go evidence.

**Identified gap:** Go lifecycle closure is inconclusive and all executable-dependent conclusions predate the repaired baseline.

**Files expected to change:** Existing memory closure scripts/tests where necessary and additive evidence only.

**Implementation steps:** Reuse accepted methodology; short validation; authoritative runs; distinguish allocator retention from leaks; regression-first fix only if a real leak is proven; atomic commit.

**Tests:** Memory analyzer, durable runner, lifecycle cleanup, relevant transport tests.

**Evidence to capture:** Baseline/active/cooldown memory, slopes/confidence, handles/tasks/threads/connections, cleanup residuals.

**Acceptance criteria:** PASS/FAIL/INCONCLUSIVE per path with reproducible raw evidence.

**Rollback/revert approach:** Revert isolated code fix if any; never delete evidence.

**Dependencies:** B5 runner and stable-load cells.

**Final status:** INCONCLUSIVE

### Task 5: B2 CPU efficiency

**Objective:** Produce reproducible measured and derived CPU-normalized efficiency.

**Current evidence:** P2A process CPU and goodput at multiple payload/concurrency cells.

**Identified gap:** Current-binary rerun and explicit derivation ledger are missing; no physical affinity/server hardware proof.

**Files expected to change:** Analyzer/tests and additive CPU evidence/report.

**Implementation steps:** Preserve historical data; RED derivation tests; current release rerun if feasible; calculate Gbit/s/core, ops/CPU-second, ns/op, and Direct/NBSR delta; atomic commit.

**Tests:** Analyzer math/metadata validation and affected benchmark self-tests.

**Evidence to capture:** Raw CPU time, logical core limits actually enforced, completed operations, goodput, formulas, hardware/toolchains.

**Acceptance criteria:** Every derived number recomputes exactly; affinity and server-class validation are not overstated.

**Rollback/revert approach:** Revert isolated analyzer/report commit; retain prior evidence.

**Dependencies:** Stable B1/B4/B5 cells.

**Final status:** PARTIAL

### Task 6: Security/adversarial campaign

**Objective:** Map current fail-closed tests into one reproducible adversarial campaign.

**Current evidence:** Existing tamper, replay, binding, expiry, revocation, generation, federation, and failover tests.

**Identified gap:** No current-SHA machine-readable attack/expected/observed/result matrix.

**Files expected to change:** Campaign runner/tests and additive security evidence/report.

**Implementation steps:** Requirement mapping; reuse tests; RED manifest validation; add only missing scenarios; run; report; atomic commit.

**Tests:** Every supported negative scenario plus campaign schema/reproduction checks.

**Evidence to capture:** Exact commands, attack, expected/observed behavior, logs, PASS/FAIL/INCONCLUSIVE.

**Acceptance criteria:** All security-negative supported cases fail closed; gaps remain explicit.

**Rollback/revert approach:** Revert campaign-only commit; never weaken protocol tests.

**Dependencies:** Stable current baseline.

**Final status:** PARTIAL

### Task 7: ISP-style federation PoC

**Objective:** Validate secure routing across reproducibly isolated administrative/network domains.

**Current evidence:** Accepted secure-route demo and federation interoperability.

**Identified gap:** Flat localhost processes do not prove ISP isolation.

**Files expected to change:** Existing-compatible container/Kubernetes topology, tests, instructions, and additive evidence.

**Implementation steps:** Choose available isolation; RED reachability/authorization tests; deploy; validate success/failure/failover claims; document; atomic commit.

**Tests:** Direct-origin denial, named-route success, unauthorized route denial, trust boundary, failure/failover where claimed, topology validation.

**Evidence to capture:** Topology, commands, manifests, logs, network proof, failure demonstrations.

**Acceptance criteria:** Third party can reproduce independent-domain behavior without publishing the private origin.

**Rollback/revert approach:** Tear down only task-owned isolated resources and revert the PoC commit.

**Dependencies:** Security campaign and available container/Kubernetes runtime.

**Final status:** PARTIAL

### Task 8: Final evidence freeze / outreach package

**Objective:** Freeze the factual demonstrated state without unsupported claims.

**Current evidence:** Distributed benchmark, protocol, demo, and security reports.

**Identified gap:** No current consolidated snapshot after Tasks 1–7.

**Files expected to change:** Evidence index, methodology/environment/results/limitations reports, reproduction guide, and concise technical summary.

**Implementation steps:** Classify Tasks 1–7; reconcile raw/derived results; claim scan; full feasible regression; checksum/report validation; atomic commit.

**Tests:** Documentation links/schema/checksums, complete feasible regression, unsupported-claim and TODO/TBD/FIXME scans.

**Evidence to capture:** Final SHA, environments, commands, classifications, limitations, remaining external validation.

**Acceptance criteria:** Every claim is labeled MEASURED/VERIFIED/OBSERVED/INCONCLUSIVE/NOT YET VALIDATED and traces to raw evidence.

**Rollback/revert approach:** Revert the evidence-freeze commit; prior task evidence remains intact.

**Dependencies:** Tasks 1–7 classified.

**Final status:** BLOCKED
