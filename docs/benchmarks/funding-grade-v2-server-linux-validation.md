# Server/Linux campaign matrix

Status: **PARTIAL_REQUIRED_PORTING / NOT_RUN / EXTERNAL_HARDWARE_REQUIRED**.
This is the closed workload and evidence definition for Task 8, not a complete executable campaign. The definition gate remains PARTIAL until every required backend and exact execution command exists and is validated. No external hardware result is claimed.

The machine-readable contract is [funding-grade-v2-server-matrix.json](../../config/benchmarks/funding-grade-v2-server-matrix.json). It enumerates forwarding, admission, independent memory axes, soak and wire cells; repeat policies; physical-core and NIC requirements; observer thresholds; fail-closed stop rules; evidence structure; and explicit implementation coverage. No runner currently executes this whole file. Do not pass it to the existing loopback subset runner, whose schema is different.

## Ordered reproduction

1. Provision one dedicated bare-metal Linux host for loopback, and two dedicated hosts with a documented 10 GbE-or-faster path for external runs. The matrix specifies minimum 16 GiB RAM and 100 GiB free evidence storage (planning requirements, not measured NBSR resource requirements). Record unavailable core counts as NOT_RUN. Docker Desktop is compatibility evidence only.
2. Follow the exact inventory/build/source-binding commands in [EXTERNAL_LINUX_SERVER_VALIDATION.md](EXTERNAL_LINUX_SERVER_VALIDATION.md). Record current clean source, locked toolchains, platform-specific binary hashes, cgroup limits, topology, frequency/power, IRQ/RSS, NIC and switch details. Do not change OS security policy to make telemetry available; record permission-dependent gaps.
3. Run the existing finite loopback subset using that document's commands, then the exact source/authority/peer/telemetry sequence in [EXTERNAL_NATIVE_TWO_HOST_RUNBOOK.md](EXTERNAL_NATIVE_TWO_HOST_RUNBOOK.md). The runbook uses actual operator-provided addresses, never guessed hosts. Both paths must perform equivalent secure transport/application work. These commands remain AUTHORED/UNEXECUTED on dedicated external servers.
4. For the Linux B5 finite reference, follow [LINUX_B5_REFERENCE.md](LINUX_B5_REFERENCE.md). Its strict loader requires exact current source/binary/topology/workload evidence. Its one-core/one-group subset cannot establish the entire 1/2/4/8/16/32-core matrix.
5. Use the following commands only to inspect the existing CLI contracts, from the repository root with the documented Python dependencies installed. They do not execute benchmarks or establish acceptance:

```bash
python3 -m scripts.performance.linux_loopback --help
python3 scripts/run_b3_v2.py --help
python3 scripts/run_b4b_linux.py --help
python3 -m scripts.performance.linux_b5_reference --help
```

6. The Linux sustained CLI is now authored; use the exact reference-bound example in LINUX_B5_REFERENCE.md. Current Rust/QUIC execution and observer qualification remain pending. The full wire/multihost executors are still absent, with null matrix commands and named missing work. Complete and validate these gaps before declaring end-to-end definition readiness.

## Cell and acceptance rules

Expand placements, paths and available physical-core counts with each workload's explicit shape fields; honor each backend's documented coverage rather than silently clipping unsupported cells. Start forwarding depth at 1 and progress in the defined order. Stop the affected ladder after the first saturated point; additional investigation must be a separately declared diagnostic. Burst and rate-controlled admission are different cohorts. Isolate connection/session/channel/stream axes where supported; otherwise report measured bundle cost and mark independent costs NOT_PROVEN.

Use three valid repeats per cell, expanding both matched paths to five when either exceeds 5% CV. Preserve unfavorable valid runs. An invalid run stops its cohort and is not replaced. Report strict-stable, degraded, saturated and diagnostic peak separately. A plateau does not establish hardware capacity. CPU bound requires at least 90% of allocated capacity; NIC bound requires at least 85% of negotiated speed plus queue/drop/IRQ evidence; memory bound requires measured sustained pressure. Missing thermal/power measurements preclude thermal qualification.

Soak uses the exact accepted reference and unchanged workload: 10 minutes at70%,30 at80%,60 at70%,120 at80% only after prior gates pass. Both representative payload classes remain required. Achieved/offered below95%, goodput decay above5%, p99 drift above20%, errors/timeouts, sampling failure, nonzero cleanup or sustained owned-resource accumulation fail the relevant gate. Do not increase timeouts or lower offered load to turn a failed cell into the same accepted cell.

Packet accounting uses fixed operation counts and separate timed runs if capture distorts performance. Retain directly measured UDP/IP bytes and packet counts separately from derived L2 estimates. Report incremental equivalent Direct-versus-NBSR cost; never rename generic secure-transport framing as NBSR overhead. Validate capture loss and reject incomplete byte accounting.

## Evidence and unresolved delivery

Each external root is `evidence/performance/v2/server-linux-{start_sha_12}-{host_id}/`, with raw, commands, telemetry and analysis directories. Retain failed partial runs, per-role commands and affinity, host inventory, completed/offered counters, latency windows, CPU, memory/ownership, cleanup, NIC/capture records, source/binary/controller manifests and SHA-256 indexes. Record an index checksum separately. Existing schemas are referenced by the implemented runners; portable sustained/wire schemas still require implementation and tests.

Remaining definition blockers are implementation work, not merely unavailable hardware: sustained Linux B5 nonreaping lifecycle/sampling, observer qualification, dedicated-interface packet orchestration, resource-axis coverage and full multihost/8+core matrix execution. Server execution separately requires external hardware. Definition PASS does not imply execution PASS; both remain unearned here.

## Definition verification

Two focused contract tests failed RED because the matrix did not exist, then passed GREEN. Ruff passed. All four existing CLI help entrypoints exited0 on the current Windows host; this validates argument-interface availability only, not Linux execution. Relative documentation/source links were checked. No runtime/security code changed; no full suite was rerun for this definition-only stage. One focused review caught and replaced a backend-module help invocation with the actual B3 CLI. Full definition acceptance remains PARTIAL.
