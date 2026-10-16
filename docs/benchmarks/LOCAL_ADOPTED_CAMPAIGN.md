# Local adopted-endpoint campaign (offline contract)

This development-only orchestration consumes a reviewed local handoff. It is not
runtime authority, deployment readiness or a throughput benchmark. No live trial
or credential action was run to validate this change.

## Minimal design and ownership

Petrit manually creates one isolated network and SIX fresh stopped containers:
source/destination pairs for normal, interrupted and fresh, in that order. Each
container has the exact reviewed image, command, public environment, isolation
settings, role-only read-only TLS mounts, source/binary/manifest mounts and output
root. Creation and private-key mounting remain outside agent authority. Do not
start any endpoint during provisioning. All six IDs must be unique full engine IDs;
labels are exactly nbsr.campaign, nbsr.run and nbsr.role. This is a trusted local
handoff, not protection from a hostile daemon or concurrent privileged operator.

AdoptedEndpoints is constructed with the network ID, ordered three-run handoff,
EndpointSpec map and expected public image environment. It never calls create or
mount. Preparation verifies the empty internal network and all six stopped/fresh
endpoint configurations before starting any. Environment and command comparisons
are evaluated inside the inspect template and return booleans, not their values.
Inspection requests selected ownership/topology fields; no full Config, Env or
HostConfig dump is requested. Templates have static/fake validation only so far.

Sequence.run retains its original fresh-owner contract: create requests are mapped
to the exact unused handoff IDs, revalidated and started. A later pair is unavailable
until both previous IDs have confirmed absence. Rejected or unobserved IDs remain
unresolved and are never removed as adopted owners. Validated unused pairs are
owned for final cleanup if work stops early. Failed cleanup is retained and not
automatically retried. Unknown ownership or clock uncertainty prevents success.
No opposite-role keys or entire private directory may be mounted.

## One deadline

Campaign.run starts its monotonic 420-second clock before configuration validation
and engine metadata preparation. It includes adoption/start, three finite cells,
cleanup of unused validated endpoints and final network removal/absence check.
Human credential generation/manual provisioning precedes this management campaign;
its time is not falsely counted as supervised time. Each new cell requires at least
145 seconds remaining: its original 95-second work/120-second total limit plus
25 seconds for final campaign cleanup. Both cell and campaign remaining time are
recomputed before cleanup observation. No callback receives a fresh overall clock.

Use the existing bounded DockerCommand (8-second maximum) and WindowsWorkload Job
supervisor. Work guard/cancellation callbacks run during preparation and workload
observation; cleanup skips work cancellation but remains deadline-bounded. Injected
callbacks must honor deadlines and return; fake tests do not prove OS containment
or preemption of a callback that refuses to return. Budget expiry can leave explicit
UNCONFIRMED ownership rather than extending the trial or claiming cleanup.

## Integration recipe (not live authorization)

Resolve exact daemon-visible paths and the pinned image's PUBLIC expected
configuration before constructing these objects. Do not read private keys or
collect an unrestricted inspect dump. Use a fresh host log root that is not mounted
in endpoints. Code below shows composition; arguments are reviewed handoff inputs,
not values to guess or defaults to widen.

```python
from scripts.performance.windows_adopted_campaign import AdoptedEndpoints, Campaign
from scripts.performance.windows_docker_provisioning import DockerCommand
from scripts.performance.windows_native_management import WindowsWorkload
from scripts.performance.local_container_sequence import Cell
from scripts.performance.native_debug_correctness import FIELD

command = DockerCommand(command_log_root, executable=approved_docker_executable)
engine = AdoptedEndpoints(
    command, campaign=campaign_name, image=pinned_image, specs=endpoint_specs,
    network_id=exact_network_id, handoff=ordered_three_pair_ids,
    expected_environment=reviewed_public_image_environment,
)
campaign = Campaign(engine, guard=approved_resource_and_cancellation_guard)
runner = WindowsWorkload(
    host_worker_root, budget_for=campaign.budget_for, guard=campaign.check_work,
)
cells = []
for run in ordered_three_pair_ids:
    config = engine.config(run, source_sha=reviewed_harness_commit)
    config[FIELD] = independently_selected_manifest_digest
    config['diagnostic_rate'] = [2, 1]
    cells.append(Cell(run, config, f'/configs/{run}.json', f'/controller/{run}'))
results = campaign.run(cells, runner, original_disk_free_bytes=historical_disk_baseline)
```

Preserve the Campaign, engine and command objects on failure to inspect sequence
results, cleanup_errors, unresolved_ids, retained_owners and the command Job owner.
Never translate failure to zero owned resources. Command/worker evidence stays in
fresh local log directories. The guard must implement the separately approved disk
exception and RAM/commit reserve; this module neither resets the historical baseline
nor grants the exception. Disk >=8GiB and RAM/commit >=2GiB reserve remain required.

All cells must match the approved endpoint configuration exactly, with the explicit
debug manifest pin, diagnostic_rate=[2,1], two application streams on ONE QUIC
connection, depth one, one core, 1024-byte payload, paired guards and post-close
reports. Existing finite execution supplies 3-second warmup/20-second issue time.
The second cell's INVALID_PARTIAL must follow validated positive progress. Existing
source/binary/clean-Git checks and distinct debug statuses remain in force.

## Verification and remaining live prerequisites

Focused test: python -m pytest -q -p no:cacheprovider
 tests/performance/test_windows_adopted_campaign.py
Neighbors: local_container_disposal, local_container_sequence, windows management,
Windows Job backend, Docker provisioning and native debug correctness test files.
Use existing provisioned Python; no downloads or real Docker are required.

Before a live trial: independently review and commit final code, bind a new manifest
runtime_source_sha to it while retaining the original Rust build identity, confirm
portable Git/source bytes, actual Docker template compatibility, daemon-visible
mount paths, non-root file access, pinned local image/dependencies and fresh resource
headroom. Supply exact six IDs/network and public configuration in a non-secret
handoff. Any metadata-only probe or live trial needs its own applicable authority.
A single trial approval must name the final commit/manifest/image and renewed one-run
disk exception; earlier e87 approval cannot authorize successor code. No push,
download, credential creation/mount, permission change or live operation follows
from offline test success.

The earlier v2/v3 422-file materialization is not import-complete: clean validation
found scripts/run_b5_v2.py missing. Its transitive committed dependencies additionally
include run_performance_validation.py, profile_b2_v2.py, run_p2a_established.py,
run_physical_core_v2.py, run_b4b_task4k.py, run_b4b_task4i.py, run_b4b_v2.py,
run_b4b_mixed_connections.py, run_max_throughput_v2_stage4.py,
run_max_throughput_v2_stage2.py (all under scripts/), and
scripts/core_v02_vectors/fixtures.py. Add the verified import closure to any later
materialization; matching 422 selected hashes was not evidence of runtime import
completeness. Previous packages and failed outcomes remain unchanged.


## Recorded metadata compatibility (October 14)

`AdoptedEndpoints` accepts an explicitly reviewed `inherited_labels` dictionary
alongside the exact pinned image ID. Its complete label comparison is the union
of those exact key/value pairs and the three task ownership labels. Inherited
keys in the case-insensitive `nbsr.` namespace are forbidden; unknown labels and
changed values still reject adoption. The saved public build metadata retained
`org.opencontainers.image.source=https://github.com/rust-lang/docker-rust`.
This is local fixture evidence, not authenticated image provenance or permission
to ignore additional Docker Desktop labels.

Windows controller sources require an explicit complete `mount_mappings` tuple.
Read a separately selected public mapping record as bytes and pass them with its
independently retained SHA256 to `load_mount_mappings`. Exact JSON shape:

```json
{"schema":"nbsr-local-mount-mapping-v1","bindings":[{"controller":"C:\\Public\\input","observed":"/recorded/input"}]}
```

The example observed path is illustrative, never an inferred daemon alias.
Every distinct EndpointSpec source must be mapped. The controller path must exist
with exact spelling, an uppercase local drive and no links/reparse points in any
ancestor; shares, traversal, short names and ambiguous components are rejected.
Observed sources may use one canonical POSIX namespace or exact Windows spelling,
as the retained Docker build metadata does. Mixed namespaces, duplicate observed
identities and output/input overlap reject. Actual inspect Source values must
match the recorded strings exactly. Container destinations remain POSIX paths.
Checks inspect filesystem metadata only; they do not read credentials or provide
a concurrent filesystem sandbox. A mapping digest is a trusted handoff identity,
not authenticated proof of a host-to-daemon relationship.

Run `tests/performance/test_adopted_metadata_compatibility.py` with the existing
adoption/ownership/sequence/Windows management/Job/provisioning/debug neighbors.
Materialized Windows-path tests are explicitly Windows-only. Fake command results
do not establish actual Docker template evaluation, non-root access or live success.

### Standalone staging and next diagnostic proposal

The retained v4 package still uses an alternate outside its checkout. Mounting
its enclosing Windows Temp directory would expose unrelated/private material and
is rejected. Do not retry the denied hardlink or introduce junctions. The precise
copying option is a fresh dedicated standalone root containing selected source,
small successor Git objects and a physical copy of the retained v3 snapshot.pack
(417,355,386 bytes, SHA256
`7304cfe8eff65fa2acc22ee888a6035b4a81b561ca7c0e08b38c374346844c09`),
its matching index and required root/shallow metadata. Verify all hashes, strict
fsck, clean status and final source identity before use. No such copy was made;
prior packages and the denied hardlink outcome remain intact. A successor manifest
must bind the final reviewed harness commit while preserving Rust build b09a851.

After standalone assembly, a separately authorized non-secret diagnostic may use
ONE fresh container from image
`sha256:7d59795425e21fc5ff09eabea1aad314806e8f20d3a505c5e47cc2df0e20e53d`,
network none, user 65532:65532, read-only root, cap-drop ALL, no-new-privileges,
private IPC, init, 1 CPU, 512 MiB memory with equal swap and 128 PIDs. Bind only
final source, existing binaries and successor manifest read-only; use public dummy
files at the three TLS targets and one fresh output directory. No private parent,
keys, Docker socket, ports, application traffic or network creation is needed.
Evaluate the real adoption template and exact public label/mapping pins, Python
imports, Git HEAD/clean status, source/binary digests, input read/execute access and
one tiny output write. Restrict image inspection to ID/platform, label keys and the
public source label, plus PATH/CARGO_HOME/RUSTUP_HOME/RUST_VERSION; other environment
entries return names only and stop the diagnostic.

Proposed limit: 120 seconds including cleanup, 95 seconds work and 25 seconds
reserved cleanup; no retry or extension. Retain the exact ID and logs, remove only
that diagnostic ID, verify absence and Job-handle release. Require at least 8 GiB
free disk and 2 GiB RAM/commit reserve. Any renewed one-run 300 MiB incremental disk
exception must retain the historical 14,247,788,544-byte baseline and its exceeded
2 GiB outcome. The approximately 398 MiB standalone pack copy is separate offline
preparation and cannot be charged to that diagnostic exception. This proposal has
not been executed and cannot establish access to future private keys.
