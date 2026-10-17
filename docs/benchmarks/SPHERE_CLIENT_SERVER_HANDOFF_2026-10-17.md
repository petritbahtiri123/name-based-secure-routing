# SPHERE client/server operational handoff for Kulleri — 2026-10-17

Status: **PREPARED / NO NEW SPHERE EXECUTION**. Two-VM functional diagnostics are feasible in principle. Execution remains blocked until live allocation, source/build/TLS provenance, resource guards and independent remote containment are verified. Sustainable capacity and full external validation are **NOT_ESTABLISHED**.

## 1. Evidence and chronology

Reviewed development source: `f07def3a7854abc5f161490b79bc00a6c646622c` on `codex/nbsr-v3-wp0-wp1`. This is the inspected GitHub snapshot, **not a verified deployed VM build**.

| Item | Evidence reviewed | Interpretation |
| --- | --- | --- |
| SSH client/server connectivity | User-supplied terminal excerpt and October 16 handoff note | Previously observed connectivity; not freshly checked from this review environment |
| VM addresses/resources | October 16 handoff note | Reported inventory; refresh before execution |
| Functional and release smoke success, no integrity errors | Sent Credo email read directly | Verified that the claim was sent; underlying execution logs were not supplied/validated |
| Earlier note says NBSR not transferred/QUIC-TLS not run | October 16 handoff note | Earlier checkpoint; later reported progress can supersede it only within the later evidence scope |
| Original three-node runbook | Current repository file | Still historical NOT_RUN / RESOURCES_NOT_RESERVED; no proof M/S/D was executed |
| Remote disposal, capacity, full acceptance | No joined run-specific SPHERE package validated in this review | UNCONFIRMED / NOT_ESTABLISHED |

Email timestamp correction: Gmail records October 16 at 23:45:38 UTC, which is **October 17 at 01:45:38 Europe/Skopje**. Keep the sender's October 16 date and the local date distinct.

The weekly publication preserves offline/synthetic SPHERE preparation and historical NO-GO records. Those records and successful local watchdog tests are not SPHERE execution evidence. Do not rewrite archived snapshots.

## 2. Actual topology and test scope

Reported mapping, to be rechecked on the existing allocation:

| Role | Host | Experiment interface | Management interface | Reported guest |
| --- | --- | --- | --- | --- |
| S, source | client | eth1, 10.77.0.2/24 | eth0, 172.30.0.11/16 | Ubuntu 24.04.4 x86_64, 2 vCPU, 3.8 GiB RAM, 30 GB disk |
| D, destination | server | eth1, 10.77.0.1/24 | eth0, 172.30.0.12/16 | Same reported guest specification |
| M, management | Existing external controller, or client sharing S resources | No benchmark relay | Must reach both endpoints via trusted SSH | Not yet selected/verified |

Windows aliases are `nbsr-client` and `nbsr-server`; the supplied Linux transcript uses `client` and `server`. Aliases are machine-local configuration, not interchangeable proof of reachability. Do not copy Windows credentials to a VM, enable agent forwarding, or create a self-SSH key to make co-location work.

The original M is an experiment coordinator, not a routing hop, registration authority, gateway or backend. Therefore a third Linux VM is **not inherently needed for two-endpoint QUIC functional traffic**.

| Test | Two experiment VMs | Extra controller / third role |
| --- | --- | --- |
| Read-only SSH, interface, route, inventory, public certificate inspection | Yes | Existing management access |
| One QUIC connection, two application streams, integrity and explicit post-close reports | Yes; client=S, server=D | Coordinator must run somewhere; co-location requires working trusted SSH to both roles, resource/containment gates |
| Matched finite Direct/NBSR diagnostics | Yes, after initial evidence review and scoped execution approval | External Linux M preferred to avoid observer contention; Direct means direct QUIC |
| 16-client lifecycle admission/marker/ACK/ownership checks | Yes, conditionally | Requires separate scoped approval, fresh lifecycle roots and sufficient headroom |
| Controlled interruption and fresh rerun | Two data VMs suffice | Independent surviving cleanup control or verified per-endpoint containment required |
| Original physically separated M/S/D procedure | No, when M is co-located | Separate M required; existing suitable external Linux host can supply M |
| Actual multi-hop forwarding / third network participant | Not demonstrated by this pair | Needs explicitly designed additional role and implementation; adding M does not create multi-hop routing |
| Full connector registration, real authority/revocation/governance | No conclusion from finite pair | Additional runtime/authority acceptance gates, not solved just by adding a VM |
| Bare-metal scaling, physical wire, WAN, sustainable capacity, long soak | Not established | Qualified resources, portable matrix, observers and separate campaign authorization required |

Recommended first shape follows the narrower October 13 integration preparation: **NBSR, payload 1024, streams 2, depth 1, cores 1 per endpoint, post_close_reports=true, 3 s warmup + 20 s issue**. Do not substitute the broader runbook's default 16 KiB or begin at 16 clients. No new VM, paid service, network-policy change or larger load is authorized by this report.

## 3. Kulleri's first actions: read-only inventory

Inspect local `AGENTS.md`, current branch/status, existing running jobs and pending changes before touching any checkout. Do not pull, reset, switch or rebuild inside Codex's active tree. Use the existing reviewed package if its provenance is complete; otherwise prepare an isolated snapshot after checking the current source.

On Windows, use the existing configuration at `C:\Users\bajra\.ssh\config`:

```powershell
ssh -G nbsr-client
ssh -G nbsr-server
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 nbsr-client 'hostname; id; date -u'
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 nbsr-server 'hostname; id; date -u'
```

These simple read-only commands have no benchmark side effects. ConnectTimeout bounds connection setup only, **not the full remote command**. Use the existing controller's approved whole-command deadline for unattended execution. Do not publish the raw `ssh -G` output; it can expose account/path identifiers.

Both VMs were reported to share ED25519 fingerprint:
`SHA256:BMzMGyhYu5eGcf6dPOIeiwFwLI9OXYCiQl9olarNoL8`.
A shared host key does not uniquely distinguish nodes. Compare allocation/console identity, hostname, interface addresses and current key fingerprint via an independently trusted management path. Do not silently regenerate keys, accept changed keys, run ssh-keyscan as authentication, or use StrictHostKeyChecking=no. Record the remaining identity limitation; stop if the mapping cannot be trusted.

On each VM, retain separate stdout/stderr and exit codes for each inventory command:

```bash
hostname
id
date -u
cat /etc/os-release
uname -a
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
ip -j address show
ip -j route show
ip route get 10.77.0.1
ip route get 10.77.0.2
lscpu -J
lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE
taskset -pc $$
free -b
df -B1 /var/tmp
cat /proc/self/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
ss -uapn
ps -eo user,pid,ppid,pgid,sid,lstart,comm
rustc -Vv
cargo -V
python3 --version
```

Missing cgroup files/tools/permissions are recorded as unavailable with the error; do not install/elevate automatically. Record NIC/MTU/offloads using the existing read-only inventory module after verifying its output path and dependencies:

```bash
python3 -B -m scripts.performance.linux_network_inventory --interface eth1 --output /var/tmp/NEW_INVENTORY_DIRECTORY
```

The peer route must select eth1 and the expected local 10.77.0.x source. Confirm the allocated UDP path is already permitted; a successful SSH/ping does not prove UDP/QUIC allowance. Do not change firewall/sysctl/MTU/offloads. Record time synchronization uncertainty; never subtract host-local monotonic clocks across machines.

## 4. Paths, source and build provenance

No actual VM checkout, binary cache, manifest, TLS or retained smoke directory was verified by this review. The following paths are **proposed examples**, not discovered installations:

- Checkout: `/home/OPERATOR/nbsr/repository`.
- Existing verified native cache/binaries: `/home/OPERATOR/nbsr-build/release`.
- Build manifest: `/home/OPERATOR/nbsr-build/build-manifest.json`.
- Private TLS: `/home/OPERATOR/nbsr-private/tls`.
- Per-role output: `/home/OPERATOR/nbsr-evidence/RUN_ID/source` or `destination`.
- M output: `/home/OPERATOR/nbsr-collected/RUN_ID`.

Resolve all placeholders from the current installation. Keep private material, evidence, builds and checkout disjoint; reject links/aliases and reused output roots. Keep the original compile-time fixture paths and `vectors/` present: copying standalone binaries is insufficient.

On both peers and M, from the actual checkout:

```bash
git rev-parse HEAD
git branch --show-current
git status --porcelain --untracked-files=all
```

Require the same clean, reviewed full SHA. A later deployment SHA may differ from the inspected snapshot; review its relevant diff first. Record source inventory/hashes, exact original build argv/toolchains, binary architecture and hashes. Manifest fields are `source_sha`, `build_profile=release`, `binary_sha256` keyed by **binary filenames**, nonempty `build_commands` and `toolchains`. All three Rust files are required even for the selected NBSR cell:

```bash
sha256sum "$BIN/perf_direct_peer" "$BIN/perf_rust_source" "$BIN/wp8_interop_server"
file "$BIN/perf_direct_peer" "$BIN/perf_rust_source" "$BIN/wp8_interop_server"
```

Inspect interpreter/library requirements using trusted file metadata/readelf. Do not run ldd on an untrusted imported executable. A fabricated manifest cannot restore missing original build provenance.

Only if an existing reviewed binary package cannot be reused, and cached building is authorized under a verified build supervisor:

```bash
export CARGO_TARGET_DIR=/absolute/verified-existing-linux-cache
cargo build --locked --offline --release --jobs 2 \
  --manifest-path crates/nbsr-transport/Cargo.toml \
  --features benchmark-harness \
  --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server
```

This is not self-supervising. Apply the original cleanup-inclusive deadline and resource guards to the build too. Cache/toolchain misses stop the attempt. Rust must support edition 2024 and the locked dependencies. Go is **not required** for this Rust-to-Rust smoke; separately selected Go work must satisfy the module's Go 1.26.5 requirement. Do not invoke Compose/bootstrap/demo credential generators as a substitute.

## 5. TLS and runtime identities

Benchmark TLS identity is independent of SSH hostname and IP:

| Role | Expected DNS identity | Private role files |
| --- | --- | --- |
| client / S | source.edge | ca.der, source.der, source-key.der |
| server / D | destination.edge | ca.der, destination.der, destination-key.der |

Inspect only public certificate bytes, validity, issuer and SANs:

```bash
openssl x509 -inform DER -in "$AUTH/ca.der" -noout -subject -issuer -dates -fingerprint -sha256
openssl x509 -inform DER -in "$AUTH/source.der" -noout -subject -issuer -dates -ext subjectAltName -fingerprint -sha256
openssl x509 -inform DER -in "$AUTH/destination.der" -noout -subject -issuer -dates -ext subjectAltName -fingerprint -sha256
```

Run the relevant leaf command on its role; both leaves need not be present everywhere. Compare the CA hash privately between peers and retain public certificate hashes. Confirm key-file presence/ownership/mode without printing or exporting keys. Private directories should be 0700 and role key files 0600; report deviations before modifying existing material.

The existing authority helper generates a one-day test CA and peer keys; **do not call it without disposable-PKI authority**. Do not regenerate expired fixtures silently, transmit private keys under general trial approval, or change names to IP SANs. A user-controlled private handoff must supply the exact role subset. Record actual QUIC/ALPN/readiness (`nbsr-quic-1`) and fixture/service binding; TLS success is not production registration authority.

Remove inherited benchmark `NBSR_*` overrides from the dedicated invocation environment on M and both endpoints, after listing variable **names only** and recording the approved overrides. Preserve unrelated global/user environment. The remote adapter inherits the remote environment and does not automatically sanitize it.

## 6. Limits and cleanup: hard execution gate

Retain original disk baseline per filesystem on M/S/D before the campaign. Require at least **8 GiB free at start**, stop below **6 GiB** or after **2 GiB cumulative loss/growth**, and preserve at least **2 GiB MemAvailable** on every host. Never reset the baseline to make a retry fit. On 3.8 GiB guests this is a material gate, especially if M shares client.

All builds/trials remain sequential, at most two compiler jobs, with **120 s total including startup, collection and cleanup**. Begin cancellation at 100 s; TERM at 105, KILL at 110; no new wait past 120. Early failure starts cleanup immediately. Endpoint/controller sub-deadlines and per-role collection allowances do not add to this outer budget.

The existing `linux_native_watchdog`:
- Is Linux-only. Raw Windows coordinator support does not supply this watchdog.
- Guards local disk/RAM and owns its local coordinator process group only.
- Does not monitor peer resources, stop remote PIDs, contain escaped sessions, or guarantee cleanup after M dies.
- Reports LOCAL_WORKER_COMPLETED at strongest, with local_cleanup and remote_cleanup UNCONFIRMED.
- Cannot turn a forced/partial worker into a valid functional result.

**Therefore do not launch until an independently reviewed per-endpoint mechanism exists.** Required contract:
1. Independently retained run ID, host/boot identity, UID, exact supervisor/cgroup identity, PID/start ticks, executable hash, process group and expected socket tuples/inodes.
2. Endpoint-local deadline/resource monitoring survives SSH loss and M interruption; child processes/sessions are contained, with a surviving cleanup authority.
3. Cancellation targets only this run's owned containment, preserves the original deadline, and records signal/stop results plus leader/descendant reap and socket disappearance.
4. Normal completion, catchable cancellation, SSH loss and failed start have reviewed cleanup acceptance; parent death/network loss remains explicitly scoped. Missing proof is UNCONFIRMED, not zero.

If a run-specific reviewed systemd user service already supplies that contract, inspection/stop commands are:

```bash
systemctl --user show "$VERIFIED_RUN_UNIT" -p Id -p ControlGroup -p MainPID -p ActiveState -p SubState -p Result -p KillMode -p TimeoutStopUSec -p RuntimeMaxUSec
systemctl --user stop "$VERIFIED_RUN_UNIT"
systemctl --user show "$VERIFIED_RUN_UNIT" -p ControlGroup -p MainPID -p ActiveState -p SubState -p Result
ss -uapn
```

These are conditional commands, not proof such a unit exists. Verify the exact run-bound unit, containment, cumulative deadlines and bounded stop behavior first; never stop arbitrary services or assume MainPID=0 proves an empty cgroup. No unit installation or remote cleanup adapter is implemented by this documentation change. If none exists, retain BLOCKED_REMOTE_CONTAINMENT and prepare/review that mechanism before traffic.

Do not use pkill, killall, guessed/reused PIDs, kill-by-name, broad docker prune, or deletion of output roots as cleanup. SSH timeout, process exit and released application counters are separate observations.

## 7. Configuration and conditional launch

Example finite config: **not a live launch target until all paths/aliases/SHA are replaced with verified deployment values**. M must authenticate noninteractively to both hosts, including its own endpoint if co-located; current adapter supports ssh/docker, not an assumed local transport.

```json
{
  "schema": "nbsr-native-finite-coordinator-v1",
  "source_sha": "f07def3a7854abc5f161490b79bc00a6c646622c",
  "path": "nbsr",
  "payload": 1024,
  "streams": 2,
  "depth": 1,
  "post_close_reports": true,
  "source": {
    "transport": "ssh",
    "host": "nbsr-client",
    "checkout": "/home/OPERATOR/nbsr/repository",
    "binaries": "/home/OPERATOR/nbsr-build/release",
    "build_manifest": "/home/OPERATOR/nbsr-build/build-manifest.json",
    "authority": "/home/OPERATOR/nbsr-private/tls",
    "output": "/home/OPERATOR/nbsr-evidence/RUN_ID/source",
    "bind": "10.77.0.2:0",
    "cores": 1
  },
  "destination": {
    "transport": "ssh",
    "host": "nbsr-server",
    "checkout": "/home/OPERATOR/nbsr/repository",
    "binaries": "/home/OPERATOR/nbsr-build/release",
    "build_manifest": "/home/OPERATOR/nbsr-build/build-manifest.json",
    "authority": "/home/OPERATOR/nbsr-private/tls",
    "output": "/home/OPERATOR/nbsr-evidence/RUN_ID/destination",
    "bind": "10.77.0.1:0",
    "cores": 1
  }
}
```

Zero destination port requests readiness-selected UDP; verify that selected port is permitted within the existing allocation. Do not add firewall exceptions. Bind is not TLS identity.

Offline schema check, from matching provisioned checkout (does not authenticate hosts, inspect VM resources, open sockets or validate binaries):

```bash
python3 -B - /absolute/finite-two-stream.json <<'PY'
import json, sys
from scripts.performance.linux_native_finite_run import validate_config
with open(sys.argv[1], encoding="utf-8") as stream:
    validate_config(json.load(stream))
print("CONFIG_VALID_OFFLINE; live gates remain unverified")
PY
```

After all execution gates and task-specific scope are recorded, the existing Linux M invocation is:

```bash
python3 -B -m scripts.performance.linux_native_watchdog \
  --mode finite --config /absolute/finite-two-stream.json \
  --output /absolute/NEW_CONTROLLER_OUTPUT \
  --original-disk-free-bytes ORIGINAL_RETAINED_BASELINE
```

Do not run the raw coordinator to bypass watchdog failure. The wrapper does not replace the independent S/D mechanisms in section 6.

Inspect the complete result and cleanup before any further cell. A separately approved 16-client lifecycle configuration uses the exact schema in EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md with count=16, rate=100, shards=2, cores=1 and fresh per-role lifecycle roots containing only 00/. The same watchdog supports --mode lifecycle, but **does not forward --archive-collection**. Do not append that unsupported flag. Archive mode on the raw lifecycle CLI needs separately reviewed aggregate supervision; do not bypass the watchdog just for faster collection.

## 8. Evidence, acceptance and interruption

Before another run, first locate the earlier smoke bundle on the user's laptop/VMs by its known operator path. No path was identified here. Read its config, command records, clean source/build manifests, certificate hashes, endpoint stdout/stderr, integrity output, exit codes, checksums and cleanup. Preserve it unchanged even if incomplete.

Each new attempt gets fresh external roots. Keep:
- Exact config/argv/environment overrides, UTC and local monotonic intervals, topology/cgroup/route/NIC inventory and competing load before/after.
- Original disk/RAM baselines and continuous guards on M/S/D.
- Build/source/binary hashes and public certificate identity, without key bytes.
- management.ndjson, relay stderr, cleanup.json, source/destination complete sealed packages, result.json or failure.json, transfer records and checksums.
- Run-bound remote containment/reap/socket evidence, cancellation actions and all failed/unfavorable attempts.

Do not modify sealed worker roots. Put supplementary postflight/export manifests in a separate parent/sidecar. Archive validation is bounded to 512 MiB per role plus both archives/validator overhead; do not bulk-extract or export private authority roots. Finish/check collection within the aggregate budget; timeout is a retained failure, not permission to extend it.

| Decision | Required evidence |
| --- | --- |
| CONFIG_VALID_OFFLINE | Existing schema validator accepts actual structure; not execution permission |
| Finite functional candidate | Worker PASS_CONTROLLED_FINITE_PAIR, complete independent endpoint/peer gates, zero payload/integrity errors, correct SHA/build/TLS/workload |
| NBSR post-close ownership | Explicit reports enabled on both peers; exact owned PID and all eleven integer counters zero; missing is NOT_MEASURED/UNCONFIRMED |
| Local supervision | Watchdog final LOCAL_WORKER_COMPLETED within original budget; no missing/partial/forced outcome |
| Operational cleanup accepted | Independent S/D run-bound containment empty, exact owned children reaped and socket tuples released, with postflight logs |
| Lifecycle candidate | PASS_FUNCTIONAL_CONTROLLED_PAIR with exact marker cardinality, hold/release/ACK/cooldown, socket/PID identity and zero final ownership |
| FAIL / INVALID_PARTIAL | Integrity/identity/provenance mismatch, nonzero/forced exits, resource abort, deadline, cardinality or checksum failure |
| UNCONFIRMED | Lost management, absent cleanup proof, missing logs/counters, unknown ownership; never substitute zeros |
| Capacity / full validation | NOT_ESTABLISHED regardless of finite functional pass |

For finite NBSR reports, the eleven fields are defined in scripts/performance/post_close_cleanup.py: transport_sessions_current_live, service_channels_current_live, application_streams_current_live, nbsr_tasks_current_live, quic_connections_current_live, quic_streams_current_live, pending_routes_current_entries, channel_registry_current_entries, stream_registry_current_entries, replay_state_current_entries and audit_queue_current_entries. Direct retains its process-exit scope.

On interruption: stop further launches, use only the verified run-owned endpoint mechanism, preserve primary and cleanup failures separately, inspect both hosts independently, and record UNCONFIRMED if either cannot be reached. A fresh rerun is allowed only after cleanup is established, resources still pass and the scope permits another attempt. Never overwrite the failed attempt.

Export only through the existing approved private channel, verify hashes at destination, retain originals and failed attempts. Public derivative allowlist: this report, sanitized configs/schema examples, aggregate outcomes and explicitly reviewed source/binary/public-certificate hashes. Exclude private keys, tokens, account/allocation IDs, raw SSH configuration and unrelated host logs. Scan the exact derivative before publication.

Rollback: stop this run's owned processes; verify reap/socket release; retain evidence. Remove only verified task-created temporary inputs after export and separate cleanup authorization where required. Restore only task changes from their recorded backups. Do not alter images/caches/shared volumes or release the experiment automatically; release only owned resources through the operator-verified SPHERE procedure with a receipt.

## 9. Handoff decision and next three actions

1. Recover and validate the existing two-VM smoke evidence before claiming a logged pass or repeating work.
2. Refresh read-only allocation/SSH identity, deployment/source/build/TLS and resource inventory; choose M without creating nodes or moving credentials.
3. Review and establish independent endpoint cleanup/resource supervision. Only then consider one authorized two-stream functional cell; keep larger lifecycle, throughput and soak work separate.

No SPHERE session, credential transfer, PKI generation, native build or benchmark was started in this review. No capacity or full-model acceptance claim is made.

## Source references

All paths below were inspected against the reviewed source; archived publication records remain historical:
- SPHERE_READINESS_RUNBOOK_2026-10-11.md
- EXTERNAL_NATIVE_FINITE_COORDINATOR.md
- EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md
- EXTERNAL_NATIVE_PEER_EXECUTION.md
- EXTERNAL_NATIVE_TWO_HOST_RUNBOOK.md
- LOCAL_TRIAL_WATCHDOG.md and NATIVE_ARCHIVE_COLLECTION.md
- EXTERNAL_LINUX_SERVER_VALIDATION.md
- ../../scripts/performance/linux_native_finite_run.py
- ../../scripts/performance/linux_native_lifecycle_coordinator.py
- ../../scripts/performance/linux_native_lifecycle_remote.py
- ../../scripts/performance/linux_native_peer.py
- ../../scripts/performance/linux_native_watchdog.py
- ../../scripts/performance/native_debug_correctness.py
- ../../scripts/performance/authority.py and post_close_cleanup.py
- ../publication/2026-10-16-weekly-reconciliation.md and preserved SPHERE_MINIMAL_INTEGRATION_2026-10-13 records

Private contextual sources: October 16 operator handoff note and the sent Credo follow-up. These establish reported progress, not independent execution validation.

## Review validation (documentation only)

JSON parsing, Bash syntax, strict SSH/post-close argument construction, and two invalid-config mutations passed using the actual AST-extracted source functions without their import graph. Full module import in this review environment failed because cbor2 is absent; no dependencies were installed. This is source/command validation only, not a complete provisioned-runtime check. No SPHERE execution was performed.
