# Smallest path to a limited SPHERE diagnostic

Current decision: GO for local integration preparation; NO-GO for SPHERE execution.
No allocation, remote access, credentials, live traffic or publication is authorized
by this checklist. Original dirty sources remain outside the deployment candidate.

## Windows management follow-up

The [Windows management adapter](../reviews/2026-10-13-windows-native-management.md)
now composes the existing finite coordinator, explicit Win32 ownership binding and
offline disposal sequence without a management container or daemon socket mount.
135 scoped offline tests passed. Native APIs were faked, and no live Docker/QUIC
or Job Object trial ran. Concrete Docker provisioning and live containment remain
gated. Known handoff metadata did not establish an exact usable TLS fixture set or
matching Linux release manifest; no private keys were read or used. Preparation
continues to be distinct from authorization for live execution.

## Current follow-up: approved offline local-container contract

The subsequently approved local producer/validator and three-cell orchestration
contract are implemented with deterministic engine/workload adapters. Exact
run/role/container bindings, fresh absence observations, retained failed ownership
and both-receipt release gate the fresh rerun. No live Docker adapter or execution
is included. See the [implementation/review record](../reviews/2026-10-13-local-container-disposal.md)
for tests, trust assumptions and the remaining bounded live-adapter/rehearsal gate.
SPHERE remains NO-GO; local container observations do not prove bare-host disposal.

## Historical follow-up: runner implementation stopped at the disposal contract

The requested normal/interrupted/fresh-rerun runner was inspected before coding.
No existing producer/validator agreement was found that can authorize replacement
after interrupted remote endpoint ownership. No runner or new test was implemented
and no disposal boolean or permissive default was invented.

Exact reuse limits:

- `linux_native_lifecycle_coordinator.require_relay_cleanup` validates local relay
  exit/reap only and requires the literal `remote_cleanup=REQUIRES_EVIDENCE`.
- `linux_native_watchdog.supervise` retains remote cleanup as UNCONFIRMED.
- `post_close_cleanup.validate_report` checks eleven zero counters bound to role/PID;
  it is not post-interruption endpoint or socket disposal evidence.
- `linux_socket_ownership.snapshot` explicitly excludes cleanup proof. Its live
  PID/start-time/binary/network-namespace observations cannot prove later absence.
- `linux_native_finite_run.execute/check_endpoint` preserve failure and reject the
  interrupted run; they do not emit a fresh-rerun authorization.

Independent read-only review confirmed this gap. Fresh focused checks:9 passed
in1.50s (2.82s supervised), no abort and direct child reaped. Exact selectors:

```sh
python -B -m pytest -q -p no:cacheprovider \
  tests/performance/test_linux_native_cleanup_failures.py::test_zero_exit_remains_only_local_evidence \
  tests/performance/test_linux_native_cleanup_failures.py::test_cleanup_gate_rejects_incomplete_or_unconfirmed_local_results \
  tests/performance/test_linux_native_finite_endpoint.py::test_source_eof_seals_failure_without_starting_child
```

On this Windows run a fresh test-owned `--basetemp` under writable Temp was used.
The preceding attempt is retained:7 passed,2 setup errors because pytest could not
create its default sandbox temporary root. No assertion defect or red-green fix is
claimed. No socket/process workload, signing or dependency build ran.

Smallest decision for the FIRST LOCAL rehearsal: select an exact disposal evidence
producer and validator bound to each invocation and role. Recommended candidate
for approval is an outer controller owning one disposable isolated container/network
namespace per endpoint, recording immutable container IDs at creation and requiring
their confirmed teardown before a new cell. No host/shared network namespace or
untracked external descendants may be assumed covered. Replayed IDs, wrong role/run,
partial teardown or lost observer access must remain unresolved. This is proposed
benchmark containment scope, not registration authority or an implemented contract.

The approved single-container recovery trial supplies a reusable observed teardown
pattern, not a multi-endpoint contract. Its result must not be relabelled SSH remote
cleanup. A future SPHERE bare-host mapping needs its separately specified endpoint
owner/evidence source; accepting a local container proof does not settle that mapping.

Before runner implementation, settle that precise producer/validator agreement:
creation identity, exact owned resources, terminal observation, per-run freshness,
uncertainty handling and the condition that permits the next cell. Then test missing,
wrong-role/run, replayed, incomplete and successful evidence with deterministic
fakes before any separately authorized live rehearsal. Existing authority/outage/
revocation semantics are not reopened. Later sections remain the intended sequence,
conditional on this unresolved integration contract.

## Reuse, do not rebuild the demonstrated capabilities

The [explicit-proxy demo](../demo/nbsr-end-to-end-demo.md) already demonstrates one
application request through fixture ACP, independent grant verification, QUIC,
service-channel/stream admission and the destination-private backend. Its
[evidence](../demo/nbsr-end-to-end-demo-evidence.md) belongs to its recorded historical
source/binaries, not a fresh validation of today's dirty checkout. Its start script
builds binaries and creates per-run trust material; do not run it as an offline
preflight. It is not the outbound connector-registration runtime.

The [finite coordinator](EXTERNAL_NATIVE_FINITE_COORDINATOR.md) is the shortest
SPHERE path: M coordinates S (`perf_rust_source`) to D (`wp8_interop_server`) with
existing benchmark fixture authority/TLS. This is a two-stream transport diagnostic,
not the Go application demo, general client-to-connector integration, or production
registration. Go/Rust wire evidence already exists separately; a Go build is not
required by this selected Rust-source cell. The current build manifest validator
still checks all three Rust benchmark binaries, including `perf_direct_peer`.

The six local watchdog process cases and four real tmpfs interruption cases are
supporting ownership/containment evidence. They do not validate this traffic chain,
SSH disconnect cleanup, remote socket release or SPHERE. Do not substitute them for
the integration trial. The latter four require a surviving controller and recover
a model object, not an application workload.

## Exact reusable commands and dependencies

Already executed unsigned offline preflight, from the repository root:

```sh
python -I -B docs/benchmarks/sphere-offline-20261012/preflight.py
```

October 13 result: CONFIG_VALID_OFFLINE; five invalid configuration mutations
rejected; endpoint SSH commands constructed but never executed. Supervised1.21s,
exit0, child reaped, no resource abort. Live trial NOT_RUN, resources NOT_RESERVED.
The synthetic config uses `.invalid`/documentation addresses and is not executable
against real targets. It fixes path=nbsr, payload1024, streams2, depth1, cores1 per
peer, post_close_reports=true, warmup3s, issue20s. Preserve that shape.

Future cached build command, only when separately authorized and cache/headroom
verified; prefer already provenance-verified binaries over rebuilding:

```sh
export CARGO_TARGET_DIR=/absolute/verified-existing-linux-cache
cargo build --locked --offline --release --jobs 2 \
  --manifest-path crates/nbsr-transport/Cargo.toml \
  --features benchmark-harness \
  --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server
```

The Linux endpoint requires Python dependencies, taskset/topology access, an exact
clean source identity, release build manifest and hashes for the three binaries,
approved private TLS fixtures outside evidence, and original compile-time fixture
paths. Rust supports edition2024. Missing cache/tool/fixture is a blocker; no cold
build or download is implied. See [native peer execution](EXTERNAL_NATIVE_PEER_EXECUTION.md).

Future controller invocation, after replacing only verified environment values and
placing all roles under approved independent containment:

```sh
python3 -B -m scripts.performance.linux_native_watchdog \
  --mode finite --config /approved/finite-two-stream.json \
  --output /approved/new-controller-evidence \
  --original-disk-free-bytes ORIGINAL_RETAINED_BASELINE
```

`endpoint_arguments()` in `linux_native_finite_run.py` constructs the exact S/D
commands. `remote_command()` retains BatchMode=yes, StrictHostKeyChecking=yes and
ConnectTimeout=10 for SSH. Do not hand-edit TLS names into IP identities. The
watchdog supervises local coordinator descendants only and explicitly leaves
remote cleanup UNCONFIRMED; its invocation alone does not satisfy the gate below.

## Smallest next implementation/test slice

Prepare one integration runner around the EXISTING finite coordinator, with fresh
roots and a retained run-specific ownership ledger for M/S/D. Reuse endpoint PID,
binary, address and post-close evidence; do not add a registration provider or alter
protocol timing. First inspect whether retained normal-run and cancellation evidence
already meets each assertion; add only the missing orchestration/evidence checks.

One later authorized local topology rehearsal should contain three sequential cells,
each independently bounded to120s including cleanup, never parallel:

1. Normal two-stream NBSR exchange and clean stop, using existing validators.
2. Deliberate management/control interruption after actual peer ownership/readiness.
   Expected result INVALID_PARTIAL, not PASS. Independently observe both endpoint
   process groups reaped and their exact UDP bindings released; missing evidence
   remains UNCONFIRMED and blocks retry. Preserve all partial logs/counters.
3. Only after verified disposal, run a fresh two-stream cell with fresh roots and
   connection/acceptance state. No application replay, old grant/session transfer,
   direct-origin fallback, or retry of denied authorization. This tests explicit
   fresh rerun after transport interruption, not transparent reconnect/resumption.

Acceptance: full source/build/TLS fixture identity and unchanged workload; successful
cells have source/destination validated results, expected stream cardinality and
payload integrity, no failure markers, eleven post-close counters independently
bound to each owned PID and zero. Interrupted cell remains failed with exact cleanup
evidence rather than invented zero counters. Fresh rerun cannot begin on uncertain
cleanup. The parent/endpoint containment path must also handle management loss;
the M-only watchdog does not kill a surviving remote process.

If independent endpoint containment/disposal cannot be composed from existing
operator-owned container/service mechanisms, stop with that precise gap. A new
security-sensitive receipt, remote trust protocol or supervisor contract needs a
separate design decision; a management EOF is never disposal evidence by itself.
No integration runner or live rehearsal was implemented/executed in this pass.

## Essential gates for first SPHERE diagnostic

| Gate | Current evidence / missing input |
|---|---|
| One exact reviewed runnable source set | Published ancestor ad77d597 plus local harness changes are identified separately. Existing peer gates demand clean source/build agreement. Isolated materialization is not a clean deployable checkout; do not bypass that gate. |
| Repeatable Linux setup | Config schema/commands pass offline. Exact usable Linux binaries, manifests, original fixture paths and dependency/cache availability need inspection before execution. |
| Authorized test traffic and trust fixtures | No live authority or fixture transfer approved in this pass. Existing approved fixtures may be reused only after validity/provenance and permitted scope are confirmed; absent/expired fixtures require explicit provisioning authority. |
| Normal/interrupted/fresh-rerun integration | Existing finite and cleanup components available; combined run-specific endpoint cleanup/retry acceptance above remains NOT_RUN. |
| M/S/D allocation and network | Not reserved. Operator must supply actual Linux nodes, trusted SSH aliases/host keys, permitted source/destination IPv4/UDP path, private paths and facility release procedure. No guessed reservation command. |
| Resource and cleanup envelope | Verify controller AND peers:8GiB disk start,6GiB floor,2GiB cumulative growth limit,2GiB RAM reserve, bounded CPU and120s including cleanup. End work by95-105s; no silent extension. Collect live socket/process evidence separately from counters. |
| Evidence transfer and release | Exact inventories/hashes, cardinality, raw failures, independent cleanup and approved private export. Exclude secret material. Release only owned allocation after evidence retention. |

The first SPHERE run is ONE functional NBSR cell, not a performance comparison.
Direct pairs, repetitions/CV analysis,16-client lifecycle work, larger workloads,
soaks and capacity claims are later separately justified scopes.

## Later product gates, not prerequisites for this benchmark cell

Full outbound connector registration with applicable controller/normal/emergency
governance, production authority/provenance, authenticated revocation and real
timers, durable process/controller-loss recovery, private-origin integration,
installer/readiness/rollback and the production security audit remain required for
plug-and-play product claims. See the [full-model matrix](../reviews/2026-10-11-registration-full-model-acceptance.md).
They must not be silently substituted with fixture trust, but need not block an
honestly labelled finite benchmark diagnostic that does not invoke that provider.

Next action: prepare/review the minimal three-cell integration runner and exact
provisioned artifact inventory, without live execution. Then request ONE combined
scope for the local topology/TLS/traffic/interruption/cleanup rehearsal. SPHERE
reservation and remote execution follow only after its go/no-go evidence and
operator environment inputs are complete. No further isolated recovery test is
needed to make progress toward this transport diagnostic.
