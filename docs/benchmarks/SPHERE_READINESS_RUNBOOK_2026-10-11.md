# SPHERE readiness runbook — preparation only

Status: NOT_RUN / RESOURCES_NOT_RESERVED. This document creates no account,
reservation, credential, signature, infrastructure or network change. No build
or deployment was executed. It is outside the frozen publication candidate.

## October 17 client/server adaptation

The status above is the historical October 11 preparation checkpoint, not a
current assertion that the operator has no allocation. For the reported two-VM
SPHERE setup, use [the client/server operational handoff](SPHERE_CLIENT_SERVER_HANDOFF_2026-10-17.md).
It maps client to S and server to D, distinguishes reported smoke success from
validated logs, and retains independent endpoint containment/resource gates.
M may be external or co-located for functional diagnostics; co-location does
not execute the original separated M/S/D topology or establish capacity.
This report does not mark the original procedure executed. Read the newer
handoff before using the legacy raw coordinator commands below; they do not
implicitly acquire aggregate supervision. Archived publication records remain
unchanged. The later isolated KAR fixture described in AGENTS.md does not turn
this historical runbook into runtime registration acceptance.

The [SPHERE project](https://sphere-project.net/) describes a cybersecurity
research testbed with user-configurable resources. Its
[official documentation](https://docs.sphere-testbed.net/) is the source for
current access and facility procedures. The linked experimentation and policies
pages returned HTTP 404 during preparation. Exact reservation, acceptable-use
and release procedures therefore remain operator verification prerequisites;
no facility CLI command is assumed here.

## Scope and synthetic topology

Use three approved Linux nodes: M manages the experiment, S is the source peer,
and D is the destination peer. Management SSH connects M to S and D; benchmark
IPv4 UDP connects S to D over the allocated experiment network. M is not a data
relay or registration authority. No customer origin, production identity or
production traffic belongs in this experiment.

Use explicit verified SSH aliases and preconfigured trusted known-host entries.
The runners require noninteractive SSH and strict host-key checks. Replace all
documentation addresses and paths with verified allocation values; do not run
against the example 192.0.2.0/24 addresses. Routing and firewall access must
already be approved and configured. These steps do not authorize changing them.

## Readiness gates

Before execution, obtain explicit reservation/execution and disposable test-PKI
authority. Existing approved private TLS fixtures must be privately transferred,
kept outside evidence roots, and never exported with logs. All nodes need the
same clean reviewed source commit; current dirty laptop state is not a deployable
commit identity. Retain full source SHA, source/binary hashes, exact commands and
fixture identity. Keep compile-time fixture paths available on both peers.

Provisioned prerequisites are Linux, Git, taskset, Python and project dependencies,
Rust supporting edition 2024, Cargo and a C linker. The Go module currently
declares Go 1.26.5. Python metadata permits 3.12–3.14; the documented tested
range is narrower, so prefer provisioned 3.12/3.13 and record the actual version.
Missing tools/caches are blockers, not permission to download.

Record these read-only baselines on each node before and after the trial:

```sh
cat /etc/os-release
uname -a
lscpu -J
lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE
numactl --hardware
free -b
df -B1 .
rustc -Vv
cargo -V
go version
python3 --version
python3 -B -m scripts.performance.linux_network_inventory --interface VERIFIED_DATA_INTERFACE --output /absolute/new-network-inventory
```

Record missing tools/permission failures instead of installing or elevating.
NIC inventory is untimed and read-only; interface totals are not per-process
traffic. Record allocation, virtualization, CPU affinity, RAM/commit headroom,
disk free, NIC/link/MTU/offloads and competing load. All observed values currently
remain NOT_RUN. Do not infer exclusive physical cores from guest topology.

## Conditional cached build

Only after separate execution authorization, reuse verified Linux cache paths
and an external evidence directory. Do not copy Windows binaries/cache assumptions.
The following are build commands, not claims of successful execution:

```sh
export CARGO_TARGET_DIR=/absolute/verified-existing-linux-cache
cargo build --locked --offline --release --jobs 2 \
  --manifest-path crates/nbsr-transport/Cargo.toml \
  --features benchmark-harness \
  --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server
(cd interop/nbsr-go-peer && GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local \
  go build -mod=readonly -trimpath -p 2 \
  -o "$CARGO_TARGET_DIR/release/nbsr-go-peer" ./cmd/nbsr-go-peer)
```

Use the build evidence procedure in
[external Linux validation](EXTERNAL_LINUX_SERVER_VALIDATION.md), recording the
actual offline/job-limited argv above, toolchains, clean source identity and
binary hashes. Reject changed HEAD/dirty source rather than invent provenance.
Remove inherited benchmark NBSR environment overrides before measurement as that
procedure requires. A cache miss ends this preparation path.

The root Dockerfile builds the Python service image, not these Rust benchmark
binaries. It performs a pip installation and is not an offline native benchmark
image. Root Compose/bootstrap flows need separate credentials/infrastructure
authority. Do not substitute `docker compose up` for this topology. Existing
coordinator Docker transport is a fixture alternative, documented in the linked
coordinator guides; it requires existing owned containers and proves guest/lab
behavior only. No supported turnkey SPHERE container deployment is established.

## Bounded trial sequence

Use an operator-validated supervisor for every build/trial: at most two build
jobs, at least 8 GiB free disk at start, stop below 6 GiB or after 2 GiB growth,
and preserve at least 2 GiB RAM reserve on controller and peers. Bound each group
to 120 seconds including cleanup, initiate stop at 95–105 seconds, terminate only
owned process groups and independently verify remote reap/socket release.
Existing endpoint deadlines do not implement this aggregate resource supervisor;
collection adds time. If cleanup cannot fit, stop and retain the failure rather
than extending the deadline. Do not start before this prerequisite is satisfied.

First use a one/two-stream functional check, then an explicitly approved
16-client paired lifecycle check. Copy the exact configuration schema from
[finite coordinator](EXTERNAL_NATIVE_FINITE_COORDINATOR.md) or
[lifecycle coordinator](EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md), replacing only
verified environment values and declared workload parameters. Use fresh native
Linux output/lifecycle roots; lifecycle roots initially contain only `00/`.

```sh
python3 -B -m scripts.performance.linux_native_finite_run --config /absolute/finite-config.json --output /absolute/new-finite-output
python3 -B -m scripts.performance.linux_native_lifecycle_run --config /absolute/lifecycle-config.json --output /absolute/new-lifecycle-output --archive-collection
```

Run these sequentially under the supervisor, never as an unbounded batch.
Finite defaults are 3-second warmup/20-second issue, 16 KiB payload, depth one;
declare stream-count changes. Lifecycle's documented small profile is count 16,
rate 100, shards 2. Preserve explicit one-slot admission as the comparison control.
No larger connection count, live-bundle workload or long soak is authorized here.
For a later authorized finite comparison, use matched Direct/NBSR parameters,
counterbalanced order, three paired repeats and five when CV exceeds 5%; retain
all failed/unfavorable attempts. These are diagnostic integrity observations,
not sustainable throughput/capacity results.

## Evidence, stop and release

Retain configs, commands, build manifests, binary/source hashes, fixture identity,
limits, full result cardinality, failure markers, endpoint logs, management
transcripts, ownership counters, cleanup events and pre/post baselines. NBSR
post-close reporting must be explicitly enabled for the finite runner if claiming
its eleven ownership counters; process exit alone does not measure them. Direct
retains its process-exit scope.

Archive collection preserves both complete archives, inventories, transfer sizes,
durations and SHA-256 values; see
[archive collection](NATIVE_ARCHIVE_COLLECTION.md). Inspect selected entries,
avoid bulk extraction, and budget up to 512 MiB per role plus overhead. Keep live
outcomes separate from offline validation. Checksums are not remote attestation.
Export through an approved private channel after excluding keys, tokens, account
identifiers and unrelated node logs; any public derivative needs a fresh exact
allowlist and scan. Do not discard original evidence to sanitize it.

On completion or abort: stop only this invocation's processes, verify exact owned
PID identities are reaped and sockets released, record all counters or explicitly
UNCONFIRMED ownership, and retain failed cleanup. Do not replace missing readings
with zero. Verify export hashes before releasing nodes. Release only task-owned
allocations using the operator-verified SPHERE procedure and retain its receipt;
no release command or successful release is claimed by this document. Preserve
unrelated images, caches, volumes, containers and allocations.

## What a pass would establish

A lifecycle pass is functional controlled-pair admission/ownership evidence;
finite pair integrity is separate. Neither establishes WAN behavior, sustainable
capacity, production readiness or plug-and-play registration. Native external
hardware execution is still NOT_RUN. Full registration acceptance remains gated
by the [full-model acceptance matrix](../reviews/2026-10-11-registration-full-model-acceptance.md),
including applicable controller/normal/emergency governance, provenance, real
timers/revocation and durable runtime integration. The proposed composed-positive
KAR signature remains unapproved and ungenerated. This runbook does not supply
those authorities or change frozen protocol contracts.
