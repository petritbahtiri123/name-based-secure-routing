# Windows Docker provisioning preparation and proposed rehearsal

## Result and scope

Implemented `scripts/performance/windows_docker_provisioning.py` in the isolated
handoff, with25 deterministic checks in its matching performance test suite.
Final scoped run:160 passed in3.20s pytest/4.42s supervised; Ruff passed.
Independent review found two compatibility gaps (unattached prestart network ID
and typed Docker absence diagnostics); regression tests reproduced them and the
reviewer confirmed the corrections. Native compatibility is NOT_RUN.

No Docker/native process operation, network trial, build, download, credential
generation/read/copy/mount, signing, commit, push or settings change occurred.
The original dirty source checkout was preserved. Its additive evidence bundle
contains the exact source patch, dependency hashes and retained test failures.

## Concrete behavior

`DockerProvisioner` creates a campaign-labelled internal bridge and two fixed-role
containers using a pinned local image ID and `--pull=never`. It records full returned
IDs before rejecting late results; creation ambiguity permanently blocks replacement.
Known created IDs remain cleanup-addressable even when subsequent inspect/start
fails. Creation failure remains a failure after cleanup; no successful-cell claim
is manufactured. An unknown creation requires reconciliation of retained command
evidence and attempted names; it does not authorize deleting by name or broad prune.

Inspect checks exact image/labels/user, private namespaces, limits, readonly root,
all capabilities dropped, no-new-privileges, no published ports, exact mounts and
one exact attached network/address after startup. Prestart allows empty attachment
fields but still requires the configured full network ID. Exact-ID `rm --force`
is followed by a fresh inspect. Only recognized missing-container diagnostics
bound to that full ID establish absence; daemon/permission errors do not. Network
release requires all known endpoints independently absent and empty membership.

`DockerCommand` runs the host CLI through a suspended-then-assigned WindowsOwner,
using the existing kill-on-close Job Object backend. Each command receives at most
8 seconds including child cleanup; timeout remains failure. The helper writes
scoped raw stdout/stderr and a request-hash-bound reply. Failed handle release
retains ownership. CLI completion cannot prove that daemon-side effects stopped.
No Docker socket is mounted or delegated, and no management container is created.

The existing `BudgetedEngine`, `WindowsWorkload`, `Sequence`, finite coordinator,
telemetry validation and disposal receipts remain the orchestration path. A composed
offline test performs normal/interrupted/fresh cells with six distinct exact IDs.
Its workload outcomes are simulated, not QUIC evidence. The live workload already
uses the finite coordinator and validates positive progress before deliberate
management cancellation; this is a safe-point interruption, not a hard crash.

## Retained validation

The original13 tests failed because the adapter was absent, then passed. Boundary
development retained6 failures/14 passes (prestart shape, late identity retention,
missing concrete command transport), then20 passed. Review regression retained
3 failures/1 pass/18 deselected (network ID, typed absence, nonexistent intermediate
output parent). Final160 passed includes25 new and135 neighboring tests. An initial
Ruff run found15 one-line-statement errors in the new tests; formatting corrected
them and the retained final supervised Ruff run passed.

Final test disk:13944516608 bytes free; available RAM7064518656 bytes. All supervised
children were reaped, no resource abort. Python3.14.6 is a focused permitted-version
result, not a full tested-version matrix. No containers were created by this slice.
The earlier135 Windows-management result is historical, not this run's count.

Exact final command is retained in `docker-provision-final.json`: provisioning,
Windows-management/Job-backend, disposal/sequence, finite-run, watchdog and
cleanup-failure suites, `-B -q -p no:cacheprovider`, and a fresh test-owned basetemp.
No repository-wide suite was run; repository instructions require affected checks.

## Targeted inventory

| Known location | Verified finding |
|---|---|
| `Temp/nbsr-kar-positive-20261012` | Hidden `.git` exists; branch `kar-positive-local`, unborn HEAD, zero tracked files. Source-manifest baseline ad77d59754651fee449bb1d9c14a946f9f3b2d15 is not the current dirty source identity. No root/crate target directory. |
| `Temp/nbsr-publication-validation-20261011` | HEAD020ed2d0e73f12a2d56c253045c02ef112aa05f9, branchci-validation,389 dirty status entries. No root/crate target directory. |
| Original NBSR checkout | HEADc7abbc4423a9ad05cea9cdf6678c231a34cafd59, branchcodex/nbsr-v3-wp0-wp1,199 dirty status entries. Preserve all work. |
| `Documents/Codex/2026-10-04/task/nbsr-handshake-target` | Debug/tmp/metadata only; no release directory. Retained metadata:Rust1.97.1, x86_64-pc-windows-msvc. Not a Linux cache. |
| Known handoff/performance metadata | No usable Linux release manifest or exact retained public TLS set located. This does not claim absence elsewhere. |

Correction to the initial inventory: the isolated checkout does have `.git`; it is
hidden and unborn. It is not a clean deployable source tree. No private-key content
was inspected or hashed. Actual certificate fingerprints and current validity are
unknown. `authority.py` is only a recipe: random P-256 credentials, source.edge and
destination.edge SANs, generation minus1 minute through plus1 day; no CA key file.

## Single proposed approval bundle — NOT AUTHORIZED / NOT RUN

This is the shortest next path to the existing two-stream diagnostic. Approval
must cover the whole bounded local preparation/rehearsal below. No additional
offline model is proposed. Missing prerequisites stop the attempt; they do not
trigger downloads, privilege changes or validator bypass.

1. **Exact inputs and native preflight.** Select one reviewed clean Linux-runnable
   source revision containing the required peer scripts and compile-time fixtures.
   The current unborn/dirty materializations cannot satisfy that gate. If making a
   clean local Git snapshot is necessary, authorize that exact reviewed tree and
   local unsigned commit separately within this bundle; no push/publication. Record
   source tree/patch and build hashes. Inspect the existing Docker executable,
   context, cached image ID, Python/dependencies, git/taskset and Linux cache/toolchain
   metadata without pulling or altering them. Confirm source ownership allows the
   non-root peer's clean Git check; do not change global safe.directory settings.
   Validate Windows Job containment with one bounded owned helper/descendant case
   before relying on it. Failure stops transport preparation.

2. **Minimal conditional build.** Prefer existing manifest-bound Linux release
   artifacts if located. Otherwise authorize exactly one cached, locked offline
   release build, max2 jobs, of `perf_direct_peer`, `perf_rust_source` and
   `wp8_interop_server` with `benchmark-harness`. Set CARGO_TARGET_DIR to an explicitly
   verified existing Linux cache. No matching cache is currently established.
   Command: `cargo build --locked --offline --release --jobs 2 --manifest-path
   crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_direct_peer
   --bin perf_rust_source --bin wp8_interop_server`. Supervise120s including cleanup,
   stop work by95s. Cache miss, time budget or resource limit stops; no cold retry.
   Retain full source SHA, binary hashes, build commands and toolchain inventory.

3. **Exact TLS provisioning/handoff.** Proposed fresh private root:
   `C:/Users/OPERATOR/AppData/Local/Temp/nbsr-two-stream-rehearsal-20261013-private`,
   only if absent at action time. Authorize one invocation of the existing helper
   for one-day private test credentials, with only task-owned private-root ACL
   provisioning if required by the approved writer; no global security change.
   Reuse an existing set only if its exact provenance, public fingerprints, SANs
   and unexpired validity are established and use is explicitly approved instead.
   Do not silently renew. Keep keys outside evidence and logs; retain only public
   certificate metadata. S receives readonly CA/source certificate/source key;
   D receives readonly CA/destination certificate/destination key. Never mount the
   opposite role's key or the whole host private directory. Verify the exact
   daemon-visible canonical paths and readability before endpoint startup. No TLS
   material was generated or transferred in this preparation.

4. **Topology and workload.** Windows host M alone owns Docker. Two endpoints only,
   one task-labelled internal bridge172.30.250.0/29, gateway.1, S.2, D.3; first check
   conflict and stop on conflict, with no silent subnet substitution. No published
   ports, host/shared namespace, socket delegation or external network. Each endpoint
   is non-root65532, readonly root, cap-dropALL, no-new-privileges, init,128 PIDs,
   1 CPU and512MiB memory with no additional swap. Mount exact clean checkout at the
   original compile-time path, release binaries/manifest and role inputs readonly;
   separate writable role evidence roots at `/evidence`. Host command/controller
   evidence is never mounted. Use NBSR payload1024,2 streams,depth1,cores1, pacing100/1,
   3s warmup/20s issue, paired live guards and post-close reports. No larger trial.

5. **Time/resources and three cells.** One normal cell, one deliberate management
   cancellation after validated positive completed transport progress, then one
   fresh cell only after both exact disposal receipts. Each cell has120s total
   beginning before network/container creation, work stops95s, commands at most8s
   within remaining time. Total cell allocation at most360s; build and native
   preflight each separately bounded120s, no automatic retries. Verify both Windows
   host and Docker guest memory/commit headroom before starting, keep at least2GiB
   reserve and abort sustained pressure. Disk start>=8GiB, stop<6GiB or aggregate
   growth>2GiB; retain one original baseline. The current adapter accepts the
   existing injected resource guard; approved runner wiring must sample both host
   and guest and must not use the tests' no-op guard.

6. **Failure evidence and exact cleanup.** Preserve normal/fresh full validator
   outputs and interrupted INVALID_PARTIAL separately. In a finalizer, inspect
   `retained_owners` as well as sequence ownership: a failed create can return an ID
   only to the provisioning ledger. Attempt exact-ID removal and fresh absence
   checks within that same cell's remaining deadline; no new grace. Then remove
   the exact network only after empty membership and confirm its absence. Retain
   unresolved IDs/names/raw replies on ambiguity and stop before replacement.
   Do not prune images/caches/volumes or unrelated resources. Retain public evidence
   and dispose only the newly approved private test fixture root, using its verified
   inventory and resolved identity. Whole-host/controller failure is not covered
   by this surviving-controller composition and is not a cleanup-success claim.

No single-host result would establish SPHERE/bare-host disposal, production
authority, durable recovery, transparent resumption, capacity or Stage3 closure.
The immediate remaining blockers are clean source, cached Linux build/runtime
provenance, exact TLS authority and approval of the bounded live actions above.
