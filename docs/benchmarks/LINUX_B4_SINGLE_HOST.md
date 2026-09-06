# Linux B4 single-host admission ladder

AUTHORED / LIVE VALIDATION PENDING. This definition preserves Task4i's finite
512-client batch, one connection per client, one or two source runtime shards,
the existing offered-rate ladder, established eight-stream 1 KiB forwarding for
30 seconds, two-second warmup, all existing deadlines, repeat/CV rules and
classification thresholds. It does not reuse B3's serial-accept scheduler.
Windows entry points retain their default Windows backend.

Use a clean native Linux checkout at the same full source SHA as the binaries.
Keep the build checkout and its vectors at their original compile-time paths.
Build separately before the quiet measurement slot; the Linux runner never
invokes Cargo. Example preparation from the clean checkout:

```bash
set -euo pipefail
export CARGO_TARGET_DIR=/srv/nbsr-build/b4-REVIEWED_SHA
mkdir -p "$CARGO_TARGET_DIR"
cargo build --release --locked --manifest-path crates/nbsr-transport/Cargo.toml \
  --features benchmark-harness --bin perf_rust_source --bin wp8_interop_server \
  > "$CARGO_TARGET_DIR/build.stdout" 2> "$CARGO_TARGET_DIR/build.stderr"
python - <<'PY'
import hashlib,json,os,pathlib,subprocess
p=pathlib.Path(os.environ['CARGO_TARGET_DIR'])
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'])
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
value=dict(source_sha=sha,build_profile='release',
    build_commands=['cargo build --release --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source --bin wp8_interop_server'],
    toolchains={tool:subprocess.check_output([tool,'--version'],text=True).strip() for tool in ['rustc','cargo','python']},
    binary_sha256={name:hashlib.sha256((p/'release'/name).read_bytes()).hexdigest() for name in ['perf_rust_source','wp8_interop_server']})
with (p/'build-manifest.json').open('x') as f: json.dump(value,f,indent=2)
PY
```

Install the existing pinned project Python dependencies outside timing. Once
the parent/operator has provided a quiet slot, run from that same checkout:

```bash
python scripts/run_b4b_linux.py \
  --target "$CARGO_TARGET_DIR" --build-manifest "$CARGO_TARGET_DIR/build-manifest.json" \
  --output /srv/nbsr-evidence/b4-linux-REVIEWED_SHA-NEW_RUN \
  --cores 1 --source-shards 1
```

Use a different output for two shards or another core count. The optional
`--offered-rates` accepts only positive, distinct, increasing integers, exactly
as Task4i does. Do not pool different placement/shard/rate definitions or call a
short diagnostic an accepted full ladder. Invalid attempts remain recorded and
cannot qualify a short repeat cell. No failed attempt is silently replaced.

`taskset` and `lscpu` must be available. The shared B3 Linux topology helper
selects one allowed logical CPU from each requested physical core. Every owned
peer receives the same explicit CPU pool before program execution; observed
thread affinity and PID/start identity must match. Original immutable executable
paths are used, with copied evidence binaries and pre-cell hash checks. A build
source mismatch or dirty controller checkout fails rather than becoming PASS.

Process samples retain Linux RSS, PSS, private resident bytes, separate private
hugetlb, file-descriptor count and threads. They are not Windows private commit,
working-set or handle aliases. Live permission/read failures reject the run.
Zombie unavailable values remain null; CPU totals cover sampled process
intervals and may omit startup/terminal fragments. Round aggregate memory peaks
combine sequential reads, not atomic snapshots. Role coverage is mandatory.

Host telemetry uses bounded `/proc/stat` and `/proc/meminfo` snapshots at the
existing runner sampling points, at most once per second. Raw CPU jiffies include
IRQ/softirq/steal/iowait, plus system context switches, runnable tasks and memory
total/available. Linux iowait can decrease and is not treated as a monotonic
process CPU counter. These fields do not imply Windows processor queue or commit
semantics, effective clocks, thermal behavior or unrelated-process attribution.
Host samples are whole-host observations, not cgroup-normalized capacity.
The [Linux kernel proc documentation](https://docs.kernel.org/filesystems/proc.html)
defines CPU counter units as USER_HZ and `procs_running` as running or runnable
threads (the retained key is `runnable_tasks`). It also cautions that iowait can
decrease and is unreliable for busy-time attribution. Private_Hugetlb is excluded
from RSS/PSS and the private clean/dirty sum, so it remains a separate metric.

Linux smaps/process sampling observer cost is NOT_QUALIFIED. A controller STABLE
classification alone does not establish a hardware or production ceiling;
matched observer qualification and separately scoped capacity evidence remain
required. Pre-cell Git/hash verification is outside the reported observation
interval.

Non-Windows Rust shard thread IDs remain zero, so per-shard CPU is explicitly
NOT_MEASURED. Aggregate admission-source CPU is still sampled. This patch does
not modify Rust, authentication, wire behavior, credits or timeout values.

Terminal checks remain exact source acknowledgment/failure marker conservation
and the existing destination cleanup gauges/process completion. They are not a
new proof of all source runtime ownership counters. On exceptional exit, raw
Linux samples and established-peer pipes are retained after owned-child cleanup;
top-level failure metadata and checksums preserve partial evidence.

The output contains source captures/hashes, declared build metadata, exact input
manifest bytes/hash, original/retained binary paths, placement/cgroup provenance,
per-repeat records and raw telemetry. A completed STABLE/SATURATED classification
is scoped to this local Linux definition. Native two-host marker transport,
distributed process ownership and clock coordination remain unimplemented;
Docker/VM results establish neither external hardware nor a server ceiling.
