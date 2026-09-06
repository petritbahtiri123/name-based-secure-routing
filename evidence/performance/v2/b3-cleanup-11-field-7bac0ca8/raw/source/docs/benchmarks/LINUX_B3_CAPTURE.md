# Linux B3 capture and analysis

Status: backend/orchestration compatibility PASS against the retained older Rust
image; run_b3_v2 CLI live remains NOT_RUN. This is an explicit Linux backend for
the existing Rust same-process B3 workload, not a two-host controller.

The Windows default and its private-commit/working-set analysis are unchanged.
Linux commands use `taskset` before either process starts, on one logical CPU per
selected physical core within one NUMA node and the inherited allowed set. Every
capture rechecks observed thread affinity, process identity/start time, CPU/time
continuity and required live memory. Missing live samples abort before the next
active/report release. Source process counts and identities remain fixed for the
whole cell, including all same-process cycles. The original lifecycle source
plan, marker barriers, report gate and deadlines remain. A later raw audit found
the inherited cleanup gate covered eight fields; the separate Rust-only
[cleanup correction](B3_CLEANUP_11_FIELD_REPAIR.md) requires all eleven fields.
Simultaneous bundle sources legitimately return after their coordinator drains.
Only final bundle cooldown, after all ACKs and destination report-ready, permits
that clean source exit: memory/CPU aggregates become null with explicit
`UNAVAILABLE_EXPECTED_EXIT`, retaining PID/start identity and last-live evidence.
Idle/active phases, destination sampling and same-process cycles stay strict.

Linux rows contain per-process readings and exact per-role sums of CPU, RSS, PSS,
private-resident, separate private-hugetlb, FD and thread counts. They never contain
Windows metric aliases. Raw phase rows are bounded per cell; failed prefixes are
retained by the existing failure record. Observations across processes are
sequential; aggregate timestamp is the latest constituent sample timestamp.

Example commands for a prepared Linux host (paths are explicit prerequisites):

```sh
python -m scripts.run_b3_v2 --platform linux --cores 1 \
  --target /opt/nbsr-build --build-manifest /evidence/build-manifest.json \
  --axis streams --counts 8 16 --fixed-channels 8 --materialized-streams \
  --repeats 3 --output /evidence/b3-streams
python -m scripts.performance.b3_linux_analysis /evidence/b3-streams \
  --output /evidence/b3-streams-analysis.json
```

`--target` must contain executable release/perf_rust_source and
release/wp8_interop_server. Linux executes these original verified inputs and
retains exact-byte copies under output/binaries; output need not allow execution.
Keep original inputs immutable during execution. The JSON build manifest requires
`source_sha` (40 lowercase hex), `build_profile: "release"`, `build_commands`,
`toolchains`, and `binary_sha256` keyed by executable basename. Actual binary bytes
must match. Source SHA is declared build provenance, not inferred from binary
bytes. `environment.json` records current controller SHA separately; differing
build/current SHAs force `DIAGNOSTIC_BINARY_SOURCE_MISMATCH`, regardless of repeat
count. An older image cannot prove current Rust behavior or measured acceptance.

The Linux analyzer rejects mixed platform/residency/resource scope, incomplete
phase/count/identity evidence, and scale rows with failed cleanup. It reports
private-resident medians/slopes separately from RSS/PSS/hugetlb and FD counts;
memory cause remains INCONCLUSIVE. Scale repeat gates require at least3 valid
repeats, or5 when CV exceeds5%. Re-run with5 in a fresh directory when required;
do not pool duplicate repeat names. Same-process cycle summaries require active
and cooldown coverage for each cycle and one process per role throughout.
Before pooling roots, the analyzer verifies every input checksum and required
binary/controller/source files, then requires matching controller/build SHA and
hashes, topology, inherited/selected CPU pool, platform tools, cgroup limit
observations and memory scope. Output retains input index/environment/records/build
hashes and diagnostic classifications. An older-image diagnostic never becomes a
current-source measurement through analysis or pooling.

Linux kernel/tool versions, lscpu topology, inherited/selected CPUs, cgroup and
mount descriptions, and available cgroup-v2 limit observations are retained.
Unavailable cgroup files are marked explicitly. These describe a guest/container
environment; they do not establish bare-metal placement, dedicated hardware,
thermal/power behavior, allocator attribution or external NIC performance.

Canonical implementation/test evidence: `evidence/performance/v2/linux-b3-capture-dc4de434/`.
Parent review and scoped rereview PASS; that implementation package predates the
separate Docker compatibility evidence below.

Subsequent compatibility: twelve retained current-controller/older-binary Docker
run_cell/backend runs PASS, with CLI live still NOT_RUN. See
`evidence/performance/v2/linux-b3-compatibility-1cca67ad/`; it preserves the failed
first evidence-capture attempt, diagnostic SHA mismatch and original eight-field
controller records plus independent eleven-field raw validation.
