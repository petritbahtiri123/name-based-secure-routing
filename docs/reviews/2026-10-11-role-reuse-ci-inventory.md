# Role reuse and CI acceptance inventory

Read-only implementation/workflow inspection after the positive-revision fix.
No builds, service operations, network trials, deployment or hosted dispatch were
performed for this inventory. Existing local work is preserved. The role map
below describes reuse candidates and approved boundaries, not a new server spec.

| Role | Existing implementation/evidence to reuse | Current CI selection and limit |
|---|---|---|
| Device Go client | `client/nbsr-go-client/internal/{identity,authority,corestate,resolution,session,retry,observability}` and `streamclient`; explicit proxy under `internal/adapter/proxy` | Existing Go module test/vet on Windows and Linux selects these packages. Windows storage tests are platform-specific; unsupported platforms skip secure storage. No full deployed client claim. |
| Windows service identity/storage | `client/nbsr-go-client/cmd/enrollment-storage-scm-gate/main_windows.go` and test; `docs/protocol/tranche2b-implementation-status.md` records STORE and two fresh-process LOADs under `NT SERVICE\NBSRClient`, exact identity recovery and `Ready=false` | Windows Go `./...` selects the deterministic fixture/marker test. It does not install/start/restart the SCM service. Historical elevated evidence is real but was not repeated here; the different-identity negative remains explicitly unexecuted in that record. |
| Resolution to connection | `internal/resolution/{router,flow,runtime_binding}.go` and tests; `internal/session`, `streamclient`; nested demo `internal/client` and `cmd/nbsr-demo-client` | Both Go modules are selected. `TestFullTask4RealSecureRoute` requires `NBSR_TASK4_RUST_BINARY`, `NBSR_TASK4_BACKEND_BINARY`, `NBSR_TASK4_AUTHORITY_DIR`; current workflow does not provision them, so that process acceptance test skips. Fixture integration tests still execute. |
| Name/control-plane services | Python `nbsr/name_node.py`, `name_node_server.py`, `name_relay.py`, `control_plane.py`, route registry; nested Go demo authority command | Explicit Python core profile selects name/control-plane/registry tests; demo Go tests are selected. Python FastAPI route-ticket control and demo authority are existing reference/fixture components, not automatically the production authority provider. |
| Source/destination Edge and connection ownership | Rust `admission.rs`, `session.rs`, `channel_registry.rs`, `channel_lifecycle.rs`, `channel_streams.rs`; `src/bin/wp8_interop_server.rs`; Go source session libraries | Rust quick library/selected integration tests and manual extended suite cover existing boundaries. The interop server is a reusable test/demo assembly, not proof of a packaged production server. Approved connector seam assigns registration/quota/cleanup to Rust destination, outbound attempts/renewal to Go origin. |
| Customer-network origin connector | Development-tagged `interop/nbsr-go-peer/connector`, Rust test-only connector modules; approved profile and retained 19-case loopback evidence | Tagged Go test/vet, Rust connector targets and Node vectors are now selected locally. Live connector test remains ignored in quick CI and has an explicit manual profile. Real authority/revocation/timer providers and origin forwarding composition are not established by this harness. |
| Deployment envelopes | `deploy/kind/{cluster,nbsr}.yaml`, `gateway/envoy.yaml`, `deploy/isp-federation-poc/adapter`, Python gateway plan/profile/journal/verify; WP5 Linux packaging decision | ISP adapter Go test/vet and Python gateway unit tests are selected. Kubernetes apply, privileged routing, cloud/ISP installation and multi-host acceptance are not run by these profiles. WP5 evidence is declarative/simulated; deployment location does not itself change protocol roles. |

## Proposed terminology for the existing plan

Use **device client**, **Name/Resolution service**, **source Edge**, **destination
Edge/gateway**, **authority/control-plane provider**, and **origin connector**.
The architecture vision defines source Edge as owning the synthetic traffic
path/source correlation and destination Edge as independently admitting access
to an authorized connector or origin. Connection/session management is already
distributed among the Go source and Rust destination libraries; it is not evidence
that a separate connection-manager daemon should be created.

“NBSR Server accepts requests and manages connections” could refer to destination
Edge transport, the Name/control-plane service, or their packaging. Do not merge
these trust boundaries based on that phrase. Whether a product process combines
them, and which deployment profiles are supported first, remain review decisions.
Kubernetes, ISP and cloud are possible hosting contexts, not three newly specified
protocol roles. The first ten-stage plan remains one service/one Docker host.

The remembered Windows service work is present and should be reused. Its SCM
storage gate does not contradict the demo limitation “no Windows service”: the
demo client has no complete installed-service lifecycle. Neither statement should
be expanded into absence of all service work or completion of a deployable client.

## Missing acceptance gates by stage

| Stage | Existing selection/evidence | Remaining CI or acceptance gate |
|---|---|---|
| 1–2 | Contract/vector suites and strict offline config are selected; scoped completion remains 2/10 | Hosted confirmation of the current unpublished selection and config changes; fixture provenance must remain explicit. |
| 3 | Go/Rust development tests, signed/timer fixtures, manual isolated TLS control loopback | Compose approved authority providers with real runtime ownership and truthful readiness; validated revocation producer packaging/threshold remains a design gate. Do not claim local/manual loopback equals a hosted pass. |
| 4 | Existing retry, lifecycle, quota, drain and cancellation unit/integration evidence | Provider-backed disconnect, expiry/revocation and backpressure matrix with confirmed cleanup or visible retained ownership. Reuse current tests, add composed cases after Stage 3 bindings exist. |
| 5 | Existing explicit-proxy and secure-route demo, but full Task 4 process test is environment-gated | A separately scoped job that builds/provisions the existing fixtures and actually executes its negative/positive path; then verify one-origin connector composition and zero origin traffic on rejection. No setup was activated here. |
| 6 | Identity/storage, resolution, session and fixture authority libraries; historical SCM storage restart | Real configured provider/trust composition, readiness and clock behavior. Windows end-to-end installed-service start/stop/restart/shutdown and different-identity storage rejection need scoped machine acceptance; ordinary Go unit CI does not supply it. |
| 7–8 | Declarative Linux gateway model, Kubernetes manifests, ISP adapter, demo packaging foundations | Authorized package/container build, bounded startup/shutdown, two complete cycles, rollback and zero residuals. Target-specific Kubernetes/ISP/cloud smoke gates only after supported deployment profiles are selected; no production inference from manifests. |
| 9–10 | Earlier enrollment/storage primitives and conformance evidence are reusable | Explicit provisioning/custody/rotation/recovery, real installation and bounded customer pilot on approved infrastructure. These are not ordinary untrusted-PR CI jobs and need separate authorization. |

No new CI wiring is proposed blindly in this read-only inventory. The prior
connector-selection patch remains the current local change; its hosted execution
is unverified. The most concrete additional coverage omission is the existing
environment-gated full Task 4 process test, followed by explicit SCM machine
acceptance. Both should reuse existing harnesses under separately reviewed setup
and cleanup scopes, not install services in routine unit tests.

Authorized follow-on: a separate bounded patch now selects the seven existing
gateway CLI tests that were missing beside their library neighbors. See
`docs/reviews/2026-10-11-gateway-cli-ci.md`. This closes only the offline CLI
invocation gap; the SCM and full Task 4 acceptance gaps above remain unchanged.

Inspection limits: the SCM success above is attributed to its retained status
record, not revalidated original machine artifacts. Missing README probes under
the Go client and ISP deployment returned file-not-found; inspection used actual
source, tests and protocol records instead. No claim that all repository tests or
all possible deployment profiles were audited.
