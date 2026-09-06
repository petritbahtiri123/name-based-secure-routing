# Linux single-core finite reference

Implementation and synthetic verification only. Linux CLI execution is **NOT_RUN**;
external dedicated/server hardware remains **EXTERNAL_HARDWARE_REQUIRED**.
This stage prepares a checksum-bound finite reference for a later Linux B5 backend.
It does not implement that backend or qualify sustained capacity.

The workload uses one selected logical CPU from one physical core, shared by the
source and destination; one endpoint group; one runtime worker per process;
1024 or 16384 payload bytes; 1–64 streams; and ordered distinct depths selected
from 1, 2, 4, 8, 16, beginning with 1. Direct and NBSR use the existing unpaced
request/response workload. Three valid repeats are required per path/depth, with
both paths extended to five when either path's throughput CV exceeds 5% after
three. Every invalid attempt is retained and aborts the campaign. Five dispersed
repeats do not automatically qualify: the existing strict depth classifier still
applies its unchanged latency, repeatability, throughput and cleanup gates.

## Prerequisites and finite command

Use a clean accepted checkout, Python 3.11 or newer with `cryptography`, Linux
`taskset` and `lscpu`, readable same-UID `/proc` process identity/CPU/affinity/FD/task
telemetry, and readable cgroup-v2 `cpu.max`, `cpuset.cpus.effective`, `memory.max`
and `pids.max`. CPU quota must permit at least one CPU. The inherited CPU pool
must expose a valid physical-core topology. Affinity is applied by `taskset`
before either binary starts; the controller verifies actual process affinity.
Container topology and quotas describe the guest/cgroup, not dedicated hardware.

Provide executable Linux release `benchmark-harness` binaries named
`perf_direct_peer`, `perf_rust_source` and `wp8_interop_server`. Their build manifest
must record `source_sha` equal to this clean checkout's full HEAD SHA,
`build_profile: "release"`, nonempty `build_commands` and `toolchains`, and a
`binary_sha256` object keyed by those exact three filenames. The runner verifies
actual bytes and retains copies. The old 3644c324 compatibility image cannot
qualify as a current-source reference. This command builds and installs nothing.

From the checkout, with actual absolute paths supplied:

```sh
python -m scripts.performance.linux_b5_reference \
  --binaries /absolute/immutable-linux-binaries \
  --build-manifest /absolute/build-manifest.json \
  --output /absolute/new-reference-output \
  --payload-bytes 16384 --streams 1 --depths 1 2 4 \
  --warmup 3 --duration 30
```

The output must be fresh and outside the checkout. Authority fixtures use the
existing ephemeral loopback helper and are removed after the campaign. TLS peer
names, authority, wire and ACCEPT behavior are unchanged. There are no new
timeouts or offered-rate adjustments. Source final CPU sampling, successful
process join, exact workload final validation and requested source 11-counter
cleanup validation precede completion ACK. Both process exits and both NBSR
11-counter reports are required before a repeat is valid. Direct reports only
process cleanup; its runtime ownership remains NOT_MEASURED.

## Load a matched 70–80% target

The strict loader verifies all indexed bytes, retained controller source against
the current files, current clean reference SHA, actual binary hashes, matching
shape and Linux placement/kernel/cgroup identity, raw source finals, both joins,
NBSR cleanup reports, and freshly recomputed strict classifications. It derives
an exact rational rate from the selected NBSR cell's median operations/time.
Run this in the same accepted checkout and intended Linux environment, replacing
the paths and shape with the finite campaign's values:

```python
import json
from pathlib import Path
from scripts.performance.linux_b5_ceiling import NAMES, current_environment, load_reference
from scripts.performance.linux_b5_reference import git_state
from scripts.performance.linux_loopback import digest

sha, status = git_state()
if status:
    raise RuntimeError("clean current checkout required")
binaries = Path("/absolute/immutable-linux-binaries")
target = load_reference(
    Path("/absolute/reference-output"), current_sha=sha,
    binary_sha256={role: digest(binaries / name) for role, name in NAMES.items()},
    shape=dict(physical_cores=1, endpoint_groups=1, runtime_workers=1,
               payload_bytes=16384, streams_per_group=1),
    linux_environment=current_environment(), percent=75, depth=1,
)
print(json.dumps(target, indent=2))
```

The returned observer qualification is always
`NOT_QUALIFIED_NO_MATCHED_COMPARISON`. A finite target does not establish paced
feasibility or a production maximum. The Linux B5 runtime backend must separately
validate achieved/offered pacing, bounded live resource and ownership coverage,
unchanged growth/drift/error guards, and a matched observer-cost comparison
before a long-soak qualification can be made.

## Evidence and remaining boundaries

`environment.json` binds workload, source, binary execution paths, topology,
selected CPU, kernel, cgroup limits and observer state. `source/`, `binaries/`
and `build-manifest.json` preserve exact inputs; `records.json`, `analysis.json`
and `raw/` preserve commands, stdout/stderr, resource NDJSON, ACKs and cleanup
reports. `checksums.sha256` indexes actual retained bytes on success or failure.
Source, executable bytes and environment are checked before each cell and again
before publishing a successful campaign. CPU totals explicitly cover the whole
process lifetime including startup, warmup and drain; there is no steady CPU
ns/op claim. This observer does not sample Windows private commit or Linux
private-resident memory, so no memory-growth claim is made by the finite stage.

Multicore/grouped references, the Linux B5 live controller backend and two-host
NIC workloads are separate unimplemented stages. Native two-host bind support
does not make this loopback controller a remote workload orchestrator.
