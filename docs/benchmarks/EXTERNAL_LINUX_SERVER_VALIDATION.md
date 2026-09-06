# External Linux/server validation definition

Status: **NOT_RUN / EXTERNAL_HARDWARE_REQUIRED**. No usable external host, physical-NIC measurement, or server scaling result is established. Docker Desktop Linux VM compatibility passed six finite repeats at 3644c324; see evidence/performance/v2/linux-compatibility-3644c324. This is not bare-metal/server capacity. A new executable Linux **loopback control** runner and machine-readable matrix now exist, with synthetic tests and a scoped Docker VM execution. Benchmark-only native IPv4 placement now has local functional/security evidence, and a [finite two-host runbook](EXTERNAL_NATIVE_TWO_HOST_RUNBOOK.md) has source/command syntax review. Remote execution is unverified. Full external definition readiness remains **PARTIAL / REQUIRED PORTING**: the complete portable admission/memory/soak/wire matrix is not implemented. Do not mark the Task 8 definition gate PASS on the basis of the loopback subset.

Contract: [funding-grade V2 plan, Task 8](../superpowers/plans/2026-08-30-funding-grade-benchmark-v2.md). Frozen protocol, trust, authority, admission, and wire semantics remain unchanged. No application payload before ACCEPT. This file contains proposed execution requirements, not measurements.

## Host and build gates

- Use a dedicated bare-metal Linux server for loopback controls and two dedicated servers connected by a documented 10 GbE-or-faster path for external cells. Record unavailable core counts as NOT_RUN; a VM or container cannot establish bare-metal capacity without explicit qualification.
- Target a maintained Ubuntu/Debian Linux distribution; record the exact distribution, kernel, architecture, microcode, BIOS, security mitigations, CPU sockets/physical cores/SMT, RAM, NUMA nodes, NIC driver/firmware, switch configuration, MTU, link speed and time synchronization. Distribution compatibility has not been tested here.
- Install a C compiler/linker and build tools for Rust native dependencies, Git, Python 3, Rust/Cargo supporting edition 2024 and the locked dependencies, and Go satisfying `interop/nbsr-go-peer/go.mod` (currently `go 1.26.5`). Pin and record exact versions rather than silently using different toolchains across cells.
- Provision `util-linux` (`lscpu`, `taskset`), `sysstat` (`pidstat`), kernel-matched `perf`, `numactl`, `ethtool`, `iproute2`, and Dumpcap/TShark. Verify profiler, NIC-statistics, and dedicated-interface capture permissions before scheduling measurements. Record missing telemetry; do not replace it with inferred values.
- Match the accepted source SHA and clean source manifest on both Linux hosts. Cross-platform binaries necessarily have different hashes: bind each binary to its platform, SHA, build flags, and toolchain. Never assert identical Windows/Linux binary hashes.
- Build outside the repository on local storage. Complete builds before timing. Record CPU governor, turbo policy, frequency, temperature, cgroup quotas/cpuset/memory limits, background activity, and available disk space. No build, profiler discovery, package installation, or competing workload during control timing.

These are real build and inventory commands for a provisioned Linux host, run from the repository root. They are **not** a claim of successful Linux compilation or a complete campaign launcher. Use a fresh output directory per attempt; the first `mkdir` intentionally fails on reuse.

```bash
set -euo pipefail
start_sha=$(git rev-parse HEAD)
initial_status=$(git status --porcelain)
test -z "$initial_status"
host_id=$(hostname -s | tr -cd 'A-Za-z0-9_-')
test -n "$host_id"
evidence_parent="${NBSR_EXTERNAL_EVIDENCE_ROOT:-/var/tmp/nbsr-evidence}"
mkdir -p "$evidence_parent"
evidence_parent=$(realpath "$evidence_parent")
repository_root=$(git rev-parse --show-toplevel)
repository_root=$(realpath "$repository_root")
case "$evidence_parent/" in
  "$repository_root/"*) printf 'Evidence must be outside the clean checkout\n' >&2; exit 1 ;;
esac
evidence="$evidence_parent/server-linux-${start_sha:0:12}-${host_id}"
mkdir "$evidence"
mkdir "$evidence/raw"
printf '%s' "$initial_status" > "$evidence/raw/git-status.txt"
git rev-parse HEAD > "$evidence/raw/source-sha.txt"
git branch --show-current > "$evidence/raw/source-branch.txt"
cat /etc/os-release > "$evidence/raw/os-release.txt"
uname -a > "$evidence/raw/kernel.txt"
lscpu -J > "$evidence/raw/lscpu.json"
lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE > "$evidence/raw/cpu-topology.txt"
numactl --hardware > "$evidence/raw/numa.txt"
rustc -Vv > "$evidence/raw/rustc.txt"
cargo -V > "$evidence/raw/cargo.txt"
go version > "$evidence/raw/go.txt"
python3 --version > "$evidence/raw/python.txt"
export CARGO_TARGET_DIR="${TMPDIR:-/var/tmp}/nbsr-linux-${start_sha:0:12}-${host_id}"
cargo build --locked --release \
  --manifest-path crates/nbsr-transport/Cargo.toml \
  --features benchmark-harness \
  --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server \
  > "$evidence/raw/rust-build.log" 2>&1
(
  cd interop/nbsr-go-peer
  go build -mod=readonly -trimpath \
    -o "$CARGO_TARGET_DIR/release/nbsr-go-peer" ./cmd/nbsr-go-peer
) > "$evidence/raw/go-build.log" 2>&1
sha256sum "$CARGO_TARGET_DIR/release/"{perf_direct_peer,perf_rust_source,wp8_interop_server,nbsr-go-peer} \
  > "$evidence/raw/binaries.sha256"
```

Evidence is created outside the checkout so inventory/build logs do not invalidate the runner's clean-source preflight. Select a fresh host/run identifier for a repeat attempt and record its relationship to the previous attempt. A dirty checkout fails provenance preflight; do not reset or discard changes automatically. Copy an accepted, finalized package into the repository only after execution and integrity verification.

## Affinity and accounting

Derive CPU sets from `(socket, core)` identifiers in `lscpu`, not CPU-number adjacency. For physical-core cells choose exactly one online logical CPU per distinct physical core on one NUMA node, starting at 1, 2, and 4 cores; extend to 8/16/32 where available. Run SMT siblings only as separately named cells with the same physical-core count. Keep unrestricted and cross-NUMA cells separate. Record IRQ/RSS placement and whether IRQ work shares workload CPUs.

The Linux runner must set affinity before workload start and verify `/proc/<pid>/task/<tid>/status` `Cpus_allowed_list` for every worker throughout the timed interval; record child processes and process start times. `taskset` on the launcher alone is insufficient evidence. Record client and server CPU sets independently across hosts. On loopback, explicitly declare whether both roles share one total CPU pool or use disjoint pools.

For a matched timed interval, effective cores = total tracked process CPU seconds / elapsed seconds; CPU ns/op = total tracked process CPU nanoseconds / successfully completed operations; Gbit/s/core = application goodput / effective cores. Report per-role values and aggregate values. Host IRQ/softirq CPU is separately measured and not silently included in process CPU. A single-core result is valid only when all declared workload roles obey the stated one-core allocation. Do not relabel multi-role CPU ns/op as isolated protocol-core cost: isolated core ns/op requires a separately defined operation boundary and corresponding portable microbenchmark, which this definition does not provide.

## Executable Linux loopback subset

`scripts/performance/linux_loopback.py` is a new Linux-only runner; it does not import Windows measurement runners. `scripts/performance/linux_loopback_matrix.json` defines matched Direct/NBSR cells at 1/2/4 physical cores for 1 KiB/64 streams and 16 KiB/8 streams, outstanding depth 1, warmup 3 seconds and measurement 20 seconds. Both roles share the selected core pool on one NUMA node. It sets affinity using `taskset` before peer execution, verifies every observed thread through `/proc`, rejects unexpected child processes, retains raw process telemetry and stdout/stderr, and alternates matched order across three repeats (five for both paths when either path exceeds 5% CV). Any invalid run is retained and stops the campaign; no silent replacement. The runner requires Python's `cryptography` package for the existing temporary test-authority helper.

The CLI is source-grounded in `run_p2a_established.run_repeat`; the current single-group NBSR destination supports at most 64 streams. This runner intentionally validates only 1/2/4 cores, payloads 1 KiB/16 KiB, streams 1–64, and outstanding 1/2/4/8/16. Changing matrix JSON within these bounds is supported. It does not implement 128+ stream groups, admission, lifecycle, soak, wire, SMT or remote cells.

Before running, use an accepted clean checkout containing these new files, and build the peers with the earlier command. Create the build manifest from those build artifacts in the same Bash session:

```bash
export NBSR_LINUX_BUILD_EVIDENCE="$evidence"
python3 - <<'PY'
import hashlib, json, os, pathlib, subprocess
root = pathlib.Path(os.environ['NBSR_LINUX_BUILD_EVIDENCE'])
target = pathlib.Path(os.environ['CARGO_TARGET_DIR']) / 'release'
names = ('perf_direct_peer', 'perf_rust_source', 'wp8_interop_server')
manifest = {
    'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'binary_sha256': {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in names},
    'build_profile': 'release',
    'build_commands': [['cargo', 'build', '--locked', '--release', '--manifest-path',
        'crates/nbsr-transport/Cargo.toml', '--features', 'benchmark-harness',
        '--bin', 'perf_direct_peer', '--bin', 'perf_rust_source', '--bin', 'wp8_interop_server']],
    'toolchains': {name: (root / 'raw' / filename).read_text()
        for name, filename in [('rustc', 'rustc.txt'), ('cargo', 'cargo.txt')]},
}
(root / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
python3 -m unittest tests.performance.test_linux_loopback
python3 -m scripts.performance.linux_loopback \
  --matrix scripts/performance/linux_loopback_matrix.json \
  --binaries "$CARGO_TARGET_DIR/release" \
  --build-manifest "$evidence/build-manifest.json" \
  --output "$evidence/loopback-control"
```

The output directory must not exist. The runner checks a clean source checkout, source SHA, executable binary hashes, declared build metadata, available physical cores and Linux tooling before launch. Keep build logs and manifest together; metadata is operator-supplied provenance, not a cryptographic proof of compilation. The earlier checksum command covers the combined build and loopback artifacts after execution. Synthetic tests run on Windows do not establish Linux execution compatibility.

CPU totals in this subset are read from the final unreaped `/proc/<pid>/stat` records and cover **whole process lifetime**, including launcher/startup/warmup/drain. It reports `lifetime_cpu_ns_per_completed_operation`, explicitly not steady-state CPU ns/op. Steady CPU ns/op and effective cores remain null because the binaries do not expose synchronized external measurement barriers. Affinity is sampled at 100 ms; inherited affinity is set before execution, and sampled mismatches fail closed. Resource cleanup means both owned peer processes exited successfully, not a proof that every internal ownership counter returned to zero. A valid repeat additionally passes the existing P2A completed-work and zero-error/corruption/session-delta contract.

`PASS_LOOPBACK_CONTROL` means all requested loopback repeats were valid and CV was at most 5%; `PARTIAL_DISPERSION` means the five-repeat dispersion gate failed. Neither establishes strict-stable capacity: the closed-loop benchmark does not prove offered-rate/backlog gates, and this subset has no matched lowest-load latency sweep. No external, physical-NIC, isolated-core, or production claim follows from either status.

Both server commands receive the existing completion-ACK path, and the runner creates it only after the source's final process sample has been flushed and source exit succeeds. This matches the existing Windows runner convention. The current single-group NBSR P2A branch returns without waiting for this ACK; the Direct P2A branch honors it. This runner change is a completion convention, not a claimed fix for a demonstrated NBSR deadlock.

## Required matrix

Direct means the existing direct-QUIC baseline, not plain TCP. Match payload, completed operation definition, offered-rate schedule, streams, outstanding depth, transport configuration, endpoint groups, process topology, warmup, measurement interval, and CPU allocation. Preserve the additional NBSR admission/setup work and report it separately. First run Linux loopback controls, then the two-host matrix; never mix the two into one ceiling.

| Stage | Required cells and progression | Acceptance evidence |
| --- | --- | --- |
| Single-core and scaling | Direct/NBSR; 1 KiB and 16 KiB; physical 1/2/4 then available 8/16/32; separate SMT/unrestricted controls | CPU ns/op, ops/s, Gbit/s, Gbit/s/core, per-role CPU, latency, verified affinity |
| Stable capacity | Streams 1/2/4/8/16/32/64/128/256/512; 768/1024 only after stability; outstanding 1/2/4/8/16; geometric progression then midpoint refinement | Offered/achieved work, p50/p95/p99, queues and drain, per-thread CPU, context switches, runtime counters, errors/timeouts |
| Admission under load | Established traffic at 50/70/80% of this host/topology's strict-stable ceiling; clients 1/2/4/8/16/32/64/96/128/192/256/384/512; connections/client 1/2/4/8; target admissions 10/25/50/75/100/150/200 per second | Admission latency/success, pending clients, achieved rate, ownership cleanup; stop each branch independently at saturation |
| Memory/lifecycle | Rust-to-Rust then Go-to-Rust; separate connections/channels/streams 1/2/4/8/16/32/64/128; 192/256 only after stability; same-process cycles 10 smoke, 25 validation, 50 authoritative, 100 only after stability | Idle/active/cooldown RSS/PSS/private memory, allocator/GC, descriptors/sockets/tasks/threads, live ownership counters, retained-memory slopes |
| Soak | Both representative workloads 1 KiB/64 streams and 16 KiB/8 streams, using measured stable load limits: 10 min at 70%, 30 min at 80%, 60 min at 70%, then 120 min at 80% only after stable 60 min | Time series, drift, thermal/frequency state, resource plateau, errors/timeouts, drain and cleanup; PASS requires a stable 120-minute cell and a 60-minute second-workload cell |
| Wire | Matched Direct/NBSR setup and established intervals on dedicated physical interfaces, plus loopback control | Raw pcapng, capture filters/drop counters, TShark exports, application/QUIC counters, `ethtool -S`, IRQ/RSS, softnet drops, negotiated link speed |

Use at least 3 **valid** independent repeats per comparison cell, increasing to 5 if throughput CV exceeds 5%. Preserve every rejected run with its reason; replacement runs do not erase failures. After five, CV >5% cannot establish a strict-stable repeatable ceiling. Alternate Direct/NBSR order and record the full schedule. Use at least 3 seconds warmup and 20 seconds steady measurement for capacity cells; retain stage-specific longer windows and explicitly record them. Profiler/capture-on measurements require matched unprofiled controls and measured instrumentation overhead.

A strict-stable point requires zero errors/timeouts, cleanup PASS, p99 at most 1.25 times the same-workload lowest-load baseline, achieved/offered work at least 95%, bounded draining backlog, and CV at most 5%. A higher repeatable but latency-degraded point is not the strict-stable ceiling. Memory PASS additionally requires at least 64 simultaneous named resources, 50 same-process cycles, zero owned-resource residue and a bounded cooldown plateau; retained RSS alone is not a leak. A positive repeated cooldown staircase exceeding 64 KiB/cycle requires investigation and fails closure until explained or fixed.

Claim a measured saturation cause only with attribution: CPU at least 90% of allocated physical capacity, or NIC at least 85% of negotiated speed with queue/drop/IRQ evidence, or measured memory pressure/paging, or another demonstrated resource limit. State the scope and CPU accounting basis. Capture loss invalidates precise packet accounting; reduce load and retry, otherwise stop that branch. Preamble, FCS and inter-packet gap are not automatically present in pcaps; disclose offloads and report only observable layers. No physical-wire precision from loopback or derived UDP overhead.

## REQUIRED PORTING before campaign commands exist

| Existing implementation | Exact gap to close |
| --- | --- |
| `scripts/run_p2a_established.py`, `scripts/run_max_throughput_v2_stage6.py` and their stage dependencies | Windows affinity/topology (`performance/windows_affinity.py`, `profile_b2_v2.windows_processor_topology`), Windows resource collection and loopback authority/endpoints must gain Linux/two-host implementations. Stage 6's fixed NBSR groups/physical-vs-SMT cells are not the full external Direct/NBSR matrix. |
| Native Rust socket addressing | Default production `connect` and absent benchmark flags remain loopback-bound. Feature-gated `--benchmark-client-bind` and `--benchmark-listen` now have parser/TLS/actual loopback-alias socket evidence; see `external-native-bind-cbdca987`. The finite two-host runbook is authored and syntax-checked, not remotely executed. Native external-interface validation and complete portable orchestration remain outstanding. |
| `scripts/run_b4b_v2.py` and `run_b4b_mixed_connections.py` | Windows performance counters and process orchestration; current V2 client levels and one connection/client do not implement the full requested admission matrix. Add remote role ownership, explicit addresses, synchronized start/drain and verified offered-rate schedules. |
| `scripts/run_b3_session_lifecycle.py` | Imports `sample_windows_process`; environment explicitly says Windows loopback. Add Linux RSS/PSS/private mapping and FD/task counters with documented semantics, remote lifecycle barriers and same-process cleanup proofs. Windows private bytes and Linux RSS must not be treated as interchangeable. |
| `scripts/run_b5_sustained_capacity.py` | Reuses P2A build/measurement and loopback authority helpers; needs Linux telemetry/affinity and two-host sustained orchestration. Preserve B5 success/cleanup semantics and implement the near-ceiling progression above. |
| `scripts/run_b1_wire_overhead.py`, `run_b4_mixed_workload.py`, `capture_*.ps1` | Existing Windows paths/capture tooling and loopback assumptions require dedicated Linux interface selection, permission preflight, packet/drop accounting, offload disclosure and transport-counter correlation. PowerShell/WPR/ETW captures are not Linux commands. |
| `scripts/run_performance_validation.py`, `scripts/performance/resources.py` | Build helper has a platform-sensitive binary suffix, but resource sampling uses WinDLL/kernel32/psapi. A portable build helper does not make the measurement runner portable. Replace OS-specific collection behind tested equivalent accounting boundaries. |

Reuse existing Rust release peers (`perf_direct_peer`, `perf_rust_source`, `wp8_interop_server`) and Go peer only after Linux smoke verification. Read their actual argument parsing when assembling the port; do not assume a `--help` contract or invent a Linux runner name. Existing `--output`, duration and repeat flags do not remove their transitive Windows dependencies. Remote authority/address support must preserve approved issuer, service and endpoint binding; any closed-contract incompatibility is a blocker, not permission to weaken checks.

Required port acceptance: machine-readable expansion of the matrix above; schema/command-contract tests; Linux affinity/resource tests; matched Direct/NBSR smoke records; remote readiness/timeout/cleanup regression coverage; exact argv recorded for every role and collector; and verified analysis of a retained miniature evidence bundle. Until then no copy/paste full-campaign command is asserted.

## Evidence and final classification

Each future `evidence/performance/v2/server-linux-{start_sha_12}-{host_id}/` contains `environment.json`, `manifest.json`, `analysis.json`, `summary.md`, `raw/`, and `checksums.sha256`. Required manifest fields: schema version, run ID, source SHA/branch/dirty status, source and per-platform binary hashes, toolchains/build flags, host topology, cell definitions and IDs, commands, run order, UTC/monotonic timing, PID/start-time ownership, affinity observations, offered/completed counts, telemetry provenance, exclusions, rejected-run reasons, cleanup outcome and final status. Bind partner-host artifacts and time-sync uncertainty. Keep unavailable measurements null with reasons, never zero placeholders.

Retain raw JSON/CSV/NDJSON, stdout/stderr, control/profile pairs, perf data and stack exports, pcapng and drop reports, NIC snapshots and all derived-analysis inputs. Limit captures to declared test traffic; exclude private authority keys and credentials. After all artifacts are finalized, generate and verify checksums from the evidence root (the checksum file excludes itself):

```bash
(
  cd "$evidence"
  find . -type f ! -path './checksums.sha256' -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum > checksums.sha256
  sha256sum -c checksums.sha256
)
```

External status stays **NOT_RUN / EXTERNAL_HARDWARE_REQUIRED** until hardware is provisioned and the port is accepted. Executed failures remain FAIL or PARTIAL with their evidence. Passing the future definition/schema gate does not constitute server validation. Windows laptop/loopback results remain scoped to that environment; Linux/server, physical-NIC, NUMA, WAN and production claims require their own executed cells.
