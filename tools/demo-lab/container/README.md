# Mac host / Linux container packaging

Status: packaging source only; no Docker build, pull, run, Intel Mac acceptance,
or Apple Silicon acceptance has been performed. This does not enable native macOS
backend execution. The existing Linux sealed executable implementation is unchanged.

## Required reviewed inputs

Reviewed official metadata is recorded in [official-image-pins.json](official-image-pins.json):
Go 1.26.5-bookworm, Rust 1.97.1-bookworm, and Python 3.13-bookworm. Each record
includes the official multiarchitecture reference, Linux amd64/arm64 child
digests, registry metadata URL and observation time. Preparation must supply
exactly those recorded references; the recipe rejects reference, version, release,
or architecture metadata drift. No mutable tags or invented digest defaults.

These are matching Debian Bookworm image families. Metadata verification does
not establish that the copied Rust toolchain and full Python image have compatible
libraries or complete compiler requirements. The recipe checks cc and exact tool
versions and installs no apt packages. If a prerequisite fails, preserve the
failure and review a new pinned input; do not add an unversioned apt install.

**Remaining gaps:** no image has been pulled or executed for this packaging task;
Debian/library compatibility, native architecture behavior and dependency cache
completeness remain untested. Host preflight must enforce the host-native platform;
an in-container machine check alone cannot detect transparent emulation.
The known local nbsr-go-linux-check-cache digest is not an execution-trust decision
and is not selected or executed by these recipes.

## Explicit preparation and offline build

Create a clean allowlisted source export, including all three Go modules, Rust
crate and lock, vectors, and tools/demo-lab. Never send private keys, runtime
artifacts, evidence archives, .git, or unrelated untracked work as Docker context.
The Dockerfile-specific ignore files provide secondary exclusions, not an export
policy. Preserve source commit plus the dirty source inventory separately.

Preparation is a separately authorized network operation using
Prepare.Dockerfile with GO_IMAGE, RUST_IMAGE, PYTHON_IMAGE and TARGETARCH. It copies
the pinned Go/Rust toolchains into the reviewed Python base, verifies versions
and compiler presence, then fetches Go dependencies and cargo fetch --locked.
It neither installs host tools nor runs NBSR. Capture the prepared image's
immutable repository digest after export to an approved local registry/store;
do not push to a remote registry without explicit authorization.

Offline assembly uses Dockerfile with BASE_IMAGE set to that reviewed prepared
name@sha256 digest, SOURCE_SHA set to the exact commit, and TARGETARCH. Require
the base locally available; invoke Docker build with --pull=false --network=none
and the explicit native --platform. A missing image or cache is a failure, never
permission for an automatic pull or network retry. Docker may still resolve FROM
metadata independently of RUN networking, so host orchestration must check the
local digest before invocation and enforce the no-download policy.

Build subprocesses use the existing guarded supervisor: 95-second stage deadline,
two jobs, at least 8 GiB free, stop below 6 GiB or after 2 GiB growth. Host
orchestration must additionally supervise the Docker build/container lifecycle;
terminating the CLI does not prove the daemon stopped its owned work. Retain failed
build logs. A cold build exceeding bounds needs a reviewed incremental preparation
plan, not a silently increased timeout.

## Image contract

- /src: reviewed source, including Rust compile-time vector paths.
- /opt/nbsr-build/nbsr-demo/image: immutable binaries named authority, client,
  backend, fixturegen, destination, test-client, test-corestate, test-resolution.
- /opt/nbsr-image/build.json: source inventory, artifact hashes and toolchain data,
  compatible with the Demo Lab build manifest.
- /opt/nbsr-image/container.json: base digest and execution architecture.
- /opt/nbsr-cache/cargo-target: prepared build cache; never host benchmark cache.
- /src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime: private runtime.
- /artifacts: the sole private host-shared receipt directory; contains the fixed
  input request and bounded output. Only a separate read-only identity snapshot mounts at /source; no Docker socket or host home mount.

The integration worker copies verified image artifacts to the selected run's
/opt/nbsr-build/nbsr-demo/<run-id> and marks files read-only before use. The runtime
and build root run IDs must match. It must not use the static image directory as
an arbitrary per-run authority root.

The fixed /opt/nbsr/demo-container-worker accepts one scenario, validates NBSR_DEMO_RUN_ID, and execs baked /src/tools/demo-lab/demo.py _container-worker --scenario. Host source identity snapshots mount /source read-only and are never executable imports.
Proposed owned execution flags (placeholders are not shell-ready commands):

    docker create --name <unique-owned-name> --label nbsr.demo.owner=<ownership-token>
      --env NBSR_DEMO_RUN_ID=<demo-32hex-id>
      --platform linux/<native-arch> --network none --read-only --user 65532:65532
      --cap-drop ALL --security-opt no-new-privileges:true
      --cpus 2 --memory 1g --pids-limit 128
      --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777
      --tmpfs /opt/nbsr-build/nbsr-demo/<run-id>:rw,nosuid,nodev,size=256m,uid=65532,gid=65532,mode=700
      --tmpfs /src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime:rw,noexec,nosuid,nodev,size=64m,uid=65532,gid=65532,mode=700
      --mount type=bind,src=<private-source-snapshot>,dst=/source,readonly
      --mount type=bind,src=<fresh-private-receipts>,dst=/artifacts
      <verified-local-image-id> <allowlisted-scenario>

IMPORTANT: mounting the entire build parent hides the image binaries at its image
child. Before using that mount strategy, integration must copy immutable image
binaries from a separate preserved image location or mount only the exact
per-run child path. Prefer an exact /opt/nbsr-build/nbsr-demo/<run-id> tmpfs.
No ports, privileged mode, host network, or socket mount. Mount bounds are proposed
limits, not measured acceptance. The receipt directory must be preprovisioned
private and writable by the container UID; failure must not trigger chmod 777.

Register the returned container ID, start it under the independent host watchdog,
and inspect/stop/remove only that ID. Do not use --rm before recording final
state. Docker unreachability is cleanup UNCONFIRMED and blocks another scenario.
No global prune. Offline receipt verification requires neither Docker nor browser.

## Bounded clean source export

From a verified checkout, run the read-only-source exporter explicitly:

    python3 tools/demo-lab/container/export_context.py --repo <absolute-checkout> --output <fresh-private-context>

The exporter asks git ls-files --stage for the six allowlisted source roots and
reads the current files, preserving dirty content rather than silently exporting
HEAD. Only the enumerated change-owned Demo Lab files and launcher wrappers may
be included when still untracked. Other untracked files are not traversed.
It excludes runtime, credential, archive and build directories plus private-key
formats. Committed CBOR/COSE/binary vectors are public fixture source, not generated
transport keys. Symlinks/reparse paths, conflicted index entries, absent selected
source, files above 8 MiB, more than 10,000 files or total source above 128 MiB
fail closed. Output must be fresh and disjoint from the checkout.

source-export.json records the exact commit, all file SHA-256 hashes/sizes and
the Demo Lab source inventory. The command also returns the manifest SHA-256.
Missing sparse source is a failure; no fetch, restore, checkout, or sparse
settings changes occur. Source is rechecked after copying. Failed exports are
retained without a success manifest and must never become build contexts.
This manifest identifies content; it is not a signature or a guarantee that a
writable snapshot cannot later change. Recheck it immediately before consuming.

Recommended next orchestration step: use a digest-verified prepared image in an
explicitly named, labelled container with a copied source snapshot at /src and
owned cache/output mounts. Run the bounded offline build as that registered
container's workload; the host watchdog can inspect and stop its recorded ID.
Only package the validated output into a final image after completion. This is
more controllable than assuming killing docker build kills a daemon build.
Do not implement an unsupervised docker build convenience command. Preserve
failed output and daemon uncertainty; no image pull or daemon operation is
authorized by running export_context.py.