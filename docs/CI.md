# Project CI

The quick workflow checks pushes to `codex/nbsr-v3-wp0-wp1`, pull requests,
and manual dispatches. It does not deploy or run live connection benchmarks.
The separate extended workflow is manual only; there is no overnight schedule.
Both files use JSON syntax, which is valid YAML and can be inspected offline
without installing a YAML parser.

## Coverage and limits

| Job | Platforms | Checks |
| --- | --- | --- |
| Python | Ubuntu 24.04, Windows 2025 | Explicit runtime, gateway, security, admission, connector model/authority/timer, offline config and CI tests; `pip check` |
| Python protocol | Ubuntu 24.04 | Protocol, vectors and federation tests except independent wire-peer builds; deterministic vector regeneration; privacy check; correctness lint |
| Rust | Ubuntu 24.04, Windows 2025 | Format, default library check, benchmark-feature library, handshake/credit/drain/config, frame codec, connector integration targets (live ignored), doc-tests, all-target Clippy |
| Go | Ubuntu 24.04, Windows 2025 | Test and vet all six modules, plus explicit `connector_development` test/vet in the interop module |
| Node and policy | Ubuntu 24.04 | Core/federation independent verifier tests and vectors, exporter and connector registration vectors, OPA policy tests |
| Manual extended | Ubuntu 24.04 | All nonignored Rust integration tests, existing ignored replay-history soak, or explicitly selected isolated connector loopback |

Python uses 3.13.14, Rust 1.97.1, Go 1.26.5 and Node 24.19.0. These are explicit
pins, not a claim of coverage for every version allowed by package metadata.
OPA 1.4.2 matches the repository policy runtime; its official static binary is
verified against a pinned SHA-256 before execution. Node packages currently
have no dependencies, so there is no npm installation.

Python installation uses `constraints/dev.txt`; Cargo fetch uses `--locked`
and tests use `--offline`; Go resolves recorded module versions, verifies its
module cache, and tests with `-mod=readonly` and `GOPROXY=off`. Lockfile diffs
fail their jobs. The Rust default-feature library check complements the
benchmark-feature suite; it is not an exhaustive feature matrix.

Quick checks intentionally exclude independent multi-language live-wire builds,
root-level historical documentation assertions, broad performance harness runs, Docker/Kind,
network capture, infrastructure startup and capacity trials. Manual extended
Rust includes more lifecycle tests but does not establish WAN or throughput
results. Federation documentation/baseline assertions are included. Full repository Ruff style/format cleanliness is not claimed: existing
Python receives the critical `E9,F63,F7,F82` gate, and new CI code gets full Ruff.

## Execution and security

All jobs run on GitHub-hosted runners with read-only `contents` permission.
Checkout does not persist credentials. Actions are pinned to full commit SHAs;
there are no secrets, deployment environments, privileged PR events or
self-hosted runners. PR code still executes as untrusted code in the disposable
hosted runner. No test job should be given repository or infrastructure secrets.

Dependency-only caches use OS/toolchain/lockfile keys. Saves occur only after a
successful push to the development branch, never from a PR or manual run.
Workspaces, compiled targets, credentials and fixtures are not cached. Failure
artifacts contain only command labels, exit codes and timeout flags, retained
for seven days; command output remains in the normal Actions log. Installation
failures can occur before an outcome file exists, so inspect the failed step.
Do not add raw environment dumps, tokens, packet captures or private fixtures.

Concurrency cancels superseded runs for the same workflow/ref. Quick runs have
seven jobs: two Python (20 minutes each), two Rust (25 each), two Go (20 each),
and one Node/policy (10). The configured upper bound is 140 aggregate runner
minutes before cancellation/overheads, not an observed duration or price.
Actual billing depends on GitHub's repository/account plan and runner rates.
Cold dependency setup may be slower; caches avoid repeated downloads but do not
cache compiled results. Rust/Go use two build workers, Rust two test threads.
Commands have explicit timeouts (90–600 seconds quick, 1200 manual), with
process-tree termination on timeout; manual jobs have a 30-minute ceiling.
No hosted duration or cost has yet been measured for this implementation.

## Local use and troubleshooting

```text
python scripts/ci/check.py validate
python scripts/ci/check.py python-core --list
python -m pytest -q -p no:cacheprovider tests/ci
python -m ruff check --no-cache scripts/ci tests/ci
```

Profiles are `python-core`, `python-protocol`, `rust`, `go`, `node`,
`rust-extended`, `connector-loopback` and `soak`. Local commands default to 90 seconds each; larger
timeouts are reserved for hosted CI. This runner does not install dependencies
or enforce the laptop's disk/RAM guards: local build/test supervision must still
follow `AGENTS.md`. Set the verified `CARGO_TARGET_DIR` and offline Go/Cargo
environment before any local build; never turn an offline miss into a download.
Do not run a whole profile locally if its cumulative time exceeds the authorized
cleanup-inclusive trial budget; invoke the listed commands in bounded groups.

Exit 124 means timeout with tree termination attempted successfully. Exit 125
with `timed_out: true` means tree cleanup failed and requires inspection, even
if the direct child was reaped. Exit 125 without a timeout means startup or
runner failure. Other nonzero codes are the command's failure. A timeout is
not permission to enlarge the budget or discard the result.

For dependency failures, inspect the pinned version and lockfile rather than
updating dependencies automatically. For Windows failures, compare the same
profile on Linux and inspect path, permission and socket assumptions. On an
unpublished workflow branch, manual dispatch may not be listed until GitHub
knows the workflow on its default branch; do not change the default branch or
protection to work around that. Hosted runs and their logs are the final check
of Actions schema, toolchain availability and cross-platform execution.

The structural validator checks selected security contracts, not GitHub's full
workflow schema. Local Windows checks cannot establish Linux success. CI status
is pending until a published commit has actual workflow/check results; an empty
check list is not a pass.

### Connector selection audit, October 11

Before this local correction, `tests/protocol` already discovered both connector
vector suites and `tests/federation` covered their existing neighbors. Four
root-level connector suites and the adjacent offline config suite were omitted.
Default Go `./...` excluded the build-tagged connector package. Quick Rust did
not execute its new integration targets; manual `rust-extended` executed their
nonignored tests but still ignored the live test. The Node connector verifier
was also absent. Earlier local connector pass counts are not hosted CI results.

The explicit selections above close these invocation gaps. The manual-only
`connector-loopback` choice prebuilds Rust, builds a Go worker in a fresh owned
temporary directory, and invokes exactly `isolated_go_rust_control_registration`.
Each command is directly supervised with a 90-second execution timeout plus
the existing bounded cleanup; this is not a 90-second cumulative job claim.
The worker directory is removed on normal completion or command failure, and
any prior worker environment value is restored. No wrapper launches a second
supervision layer. Hosted cancellation still depends on runner teardown.

The existing pinned Go version and module lockfiles are reused only when this
manual choice is selected; no dependency versions, permissions, secrets, runner
selection or branch safeguards change. The helper uses real loopback TLS with
ephemeral in-memory test PKI and synthetic authority/revocation inputs. It does
not establish live authority, real timers, application traffic or Stage 3 closure.
Local use still requires explicit socket/test-PKI authorization, provisioned
caches, and the laptop's cleanup-inclusive resource supervisor.

Local Windows selection/security regressions and the exact loopback profile
passed; hosted schema validation, Linux execution and the published matrix remain
unrun for this change. See `docs/reviews/2026-10-11-connector-ci-selection.md`.

The subsequent role/reuse audit adds the existing `tests/test_gateway_cli.py`
to `python-core` on both platforms, alongside its four gateway library suites.
Its seven tests exercise real CLI subprocesses for deterministic plans, unchanged
inputs, verification exit codes, resolver-last rollback plans, bounded/redacted
input rejection, explicit paths and the example profile. This is offline planning
and simulated verification, not privileged installation, service startup or live
rollback. See `docs/reviews/2026-10-11-gateway-cli-ci.md` and the role inventory.

## Release boundary

Versioned binaries and Docker images, single-instance/Kubernetes installation,
and a device Go client are future product goals. These workflows only build
and test source. Release publication needs a separate reviewed design covering
version/tag authority, reproducible artifacts, provenance/signing, registry
ownership and narrowly scoped publication permissions. It must run from an
explicitly authorized trusted release, never a pull request. No package push,
registry credential, cluster provisioning or device DNS change is configured
or authorized by this CI change. Deployment feasibility is a separate study.

## Sources and pin maintenance

Action release SHAs were resolved from the official `actions/*` repositories
on 2026-10-10: checkout v7.0.1, setup-python v7.0.0, setup-go v7.0.0,
setup-node v7.1.0, cache v6.1.0 and upload-artifact v7.0.2. Review source and
release notes before changing pins, then rerun CI regressions and a hosted run.
See [GitHub secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use),
[Ubuntu runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md),
[Windows runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md),
and the [OPA release](https://github.com/open-policy-agent/opa/releases/tag/v1.4.2).
# Approved transport source authority

The current-source gate in `tests/federation/test_baseline_immutability.py` uses
`assert_transport_lifecycle_core_overlay`. Its separately versioned authority is
`docs/protocol/registries/core-v0.2-transport-lifecycle-overlay.json`, recognizing
the reviewed `99ac954e0c0d90a221b42492a59fa4d5b962ea5d` source snapshot.
The original baseline, F75, P1/P2 and ACK authorities remain unchanged. Historical
ACK tests use their approved `94a1e4a` fixture, while the main gate still reads
current canonical source bytes.

The layer checks all 110 legacy artifacts and explicitly pins `owned_send.rs`,
`udp_socket.rs`, `benchmark_bind.rs`, `Cargo.toml` and `Cargo.lock` in the transport
crate. The six verification-source hashes in the approval proposal identify
review evidence; they are not additional runtime protocol gates. This selected
scope is not a complete build dependency closure or production certification.
Future ACK or other changes to pinned files require a new reviewed versioned
authority rather than extending this snapshot's approval silently.

Run focused authority, current-source and historical ACK tests in bounded groups
using the provisioned environment; retain failed attempts and distinguish local
validation from the hosted CI matrix. See the activation checkpoint under
`docs/reviews/2026-10-10-authority-activation.md` for measured results and limits.

Sparse local checkouts may omit committed packet evidence required by federation
tests. Inspect skip-worktree flags, sparse patterns and Git blob availability
before diagnosing missing packaging. Validate exact committed test/evidence bytes
in a temporary materialization when appropriate; preserve the original missing-
input result and do not overwrite user deletions or weaken tests. This scoped
check is not a claim that the incomplete working checkout passes the full suite.

Runner-dependent paths must be initialized at step execution time, for example
through `RUNNER_TEMP` and `GITHUB_ENV`; GitHub does not expose the `runner` context
in job-level `env`. Local contract validation catches this known error but is not
a full hosted schema check. The first published run failed before job creation;
see `docs/reviews/2026-10-10-hosted-ci-d4ca54eb.md` for the preserved result.

Node verification includes a Python vector-generator subprocess and therefore
requires the constrained project runtime, not just a Python executable. The
prepared setup uses `python -m pip install --constraint constraints/runtime.txt
-e .` on the hosted runner. This does not authorize local dependency downloads.
The first executing matrix's three successes and four failures are retained in
`docs/reviews/2026-10-10-hosted-ci-9ac925df.md`; the Node setup correction is still
unpublished, and the Linux diagnostic/fixture and Windows ACL failures remain.

The subsequent local portability patch is documented in
`docs/reviews/2026-10-10-ci-portability.md`. It preserves alias rejection across
filesystem diagnostics, uses the existing platform-specific Go fixture hierarchy,
and replaces the complete ACL only on test-owned enrollment directories. It does
not relax production ACL validation. Native Linux and hosted rerun remain required.

Run 38054824820 at 2251ea95 subsequently passed Python/Rust on both platforms and
Node/policy; both Go jobs failed. The Linux federation trust-anchor mismatch is
an authority/version decision, not a pin to refresh for CI. The local Windows
storage fixture follow-up canonicalizes only newly created test-owned roots and
retains production alias rejection. Its short-name regression and authority
package pass locally; the hosted path cause and fix remain unconfirmed. See
`docs/reviews/2026-10-10-go-hosted-diagnosis.md` for exact boundaries and evidence.


The approved local federation version split restores original v1 package bytes
and retains its default selection and independent pin. CI explicitly checks the
separate v2 through Python, Go and Node commands; their default invocation rejects
v2. Both version suites remain required. V1 reads its exact archived development
registry; v2 uses the already approved current registry. See
`docs/reviews/2026-10-10-federation-version-approval-scope.md` and its implementation
JSON for pins, exact verification and limits. Local success does not establish a
hosted pass; no publication or workflow security changes are part of this change.

The Rust connector group also selects `--test connector_signature`, a test-only
exact COSE signature prerequisite with retained public single/threshold signature
inputs. The Python protocol group runs
`python -m scripts.extract_connector_signature_fixtures --check`; extraction uses
existing signed bytes and generates no keys or signatures. Neither check grants
registration authority or establishes threshold/governance acceptance. The
development registry remains runtime/live-trust disabled. See
`docs/reviews/2026-10-11-registration-full-model-acceptance.md` for the complete
security obligations and unresolved runtime gates. Local results are not hosted
CI evidence.

## Normal revocation local conformance

The python-protocol profile runs `python -m scripts.normal_revocation_conformance --check`
and selects `tests/federation/test_normal_revocation_conformance.py`
through the federation suite. It verifies the separate versioned amendment and
retained vectors using existing public fixture material. It does not activate
runtime trust, prove real membership/witness provenance or replace hosted results.

The same federation suite selects `test_normal_revocation_witness_integration.py`,
which composes existing signed checkpoint/consistency/witness verifiers with the
normal record reference. It proves fixture-configured checkpoint confirmation,
not record inclusion, real trust provisioning or durable restart protection.

The separate approved v2 inclusion amendment is selected through
`test_revocation_inclusion_v2.py` and the `revocation-inclusion-v2` command
(`python -m scripts.revocation_inclusion_v2 --check`). It adds full-record inclusion
under fixture configuration; historical profile defaults/literals remain unchanged.
Real provenance, durable restart protection and runtime activation remain outside CI's local claim.

The explicit `inclusion-persistence-local` command runs
`tests/federation/test_inclusion_persistence.py` with pytest and no cache provider.
It exercises the approved snapshot/recovery coordinator using a memory backend;
it performs no private filesystem writes or ACL changes. It also remains selected
by the federation suite. Successful local execution does not establish hosted
success, real filesystem crash recovery, trusted restart floors or power-loss
durability. Windows private-write integration requires separate authorization.

The Rust connector command also selects `connector_authority`, a test-only native
normal negative-enforcement bridge into a fixture-created owner. Python-protocol
selects its federation test and the `connected-authority-vectors` command
(`python -m scripts.check_connected_authority_vectors --check`). Explicit supplied
test trust, dependency membership, same-record replay and retained cleanup are
local conformance inputs; this adds no positive registration authority or READY.
The retained prior anchor is identity-bound; freshness applies to the current
containing checkpoint. Local test success is not hosted CI or runtime governance.

The Rust connector command selects `connector_kar` and `connector_genesis`,
isolated test-only KAR and NOR/direct-delegation prerequisites. Retained public
signed positives and negatives complement explicitly unsigned semantic probes;
the native targets create no keys/signatures and perform no live execution.
The bounded genesis chain checks supplied purpose5/6 signer context, ordinary
LDH names, service IDs, inclusive validity and scope narrowing. ACE, updates and
other recognized out-of-slice features remain unsupported, not authorized.
These checks do not establish provisioning, full governance, registration
readiness or hosted CI success. See the 2026-11-14 evidence reviews.

## Private connector dispatch regression coverage

The default `rust` profile additionally executes four exact, single-threaded cases
on both Ubuntu 24.04 and Windows 2025: the two `connector_refusal_tests` binary
unit cases, `connector_mode_refuses_through_private_route_wrapper_before_supervisor`,
and `main_connector_function_relays_positive_federated_credit` in `demo_backend`.
These are execution gates, not just the existing all-target Clippy compilation.
The Rust jobs prepare pinned Go 1.26.5 and verify the demo module dependencies
before testing; the backend build then runs with `GOPROXY=off` and read-only module
flags. Existing checks, per-command bounds and workflow permissions are retained.

The cases cover unavailable connector refusal without direct fallback and an
unchanged direct demo relay, using local fixture authority and loopback transport.
They do not authorize a positive connector producer, real identity provisioning,
SPHERE activity or a load benchmark. Other `demo_backend` tests remain outside
this focused default addition; the manual extended profile is not automatic.
Confirm the named tests actually ran in the hosted log: local results and a green
Clippy step are not hosted execution evidence for these cases.

## Performance Lab source checks

The independent `.github/workflows/performance-lab.yml` job selects the Performance
Lab pytest suite, frontend Node regressions, and locked npm typecheck/build on
Ubuntu. It uses the package's own dependency pins; existing project jobs are unchanged.
See [scope and limits](../tools/performance-lab/docs/ci.md). No live source collection,
real evidence import or benchmark is selected; hosted acceptance is separate.

## Offline security-result contracts

The automatic Python core profile runs the seven adversarial campaign manifest,
result-schema and result-analysis tests on Ubuntu and Windows. This selects
`tests/security/test_adversarial_campaign.py`, not the campaign runner. It does
not run attack scenarios, compile peers or establish live security coverage.

## Offline Name Node adapters

The Python core profile also selects the existing Name Node DNS-adapter and
observability suites on Ubuntu and Windows: seven synthetic-route/lifetime cases
and twelve bounded-label, privacy and observer-failure cases. They use in-memory
fixtures and fake clocks, not live DNS, socket servers or timing measurements.
The separate Name Node server and end-to-end route tests remain outside this
addition and require their own effects and resource review.

## Demo fixture generator

The Go profile includes the standard-library-only `tools/demo-lab/fixturegen`
module in test/vet and dependency-manifest checks on Ubuntu and Windows. Its
two tests generate certificates/keys only in test-owned temporary directories,
verify identity/expiry and non-overwrite rules, and reject unsafe output paths.
POSIX permission assertions run only outside Windows; the symlink rejection
case can skip where symlink creation is unavailable. This is fixture generation
coverage, not enrollment, deployment or connector readiness. Generated private
material is not uploaded or cached; existing dependency-only cache rules remain.

## Private carrier transport fixture

The default Rust profile executes `private_carrier_refusal` serially on Ubuntu
and Windows, rather than relying on compile-only Clippy. The two tests cover
strict fixture peer-key extraction and a private mutual-TLS Quinn loopback with
an empty stream, owner-bound fixture evidence and authority refusal. Ephemeral
CA/keys remain in memory; no registration or application payload is sent.
This is a transport primitive fixture, not authenticated operator/principal
mapping, runtime registration, reconnect, production cleanup or READY. The
fixture has operation/endpoint bounds and the existing profile supervisor;
its failure-path cleanup branches are not exhaustively exercised. No SPHERE,
external endpoint, deployment credential or throughput workload is selected.

## Static deployment security contracts

The default Python core profile runs `tests/test_deployment_tls.py` and
`tests/test_kind_security.py` on Ubuntu and Windows. These twelve existing cases
read tracked Compose, Envoy, kind manifests, configuration and bootstrap/probe
script source. They assert loopback bindings, declared mutual-TLS settings,
trust-boundary separation, pinned images and named network-policy/probe contracts.
They do not execute those scripts, start Docker/Kubernetes, connect to endpoints,
or prove live TLS or network-policy enforcement. No deployment credentials,
additional services or throughput workloads are introduced.

## Snapshot codec subset

The default Python core profile selects four exact node IDs from
`tests/test_wp6_continuity_snapshot.py` on Ubuntu and Windows (eight parametrized
cases): canonical round-trip/digest stability; malformed, unknown, missing,
corrupt, unsorted or duplicate state; noncanonical/partial/oversized input; and
sorted unique bounded-majority replica configuration. These are in-memory
prototype codec/configuration checks, not consensus or authority validation.
The snapshot file is deliberately not selected wholesale: repository persistence,
rollback/lock/concurrent-writer, symlink and independent file-verifier tests remain
outside this addition pending their own effect/cleanup review. Those other cases
can write temporary files, create threads and invoke Windows ACL helpers; none of
those operations is exercised by these four selected node IDs.

## Legacy-origin cache model

The default Python core profile executes `tests/test_legacy_origin.py` on Ubuntu
and Windows (32 parametrized cases). Supplied synthetic DNS snapshots, explicit
timestamps and validator callbacks exercise normalization/bounds, cache freshness
and grace, bounded retry scheduling, sequence/digest chaining, equivocation,
hard-failure invalidation, tombstones and capacity refusal. These tests perform no
DNS queries, network connections, subprocesses or file persistence. DNSSEC status
is fixture input, not cryptographic validation; scheduling is numeric state, not
a live retry loop. Passing this model does not establish resolver interoperability,
authenticated discovery or production authority. Live Name Node/server end-to-end
tests are not enabled by this addition.

## In-memory NameRouteService checks

The default Python core profile runs `tests/test_name_service.py` on both platforms
(14 cases). Tests use generated ephemeral keys, inline fixture route policies and
in-memory synthetic-address pools. They check response privacy, invalid names and
client keys, allocation preservation, capability validation and mapping lifetime.
A separate valid-HTTP/443-only-policy regression checks the registered-port guard
before admission accounting, address allocation or binding signing; the invalid
capability test remains separately named. No real resolver, listener, system route
or network connection is started, and generated keys are not written to files.
This does not establish live routing, authenticated operator authority or READY.

### WP7 audit and privacy model subset

The default Python core profile selects ten exact WP7 conformance functions (eleven parametrized cases). They exercise bounded operator-owned audit logs, sequence exhaustion, admission preflight, private-destination redaction, receipt linkage resistance, closed topology and duplicate JSON-member rejection. The connector and raw-scan operations here are deterministic in-memory models with supplied authority and time inputs, not network operations. The config-file check and subprocess-based verifier remain outside this subset. These cases do not establish live connector security, authenticated authority provenance or production readiness. A selector contract rejects broad whole-file admission and preserves the exact subset.

### Legacy demo client security contracts

The default Python core profile runs the four contracts in `tests/test_demo.py`: signature-byte tampering, static wrapper TTL settings, and HTTPS/enterprise-CA parameters for the two demo clients. HTTP calls and the container client are mocked; the dummy identity token is test-owned temporary data. Neither the Docker-containing demo entry point nor a live service is executed. These checks protect request configuration, not actual TLS verification, network isolation or deployment readiness.

### WP4 deterministic exporter vectors

The default Python core profile runs both WP4 exporter-vector tests. They independently recompute canonical context encoding and HKDF outputs from public deterministic fixture secrets, and verify the mutation artifact inventory. The generator runs only with `--check`, under a 30-second subprocess timeout: it regenerates into its own temporary directory and compares the tracked package without rewriting it. It starts no network service or descendant process. Normal completion cleans its temporary directory; a forced timeout does not guarantee removal of temporary files. These tests do not exercise a real TLS exporter or establish live channel binding.

### Offline release packaging contracts

The default Python core profile selects seven release-packaging contracts: static runtime/container pins, exact constraints, explicit-ref wrappers, Git executable delegation, prohibited-path and secret-shape redaction, deterministic inventory/ZIP output, and ignore-file policy. Git execution is mocked and archive tests use only two temporary fixture files. The release builder, Docker and network operations are not invoked. These checks do not certify an actual release artifact or exhaustive detection of sensitive content.

### Frozen wire documentation and stable API contracts

The default Python core profile selects three exact functions from `tests/test_documentation.py`: required wire-contract scope/non-claims, frozen numeric mappings and schema-table alignment, and the stable Protocol Core public export surface. These perform static document reads and an in-process protocol import. Historical PDF/link checks and the rest of that file are not selected. String/table consistency and export membership do not establish wire implementation conformance, authenticated provenance or production readiness.

### Transport fixture index ownership

Python core selects only the certificate-fixture filename policy from the transport-isolation file, plus its isolated inventory regressions. The policy uses read-only `git ls-files -z` scoped to the crate with a 10-second direct-child timeout, strict path validation and a required tracked Cargo manifest. Git failures, timeouts and malformed/empty inventories fail rather than silently pass. Untracked build output is excluded; sparse tracked names remain visible. This is an index filename policy, not a HEAD/history audit or secret-content scan. Captured output size is not independently capped. The Windows-specific Cargo metadata test and other transport tests remain excluded; no Cargo build or live TLS is added to Python CI.
