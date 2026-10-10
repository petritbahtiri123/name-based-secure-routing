# Single-instance operator package implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement one
> approved, bounded task at a time. This is a proposed plan, not approval of new
> protocol semantics, platform identity design, credentials or publication.

**Goal:** An operator can configure one existing private HTTP service on one
Docker host and an enrolled device can reach its NBSR name through an explicit
Go proxy, with bounded startup, shutdown, restart and rollback behavior.

**Architecture:** Two logical operator roles remain distinct even on one host:
the Source Operator enrollment/authority service and the authenticated
destination transport/connector. A native device client owns identity,
freshness, sessions and the loopback explicit proxy. The origin address exists
only in operator-side configuration. Reuse the frozen authority and transport
interfaces; do not turn the demo fixture assembly into production by renaming it.

**Tech stack:** Existing Go client/authority libraries, Rust/Quinn transport,
stdlib Go origin connector, Docker Compose. No new runtime dependency is
proposed for the first patch.

**Spec:** Petrit's 2026-10-10 delegated brief and the proposed scope below;
the repository's approved protocol documents remain authoritative. This plan
is a decomposition for review, not a replacement protocol specification.

## Scope and constraints

- User-selected topology: the first service is inside the customer's private
  network. For a product requiring no inbound port forwarding, propose a new
  authenticated outbound reverse connector from that network to a reachable
  edge. Its design must cover service registration, reconnection, revocation
  and bounded resources. The existing per-request origin child is not this
  capability. Resolution remains a control-plane lookup; client traffic goes
  to the resolved edge. This is a design proposal, not implemented behavior or
  permission to configure real networks. Defer implementation until the CI
  authority review checkpoint; patch 1 below alone cannot deliver this topology.

- First service profile: one operator-configured private HTTP endpoint,
  initially the existing bounded `GET /` profile. This does not yet support
  arbitrary web applications, streaming, WebSocket, POST, HTTPS-to-origin,
  arbitrary paths or responses larger than 4096 bytes.
- Suggested first target: Linux Docker operator host plus native Windows
  explicit client, because Windows enrollment-state persistence exists.
  This is a platform proposal, not a claim that a production Windows signer
  or installer is complete. Linux/macOS device clients require separate
  persistent-identity work; do not add plaintext or ephemeral fallback.
- Preserve Core/F75/P1F/P2D, initial-enrollment-only semantics, signer purposes,
  independent grant verification, freshness and the authority-generation floor.
- No new package implementation is mixed into CI commit `f6400959`. Its clean
  federation authority mismatch remains a separately scoped blocker; see
  `docs/CI_VALIDATION_2026-10-10.md`.
- No public image/binary publication, registry credentials, credential
  generation, machine security changes, device DNS/routes or paid deployment
  are authorized by this plan. A future installer/service-account test needs
  its own explicit machine-level authorization.
- Local checks use existing caches, offline dependency settings, at most two
  workers, 95-second work cutoff/120-second cleanup budget, 8 GiB starting disk,
  6 GiB floor, 2 GiB disk-growth stop and 2 GiB RAM reserve. No Docker startup
  is needed for patch 1.
- Kubernetes, transparent routing/TUN/DNS, multiple origins, HA and WAN capacity
  are later gates. A single-instance acceptance result establishes none of them.

## Repository evidence and actual gaps

| Area | Existing implementation | Gap for the requested package |
| --- | --- | --- |
| Origin connector | `deploy/isp-federation-poc/origin-connector/main.go`: fixed `private-origin:8080`, exact `service-a.nbsr.test:8080`, `GET /`, 4096-byte request/response caps, 3-second operation, one private IPv4 result and literal-address dial | Target/name/port are fixture constants; only status 200 and complete bounded response accepted. It is a stdio child per request, not the architectural outbound-connector state machine. |
| Runnable topology | `deploy/isp-federation-poc/compose.yaml`, `Dockerfile`, `supervisor.py`: seven-service isolated PoC, bounded children, non-root/read-only containers, immutable local image inputs | Builds/imports demo and test fixtures; generated runtime paths and per-run state are unsuitable as durable operator installation. Do not ship its workload/private-origin fixture as the user's service. |
| Explicit Go access | `client/nbsr-go-client/internal/adapter/proxy`, `internal/resolution`, `internal/session`; demo assembly supplies a loopback proxy and secure-route owner | Runnable assembly in `demo/internal/client/assembly.go` uses fixture bootstrap, fixed `NowUnix`, synthetic identity/state values and demo service inputs. A non-fixture composition root and config are missing. |
| Enrollment and ACP | `internal/authority/runtime.go`, `source_operator_runtime.go`, HTTP clients and file idempotency store implement frozen interfaces | Operator CLI, configured issuer/key providers, transactional bootstrap authorization and real policy/initial-enrollment adapters must be supplied. Inspected concrete enrollment/bootstrap implementations in this runtime area are tests. |
| Device persistence | Windows `storage_windows.go` and `enrollment_state_windows.go` validate paths/ACLs, lock state and use DPAPI for the integrity blob; `ClientRuntime.StartPersisted` requires fresh validation before Ready | Non-Windows implementations return `ErrStorageUnsupported`. Durable enrollment state contains a device key reference; it does not by itself supply a persistent device signing-key provider. `internal/identity/signer.go` labels `MemorySigner` test-only. |
| Destination process | `crates/nbsr-transport/src/bin/wp8_interop_server.rs` has runtime-admission and hashed demo-backend-map seams | Interop readiness/credential handling and demo service/launcher restrictions are not a non-fixture operator entrypoint. Avoid exposing credential-bearing readiness as health output. |
| Health/lifecycle | PoC supervisor watches owned children and terminates/waits/kills them; health script checks files/listening sockets | Health file existence is not current authority readiness or end-to-end route success. Durable restart, fresh readiness, operator shutdown and rollback need package-level proof. |

Historical design READMEs and status headers contain older “not started” claims;
the Tranche 2B implementation ledger and current source show substantially more
library implementation. Conversely, those library results do not prove a
deployable non-fixture product. Preserve historical evidence; reconcile only
documentation directly touched by each subsequent patch.

## Approach selection

1. **Recommended: build out the existing bounded connector and production library
   seams, then add a separate operator composition root.** Small local tests can
   establish each boundary; existing PoC remains an explicit regression control.
2. Package the current seven-service demo unchanged. This is quickest for a
   demonstration but does not meet real-service, durable-identity or non-fixture
   requirements, so it is not the operator package.
3. Implement a general outbound connector, all device platforms and Kubernetes
   together. This introduces several architectural contracts and is deferred.

## Review focus

- Untrusted request names/headers must never select an origin or extend network
  reach. Invalid input must cause zero resolution/dial attempts.
- DNS ambiguity/rebinding and configuration mistakes must fail before origin
  access; dial only the validated literal private address.
- Missing/corrupt/wrong-user identity and expired freshness must keep the device
  unready, including after restart. No identity regeneration fallback.
- Crash or shutdown during an in-flight request must not replay an ambiguous
  operation or leave an owned child/connection running.
- Rollback/uninstall must not erase or roll back authority floors, identity,
  unrelated resources or operator data. Unsupported state versions fail closed.

## Patch 1 — configurable bounded private-origin target (proposed next patch)

**Files:** Modify `deploy/isp-federation-poc/origin-connector/main.go` and
`main_test.go`; document the new opt-in contract alongside
`PRIVATE_ORIGIN_FIXTURE.md`. Keep Go source in the existing compiled file so
the Dockerfile's explicit `main.go` build does not silently omit a new file.

**Interfaces:** Add `parseOriginConfig(raw []byte) (originConfig, error)` and
`runConfigured(ctx context.Context, input io.Reader, output io.Writer,
config originConfig, resolver resolver, dialer dialer) error` in `main.go`.
Keep the existing `run(..., cidr string, ...)` as a legacy fixture wrapper,
so existing callers retain exactly their old behavior.

The proposed local-only schema `nbsr-origin-config-v2` has exactly
`schema`, `private_cidr`, `service_authority`, `origin_host`, `origin_port`.
The current `nbsr-isp-origin-config-v1` remains accepted with exactly its two
fields and maps to the current constants. No v2 field may be silently defaulted.
Keep the 1024-byte config cap and reject duplicate/unknown keys, trailing JSON,
missing fields, noncanonical private IPv4 CIDR, zero/out-of-range port, and
invalid authorities/hostnames. Define hostname syntax as lowercase ASCII DNS
labels (1–63 characters each, total at most 253, alphanumeric ends, internal
hyphens permitted), no trailing dot, IP literal, scheme, path or userinfo.
`service_authority` is that name plus an explicit decimal port 1–65535.

Keep existing request/response limits, method/path, success-status and deadlines.
Forward the validated request unchanged; upstream virtual-host rewriting and
TLS are separate later features. An operator's selected origin must accept the
configured presentation Host for this first profile.

- [ ] Add `TestOriginConnectorConfiguredPrivateTarget`: configure
  `reports.private.example:8080` to `reports-backend:9000` within `10.42.0.0/24`.
  An injected resolver returns `10.42.0.7`; a recording dialer backed by an
  in-memory connection must see exactly `tcp4`, `10.42.0.7:9000`, once. A complete
  small 200 response is returned byte-for-byte. The existing constants cannot
  satisfy this test, establishing a meaningful RED before implementation.
- [ ] Add table regressions for malformed/duplicate/unknown configuration;
  wrong Host/method/path and body framing; zero/multiple/out-of-CIDR answers;
  oversized/incomplete/non-200 responses; cancellation and origin timeout.
  Invalid configuration/request must produce no resolver/dialer call and no
  response bytes. Resolution rejection must produce no dial. Closed connection
  and bounded completion must be asserted for cancellation after the origin
  dial; changing the arbitrary input-reader lifetime is outside this config patch.
- [ ] Verify v1 produces the same fixed target/authority and retains existing
  negative tests. Do not use v2 to relax the old fixture configuration.
- [ ] Run focused RED, implement only the config/target seam, run focused GREEN,
  neighboring connector tests and scoped review. From the connector directory:
  `go test -mod=readonly -p=2 -timeout=30s main.go main_test.go` and
  `go vet -mod=readonly main.go main_test.go`, using provisioned offline caches.
- [ ] Report exact results before broader wiring. This patch alone does not
  claim NBSR end-to-end delivery, enrollment, production readiness or a package.

## Ordered gates after patch 1

Each gate below is a separate design/test-backed patch series. Interfaces that
change authority or persistent key handling require scoped design review before
implementation; do not infer their approval from the connector patch.

### 2. Define and validate a non-fixture installation contract

- [ ] Create `deploy/single-instance/config.schema.json`, a secret-free example,
  `validate_config.py` and `test_validate_config.py`. Version the operator role,
  approved profile/issuer references, one service identity/name mapping, endpoint
  bindings, mounted secret references, persistent directories and image digests.
  Origin target fields belong only to the destination-side config. A standalone
  `check-config` operation must perform no network access, writes or credential
  generation. Keep the explicit-proxy client config origin-free.
- [ ] Acceptance: malformed, duplicate, unknown, fixture-marked and incomplete
  inputs fail closed; absent secret references fail preflight without printing
  values; a supplied valid one-service configuration passes without starting
  Docker. Define the schema and migration behavior before adding live consumers.

### 3. Close the identity and enrollment deployment decisions

- [ ] Specify the native Windows persistent device signer behind
  `identity.Signer`, distinct from enrollment-state integrity protection.
  Review purpose separation, Ed25519 compatibility, account binding, key
  references, recovery and non-export/logging behavior. Do not silently choose
  plaintext, `MemorySigner`, machine-scoped DPAPI or a different identity model.
- [ ] Supply configured Source Operator implementations for
  `BootstrapAuthorizer`, `InitialEnrollmentService`, request-key resolution and
  result signing. Reuse transactional idempotency; no auto-approve enrollment
  and no implicit reenrollment operation. Operator provisioning is explicit and
  consumes separately authorized credentials rather than generating them on boot.
- [ ] Acceptance: one initial-enrollment winner; replay/ambiguous restart remains
  closed; corrupt or other-account state fails; exact identity survives two
  process restarts; Ready stays false until fresh ACP validation. Non-Windows
  clients explicitly report unsupported persistent storage. Service/ACL tests
  are a later authorized gate, not actions for this laptop now.

### 4. Add non-fixture operator and client composition roots

- [ ] Proposed entrypoints: `client/nbsr-go-client/cmd/nbsr-operator` and
  `cmd/nbsr-client`, with small new internal config/runtime adapters that reuse
  `authority.ClientRuntime`, `NewSourceOperatorRuntime`, resolution, session and
  proxy ownership. Preserve demo modules and their regression fixtures.
- [ ] Use a real injected clock, independently verified service/authority inputs,
  configured TLS trust, real signer providers and explicit endpoints. A client
  proxy may listen only on loopback in this first package. No origin address,
  bypass route or fixture fallback enters client configuration.
- [ ] Add a separately reviewed destination operator entrypoint/config consumer
  around the Rust transport, preserving runtime-admission validation and the
  exact service-to-connector binding. Do not relabel `wp8_interop_server` or
  expose fixture credential/readiness blobs to clients or health consumers.
- [ ] Acceptance: valid enrollment and authority permit one exact name/port;
  wrong service, revoked/expired grant, stale generation and unavailable ACP at
  restart fail closed. No private-origin request occurs before admission.
  Persist no live grants, sessions, channels, credits or streams across restart.

### 5. Establish live health and bounded lifecycle

- [ ] Add runtime-owned liveness/readiness state: config and persistent store
  loaded, trusted identity active, required listeners serving and current
  authority ready. Remove readiness on child loss, fatal store failure or
  freshness loss. Files/ports alone are not readiness or proof of authorization.
- [ ] Bound SIGTERM shutdown within a proposed 15-second container grace:
  withdraw readiness, stop new admissions, drain for at most five seconds, then
  cancel/reap remaining owned work. Preserve durable identity/idempotency/floors.
  Surface nonzero failure if cleanup cannot be established.
- [ ] Acceptance: kill each owned component, withhold origin progress and stop
  during a request; no stale Ready, duplicate request retry, surviving child,
  occupied listener or leaked quota. Restart requires fresh validation. Keep
  diagnostic fields bounded and free of keys, bodies and origin details.

### 6. Package one Docker-host installation

- [ ] Add separate `deploy/single-instance/compose.yaml`, Dockerfiles and runbook
  consuming the validated config and externally provisioned secrets. Prefer
  separate authority and destination roles; the connector is an owned child of
  the destination role, and the private service already exists outside the
  package. Do not include a synthetic workload or origin fixture in the shipped
  path. Final image/process split follows gate 4 interfaces.
- [ ] Use immutable local/approved image references, non-root/read-only runtime,
  bounded resources, scoped writable state, a private origin network, only the
  required authenticated ACP/QUIC ingress, and no Docker socket mount. No build
  step runs on normal startup. Publishing images remains separately authorized.
- [ ] Acceptance in an authorized disposable environment: install from an empty
  package-owned directory using supplied identity material, enroll the explicit
  client, reach one real private test service by NBSR name, and show the same
  client cannot directly reach the origin. Wrong-name and unauthorized requests
  must leave the origin request counter unchanged. Retain source/image/config
  hashes and cleanup evidence; no throughput claim.

### 7. Make stop, uninstall and rollback predictable

- [ ] Record exact package/project/resource ownership and state/config versions.
  Stop/uninstall removes only the package's running resources; preserve durable
  identity and state by default. Explicit destructive purge is a separate action.
  Repeated stop/uninstall must be idempotent and leave unrelated resources intact.
- [ ] Roll back compatible image/config versions without rolling back signed
  authority floors or reusing old live authority. An older binary that cannot
  safely read current state must refuse startup. Design migration/backups before
  introducing a state-schema change; do not restore stale state to force success.
- [ ] Acceptance: interrupted install leaves no half-ready runtime; restart uses
  the same identity; an upgrade failure returns to the prior compatible image
  with fresh ACP validation; an incompatible rollback fails closed; unrelated
  volumes/networks/files survive uninstall.

### 8. Release and later platform gates

- [ ] Only after clean-checkout CI and one-service acceptance, design versioned
  binary/image publication, provenance, signing and registry permissions as a
  separate release workflow. No credentials or publication job is part of CI.
- [ ] Next decide Linux/macOS native identity persistence, then Kubernetes
  lifecycle/storage/network policy. Treat transparent device DNS/routing as a
  separate platform integration with its own bypass and uninstall proofs.

## Handoff

The next proposed implementation is **patch 1 only**, with the configured-target
success test and zero-dial negative cases above. No operator-package code,
credentials, containers, services or platform settings were changed while
preparing this plan. Review the service profile and initial platform proposal
before implementing the broader package gates.

## Recovered original direction (2026-10-10; proposals only)

This addendum preserves the preceding plan as history. Published source is
`fb587d76fe2cf691a9caa9c278f4db4da46298b4`, verified by CI run38060957353 (7/7).
The earlier configurable one-request target patch is supporting work; it cannot
by itself deliver the original persistent outbound role. No runtime or deployment
approval is implied by this addendum.

### Recovered sources

The parent supplied the July26 statement: “Origin connector-i krijon tunnel
outbound drejt destination gateway-it.”
[Original statement](https://chatgpt.com/c/6a625ce1-f75c-83eb-93fd-7e868470b36e?messageId=4c575030-d0a1-5b37-b5da-b658880e2832).
[Topology context](https://chatgpt.com/c/6a625ce1-f75c-83eb-93fd-7e868470b36e?messageId=cef2b71a-eaf5-495b-9790-21d3b86b8bb7)
separates name resolution and tunnels, with clients/servers behind distinct
gateways and ideally no public address or inbound service port on the origin.
[NBSR Node packaging](https://chatgpt.com/c/6a625ce1-f75c-83eb-93fd-7e868470b36e?messageId=f3904e45-4509-505a-ae66-79051989babd)
groups resolver, authoritative names, registry, route controller, policy engine,
tunnel gateway and federation client while separating name/data failure domains.
The [August30 one-request PoC](https://chatgpt.com/c/6a88ba55-2ab4-83eb-8aea-9cd77934aa8c?messageId=d061182d-c801-4aba-b0af-8f9ea782e912)
was architecture-approved/implementation-pending at that date. These are recovered
excerpts supplied by the parent, not an independently reread full transcript or
new blanket security authorization.

Current V3.6 and protocol terminology remain governing. Earlier V3 directive
sections11.4 and19.1 supply connector lifecycle and Node packaging history.
`nbsr/protocol/states.py` implements the frozen connector transitions; failure,
retry and drain mapping must be reviewed without inventing new transition edges.

### Reuse, adapt, missing

| Category | Evidence | Boundary |
| --- | --- | --- |
| Reuse | `interop/nbsr-go-peer/wirepeer/client.go`, `session.go`, `internal/transport/quic.go` | QUIC/TLS, framing, proof-bound handshake, exact RouteGrant checks and credits. Existing APIs initiate source/client flows; they do not authorize service publication. |
| Reuse | `client/nbsr-go-client/internal/session/{types,manager,rotation,application_stream}.go` | Bounded ownership, current/draining generations, quotas and recovery patterns. Device/source-specific authority and proof bindings are not connector identity semantics. |
| Reuse | `crates/nbsr-transport/src/quinn_adapter.rs` and session/credit tests | Independent destination admission, stream isolation and revocation cleanup. Connector availability cannot bypass admission. |
| Reuse | `nbsr/protocol/states.py`, `nbsr/two_operator_lab.py:DestinationConnector`, `docs/protocol/wp7-two-operator-isp-lab-decision.md` | Frozen lifecycle and exact owner/capability/privacy model. The Python connector explicitly performs no network I/O. |
| Adapt | `deploy/isp-federation-poc/origin-connector/main.go` and tests | Strict target containment, literal-IP dial and bounded I/O can serve a later data adapter. The stdio child handles one request; renaming it does not create a persistent tunnel. |
| Adapt | `client/nbsr-go-client/demo/internal/client/{assembly,transport_wire}.go` and transport `Readiness` | Replace fixture clock, identifiers and credential-path composition with explicit providers. Reuse primitives without copying crypto. Credential-bearing readiness is not public health output. |
| Adapt | `deploy/isp-federation-poc/supervisor.py` | Reuse bounded process ownership/cleanup patterns; preserve the one-shot demo separately from durable installation. |
| Missing | Persistent connector and destination-gateway registration/dispatch | Service-bound registration, live readiness, freshness/expiry, reconnect revalidation, stale-registration removal and revocation propagation. Not found in inspected current-branch paths; no exhaustive all-branches claim. |
| Missing | Production identity and package composition | Connector issuer/delegation/key-provider contracts, safe provisioning/rotation, persistent installation and recovery. Device enrollment-state persistence alone is insufficient. |

### Requirements and open decisions

Established requirements: connection originates in the private service network;
origin details remain out of client config; name/data failure domains stay
separate; both peers authenticate; service/operator/gateway scope, freshness and
revocation remain enforced; destination admission stays independent; queues,
streams, retries and cleanup are bounded; reconnect does not replay ambiguous
application work. `docs/protocol/originset-compatibility-authority-decision.md`
requires explicit service-bound delegation: reachability or TLS alone is not
ownership or publication authority. The PoC GET / and4096-byte limits are not
the product's universal application protocol.

Decisions before runtime implementation:

1. Gateway placement/reachability and allowed egress. LAN origin is selected;
   public/operator gateway placement remains a proposal. An in-LAN edge can
   reach the origin directly but is a different deployment option.
2. Connector identity, signer purpose, authorized issuer and service delegation.
   No implicit reuse of device credentials or route grants as publication rights.
3. Registration/lease/revocation wire contract and data-stream initiation roles.
   No invented Core message IDs, ALPN changes or role reversal. Existing client
   source-bidirectional APIs do not establish reverse-serving authorization.
4. Go/Rust composition and package location. Go internal-package boundaries must
   be respected; prefer a narrow shared transport seam over copying/moving broad
   security code. Identity/state persistence requires its own reviewed contract.
5. Retry/liveness/lease/drain limits, queue rejection and exact failure mapping
   onto frozen connector states. No unbounded retry list or premature READY.

### Proposed first persistent milestone

Approve a small control contract and deterministic vectors for one connector,
one service, one destination gateway and one live connection. Then implement a
**control-lifecycle-only local harness**: outbound dial, mutual authentication,
explicit authorized service binding, READY after acceptance, idle reuse,
disconnect detection, bounded backoff/re-authentication, expiry/revocation and
bounded stop. It does not yet forward arbitrary customer traffic or constitute
a production daemon. Test credentials belong only to the labelled harness.

Proposed files, not created: `docs/protocol/connector-outbound-profile.md` and
connector-control vectors/tests first; if Go is selected,
`client/nbsr-go-client/internal/connector/lifecycle.go` and `lifecycle_test.go`;
a narrowly reviewed `interop/nbsr-go-peer/wirepeer/connector.go` seam/tests if
needed; separate config/preflight/harness recipe under `deploy/connector-lifecycle/`.
Gateway implementation placement depends on the composition decision. Any
pinned Rust-source change needs separately reviewed versioned source authority.

Acceptance criteria:

- Strict side-effect-free preflight: invalid config causes zero dial/write;
  valid check performs no DNS/network, credential creation or Docker startup.
  Check secret references without logging values; config-valid is not READY.
- A real authenticated loopback connection survives two control exchanges.
  Wrong peer/service, expired/revoked delegation or stale generation never
  becomes READY. Connector presence cannot replace destination route admission.
- Observed disconnect withdraws readiness/registration before bounded retry.
  Fake-clock tests prove retry limits; reconnect reauthenticates/revalidates,
  drops stale live state and never replays prior application work.
- Queue saturation fails predictably at the chosen bound. Revocation while
  idle, connecting or backpressured prevents new work and releases ownership,
  following the approved failure/transition contract.
- Cancel/stop at every phase closes owned streams/connections and joins tasks
  within the reviewed deadline; no live registration, listener or reservation
  remains. Name-plane failure must not imply unlimited data-plane authority.
- Later authorized Docker smoke verification uses verified cached image digests,
  no pulls/build-on-start, isolated private-origin networking, no published origin
  port and exact owned teardown. Retain source/image/config hashes and counters.
  This proves local reproducibility only, not NAT/WAN or production readiness.

The next separate milestone may attach one bounded origin flow through this
persistent connection using the existing strict forwarder. No runtime, secrets,
network settings, authority pins or images changed during this gap analysis.

## Consolidated completion roadmap (2026-10-10)

Accepted-history synchronization: see the connector profile's "Accepted chronology:
admission expiry is not universal transfer expiry" section for V3 section 14,
F93 (August 5), P2D (August 11) and Tranche 5/6 (August 24), including history links.
Preserving admitted work under its own authorization and bounded drain is already
decided. Mapping expiry is not connector-lease policy by analogy. The next proposed
mock task is to disambiguate Permission.expires into admission eligibility,
ongoing stream authority and a profile-bound completion/drain context, then test
admission-only expiry and authorized renewal continuity without replay. This is
not yet implemented or authorization for new runtime semantics. Both existing
lease_bounds_active variants remain exploratory until mapped to those meanings.

The connector profile's "Federation reconciliation and recommended binding"
section now governs interpretation of these stages. Reuse F61/F106 authority and
existing scoped delegation, COSE and dependency binding; do not create a parallel
trust/discovery system or presume new credential purposes are needed. Earlier
blanket revocation-cancels-everything language is historical and superseded by
mode-aware enforcement. The legacy fake verifier's immediate-cancel assumption
remains; the approved typed-event extension adds separate deny-new behavior and
does not turn legacy verifier failure into production outage-policy evidence.

This is the current ordering: **10 milestones total, 8 to the reproducible local
demo finish line and 2 further milestones to a bounded customer pilot**. The
earlier patch/gate numbering and handoff above are preserved historical proposals,
not additional milestones. In particular, configurable forwarding is now part of
milestone 5; the next task is milestone 1, not the old patch-1 handoff. The earlier
claim that the connector is a destination-owned child is superseded: the outbound
connector runs beside the private origin and dials the destination gateway. On
one Docker host those remain isolated logical roles, not proof of a real WAN.
The old CI blocker is historical; the recorded published baseline is fb587d76
with hosted run 38060957353 passing all seven jobs.

**Current status:** source/evidence mapping and this roadmap are complete.
Transport, authentication/admission, bounded session ownership, Windows enrollment
state storage, the restricted one-request forwarder and PoC supervision already
exist as described above. **0/10 new package milestones are accepted complete.**
Existing library/CI passes are prerequisites, not a percentage of product
completion. This document authorizes neither implementation nor deployment.

**Finish line A (milestone 8):** from a documented, provisioned single-host
environment, supplied local images and explicitly supplied test credentials,
start the package, use a loopback explicit client to reach one named private HTTP
service through a persistent outbound connector, exercise failures, then stop,
restart and roll back with exact ownership evidence. The first application
profile remains GET /, complete 200 response, 4096-byte caps and the existing
bounded origin operation. Harness identity providers are conspicuously test-only.
No production signer, arbitrary web application support or customer deployment is
implied. An isolated test origin is permitted only in acceptance fixtures; it is
not shipped as the customer's service.

**Finish line B (milestone 10):** one explicitly authorized customer/service on
the selected supported platform and reviewed gateway placement, using real
service delegation and durable identity providers, passes the same safety tests
and a bounded real-network acceptance run. This is a pilot, not Internet-wide
production readiness, HA, universal NAT traversal or demonstrated capacity.
Unsupported application/platform needs require a separately scoped extension
before that pilot, not a silent relaxation of the profile.

For every implementation milestone: first retain the focused failing regression,
make the smallest contract-consistent change, run its focused and relevant
neighbor tests, inspect the diff and perform one scoped correctness/security
review. Record exact source/patch hashes, commands, failures, counts and cleanup.
Use the repository's provisioned offline caches and resource/time limits; no
cold builds or downloads. Stop on missing prerequisites. Commit/push, credential
provisioning, machine changes, Docker execution and external deployment require
their applicable explicit authorization. The roadmap itself adds none of these.

### 1. Freeze the outbound control and authorization contract

**Depends on:** current evidence; **status:** partial: approved mock-only model
implemented and reviewed; protocol design decisions remain open.
Review draft now exists at `docs/protocol/connector-outbound-profile.md`.
It includes 16 planned acceptance cases and explicit unresolved failure-state,
identity, wire, time/lease and ownership decisions. It is not an approved profile
or completed milestone; executable vectors and runtime implementation remain pending.
The isolated model now has 72 passing tests plus 13 frozen-state and 24 federation
revocation neighbor tests (109 total); see
`docs/reviews/2026-10-10-connector-active-work.md`. The earlier 49-test checkpoint
remains in `docs/reviews/2026-10-10-connector-control-model.md`. These are partial model
coverage of the 16 cases, not real authentication, asynchronous I/O or deployment
acceptance. The 0/10 completed-package-milestone count remains unchanged.
Reuse V3.6, frozen connector states and OriginSet delegation rules. Produce
`docs/protocol/connector-outbound-profile.md` plus a vector/test manifest naming
the exact proposed control artifacts before runtime edits. Resolve connector
issuer/signer purpose, service/operator/gateway binding, registration generation,
lease/expiry/revocation, stream initiation roles, error-to-state mapping and
finite retry/queue/drain limits. Select the narrow Go/Rust ownership seam and
gateway location. New Core IDs, ALPN, state edges or pinned-source authority
changes need explicit versioned protocol review; do not invent them in code.

- [ ] Review one success transcript and wrong peer/service, expired/revoked
  delegation, stale generation and duplicate-registration vectors. Each must
  have an unambiguous accept/reject and ownership outcome.
- [ ] Approve the profile and exact interface/vector inventory. TLS possession
  alone must never imply service publication; destination admission stays
  independent. This is the first material-design approval gate.

### 2. Establish safe configuration and side-effect-free preflight

**Depends on:** 1; **status:** planned. Create the previously proposed
`deploy/single-instance/config.schema.json`, `validate_config.py`,
`test_validate_config.py` and a secret-free example. Separate client, gateway and
origin-side fields; consume approved identity/trust references and finite limits.
Version the schema. Normal startup never invents keys, authority, default
passwords or enrollment permission. Local harness test material must be supplied
explicitly and rejected by the future pilot mode.

- [ ] Test duplicate/unknown/missing keys, invalid scope/limit/target, absent
  secret reference and unsupported schema. Assert zero DNS, dial, write,
  credential creation and container startup during check-config.
- [ ] Accept a valid sample without exposing secret contents. Client config has
  no private-origin endpoint. Configuration validity is not live readiness.

### 3. Implement persistent outbound registration and gateway ownership

**Depends on:** 1–2; **status:** planned. Reuse QUIC/TLS, proof and framing
primitives; add the approved connector lifecycle and gateway registration seam.
The earlier proposed `internal/connector/lifecycle.go` and narrow wirepeer seam
are candidates, not a reason to violate Go internal-package boundaries. Milestone
1 selects exact implementation/test files before this task starts. No second
crypto stack and no relabeling of the source-client session as service hosting.

- [ ] A real authenticated loopback connection carries two control exchanges
  without reconnecting; READY follows accepted service registration only.
- [ ] Wrong identity/service/delegation/generation never enters the dispatch
  table. One service has the approved active ownership; duplicate/stale
  registrations behave exactly as the profile specifies. Stop removes it.

### 4. Prove reconnect, leases, revocation and resource bounds

**Depends on:** 3; **status:** planned. Extend the same lifecycle owners, reusing
existing quota/cancellation patterns. Withdraw stale registrations on observed
loss, reauthenticate and revalidate on reconnect, and expire authority at its
approved deadline even if the peer is silent. No replay of ambiguous work.

- [ ] Fake-clock tests exhaust backoff/retry/lease boundaries without sleeps;
  a reconnect cannot reuse stale registration or bypass fresh authorization.
- [ ] Revoke while idle, connecting, blocked on credit and actively serving.
  Deny-new-use withdraws selection/renewal but preserves only still-authorized
  existing work within its original policy/deadline. Terminate-active-use cancels
  affected work. Decode Core/federation enforcement semantically, never by numeric
  enum cast. Saturated queues reject at their configured bounds. Confirmed cleanup
  leaves zero owned resources; failed cleanup retains visible ownership and
  prevents takeover rather than claiming success.
- [ ] A lost name/control plane follows approved freshness semantics; it neither
  grants indefinite authority nor silently changes the independent data plane.

### 5. Relay one authorized flow to the configured private origin

**Depends on:** 2–4; **status:** planned. Fold the earlier configurable-target
patch and its detailed tests into this milestone. Adapt
`deploy/isp-federation-poc/origin-connector/main.go`/`main_test.go` as a bounded
forwarding adapter, preserve the legacy v1 fixture behavior, and bind gateway
dispatch to the accepted service registration through the outbound connection.
Only the origin-side configuration contains the backend target.

- [ ] An admitted exact name/port request reaches the configured private literal
  address once and returns the bounded response byte-for-byte through the tunnel.
- [ ] Wrong Host/name/method/path, unauthorized grant and stale registration
  cause zero origin requests; invalid/ambiguous/out-of-CIDR resolution causes
  zero dial. Oversized, incomplete and stalled origin responses fail boundedly.
- [ ] Disconnect after origin receipt does not automatically repeat the request;
  count origin requests and verify stream/credit cleanup. Keep the old fixture
  tests and strict limits intact. Broader HTTP support is outside this milestone.

### 6. Compose the local client, authority and destination runtimes

**Depends on:** 2–5; **status:** planned. Add the small explicit entrypoints
proposed earlier under `client/nbsr-go-client/cmd/` and the destination entrypoint
chosen in milestone 1. Reuse authority, resolution, session and explicit-proxy
libraries. Inject a real clock, configured trust and provider interfaces; keep
test-only providers in the labelled local harness. Preserve demo regression paths.

- [ ] An explicitly supplied initial enrollment and fresh authority permit the
  exact service. Proxy binds loopback only. Expired/revoked authority, unavailable
  required validation and stale state keep readiness false after restart.
- [ ] Production/pilot mode rejects fixture providers and missing durable signer
  support rather than falling back. No grant/session/credit survives restart.
  This does not claim milestone 9's real identity providers are implemented.

### 7. Package bounded Docker startup, supervision and diagnostics

**Depends on:** 6; **status:** planned. Add separate single-instance Compose,
Dockerfiles and package lifecycle commands under `deploy/single-instance/`.
Reuse existing supervisor ownership patterns. The connector and private service
share only their required origin-side reachability; the connector dials gateway
egress. No origin host port, Docker socket or credential-bearing health endpoint.
Use approved local image digests, non-root/read-only runtime, bounded resources
and scoped persistent mounts. No build, pull or credential generation on startup.

- [ ] Preflight rejects missing images/config/secrets before partial startup.
  Live readiness requires current authenticated registration and authority;
  port/file presence alone does not suffice. Logs redact secrets, bodies and
  private-origin details and have bounded retention.
- [ ] In a separately authorized disposable environment, kill each component
  and stop under stalled work. Readiness withdraws and owned processes are
  joined within approved deadlines, with exact zero-survivor counters.
  The earlier 15/5-second timings remain proposals until milestone 1 approves
  consistent application and container deadlines.

### 8. Accept and document the reproducible local package

**Depends on:** 7; **status:** planned; **finish line A**. Deliver a single-host
runbook and automated acceptance recipe alongside the package: prerequisites,
check-config, supplied credentials/images, start, readiness, one request, stop,
restart, compatible rollback and uninstall. Record ownership before execution;
preserve identity, authority floors and unrelated files/volumes by default.

- [ ] From a clean package-owned directory, complete two start/request/stop
  cycles with immutable inputs and exact source/image/config hashes. Exercise
  wrong name, revoked/expired grant, silent origin, dropped tunnel, gateway loss,
  queue saturation and interrupted startup; retain negative outcomes.
- [ ] Show the explicit client cannot directly reach the isolated origin.
  Stop/uninstall is idempotent with zero owned survivors. Compatible rollback
  revalidates fresh authority; incompatible state fails closed without lowering
  floors or deleting identity. Unrelated resources survive.
- [ ] Run affected clean-checkout CI profiles and one authorized bounded Docker
  smoke run; reconcile their evidence and document prerequisites and limits.
  Missing images/resources are blockers, not permission to pull or enlarge runs.

### 9. Close real identity, provisioning and pilot installation gaps

**Depends on:** 8 and approved deployment/key-provider decisions from 1;
**status:** planned. Implement reviewed connector/operator key providers and
explicit service delegation, configured bootstrap/initial-enrollment adapters,
and the native Windows persistent device signer. Reuse DPAPI enrollment-state
storage and transactional idempotency without equating either with key custody.
Select recovery, rotation, account binding and package installation permissions
before integration. Limit the pilot to platforms with verified persistence.

- [ ] Real identity survives two process restarts; wrong-account/corrupt/missing
  state and unapproved issuer fail closed. No plaintext/test/ephemeral fallback,
  auto-enrollment or key regeneration. Concurrent initial enrollment has one
  winner; ambiguous restart cannot create a second authorization.
- [ ] Test rotation/revocation, service delegation scope and recovery without
  leaking keys or lowering authority floors. Service-account/ACL and installer
  tests require explicit machine authorization. Re-run milestone 8 with these
  providers before declaring the pilot package eligible.

### 10. Run and close one bounded customer pilot

**Depends on:** 9; **status:** planned; **finish line B**. Obtain approval for
the exact customer host, reachable gateway, trust/delegation, one compatible
service, permitted egress and operator responsibilities. Agree finite duration,
request/resource bounds, failure/abort criteria, support owner and rollback
before any traffic. Reuse the local acceptance suite and supplied immutable
artifacts; do not generalize the one-host result to WAN or capacity.

- [ ] Verify actual permitted outbound connectivity without exposing the origin
  inbound; record authenticated readiness and one service delivery. Test an
  agreed tunnel interruption/reconnect, expiry/revocation and bounded stop in
  that topology. Prove no duplicate origin request or residual owned resources.
- [ ] Retain redacted results, versions/hashes, failures, resource maxima and
  cleanup. Operator performs the documented restart and rollback. Close with an
  explicit accept/reject against agreed criteria and a list of limitations.
  Do not call a skipped or partially executed pilot successful.

### Optional distribution and work beyond these ten milestones

Registry publication is **not required** for either finish line: approved local
image transfer/import can serve the demo and pilot. If distribution is requested,
add a separately authorized release task after milestone 8 (and use pilot-ready
providers for a pilot release): versioned artifacts, provenance, signing,
secret/license scan, exact registry/digest and credentials approval, then verify
the published digest. Never publish harness secrets or imply a test image is a
production release. This optional task is excluded from the 10-milestone count.

Multiple origins/operators, arbitrary HTTP/streaming, other native platforms,
transparent DNS/TUN, Kubernetes, HA, sustained load and Internet-wide production
hardening remain separate future scopes. No dates or capacity promises are
assigned without evidence. Work sequentially; milestone 1 is the next bounded
deliverable, and each acceptance gate controls the next expenditure.

### One-pass roadmap consistency review

Follow-up approved and completed only at the mock boundary: one fake active-work
fixture now separates dispatch eligibility from active-owner lifetime, using the
two approved enforcement modes. B6/B7 are simulated; B8 rejects wrong enum types
without implementing a decoder; B9 covers stale owners, not future-effective
signed events; B11 is an instance-local latch, not durable revocation. B10 outage
policy remains unimplemented. Both lease/work variants are tested exploratory
fixtures, not two newly approved protocol policies. Accepted chronology already
separates new-use eligibility, admitted-work authorization and bounded drain.
The remaining model gap is mapping Permission.expires and renewal/completion grace
to those existing meanings; do not reopen transfer continuity as a new decision.
Wire-role/proof mapping and exact existing-purpose credential binding remain
integration decisions.
No stage count changes; no real trust, wire ID, credential or runtime change.

Reviewed once against the recovered direction and inspected repository evidence:
outbound topology and service authorization are owned by 1/3; lifetime and quota
failures by 4; safe origin access by 5; fixture separation by 6/9; side-effect-free
config by 2; supervised packaging by 7; reproducibility/rollback by 8; real
identity and customer authorization by 9/10. Dependencies are forward-only.
Historical patch numbering, child-connector topology and stale CI blocker are
explicitly superseded above. Milestone 8 permits labelled supplied test identity;
milestone 10 requires verified real providers. Optional publication is outside
the count. No runtime tests or deployment were performed for this roadmap edit.
