# NBSR End-to-End Demo Implementation Plan

> **For agentic workers:** Execute sequentially after human approval. Begin each task with the listed literal RED test, stop at its review gate, and do not start the next task early.

**Goal:** Prove one real application request traverses the production Go explicit-proxy resolution and authority ownership path, the validated Go/quic-go to Rust/Quinn secure transport, a destination-only backend connector, and returns the backend response without origin disclosure or direct fallback.

**Architecture:** A proxy-aware application sends `CONNECT service-a.nbsr.test:8080` to a loopback Go demo client. A demo resolution fixture supplies signed/control-plane-substitute service metadata, while the existing production resolver, MappingTable, FlowStore, AuthorityProvider/ACP client, independent RouteGrant verifier, TS, SC, Stream Credit, and Application Stream code enforce the route. The existing Go/quic-go wire peer connects to the Rust/Quinn destination peer; only after route and stream admission does a destination-local connector spawn a deterministic HTTP backend and relay over anonymous child-process pipes that the application cannot address.

**Tech Stack:** Go 1.26.5, quic-go 0.61.0, Rust 1.97.1 source baseline with the separately validated Rust binary, Quinn 0.11.11, rustls 0.23.43, TLS 1.3, QUIC v1, ALPN `nbsr-quic-1`, PowerShell 7, Python only as an evidence/test runner.

**Spec:** `docs/architecture/production-go-client/tranche6-resolution-secure-routing.md`, `docs/architecture/production-go-client/requirements.md`, and the user-approved first-demo mission dated 2026-08-25.

## Global constraints

- Preserve the exact path: application -> explicit local proxy -> canonical resolution -> immutable Mapping/FlowContext -> verified RouteGrant -> TS -> independently authorized SC -> Stream Credit -> Application Stream -> Rust destination -> backend.
- The successful demo must execute the real resolution lifecycle: service name -> canonicalization -> ServiceDigest -> ResolutionResult -> Mapping. Demo fixture data may supply deterministic resolution inputs, but a pre-seeded Mapping must not bypass this path.
- Use one configured shared loopback Synthetic IP. It is local correlation output only, never Service Identity, authority, or an Origin Endpoint.
- Use SOCKS5 domain-name and HTTP CONNECT only. Do not add DNS interception, TUN, WFP, packet capture, kernel integration, UDP, an SDK, or transparent-operation claims.
- No direct-origin fallback, payload before `STREAM_ACCEPT`, authenticated-transport-as-authorization shortcut, wire/schema/registry/vector/crypto change, or automatic application replay.
- All fixture trust material is generated under ignored `test-results/nbsr-demo/runtime/`; no private key, token, RouteGrant, proof, or Origin Endpoint enters normal application-facing output.
- Use fixed-enum Tranche 7 events and aggregate resource snapshots. Demo evidence may contain canonical/service names only in the operator-owned evidence file, never as metric dimensions; normal client logs remain identifier-free and origin-free.
- Rust fresh-build provenance remains a separate risk. Initial implementation uses the previously validated Rust binary only after SHA-256 verification; it must not silently rebuild or upgrade Rust dependencies.
- Every task is independently reviewed and tested. No commit, push, merge, rebase, PR, or work on `main` occurs without separate authorization.

---

## A — Repository baseline

| Ref/state | Observed value |
|---|---|
| Branch | `codex/nbsr-v3-wp0-wp1` |
| Local HEAD | `758a3dc5025bfa2d0b444e3ae8992f69d97cf2b1` |
| `origin/codex/nbsr-v3-wp0-wp1` | `758a3dc5025bfa2d0b444e3ae8992f69d97cf2b1` |
| `main` | `1938154d498b32d81a3564319969430644e8a688` |
| `origin/main` | `1938154d498b32d81a3564319969430644e8a688` |
| Worktree before planning | clean; branch tracks its matching remote |

`git fetch --prune origin` refreshed refs and emitted a non-fatal permission warning while trying to delete stale `.git/worktrees/nbsr-name-routing` administration. No repository cleanup is part of this plan.

## B — Existing components and reuse classification

| Component | Current implementation | Reuse decision | Evidence/path |
|---|---|---|---|
| Canonical resolution and digest | IDNA Lookup, lowercase ASCII, IP rejection, SHA-256 over canonical ASCII | REUSE_AS_IS | `client/nbsr-go-client/internal/resolution/canonical.go` |
| Immutable resolution result | Binds ServiceIdentity, RouteIntent, earliest expiry, ServiceDigest | REUSE_AS_IS | `client/nbsr-go-client/internal/resolution/context.go` |
| MappingTable | Bounded immutable mapping ownership, acquire/release and expiry | REUSE_AS_IS | `client/nbsr-go-client/internal/corestate/mapping.go` |
| Shared Synthetic IP service | Returns one configured loopback IP plus local MappingID | REUSE_AS_IS | `client/nbsr-go-client/internal/resolution/registry.go` |
| FlowStore/FlowContext | Bounded, single-use `LocalFlowID -> MappingID` correlation | REUSE_AS_IS | `client/nbsr-go-client/internal/resolution/flow.go` |
| Explicit proxy | SOCKS5-domain and HTTP CONNECT parsing, bounded listener, buffered handoff | REUSE_AS_IS | `client/nbsr-go-client/internal/adapter/proxy/` |
| Mapping router | Consumes FlowContext, revalidates mapping digest/provenance, releases once | REUSE_AS_IS | `client/nbsr-go-client/internal/resolution/router.go` |
| AuthorityProvider and ACP client | TLS 1.3/HTTP/2 Acquire/Renew/Freshness and signed result verification | REUSE_AS_IS | `client/nbsr-go-client/internal/authority/http_provider.go` |
| Source Operator ACP runtime | Bounded `/acp/authority` server and signed terminal decisions | REUSE_WITH_MINIMAL_ADAPTER | `client/nbsr-go-client/internal/authority/source_operator_runtime.go` needs demo-only decision/config assembly |
| RouteGrant manager/verifier | Independently verifies exact signed grant and binds full AuthorityKey | REUSE_AS_IS | `client/nbsr-go-client/internal/authority/{manager.go,verifier.go,cache.go}` |
| TS/SC ownership | Bounded session/channel lifecycle and independent sealed-authority commit | REUSE_AS_IS | `client/nbsr-go-client/internal/session/manager.go` |
| Stream Credit/Application Stream | `nbsr-stream-credit-1`, actual StreamID, accept-before-payload, refill and teardown | REUSE_AS_IS | `client/nbsr-go-client/internal/session/{credit.go,application_stream.go,stream_credit_codec.go}` |
| `streamclient.OwnedChannel` | Production stream ownership around pre-established fixture authority | TEST_ONLY | `client/nbsr-go-client/streamclient/streamclient.go`; it uses `fixedGate`, so it cannot prove the live ACP/Manager chain by itself |
| MappedRouteOpener | Binding check from Mapping route to one pre-owned channel | REUSE_WITH_MINIMAL_ADAPTER | `client/nbsr-go-client/streamclient/mapped.go`; demo needs lazy per-route authority/session/channel acquisition rather than one pre-owned channel |
| Live Go/quic-go peer | Real QUIC/TLS, HELLO, ROUTE_OPEN/ACCEPT, credited streams | REUSE_WITH_MINIMAL_ADAPTER | `interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go`; extract existing behavior behind an importable adapter without changing verifier behavior |
| Rust/Quinn destination | Validates route/admission/credit and currently echoes accepted payload | REUSE_WITH_MINIMAL_ADAPTER | `crates/nbsr-transport/src/bin/wp8_interop_server.rs`; demo mode needs a destination-local backend connector after admission |
| P1F/P2D live runner | Seven real Go-to-Rust positive/negative cases | TEST_ONLY | `scripts/verify_p1f_p2d_live_go_rust.py` |
| Tranche 5 rotation runner | Proven two-generation real interop | TEST_ONLY | `scripts/verify_tranche5_rotation.py` |
| Old FastAPI/OPA/Envoy Compose demo | JWT/ticket/Host-SNI prototype with separate authority and routing semantics | LEGACY_REFERENCE_ONLY | `compose.yaml`, `scripts/demo.py`, `services/name-relay/`, `demo-video/` |
| Kubernetes/Kind assets | Lab deployment for the old prototype | REMOVE_FROM_NEW_DEMO_PATH | `deploy/kind/`, `scripts/demo-kind.ps1`, `scripts/demo-kind.sh` |
| Old name-route scripts | Exercise legacy name relay, not Tranches 1-7 production client | REMOVE_FROM_NEW_DEMO_PATH | `scripts/name-route-demo.ps1`, `scripts/name-route-demo.sh` |

Nothing is deleted by this plan.

## C — Missing demo glue

1. A demo-only executable assembly that is inside the production client import boundary and joins resolution, proxy accept, flow routing, ACP authority acquisition, TS/SC creation, credited Application Stream, and bidirectional copy.
2. A deterministic resolution fixture defining `service-a.nbsr.test` -> ServiceIdentity + canonical RouteIntent + authoritative expiry. The fixture substitutes for a production resolver/control plane and must be labeled `DEMO FIXTURE — NOT PRODUCTION AUTHORITY`.
3. A runnable demo Source Operator ACP configuration that signs deterministic, bounded RouteGrants and freshness results; the existing client must still independently verify them.
4. A reusable wrapper around the already validated Go/quic-go peer so the demo assembly does not create a second transport implementation.
5. A Rust destination-only backend connector that runs only after route and Application Stream admission, owns anonymous pipes to a child backend with no network listener, and has no client-side fallback.
6. Deterministic Windows lifecycle scripts and a machine-readable evidence verifier.

## D — Proposed topology

Use native local processes. This avoids conflating the legacy Compose topology with the production Go client and avoids Kubernetes. The backend has no socket listener: the Rust destination starts it only after admission and owns its anonymous stdin/stdout pipes. The demo application is explicitly configured with the loopback HTTP CONNECT proxy and has no addressable route to the backend.

```text
 Demo application (curl)
 service-a.nbsr.test:8080
          |
          | HTTP CONNECT with domain name
          v
 Go demo client / explicit proxy 127.0.0.1:<proxy>
 [canonicalize -> SHA-256 -> shared 127.0.0.2 -> MappingID -> FlowContext]
          |
          +---- TLS 1.3 + HTTP/2 ----> Go demo ACP 127.0.0.1:<acp>
          |                              [signed DEMO fixture RouteGrant]
          |<--- independently verified RouteGrant ------------------+
          |
          | QUIC v1 + TLS 1.3, ALPN nbsr-quic-1
          | TS -> SC -> Stream Credit -> Application Stream
          v
 Rust destination peer 127.0.0.1:<quic>
 [destination admission; backend command is private process config]
          |
          | anonymous child stdin/stdout, after admission
          v
 Go deterministic backend (no listener; Rust child process)
 "hello from service-a through NBSR"
```

| Process | Language | Listener | Trust/state role | Dependencies | Application reachability |
|---|---|---|---|---|---|
| `nbsr-demo-backend` | Go | none; stdin/stdout pipes | Non-authoritative deterministic origin; holds no NBSR authority | spawned by Rust after admission | no addressable listener or inherited pipe handle |
| `nbsr-demo-authority` | Go | loopback random TLS/HTTP2 | Authoritative only within signed demo fixture profile; signs RouteGrant/freshness | generated demo trust material | no |
| `wp8_interop_server --demo-backend` | Rust | loopback random UDP/QUIC | Destination peer; authenticates transport, validates route/stream admission, alone owns the backend command and pipe handles | backend executable, authority fixture directory | no |
| `nbsr-demo-client` | Go | `127.0.0.1:<proxy>` TCP | Production client state owner; resolution mapping is non-authoritative; verifies authority | ACP and Rust peer | yes, proxy only |
| `curl.exe` | application | none | Untrusted proxy-aware application | Go proxy | yes |

## E — Exact success flow

1. Runner prepares the backend executable, then launches the ACP fixture, Rust destination, and Go client and waits for bounded readiness files. Rust does not start a backend child before an admitted request.
2. Go client loads public trust/config, validates limits, and publishes one immutable fixture resolution for presentation name `service-a.nbsr.test`.
3. `CanonicalizePresentationName` produces `service-a.nbsr.test`; `DigestCanonicalName` produces `SHA-256(canonical ASCII)` as ServiceDigest.
4. `resolution.Service.Publish` creates an immutable Mapping and returns shared Synthetic IP `127.0.0.2` plus local MappingID. The application receives/uses only its service name and proxy, not MappingID or origin.
5. `curl.exe --proxy http://127.0.0.1:<proxy> http://service-a.nbsr.test:8080/` sends HTTP CONNECT containing the domain name.
6. The proxy canonicalizes the target, looks up the exact name+port mapping, creates one single-use FlowContext, and returns the captured downstream connection.
7. The router consumes LocalFlowID, acquires MappingID, rechecks canonical-name digest, RouteIntent digest, service identity, port, policy, and expiry.
8. Demo route assembly calls `BuildAcquireRequest`; all AuthorityKey service/intent/operator/edge/profile/device/proof/policy/generation fields come from mapping and current identity/session state.
9. The existing HTTPProvider sends a signed ACP Acquire over TLS 1.3/HTTP2 to the demo Source Operator runtime.
10. The ACP demo fixture signs a RouteGrant for the exact request; HTTPProvider verifies the ACP result envelope, and `authority.Manager` independently verifies the RouteGrant issuer, signature, ServiceDigest, ServiceIdentity, TS proof thumbprint, transport, port, policy, validity, nonce/sequence, and generation before reserving it.
11. The session Manager selects or creates the exact TS through the extracted existing quic-go adapter, authenticated to the Rust destination with QUIC v1/TLS 1.3/`nbsr-quic-1`.
12. Session Manager opens a fresh independently authorized SC using the single-use reservation and exact RouteGrant bytes; Rust validates ROUTE_OPEN and returns correlated ROUTE_ACCEPT.
13. Session Manager reserves one Stream Credit, opens a real QUIC stream, sends the deterministic credit preface containing actual StreamID, and waits for ACCEPT.
14. Only after ACCEPT and the final authority barrier does the client copy the application HTTP bytes into the Application Stream.
15. Rust starts the configured fixed backend command only for the admitted service, gives it anonymous pipes not inherited by the application, and relays bytes; the backend returns `hello from service-a through NBSR`.
16. Rust relays the response through the same admitted QUIC stream; Go relays it to curl, then half-close/close releases stream, mapping reference, FlowContext, SC/TS on shutdown, and aggregate usage returns to expected idle/zero.

## F — Security boundaries

| Boundary | Enforcement |
|---|---|
| Name identity | IDNA canonical ASCII and SHA-256 in `resolution`; IP literals are rejected |
| Correlation | Explicit proxy name+port -> immutable MappingID -> single-use FlowContext; shared IP, Host, SNI, recency, and destination IP do not select service |
| Authority | TLS/HTTP2 authenticates ACP delivery, but only independent RouteGrant/ACP result verification creates sealed authority |
| TS proof | Generation-specific proof thumbprint and full ReuseKey bind TS; QUIC reachability alone grants nothing |
| Service authorization | Fresh single-use RouteGrant is committed to one channel ID; each SC is independently authorized |
| Payload admission | Stream Credit and same-stream ACCEPT precede any application payload; final authority barrier runs after ACCEPT |
| Destination connector | Rust selects a fixed backend executable from destination-private fixture config only after admission; no backend listener, address, or command exists in resolution/Mapping/client config |
| Origin concealment | The backend command path appears only in runner-private runtime config and Rust process memory; it never appears in application response metadata, Go normal logs, metrics, resolution answer, ServiceIdentity, or fallback |
| Resource/privacy | Existing hard bounds and Tranche 7 closed-enum aggregate counters; evidence writer uses an allowlist and bounded values |

## G — Demo fixtures

| Fixture | What it substitutes | Signing/verification | Why the claim remains valid |
|---|---|---|---|
| Service catalog (`service-a.nbsr.test`) | Future production resolver/control-plane source for ServiceIdentity, RouteIntent, and expiry | Static config is hash-bound by the runner; production `NewResult` validates it before Mapping creation | Demo proves production canonicalization/mapping/correlation, not production resolver authority/distribution |
| Demo ACP identity, issuer, freshness, and RouteGrant signer | Enrolled Source Operator and live production authority policy | Generated Ed25519 keys sign ACP request/result/RouteGrant objects; existing HTTPProvider, result verifier, RouteGrant verifier, manager freshness/generation barriers validate them | Signed fixture changes who supplies authority, not the mandatory authority verification path |
| Destination authority directory | Public-safe interop trust material | Existing Rust verifier checks the same accepted bindings used by current live interop | Reuses the validated destination admission mechanism; it does not claim production trust operations |
| Backend command map | Private destination connector configuration | Runner passes a fixed executable/hash only to Rust and verifies absence from client artifacts; anonymous pipe handles are not inherited by the application | Demonstrates origin concealment and destination-only connection, not NBSR-native OriginSet publication |

All four are labeled `DEMO FIXTURE — NOT PRODUCTION AUTHORITY` in config and evidence. Private material is generated, ignored, permission-restricted where Windows permits, and destroyed by stop/cleanup.

## H — Minimal first-demo negative cases

| Case | First-demo method | Expected result |
|---|---|---|
| Unknown service | CONNECT `unknown.nbsr.test:8080` | Proxy fails closed before FlowContext/authority/backend; no direct lookup/fallback |
| Invalid/missing authority | Start client with ACP unavailable or signed fixture denied | No SC, no Application Stream, zero backend requests |
| ServiceDigest mismatch | Test-only mutation at resolution-to-acquire boundary | `ErrRouteBinding`/binding rejection before channel and payload |
| Expired mapping | Advance injected demo clock beyond earliest expiry, open new flow | New flow rejected; zero backend requests |
| Direct backend attempt | Application probes the documented demo host interfaces/ports and verifies no backend listener exists; process inspection confirms the backend is a Rust child with anonymous pipes only | No addressable application-to-backend path exists outside NBSR |

Cross-service confusion with two names sharing one Synthetic IP and port is high-value follow-up validation in Task 6 only after the single-service success path is green. The existing Tranche 6 integration test already proves local same-IP/same-port isolation; the live two-service case must not delay the first successful demo if it requires Rust multi-backend selection beyond the bounded adapter.

## I — Sequential implementation plan

### Task 1: Freeze demo contracts and reusable wire adapter

**Goal:** Create an importable wrapper around the existing validated Go/quic-go path and freeze demo config/evidence schemas without changing wire behavior.

**Files:**
- Create: `interop/nbsr-go-peer/wirepeer/client.go` (NEW)
- Create: `interop/nbsr-go-peer/wirepeer/client_test.go` (NEW)
- Modify: `interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go`
- Create: `client/nbsr-go-client/demo/go.mod` (NEW nested demo-only module)
- Create: `client/nbsr-go-client/demo/internal/config/config.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/config/config_test.go` (NEW)
- Create: `client/nbsr-go-client/demo/testdata/service-a.json` (NEW, public non-secret fixture metadata)

**Existing components reused:** Existing peer TLS/QUIC/HELLO/ROUTE/credit implementation, current module versions, frozen vector/registry inputs.

**RED tests first:** `TestWirePeerAdapterPreservesValidatedRouteAndStreamSequence` fails because no importable adapter exists; `TestConfigRejectsOriginInClientSectionAndNonSharedSyntheticIP` fails because no schema exists.

**Implementation:** Extract, without semantic edits, the peer connection and SC/Application Stream callbacks used by `main.go` into `wirepeer`. Define closed config structs separating client-visible, ACP-fixture, destination-private, and evidence paths. Classify QUIC v1, TLS 1.3, ALPN `nbsr-quic-1`, and `nbsr-stream-credit-1` as production-semantic transport contracts. Classify TCP as the demo application's reliable-stream/application profile carried through NBSR, and port 8080 plus shared IP `127.0.0.2` as demo/application configuration. Pin limits, timeouts, required file permissions, and the validated Rust binary SHA-256 input. Keep the existing CLI as a caller of the extracted adapter so the seven-case verifier remains unchanged.

**GREEN criteria:** Adapter tests pass; current peer command emits byte/sequence-equivalent positive and negative outcomes; config cannot place an origin in client/resolution sections.

**Security invariants:** No new wire value or fallback; origin endpoints are unrepresentable in client config; dependency changes are confined to the nested demo module.

**Verification:** `go test ./wirepeer ./cmd/nbsr-go-peer -count=1`; `go test ./internal/config -count=1` from `client/nbsr-go-client/demo`; `python scripts/verify_p1f_p2d_live_go_rust.py --build-root <validated-build-root>`.

**Stop condition:** Existing live verifier remains 7/7 and config review confirms no client-side origin field.

### Task 2: Add deterministic backend and admitted destination connector

**Goal:** Replace echo only in explicit demo mode with destination-local TCP relay to a boring backend after successful NBSR admission.

**Files:**
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-backend/main.go` (NEW)
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-backend/main_test.go` (NEW)
- Modify: `crates/nbsr-transport/src/bin/wp8_interop_server.rs`
- Create: `crates/nbsr-transport/tests/demo_backend.rs` (NEW)

**Existing components reused:** Rust route/SC/Stream Credit/Application Stream gates and the existing echo mode (retained for all current verifiers).

**RED tests first:** Rust `demo_backend` test proves an accepted stream currently echoes and never reaches a backend; pre-admission/mismatched-service tests require backend accept count zero. Go backend test requires exact HTTP body and deterministic request count.

**Implementation:** Add opt-in `--demo-backend-map <private-path>` with one bounded service-to-executable binding and pinned executable hash. After ROUTE_ACCEPT and credited stream ACCEPT, spawn the backend with explicit non-inherited handles and relay through stdin/stdout using fixed buffers, cancellation, and child termination. Preserve echo behavior when the flag is absent. The backend accepts one HTTP request on stdin, returns the fixed response on stdout, emits only an aggregate completion status on stderr, and opens no listener.

**GREEN criteria:** Accepted service receives exact backend response; rejected route/credit/mismatched service produces zero backend accepts; legacy interop echo tests remain unchanged.

**Security invariants:** Only Rust reads the fixed command; no pre-admission child; no command/argument from wire or client; no inherited application handle, listener, shell expansion, or direct fallback; bounded copy and timeout.

**Verification:** `go test ./cmd/nbsr-demo-backend -count=1`; `cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test demo_backend`; focused existing Rust admission/application-stream/stream-credit tests.

**Stop condition:** Backend access is impossible before both route and stream admission, and all existing echo-mode tests pass.

### Task 3: Build signed demo ACP and production authority-manager assembly

**Goal:** Exercise TLS 1.3/HTTP2 ACP delivery and independent RouteGrant verification with generated demo authority material.

**Files:**
- Create: `client/nbsr-go-client/demo/internal/fixture/authority.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/fixture/authority_test.go` (NEW)
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-authority/main.go` (NEW)
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-authority/main_test.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/client/authority.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/client/authority_test.go` (NEW)

**Existing components reused:** `SourceOperatorRuntime`, `NewSourceOperatorHTTPServer`, `HTTPProvider`, ACP request/result codecs, `Verifier`, `Manager`, generation floor, identity registry, and Tranche 7 observer.

**RED tests first:** Live loopback Acquire fails because no fixture authority exists; tests require verified reservation on exact bindings and fail closed for missing issuer, wrong ServiceDigest, expired grant, wrong proof thumbprint, stale freshness, and ACP outage.

**Implementation:** Generate TLS and Ed25519 fixture keys under the ignored runtime directory; implement the narrow SourceOperatorAuthority/issuer/freshness interfaces to sign only the exact catalog entry and request bindings. Assemble HTTPProvider and production Manager; expose a demo-internal `AcquireRoute(ctx, RouteContext, TSGeneration, proof)` returning only the sealed reservation metadata required by session creation, never raw private material or a bypass token.

**GREEN criteria:** Exact request obtains a Manager reservation through real HTTP/2 ACP and independent verification; every mutation/expiry/outage rejects with no SC/backend activity.

**Security invariants:** Authenticated transport alone never authorizes; signer purposes are separate; RouteGrant is single-use; freshness/generation checks remain mandatory; raw grants/keys are absent from logs.

**Verification:** `go test ./internal/fixture ./internal/client ./cmd/nbsr-demo-authority -run 'Authority|ACP|RouteGrant' -count=1`; then package tests and race tests for `./internal/fixture ./internal/client`.

**Stop condition:** A reviewer can trace Mapping-derived AuthorityKey -> HTTPProvider -> signed ACP result -> independent verifier -> one sealed reservation, with negative cases failing before SC creation.

### Task 4: Assemble resolution, proxy, TS/SC, and forwarding

**Goal:** Join the production Tranche 6 prefix to the real authority/session/wire path for one HTTP request.

**Files:**
- Create: `client/nbsr-go-client/demo/internal/client/runtime.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/client/runtime_test.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/client/forward.go` (NEW)
- Create: `client/nbsr-go-client/demo/internal/client/forward_test.go` (NEW)
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-client/main.go` (NEW)
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-client/main_test.go` (NEW)

**Existing components reused:** `corestate.Store`, `resolution.NewResult/Registry/Service/FlowStore/Router/BuildAcquireRequest`, `proxy.Server`, authority Manager, session Manager, Tranche 7 collector, and `wirepeer` adapter.

**RED tests first:** `TestProxyRequestTraversesMappingAuthoritySessionAndReturnsBackendResponse` fails at absent runtime assembly. Additional RED cases assert no payload/backend accept on unknown flow, wrong digest, expired mapping, ACP denial, or Stream Credit rejection; buffered CONNECT payload must survive handoff.

**Implementation:** Load and validate the catalog as deterministic resolution input; execute service name -> canonicalization -> ServiceDigest -> `resolution.NewResult` -> `resolution.Service.Publish` to create the immutable Mapping; never accept a pre-seeded Mapping as a shortcut. Then accept proxy flows; consume FlowContext through Router; acquire/verify authority lazily; select/create TS and one independently authorized SC; open credited Application Stream; copy both directions with fixed buffers, deadlines, half-close, cancellation, and exactly-once cleanup. Emit only closed-enum events and aggregate usage/evidence hooks.

**GREEN criteria:** One configured curl-equivalent request returns the exact backend body through the real QUIC stream; every RED negative has zero backend requests and no leaked FlowStore/proxy/session ownership.

**Security invariants:** Fixture data supplies resolution inputs only; the real canonicalization, ServiceDigest, ResolutionResult, and Mapping lifecycle is mandatory and no pre-seeded Mapping bypass is allowed. Mapping fields, not adapter input, create AuthorityKey; TCP names the demo application's reliable-stream/application profile while NBSR secure transport remains QUIC v1/TLS 1.3/`nbsr-quic-1`; one TCP flow maps to one Application Stream; no payload replay/fallback; Synthetic IP is never a selector; cleanup releases the mapping exactly once.

**Verification:** `go test ./internal/client ./cmd/nbsr-demo-client -count=1`; UCRT `go test -race ./internal/client ./cmd/nbsr-demo-client -count=1`; `go vet` on the same packages.

**Stop condition:** The in-process integration proves the complete ownership sequence and returns all aggregate usage to zero before external lifecycle scripting begins.

### Task 5: Add deterministic Windows start/run/stop surface

**Goal:** Make the single-service demo reproducible with three small PowerShell commands while keeping runtime material outside Git.

**Files:**
- Create: `scripts/demo/start-nbsr-demo.ps1` (NEW)
- Create: `scripts/demo/run-nbsr-demo.ps1` (NEW)
- Create: `scripts/demo/stop-nbsr-demo.ps1` (NEW)
- Create: `scripts/demo/lib-nbsr-demo.ps1` (NEW shared lifecycle helpers)
- Create: `scripts/demo/test-nbsr-demo-scripts.ps1` (NEW)
- Modify: `.gitignore` only if a new runtime suffix is not already covered by `test-results/`, `*.pem`, `*.key`, and `*.log`

**Existing components reused:** Validated binary location convention `C:\NBSR-build`, readiness JSON pattern from current interop runners, and PowerShell process handling patterns.

**RED tests first:** Script test fails because start/run/stop commands do not exist; it requires refusal of OneDrive build roots, stale/PID-mismatched state, wrong Rust hash, occupied ports, missing trust files, and start-order inversion.

**Implementation:** `start` creates `test-results/nbsr-demo/runtime`, generates secrets/config, verifies the validated Rust binary hash, reserves ports, and starts backend -> ACP -> Rust -> Go client with readiness gates. `run` uses `curl.exe` with the explicit proxy and service name. `stop` verifies recorded PIDs/start times, stops only owned processes in reverse order, removes secret/runtime files, and retains redacted evidence. No script rebuilds Rust automatically.

**GREEN criteria:** Fresh start/run/stop succeeds twice; stale state and wrong hashes fail safely; no orphan process, secret, live mapping, flow, SC, stream, or listener remains.

**Security invariants:** Exact PID/start-time/parent ownership before termination; secrets ignored and cleaned; backend command absent from application command/output; no broad process kill or filesystem deletion.

**Verification:** `pwsh -NoProfile -File scripts/demo/test-nbsr-demo-scripts.ps1`; then manual three-command run from repository root.

**Stop condition:** A Windows user can run only start, run, stop and obtain the response while no backend network endpoint exists.

### Task 6: Add minimal negative matrix and shared-IP isolation gate

**Goal:** Prove the high-value fail-closed cases and, if bounded by the existing destination adapter, two-service same-IP/same-port isolation.

**Files:**
- Create: `scripts/demo/verify-nbsr-demo.py` (NEW)
- Create: `tests/demo/test_nbsr_end_to_end.py` (NEW)
- Modify: `client/nbsr-go-client/demo/testdata/service-a.json`
- Create: `client/nbsr-go-client/demo/testdata/service-b.json` only if the Rust connector map already supports a second fixed binding without another wire/API change (NEW, conditional but fully defined)

**Existing components reused:** Tranche 6 two-service correlation tests, ACP mutation hooks, Rust admission mutation modes, and backend request counters.

**RED tests first:** Evidence verifier requires successful service A plus unknown-service, authority-denied, digest-mismatch, expired-mapping, and direct-backend-denied results with backend counts. If service B is enabled, require both names to resolve to `127.0.0.2`, port 8080, and return distinct bodies with zero cross-delivery.

**Implementation:** Orchestrate the five mandatory negatives using explicit test hooks unavailable in normal run mode. Add service B only as a fixed second catalog/connector binding; if that requires new wire semantics or unbounded dynamic routing, record it as POST-DEMO and rely on the existing Tranche 6 same-IP isolation regression for initial completion.

**GREEN criteria:** Mandatory matrix passes; every denial has zero destination payload/backend requests. Optional service B proves identical Synthetic IP+port with distinct immutable mappings and responses.

**Security invariants:** Test mutation hooks are explicit, opt-in, and rejected in normal mode; direct-backend case uses topology enforcement rather than secrecy alone; no negative retries to origin.

**Verification:** `python -m pytest tests/demo/test_nbsr_end_to_end.py -q`; `python scripts/demo/verify-nbsr-demo.py --runtime test-results/nbsr-demo/runtime`.

**Stop condition:** The minimum five negative properties are machine-verified; service B is either proven live or explicitly recorded POST-DEMO without weakening service A.

### Task 7: Evidence, cleanup, privacy, and reproducibility closure

**Goal:** Produce a reviewed evidence bundle and exact completion gate without overstating demo scope.

**Files:**
- Create: `docs/demo/nbsr-end-to-end-demo.md` (NEW)
- Create: `docs/demo/nbsr-end-to-end-demo-evidence.md` (NEW)
- Create: `docs/demo/nbsr-end-to-end-demo-limitations.md` (NEW)
- Modify: `scripts/demo/verify-nbsr-demo.py`
- Modify: `docs/protocol/status.md` only after all acceptance evidence passes

**Existing components reused:** Tranche 7 collector/health snapshots, repository privacy scan patterns, Go/Rust focused suites, and V3.6 anti-drift checklist.

**RED tests first:** Evidence verifier rejects missing requested/canonical name, Mapping event, authority verification, TS/SC selection, Stream Credit/Application Stream admission, backend response digest, negative outcomes, binary/source hashes, cleanup snapshot, or forbidden origin/secret/raw identifier.

**Implementation:** Emit an allowlisted JSON evidence bundle with schema/version, source and binary hashes, safe event enums, aggregate counts, expected response hash/body, negative results, and final zero/idle usage. Document Demonstrated, Implemented but not demonstrated, Demo fixture, Not implemented/future, Rust provenance limitation, and exact commands.

**GREEN criteria:** Evidence verifier passes; focused Go, Go race, vet, Rust, legacy interop, privacy scan, and diff hygiene pass; runtime directory contains no secret after stop; no wire/schema/vector changes appear in diff.

**Security invariants:** No endpoint, key, token, raw grant/proof, unbounded identifier, or payload beyond the fixed public demo body in normal logs/metrics/evidence; claims remain loopback/demo-specific.

**Verification:** Focused commands from Tasks 1–6; `go test ./... -count=1` in the production client and demo modules; UCRT race tests for affected Go packages; focused Rust tests; `python scripts/verify_p1f_p2d_live_go_rust.py --build-root <validated-build-root>`; repository privacy scan; `git diff --check`; explicit frozen wire/schema/registry/vector diff.

**Stop condition:** All completion criteria below are evidenced and one focused correctness/security review reports no remaining Critical/Important issue. Only then may status say `NBSR END-TO-END DEMO COMPLETE`.

## J — Human decisions

NONE. The approved explicit proxy, shared Synthetic IP, ACP authority chain, Go/quic-go to Rust/Quinn transport, and destination-private connector boundary determine the implementation. Rust fresh-build provenance is a separately recorded risk, not a reason to redesign the demo.

## K — POST-DEMO

- Transparent DNS interception, TUN, WFP, kernel routing, proxy autoconfiguration, application SDK, UDP, CONNECT-UDP.
- Installer/service packaging, Kubernetes, router/OpenWrt packaging, mobile clients, UI/dashboard, external telemetry backend.
- Resolver failover/conflict policy, production trust distribution, production OriginSet publication, multi-region/cross-edge handover, production sizing/benchmark campaign.
- Live two-service same-IP/same-port demonstration if Task 6 proves it requires more than a fixed second destination-private mapping; the deterministic Tranche 6 isolation regression remains required.
- Fresh Rust 1.97.1 provenance repair. Do not modify Cargo source/lock/dependencies under this demo plan.

## Completion gate

Declare `NBSR END-TO-END DEMO COMPLETE` only when evidence proves: application request by service name through the explicit proxy; production canonicalization and ServiceDigest; one shared Synthetic IP semantics; immutable Mapping and single-use FlowContext; verified RouteGrant through ACP; TS and independently authorized SC; Stream Credit and Application Stream; real QUIC/TLS Go-to-Rust payload; backend receipt and response; no successful direct-backend path/fallback; mandatory negative cases fail closed with zero backend activity; normal application/log/metric surfaces contain no Origin Endpoint; affected tests/race/vet pass; shutdown returns state to zero/idle; and frozen wire/schema/registry/vector paths are unchanged.

## L — Implementation readiness

**PLAN READY FOR HUMAN REVIEW**

The demo can use the previously validated Rust binary and must verify its hash. A fresh Rust rebuild is not required for the first implementation on this checkout. Reproducibility on a machine lacking that validated artifact remains explicitly limited by the existing Rust 1.97.1 provenance issue; if the validated artifact is unavailable at implementation time, report `DEMO_BLOCKER — RUST BUILD PROVENANCE` rather than rebuilding silently.
