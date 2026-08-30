# Funding-Grade Benchmark V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve and rerun every material NBSR benchmark until evidence identifies either a measured host/hardware ceiling or a specific software/harness bottleneck that must be fixed first.

**Architecture:** V2 is one sequential measurement program: reproduce the current baseline, profile the unexplained plateau, optimize only proven bottlenecks, re-establish the stable ceiling, then scale mixed connections, lifecycle memory, soak, and packet capture against that ceiling. Every stage writes immutable raw evidence and a mechanically derived classification; later stages consume only accepted earlier-stage ceilings.

**Tech Stack:** Rust release benchmarks and diagnostics, Go peers, Python orchestration/analysis, Windows process and host telemetry, ETW/WPR or another verified stack profiler, Wireshark/TShark/Dumpcap with Npcap, JSON/CSV/NDJSON/Markdown evidence, and external Linux/server validation definitions.

**Spec:** User-approved funding-grade benchmark V2 scope dated 2026-08-30; existing benchmark authority and frozen protocol/security documents remain unchanged.

## Global Constraints

- Pause the ISP/Federation PoC implementation. Do not modify its accepted design or plan.
- Never modify `main`; never weaken frozen authority, wire, crypto, trust, replay, admission, ACK, authorization, or fail-closed behavior.
- Use release binaries for authoritative measurements. A symbol-enabled profiling build is diagnostic only and must be mapped back to an identical optimized release source SHA.
- Never change benchmark semantics, payload accounting, assertions, timeouts, sampling windows, or success criteria to improve a number.
- Preserve Direct/NBSR workload equivalence and record every difference in instrumentation source.
- Preserve bad-but-valid runs. Raw evidence is write-once; derived reports are reproducible.
- Run one stage at a time. Do not continue when the current stage has unexplained failures, invalid telemetry, or an unresolved correctness/security concern.
- **Hardware-limited** requires measured saturation: allocated CPU capacity at least 90%, a verified NIC/data-path limit at least 85%, sustained memory pressure with paging/commit evidence, or another named host resource at its measured bound. Loopback throughput alone cannot establish a NIC limit.
- A plateau with available host resources is **SOFTWARE/HARNESS-LIMITED** and requires profiling before any further scaling claim.
- Optimization requires a profiled root cause, a literal RED performance/regression test where practical, no security regression, and a matched before/after gate.
- Every authoritative cell has at least three valid repeats; use five when coefficient of variation exceeds 5%. Never average invalid repeats.
- Every result records Git SHA/branch, timestamp, command, OS, CPU, physical/logical cores, RAM, power plan, thermal/frequency telemetry where available, toolchains, binary hashes, build profile, affinity verification, payload, streams, concurrency, duration, and success state.

## Common classifications

**Evidence PASS:** required cells, repeats, telemetry, integrity, cleanup, and derivations are complete and reproducible.

**Evidence PARTIAL:** valid measurements exist but one required scale, profiler, capture, or platform dimension is missing.

**Evidence FAIL:** a benchmark assertion, security invariant, cleanup gate, evidence-integrity rule, or required workload equivalence fails.

**System classifications:** `SCALING`, `CPU-LIMITED`, `NIC-LIMITED`, `MEMORY-LIMITED`, `HOST-LIMITED:{resource}`, `SOFTWARE-LIMITED:{hotspot}`, `HARNESS-LIMITED:{hotspot}`, `STABLE`, `DEGRADED`, `SATURATED`, or `UNRESOLVED`.

## Common saturation rules

A load point is stable only when errors/timeouts are zero, cleanup passes, p99 is no more than 1.25x the lowest-load p99, achieved/offered work is at least 95%, backlog is bounded and drains, and repeat CV is at most 5%.

Degradation begins when any two valid repeats show one of: goodput below 90% of the best stable point, p99 above 1.25x, achieved/offered below 95%, persistent queue growth, or cleanup delay growth.

Saturation requires one of: errors/timeouts; achieved/offered below 90%; goodput below 75% of the best stable point; p99 above 2x; non-draining backlog; or two consecutive load increases with less than 5% throughput gain plus a measured resource/queue/lock bottleneck.

The stable ceiling is the highest load point meeting every stable rule in at least three repeats. B5-v2 load is derived only from this ceiling.

## Common evidence layout

Each stage writes `evidence/performance/v2/{stage}-{start_sha_12}/`, where both tokens are generated from the fixed stage name and pre-run `git rev-parse HEAD`, containing `environment.json`, `manifest.json`, `analysis.json`, `summary.md`, `raw/`, and `checksums.sha256`. Raw profiler/capture formats remain alongside exported machine-readable tables. `manifest.json` binds source files, binaries, commands, run order, telemetry sources, and exclusions.

---

### Task 1: B2-v2 plateau profiling

**Current result:** B2 is Evidence PASS / System SOFTWARE-LIMITED. At 4-core affinity, 1 KiB/64 NBSR reached 0.549 Gbit/s using 1.478 effective cores; 16 KiB/8 reached 0.686 Gbit/s using 1.437 effective cores. Throughput increased from 1 to 4 cores but plateaued without allocated-core saturation.

**Current limitation:** The exact bottleneck is unattributed. Existing CPU totals cannot distinguish benchmark one-outstanding behavior, a serialized control/data path, lock contention, scheduler wakeups, syscall/QUIC pacing, copy/allocation cost, or observer overhead.

**Files:**
- Create: `scripts/profile_b2_v2.py`
- Create: `tests/performance/test_b2_v2_profile.py`
- Create: `docs/benchmarks/funding-grade-v2-methodology.md`
- Reuse: `scripts/run_p2a_established.py`, `scripts/run_p2b_profile.py`, Rust diagnostics, and B2 raw evidence.

**Profiling needed:** matched Direct/NBSR wall-clock and CPU stack samples; per-process CPU time; effective cores; cycles/instructions when available; context switches; ready/wait time; thread utilization; syscalls; allocations; lock/wait spans; QUIC send/receive/pacing counters; operations outstanding; queue depth; scheduler lateness; working/private set; frequency/thermal/power state.

**Optimization gate:** no code change until one reproducible hotspot accounts for at least 15% of CPU/wall blocked time or a serialized stage explains the plateau through measured utilization/queue data. Diagnostic overhead must be quantified against an unprofiled control.

**Load progression:** both 1 KiB/64 and 16 KiB/8; verified affinity 1, 2, 4 logical CPUs; stream/outstanding sweeps 1, 2, 4, 8, 16, 32, 64, 128, 256; three repeats, five above 5% CV.

**Saturation criteria:** use the common rules. The profiling stage must sample the last scaling point, first plateau point, and first degraded/saturated point; a plateau without a saturated measured host resource is software/harness-limited by definition.

**Required telemetry:** common telemetry plus profiler version/config, symbol resolution rate, per-thread stacks, queue/outstanding samples, context switches, and diagnostic-vs-control delta.

**PASS/PARTIAL/FAIL:** PASS requires a named measured bottleneck reproduced in both an authoritative cell and a focused diagnostic. PARTIAL means plateau reproduced but attribution remains ambiguous. FAIL means profiling changes workload results beyond 5%, symbols are unusable, or evidence cannot correlate stacks and runs.

**Evidence output:** `evidence/performance/v2/b2-profile-{start_sha_12}/` with raw ETW/profiler trace, exported stack table, matched control runs, and attribution report.

**Stop condition:** stop before optimization if no profiler produces reliable symbols/blocked-time attribution or if the plateau does not reproduce.

- [ ] **Step 1: Write RED contract tests** requiring closed profiler metadata, verified affinity, control/profile pairs, symbol-resolution threshold, hotspot attribution, and prohibition on `HARDWARE-LIMITED` without resource saturation.
- [ ] **Step 2: Run RED:** `python -m pytest tests/performance/test_b2_v2_profile.py -q`; expect missing runner/schema failure.
- [ ] **Step 3: Implement minimum runner:** tool discovery, bounded control/profile pairs, raw trace retention, exports, and classification. Use direct argv execution and an external build/output root.
- [ ] **Step 4: Run GREEN self-tests and short profiles**, then one authoritative profiling matrix. Preserve overhead-invalid profiles as rejected attempts.
- [ ] **Step 5: Commit atomically:** `test(bench): profile pre-saturation throughput plateau` only after attribution is defensible.

### Task 2: Evidence-driven bottleneck optimization

**Current result:** No V2 optimization exists. Previous B2 deliberately stopped at SOFTWARE-LIMITED without attributing or changing the implementation.

**Current limitation:** Optimization target is unknown until Task 1 passes. Any preselected change would be speculative or benchmark gaming.

**Files:**
- Modify only the exact source/harness file named by Task 1 attribution.
- Create: one focused regression/performance test adjacent to the owning package.
- Create: `scripts/compare_b2_v2_optimization.py`
- Create: `tests/performance/test_b2_v2_optimization.py`

**Profiling needed:** repeat the same profiler and control matrix before and after each candidate; confirm the targeted hotspot shrinks rather than moving measurement work outside the timed region.

**Optimization gate:** keep a change only if five matched before/after pairs show median goodput improvement at least 10% or CPU ns/op reduction at least 10%; p99 regression no more than 5%; zero errors/timeouts; identical useful work; cleanup PASS; profiler hotspot reduced; all security/protocol tests unchanged.

**Load progression:** focused hotspot micro/regression cell, then B2 workloads at 1/2/4 verified CPUs and the Task 1 outstanding/concurrency points around the plateau.

**Saturation criteria:** use common rules; an optimization that merely shifts saturation lower or increases queueing is rejected.

**Required telemetry:** all Task 1 telemetry plus before/after source/binary hashes, timed-region markers, payload/operation equality, and statistical paired deltas.

**PASS/PARTIAL/FAIL:** PASS means a measured bottleneck was reduced and the full gate passes. PARTIAL means the bottleneck is real but no safe candidate clears the gate; revert production changes and retain evidence. FAIL means correctness/security/work equivalence regresses or the candidate games accounting.

**Evidence output:** `evidence/performance/v2/b2-optimization-{start_sha_12}/`, retaining every accepted and rejected candidate.

**Stop condition:** stop after two independently reasonable candidates fail the gate, or immediately if a fix would affect frozen/public/security semantics; report SOFTWARE/HARNESS-LIMITED with the named owner.

- [ ] **Step 1: Convert the Task 1 cause into a literal RED test** whose failure is the measured serialization/copy/wakeup/queue symptom, not a lower assertion threshold.
- [ ] **Step 2: Implement the smallest candidate** without protocol/security changes.
- [ ] **Step 3: Run focused correctness GREEN**, then five paired release measurements and the same profiler.
- [ ] **Step 4: Keep or revert based only on the gate**; preserve rejected evidence.
- [ ] **Step 5: Run affected Rust/Go/Python, fmt, Clippy/vet, safety, and diff checks.**
- [ ] **Step 6: Commit accepted optimization separately:** `perf(runtime): reduce measured {named-hotspot}`, replacing the brace token with the profiler's exact owner; if none passes, commit evidence/docs only.

### Task 3: Max-throughput and saturation sweep

**Current result:** B2 peak observations are 0.549 Gbit/s for 1 KiB/64 and 0.686 Gbit/s for 16 KiB/8 NBSR at verified 4-core affinity, but they do not establish a true stable maximum or hardware ceiling.

**Current limitation:** Only 1/2/4 affinity cells and two fixed stream counts were tested; the plateau owner was not known and offered load/outstanding depth did not progress to a fully attributed saturation boundary.

**Files:**
- Create: `scripts/run_max_throughput_v2.py`
- Create: `tests/performance/test_max_throughput_v2.py`
- Reuse or minimally extend: existing established-data-plane harness.

**Profiling needed:** low-overhead counters in every cell; full profiler at last stable, first degraded, and first saturated points.

**Optimization gate:** Task 2 must be PASS or explicitly PARTIAL with all speculative code reverted and a named unresolved bottleneck.

**Load progression:** payloads 1 KiB and 16 KiB; streams 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, then 768/1024 only if previous point is stable and within configured limits; outstanding operations 1, 2, 4, 8, 16; verified affinity 1/2/4 and unrestricted; matched Direct/NBSR; geometric growth followed by midpoint refinement around transition.

**Saturation criteria:** common rules plus explicit offered/achieved goodput, per-core CPU, and queue/outstanding conservation. Peak is the median of the highest stable cell, not the largest observed spike.

**Required telemetry:** goodput, ops/s, p50/p95/p99, CPU/effective cores, CPU ns/op, Gbit/s/core, per-process/thread CPU, memory, queues, context switches, runtime counters, errors/timeouts, affinity, thermal/frequency state.

**PASS/PARTIAL/FAIL:** PASS requires stable, degraded, and saturated regions plus a measured bottleneck classification. PARTIAL if safe host/harness bounds stop before saturation. FAIL on invalid work, errors below the prior stable region, or unexplained regression.

**Evidence output:** `evidence/performance/v2/max-throughput-{start_sha_12}/` and a machine-readable ceiling artifact consumed by B4b-v2/B5-v2.

**Stop condition:** stop escalation on first FAIL, memory pressure, thermal throttling that invalidates comparability, or configured safe resource bound; never increase a hard safety limit during the run.

- [ ] **Step 1: Write RED schema/load-ladder tests** including midpoint refinement and stable-ceiling derivation.
- [ ] **Step 2: Implement runner and short smoke sweep GREEN.**
- [ ] **Step 3: Run authoritative Direct/NBSR progression**, profile boundary cells, and derive peak/classification.
- [ ] **Step 4: Commit:** `test(bench): establish v2 stable throughput ceiling`.

### Task 4: B4b-v2 mixed multi-client/connection/route scaling

**Current result:** Evidence PASS / System SATURATED. Clients 1–8 were STABLE, 16–64 DEGRADED, and 128 SATURATED. At 128 clients: 0.271 Gbit/s, 22.22 admissions/s, 71 pending clients, 1,032 failures, and 258 timeouts.

**Current limitation:** Established forwarding and churn used separate destination processes/listeners. The 128-client failure is real for this harness/host, but it is not attributed to process creation, handle limits, scheduler contention, UDP/QUIC, admission serialization, or NBSR runtime behavior.

**Files:**
- Create: `scripts/run_b4b_v2.py`
- Create: `tests/performance/test_b4b_v2.py`
- Reuse/minimally extend: `scripts/run_b4b_mixed_connections.py`.

**Profiling needed:** process creation rate/time, handles, threads, context switches, ready time, per-runtime CPU, connection/session/channel/stream counters, admission stage durations, queue depth, socket errors, ephemeral UDP state, and boundary-cell stack profiles.

**Optimization gate:** fix only an attributed harness/runtime bottleneck that meets Task 2's paired 10%/5%/correctness gate. Separate-process and shared-runtime variants must never be compared as equivalent semantics.

**Load progression:** clients 1, 2, 4, 8, 16, 32, 64, 96, 128, 192, 256, 384, 512; connections/client 1, 2, 4, 8; admission target rates 10, 25, 50, 75, 100, 150, 200/s; established load at 50%, 70%, and 80% of Task 3 stable ceiling. Stop branches independently at saturation.

**Saturation criteria:** common rules plus admission success below 90%, pending clients non-draining, process/handle creation failure, or ownership counters not returning to zero.

**Required telemetry:** established goodput, admissions/s, success/failure/timeout, p50/p95/p99, CPU, memory, handles, processes, threads, context switches, queue/backpressure, connection/session/channel/stream ownership, cleanup duration.

**PASS/PARTIAL/FAIL:** PASS requires stable/degraded/saturated regions and an attributed bottleneck. PARTIAL if safe Windows process/handle bounds prevent the upper region without attribution. FAIL if resources leak, fail-closed behavior changes, or errors appear below the accepted stable region without explanation.

**Evidence output:** `evidence/performance/v2/b4b-{start_sha_12}/` with all bad-valid high-load cells.

**Stop condition:** stop on resource leak, system instability, security regression, or a host process/handle safety threshold recorded before execution.

- [ ] **Step 1: Write RED progression, telemetry, and attribution tests.**
- [ ] **Step 2: Implement low-load GREEN without changing B4b semantics.**
- [ ] **Step 3: Execute the load matrix branch-by-branch and profile boundaries.**
- [ ] **Step 4: Apply only separately gated fixes, rerun affected branches, and commit:** `test(bench): attribute v2 mixed-connection saturation`.

### Task 5: B3-v2 memory/session scaling and same-process lifecycle

**Current result:** Rust↔Rust and Go↔Rust are Evidence PARTIAL / Lifecycle CLEAN for counts 1/2/4/8. Measured connection slopes were approximately 230,961 and 222,466 private bytes/connection. All ownership counters returned to zero.

**Current limitation:** More than eight active resources and same-process open/steady/close/cooldown staircase cycles are unproven. Process-isolated cycles reset allocator/runtime state; the serialized lifecycle server and 10-second ACK bound constrained prior cells.

**Files:**
- Create: `scripts/run_b3_v2.py`
- Create: `tests/performance/test_b3_v2.py`
- Modify only if RED proves a harness ownership limitation: benchmark-harness code, never transport semantics.

**Profiling needed:** allocation/heap owner where available; working set/private bytes/commit; handles; threads/goroutines/tasks; sockets; NBSR connections/sessions/channels/streams; queues/replay/cache; GC; cleanup duration; same-process cycle slope and changepoints.

**Optimization gate:** harness changes must preserve ACK and lifecycle semantics, pass existing timeout tests unchanged, and prove that higher counts represent simultaneously active named resources. Runtime fixes require a reproducible lifecycle defect and regression test.

**Load progression:** resources 1, 2, 4, 8, 16, 32, 64, 128; then 192/256 only after stability. Separate connection, channel, and stream dimensions. Same-process cycles 10 smoke, 25 validation, 50 authoritative, 100 only if 50 is stable. Rust↔Rust first, then Go↔Rust.

**Saturation criteria:** common rules plus inability to hold requested active resources, cleanup counters nonzero, cooldown staircase exceeding 64 KiB/cycle with positive fit across repeated windows, handle/task growth, or GC/allocator growth without plateau.

**Required telemetry:** idle/active/cooldown memory, slopes/dispersion/confidence, resource counts, task/goroutine/thread counts, handles/sockets, GC, replay/cache/queue counters, process identity, and allocator-retention notes.

**PASS/PARTIAL/FAIL:** PASS per path requires at least 64 simultaneous resources, 50 same-process cycles, zero owned-resource residue, and bounded cooldown plateau. PARTIAL for valid scaling without same-process closure. FAIL for reproducible unbounded resource growth or cleanup violation. Retained RSS alone is never a leak classification.

**Evidence output:** `evidence/performance/v2/b3-memory-{start_sha_12}/`, preserving the earlier slopes as host-specific comparison only.

**Stop condition:** stop and diagnose at the first nonzero ownership counter or staircase growth; do not raise timeouts blindly.

- [ ] **Step 1: Write RED simultaneous-resource and same-process-cycle tests.**
- [ ] **Step 2: Prove current harness RED at the first unsupported count/cycle.**
- [ ] **Step 3: Make the smallest harness-only change, run focused GREEN and unchanged timeout tests.**
- [ ] **Step 4: Run scaled matrices/cycles and classify each transport independently.**
- [ ] **Step 5: Commit:** `test(bench): scale v2 memory lifecycle evidence`, or a separate minimal lifecycle fix followed by evidence commit if a real bug is proven.

### Task 6: B5-v2 60–120 minute near-ceiling soak

**Current result:** Evidence PASS / System STABLE: 1 KiB/64 ran 60 minutes at median 0.734 Gbit/s with -3.168% drift; 16 KiB/8 ran 30 minutes at 0.853 Gbit/s with +1.599% drift; zero errors/timeouts and cleanup PASS.

**Current limitation:** Loads predate V2 optimization/ceiling discovery, the second cell is only 30 minutes, and no near-new-ceiling 120-minute cell exists.

**Files:**
- Create: `scripts/run_b5_v2.py`
- Create: `tests/performance/test_b5_v2.py`
- Reuse/minimally extend: `scripts/run_b5_sustained_capacity.py`.

**Profiling needed:** periodic low-overhead telemetry only; a profiler is used in a separate 5-minute matched diagnostic if drift/anomaly appears, never across the authoritative soak.

**Optimization gate:** Tasks 2–3 classification and stable-ceiling artifact must be accepted; no soak starts from an unresolved or single-repeat peak.

**Load progression:** 10-minute validation at 70%; 30-minute validation at 80%; 60-minute authoritative at 70%; 120-minute authoritative at 80% if 60-minute cell is stable. Run both representative workloads unless one is already invalidated by Task 3.

**Saturation criteria:** errors/timeouts; throughput decay above 5%; p99 drift above 20%; positive non-plateau memory/handle/task/queue slope; cleanup failure; thermal throttling invalidating load; or resource utilization crossing the measured safe boundary.

**Required telemetry:** exact goodput/ops, latency time series, CPU/effective cores, memory/private/commit, handles, threads/tasks, sessions/connections/streams, queues, GC, errors/timeouts, cleanup, frequency/thermal/power, sampling overhead.

**PASS/PARTIAL/FAIL:** PASS requires at least one 120-minute near-ceiling stable cell and one 60-minute second workload cell. PARTIAL if only 60 minutes are valid. FAIL on unbounded growth, cleanup violation, error accumulation, or unexplained decay.

**Evidence output:** `evidence/performance/v2/b5-soak-{start_sha_12}/` with periodic NDJSON/CSV and phase analysis.

**Stop condition:** abort safely on any FAIL threshold, host thermal/power instability, or cleanup anomaly; preserve partial raw data.

- [ ] **Step 1: Write RED ceiling-consumption, phase, drift, and abort tests.**
- [ ] **Step 2: Run 10-minute GREEN validation before any long run.**
- [ ] **Step 3: Run 30-, 60-, then 120-minute cells sequentially with analysis gates.**
- [ ] **Step 4: Commit:** `test(bench): add v2 near-ceiling soak evidence`.

### Task 7: B1-v2 packet-level Direct vs NBSR overhead

**Current result:** B1 is INCONCLUSIVE. The loopback relay measured UDP bytes/datagrams and setup overhead, but established Direct/NBSR deltas were within pair dispersion; retransmissions and physical framing were not measured because pktmon access was denied.

**Current limitation:** No authoritative pcap, frame inventory, capture-drop proof, or transport-counter correlation. Windows loopback cannot measure Ethernet preamble, FCS, inter-packet gap, or physical NIC bytes.

**Files:**
- Create: `scripts/capture_b1_v2.ps1`
- Create: `scripts/analyze_b1_v2_capture.py`
- Create: `tests/performance/test_b1_v2_capture.py`
- Reuse: `scripts/run_b1_wire_overhead.py` and existing WP8 Dumpcap/Npcap capture conventions.

**Profiling needed:** not CPU profiling; quantify capture observer overhead with capture-disabled controls and preserve tool/interface/filter/drop metadata.

**Optimization gate:** no performance optimization in B1-v2. Capture methodology is accepted only if matched controls differ by at most 5% goodput/p99 and dumpcap reports zero drops.

**Load progression:** setup-only and established phases; 1 KiB/64 and 16 KiB/8; Direct then NBSR in randomized paired order; five valid pairs; fixed useful operations; fresh capture per run; optional reduced-rate validation before full runs.

**Saturation criteria:** B1 cells run below the V2 stable ceiling to avoid loss caused by overload. Any capture drops, interface ambiguity, unrelated packets, or workload mismatch invalidates the pair.

**Required telemetry:** pcapng; frame count and `frame.len`; UDP/IP payload and packet counts; direction; setup vs established markers; capture drops; interface identity; filters; tool versions; useful payload; QUIC native loss/retransmission counters if exposed. Do not infer exact retransmissions from encrypted packet capture alone.

**PASS/PARTIAL/FAIL:** PASS requires exact packet/frame byte totals, five valid pairs, stable incremental result outside paired uncertainty or an honest statistically indistinguishable result, setup/data-plane separation, and zero capture drops. PARTIAL if only loopback frame bytes are available. FAIL on mixed flows, drops, privacy leak, or incomparable workloads.

**Evidence output:** `evidence/performance/v2/b1-wire-{start_sha_12}/` with pcaps, TShark CSV, relay/transport counters, analysis, privacy inventory, and checksums.

**Stop condition:** stop if Dumpcap/Npcap lacks capture permission, capture drops persist at reduced load, or the allowlisted flow cannot be isolated. Do not fall back to invented physical-wire precision.

- [ ] **Step 1: Write RED wrapper, pcap parser, flow-closure, drop, and privacy tests.**
- [ ] **Step 2: Discover `dumpcap.exe`, `tshark.exe`, NPF loopback, versions, and permissions without installing software.**
- [ ] **Step 3: Run a short capture RED/GREEN validation and observer-control pair.**
- [ ] **Step 4: Execute five authoritative matched pairs and derive uncertainty-aware overhead.**
- [ ] **Step 5: Commit:** `test(bench): measure v2 direct nbsr packet overhead`.

### Task 8: External Linux/server-class validation definition

**Current result:** All V2 predecessor results are scoped to Windows loopback on an Intel i5-10210U host. No server-class, Linux, physical NIC, WAN, NUMA, or multi-host hardware-scaling claim exists.

**Current limitation:** The local host cannot prove physical NIC limits, server CPU scaling, NUMA behavior, IRQ/RSS distribution, or cross-host network capacity.

**Files:**
- Create: `docs/benchmarks/funding-grade-v2-server-linux-validation.md`
- Create: `config/benchmarks/funding-grade-v2-server-matrix.json`
- Create: `tests/performance/test_funding_grade_v2_server_plan.py`

**Profiling needed:** Linux `perf` stacks/counters, `pidstat`, `/proc`, cgroup stats, NIC `ethtool -S`, link speed, IRQ/RSS, softnet drops, socket/QUIC counters, NUMA placement, CPU frequency/governor, thermal/power, and packet capture on dedicated interfaces.

**Optimization gate:** local Windows optimizations must first pass Tasks 1–7. External runs use the same source SHA, binary hashes, workload semantics, analysis schema, and stable/saturation rules.

**Load progression:** single host loopback control; two hosts on 10 GbE or faster; payloads 1 KiB/16 KiB; Direct/NBSR; 1/2/4/8/16/32 verified physical cores where available; stream/outstanding ladders from Task 3; B4b client ladders; B3 resource ladders; 60/120-minute soak.

**Saturation criteria:** common rules plus CPU at least 90% of allocated physical capacity, NIC throughput at least 85% of negotiated speed with queue/drop/IRQ evidence, memory pressure/paging, or another explicitly measured host limit.

**Required telemetry:** exact hardware inventory, BIOS/firmware, kernel, mitigations, NUMA, NIC/driver/firmware/link, topology, isolated CPUs/affinity, IRQ/RSS, power governor, toolchains, container/cgroup limits, switch/path details, and time synchronization.

**PASS/PARTIAL/FAIL:** PASS for the definition requires a closed machine-readable matrix, exact commands, schemas, hardware gates, and acceptance rules that a third party can execute. It does not mean server validation was run. External evidence is PASS only after raw results satisfy the matrix; otherwise `NOT YET VALIDATED`.

**Evidence output:** no fabricated measurements. Future runs use `evidence/performance/v2/server-linux-{start_sha_12}-{host_id}/`, with both tokens recorded in the run manifest.

**Stop condition:** never label Windows evidence hardware-scaled while external cells remain unrun; never compare hosts with different workload/source semantics as matched scaling.

- [ ] **Step 1: Write RED schema tests** requiring hardware, topology, affinity, NIC, profiler, workload, repeat, and stop-gate fields.
- [ ] **Step 2: Implement the closed JSON matrix and reproduction document GREEN.**
- [ ] **Step 3: Validate JSON/schema, commands, claim language, and links.**
- [ ] **Step 4: Commit:** `docs(bench): define server linux validation matrix`.

## Program completion gate

The V2 program is complete only when Tasks 1–7 are classified and Task 8 defines the external matrix. Final local classification must be exactly one of:

- `MEASURED_HOST_CEILING:{resource}` with telemetry meeting the hardware gate;
- `SOFTWARE-LIMITED:{named-hotspot}` with profiler evidence and optimization disposition;
- `HARNESS-LIMITED:{named-hotspot}` with affected claims withheld;
- `UNRESOLVED` with exact missing evidence.

Before final completion: verify every stage SHA, binary/source hash, raw checksum, derived number, workload equivalence, affinity claim, telemetry source, rejected run, cleanup result, and documentation claim; run affected Rust/Go/Python suites, fmt, Clippy `-D warnings`, vet, dependency/privacy/safety checks, and `git diff --check`. Do not start ISP/Federation implementation or final outreach packaging.
