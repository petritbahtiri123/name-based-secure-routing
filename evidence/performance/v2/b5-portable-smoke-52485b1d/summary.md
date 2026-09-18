# Native Linux B5 placement validation

Status: portable diagnostic runner; native/server execution NOT_RUN.
This is a bounded follow-up to the retained WSL placement experiment, not a full
external matrix executor or an accepted sustained benchmark.

## Prerequisites

Use a clean checkout at a reviewed full SHA containing
`scripts/performance/linux_b5_placement.py`, an exact-SHA release build and its
immutable build manifest. Keep build-time fixture paths present. The existing
build/environment instructions are in `EXTERNAL_NATIVE_TWO_HOST_RUNBOOK.md` and
`EXTERNAL_LINUX_SERVER_VALIDATION.md`. No SSH or remote access is required by this
single-host loopback diagnostic. Do not infer physical NIC performance from it.

Requires Linux procfs/smaps, cgroup v2 with readable limits, taskset, lscpu,
Python and the existing pinned authority-helper dependencies. At least two
distinct topology-reported cores must be available, with CPU quota for both.
Use one logical CPU per reported core; the helper rejects unavailable topology.
Prefer a dedicated native host, at least 16 GiB RAM and 100 GiB free evidence
space per the server matrix. Record distribution/kernel, CPU model/topology,
virtualization, RAM, power/thermal policy and other workload activity before
timing. A VM result remains a VM result even when topology reports distinct cores.

Run as the ordinary benchmark user with permission to read its own procfs data.
No root, capabilities, firewall/sysctl changes or reduced security settings are
part of this command. Remove inherited `NBSR_*` experimental settings explicitly;
the wrapper refuses them rather than silently changing their values. Output must
be a fresh path outside the source checkout. Build before timing, never alongside
the experiment. Preserve failed outputs and never reuse their directory.

## Exact diagnostic workload

Substitute only the three absolute artifact paths below. The rational rate
reproduces the historical offered workload; it is deliberately NOT a native
capacity calibration. Source and destination use the same release binaries in
both placement arms, 16 KiB payload, eight streams, depth one, one worker per
peer, three-second warmup and 300 seconds of measurement.

```bash
python3 -B -m scripts.performance.linux_b5_placement \
  --binaries /absolute/immutable-linux-binaries \
  --build-manifest /absolute/build-manifest.json \
  --output /absolute/new-native-b5-placement-output \
  --rate 64804600000000 7500349701 \
  --path nbsr --payload 16384 --streams 8 --depth 1 \
  --warmup 3 --duration 300 --progress 30
```

The wrapper executes three counterbalanced shared/split pairs, extending both
arms to five if the first-three goodput or median-window-p99 CV exceeds 5%.
Expected traffic time is 30 or 50 minutes plus startup/cleanup. It retains
performance gate failures as FAIL_DIAGNOSTIC_RETAINED. Invalid data, process or
ownership cleanup failure, unexpected controller exceptions, and source/build/
environment changes stop the cohort without replacement. No threshold or timeout
is increased. Repeating the same experiment with `--path direct` in a separate
fresh output supports a Direct placement diagnostic with identical offered
workload; the separate invocations do not constitute a counterbalanced
Direct-versus-NBSR capacity comparison.

Each underlying cell records commands, per-thread affinity, source/build hashes,
resource samples, ownership where available, latency windows and final cleanup.
NBSR has eleven-counter ownership evidence; Direct has process joins, not those
NBSR counters. Shared allocates one selected CPU total; split allocates two,
one per peer. Compare summed CPU and CPU/work along with latency before claiming
efficiency. CPU selection inside a guest does not establish host-core isolation.

## Evidence and interpretation

The root contains environment/source identity, the executed controller, records,
summary or failure, and a recursive SHA-256 index including child indexes. Each
`shared-rN` / `split-rN` directory is an unmodified B5 diagnostic evidence root.
Record the root index hash separately:

```bash
sha256sum /absolute/new-native-b5-placement-output/checksums.sha256
cd /absolute/new-native-b5-placement-output
sha256sum --check checksums.sha256
```

Exit zero means the diagnostic collection completed, not that stability passed.
Inspect `failed_gate_runs`, dispersion and every cell's gate failures. Never merge
independent runs into a continuous soak. A successful comparison alone does not
qualify the observer, calibrate native capacity, prove a bottleneck, eliminate a
leak, or close the 60-minute B5 gate. Follow-up profiling must separately satisfy
matched observer-impact gates. The full wire/multihost/server matrix remains a
separate unfinished definition; this command does not claim to implement it.

## Portable runner verification

At 52485b1d, a Docker/WSL integration smoke exercised all ten shared/split cells
after the CV rule expanded three to five pairs. Its deliberately short 15-second,
1000 offered-op/s workload verifies mechanics only; it does not replace the
five-minute fixed-rate experiment. All cells completed without errors/timeouts,
both NBSR peers' final eleven counters were zero, and the runner retained its
unresolved p99 dispersion as NOT_PROVEN sustained stability. No native/server
result follows from this compatibility check.

Literal RED covered the absent paired driver and nested-index sealing; 83 focused
Python tests subsequently passed. These include performance-failure retention,
no replacement after correctness/cleanup failure, sticky five repeats, repeat
identity, unexpected controller exception rejection and nested checksum coverage.
Ruff passed. The exact-SHA release build reproduced all three earlier binary
hashes. Evidence: `evidence/performance/v2/b5-portable-smoke-52485b1d`, with raw
under `C:/NBSR-build/b5-portable-smoke-52485b1d`.
