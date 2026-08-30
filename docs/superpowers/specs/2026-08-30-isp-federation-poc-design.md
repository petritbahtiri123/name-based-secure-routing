# ISP/Federation PoC Design

**Status:** Approved architecture, implementation pending a separate approval.

**Goal:** Demonstrate the accepted NBSR secure-route and federation admission path across two isolated logical operator regions, ending at an Origin Connector that is the only component able to reach a private origin.

**Evidence scope:** Docker Desktop on the current Windows host, Linux containers, current repository SHA, deterministic demo identities, and one bounded request at a time. This PoC is not evidence of independent physical ISPs, WAN behavior, production high availability, transparent routing, server-class capacity, or internet scale.

## Non-negotiable invariants

The PoC does not modify frozen authority files or approved digests. It does not change Core v0.2, QUIC/TLS, ALPN, RouteGrant, federation objects, trust bundles, cryptographic formats, authentication, authorization, replay handling, stream admission, ACK meaning, send completion, or fail-closed behavior.

The existing loopback bindings remain unchanged:

- the Go demo ACP remains loopback-only;
- the Go secure-route proxy remains loopback-only;
- `wp8_interop_server` remains bound to `Ipv4Addr::LOCALHOST`;
- no Quinn stream or private transport state is exposed.

Adapters forward opaque bytes between a named container interface and an existing loopback endpoint. They do not parse names, grants, federation objects, QUIC, TLS, HTTP, application payloads, or authorization results. They do not select an origin, mint authority, retry through another security path, or provide fallback.

The legacy FastAPI/OPA/Envoy/name-relay Compose demo remains `LEGACY_REFERENCE_ONLY` and is not started, imported, or cited as evidence.

## Topology

```text
client workload
    |
    | TCP, explicit CONNECT to service-a.nbsr.test:8080
    v
ISP-A ingress adapter --- loopback ---> existing Go secure-route client/runtime
                                             |
                                             | QUIC v1 / TLS 1.3
                                             | ALPN nbsr-quic-1
                                             v
                                      federation-transit network
                                             |
                                             v
ISP-B transport adapter --- loopback ---> existing Rust wp8_interop_server
                                             |
                                             | admitted backend stdin/stdout contract
                                             v
                                      Origin Connector
                                             |
                                             | one bounded TCP connection
                                             v
                                      private origin service
```

Compose creates three isolated bridge networks with project-unique names:

| Network | Members | Internet-facing ports | Purpose |
| --- | --- | --- | --- |
| `isp_a_access` | client workload, ISP-A runtime/ingress adapter | none | Client can address only the ISP-A adapter. |
| `federation_transit` | ISP-A runtime, ISP-B runtime/transport adapter | none | Carries only the existing protected QUIC flow between operators. |
| `isp_b_private` | ISP-B runtime/Origin Connector, private origin | none; `internal: true` | Makes the origin reachable only from the destination-side namespace. |

The client workload is not attached to `federation_transit` or `isp_b_private`. ISP-A is not attached to `isp_b_private`. The private origin is attached only to `isp_b_private`. No service publishes a host port. The Compose project uses a unique bounded project name and labels every owned container, volume, and network for exact cleanup.

The ACP and Go proxy execute in the ISP-A runtime namespace. The Rust destination and its fixed backend child execute in the ISP-B runtime namespace. A PoC-only adapter sidecar may share the corresponding runtime namespace solely so it can reach the unchanged loopback listener; namespace sharing does not add another network attachment.

## Adapter boundaries

### ISP-A ingress adapter

The ISP-A adapter accepts TCP only on its `isp_a_access` address and forwards it byte-for-byte to the Go proxy's exact loopback readiness endpoint. It has one configured upstream, a bounded connection count, bounded idle/operation deadlines, no DNS lookup, and no alternate route. Closing either side closes the other side. Startup fails if the loopback readiness artifact is absent or malformed.

### ISP-B transport adapter

The ISP-B adapter accepts UDP only on one fixed `federation_transit` port and forwards datagrams byte-for-byte to the Rust destination's exact loopback UDP endpoint. Return datagrams are associated only with the initiating peer and bounded by idle time and capacity. It has no packet parser, no QUIC secrets, no TLS keys, no origin-network listener, and no alternate destination.

The orchestrator creates a PoC transport-readiness copy by replacing only `endpoint` with the ISP-B adapter's Compose DNS name and fixed UDP port. It must prove that `alpn`, `ca_der`, `client_cert_der`, `client_key_der`, `quic_version`, `server_name`, and `tls_version` are byte-for-byte identical to the Rust-produced readiness object. The original readiness file is retained as raw evidence. The copied endpoint is plumbing metadata, not new authority.

### Adapter implementation constraints

Adapters live under `deploy/isp-federation-poc/adapter/` and are built as PoC-only binaries or scripts with closed configuration. They must not import NBSR authority, protocol, federation, cryptographic, or application packages. Tests reject additional listeners, configurable fallback targets, payload inspection, and access to `isp_b_private` from the ISP-A adapter.

## Origin Connector contract

The Origin Connector is a new PoC-only executable selected by the existing fixed-hash demo backend map. It implements the existing backend process contract without changing `wp8_interop_server`:

1. read at most one request from stdin, bounded to 4,096 bytes;
2. require the existing accepted request shape for `GET /` and `Host: service-a.nbsr.test:8080`;
3. open exactly one TCP connection to the compile-time/config-file exact target `private-origin:8080`;
4. require the resolved address to belong to the Compose `isp_b_private` subnet recorded by the orchestrator;
5. write the unchanged bounded request, read a bounded response, return it on stdout, and emit only identifier-free completion status on stderr;
6. close all descriptors and exit after the single operation.

The connector does not receive an origin address from the client, request, RouteGrant, environment, DNS outside the Compose private network, or adapter. It does not follow redirects, proxy requests, retry another address, connect through the host, or fall back to a public/direct origin. Resolution failure, address mismatch, timeout, malformed input, excess input/output, origin failure, or cancellation returns no successful response and exits nonzero.

The connector is not an authorization authority. Existing destination admission and backend-map service binding occur before it is spawned. Its fixed target and subnet check are containment controls for this PoC.

## Federation data flow

The PoC reuses `LiveFederationAdmission`, `BilateralAuthorizer`, the sealed WP7 operator-pair admission model, current F75 federation context, and existing local admission attestations. A preflight container executes the exact current-SHA federation admission test path and writes a closed, non-secret result containing only digests, operator labels, PASS/FAIL, and zero-state counters.

The orchestrator starts the data plane only after preflight PASS. It verifies that the federation context and local-attestation digests recorded by preflight match the artifacts consumed by the unchanged Rust destination. A failed or missing preflight prevents adapters and workload from starting. This dependency is orchestration gating, not a new wire message or authorization mechanism.

The successful application flow remains:

1. client sends an explicit CONNECT request naming `service-a.nbsr.test:8080` to the ISP-A adapter;
2. adapter forwards bytes to the unchanged loopback Go proxy;
3. the existing Go path performs resolution, Mapping/FlowContext, ACP authorization, independent RouteGrant verification, QUIC/TLS, Service Channel, Stream Credit, same-stream ACCEPT, and final authority barrier;
4. protected QUIC crosses only `federation_transit` through the ISP-B adapter;
5. the unchanged Rust destination performs destination admission and selects the exact hashed Origin Connector through the existing backend map;
6. the connector reaches the private origin through `isp_b_private` and returns the bounded response over the already admitted application stream.

No application payload reaches the connector or origin before ACCEPT and the final authority barrier.

## Isolation and fail-closed rules

- `private-origin` has no published port and no membership outside `isp_b_private`.
- Client and ISP-A containers must fail DNS resolution and direct TCP access to both `private-origin` and its inspected container IP.
- The federation-transit network cannot route to the origin subnet.
- ISP-A adapter configuration contains no origin name, address, subnet, or credential.
- The client-visible readiness, route, logs, and result contain no private-origin IP.
- Removing the Origin Connector, private origin, federation preflight, or either adapter produces failure, never a direct retry.
- Wrong service/name, unauthorized federation evidence, wrong operator/delegation/trust binding, and stale/replayed context fail before the Origin Connector starts.
- Cleanup requires zero running project containers, zero project networks/volumes, zero connector children, and zero reported NBSR connections, sessions, channels, streams, pending admissions, and queued work.

## Scenarios

| Scenario | Action | Required result |
| --- | --- | --- |
| Authorized route | Valid federation preflight and `service-a.nbsr.test:8080` request | Exact private-origin response; one connector operation; PASS. |
| Direct origin by name | Resolve/connect from client and ISP-A containers | DNS/connect failure; no origin request; PASS. |
| Direct origin by inspected IP | Connect from client and ISP-A using the evidence-recorded origin container IP | Timeout/no route/refused outside the private network; no origin request; PASS. |
| Wrong route | Request an unregistered service/name or wrong port | Fail closed before connector spawn; origin request count remains zero; PASS. |
| Unauthorized federation | Run existing wrong-operator/delegation/trust case | Preflight FAIL, data plane not started, origin request count zero; PASS. |
| ISP-A adapter failure | Stop ingress adapter during/before a new request | Request fails; no direct connection or fallback; resources return to baseline. |
| ISP-B adapter failure | Stop UDP adapter during/before a new route | QUIC/route fails within existing timeout; connector/origin untouched; resources return to baseline. |
| Recovery | Restart the failed adapter, then create a new route/session | A new authorized request succeeds and cleanup returns to baseline. |
| Origin failure | Stop private origin after admission and issue a new request | Connector exits nonzero; no alternate target/fallback; NBSR resources clean up. |

Recovery is a new-connection restart test. The PoC makes no claim of live QUIC connection migration, cross-edge session resumption, automatic production failover, or zero interruption. A second adapter may be tested in a separate cell, but active/standby selection must occur before a new connection and must not alter trust or admission.

## Docker and Compose design

`deploy/isp-federation-poc/compose.yaml` is standalone and must not extend the repository root `compose.yaml`. Images are built from current source using pinned Go, Rust, and runtime base-image digests. Release binaries are copied into minimal non-root runtime images. Build metadata records image digests and executable SHA-256 values.

Compose health checks prove only process/readiness state. They do not classify authorization. The orchestrator performs ordered startup:

1. validate Git state and Compose configuration;
2. build release images;
3. create the isolated networks and private origin;
4. run federation preflight and verify its closed result;
5. start ISP-B destination, create and verify the endpoint-only readiness copy, then start the ISP-B adapter;
6. start ISP-A authority/client runtime and ingress adapter;
7. run each scenario in a fresh bounded lifecycle or explicitly reset all one-shot state;
8. capture logs, inspect topology, collect network membership and counters, then tear down exact project-owned resources.

No automatic installation, firewall modification, host route modification, privileged container, host networking, Docker socket mount, or host port publication is permitted.

## Testing and evidence plan

Implementation follows literal RED to GREEN:

- static tests first reject missing/incorrect networks, host ports, privileged settings, legacy Compose references, extra adapter targets, and origin membership leakage;
- Origin Connector contract tests first fail for absent connector behavior, then cover valid request, wrong host/name, oversize/malformed request, wrong subnet resolution, timeout, cancellation, bounded response, and zero fallback;
- readiness-copy tests prove endpoint-only mutation and reject changes to every cryptographic/transport field;
- orchestration tests prove failed federation preflight cannot start adapters/workload and failed commands cannot become PASS evidence;
- live Compose tests prove authorized success, unauthorized rejection, name/IP direct-origin denial, adapter failures, origin failure, restart-based recovery, and complete cleanup.

The authoritative evidence directory is additive and current-SHA-specific:

`evidence/federation/isp-poc-<start-sha>/`

It contains:

- `environment.json`: Git, branch, timestamp, OS, Docker/Compose, CPU/RAM, toolchains, image and executable hashes;
- `topology.json`: exact container IDs, network IDs/subnets/memberships, no published ports, and inspect commands;
- `analysis.json`: closed scenario matrix with expected/actual/reason, protected-service reachability, origin request count, cleanup, PASS/FAIL/INCONCLUSIVE;
- `summary.md`: factual human-readable report and exact reproduction command;
- `raw/`: Compose config, inspect output, bounded logs, test stdout/stderr, readiness before/after, federation preflight, failure demonstrations, and cleanup inventory;
- `checksums.sha256`: hashes for every evidence file except the checksum manifest itself.

Raw evidence is never manually edited. Derived reports are generated from raw evidence. Logs are allowlisted/redacted to exclude keys, certificates, RouteGrants, proofs, raw subscriber identifiers, internal filesystem paths, and private-origin IP from client-visible artifacts. The origin IP may appear only in the topology and direct-scan raw evidence needed to prove isolation.

Required verification includes focused Python/Go/Rust tests, the existing live federation and secure-route demo tests, Rust release tests, `cargo fmt`, Clippy with `-D warnings`, Go test/vet, Python lint/tests, dependency/privacy/repository-safety checks, `docker compose config`, live scenario execution, checksum validation, and `git diff --check`.

## Expected implementation files

### Add

- `deploy/isp-federation-poc/compose.yaml` — standalone isolated topology.
- `deploy/isp-federation-poc/Dockerfile` — pinned multi-stage release builds and non-root runtime images.
- `deploy/isp-federation-poc/adapter/` — byte-forwarding ISP-A TCP and ISP-B UDP adapters with closed configuration.
- `deploy/isp-federation-poc/private-origin/` — one bounded private HTTP service used only inside `isp_b_private`.
- `client/nbsr-go-client/demo/cmd/nbsr-demo-origin-connector/main.go` — fixed-target stdin/stdout backend-contract connector.
- `client/nbsr-go-client/demo/cmd/nbsr-demo-origin-connector/main_test.go` — connector RED/GREEN contract and failure tests.
- `scripts/federation/run_isp_federation_poc.py` — bounded build/run/evidence/cleanup orchestrator.
- `tests/federation/test_isp_federation_poc.py` — closed Compose, readiness, evidence, and orchestration tests.
- `docs/demo/isp-federation-poc.md` — exact reproduction and non-claims.
- `evidence/federation/isp-poc-<start-sha>/` — generated raw and derived evidence.

### Reuse unchanged

- `nbsr/federation/live_lab.py` and existing federation authority/authorization modules.
- `nbsr/two_operator_lab.py`.
- `tests/federation/test_live_interoperability.py` and F75/local-admission vectors.
- `client/nbsr-go-client/demo/cmd/nbsr-demo-authority/`.
- `client/nbsr-go-client/demo/cmd/nbsr-demo-client/` and its secure-route assembly.
- `crates/nbsr-transport/src/bin/wp8_interop_server.rs`.
- frozen Core/federation/transport authority and existing security regressions.

### Modify only if mechanically required

- `.gitattributes` for byte-stable raw evidence files.
- repository dependency/privacy inventories to list the new PoC-only connector and deployment files.
- `docs/superpowers/plans/2026-08-29-nbsr-evidence-closure.md` to record the final Task 7 classification after evidence exists.

No existing runtime, transport, authority, protocol, cryptographic, trust, or demo component is an expected modification. Discovery that implementation requires such a modification is a stop condition requiring new approval.

## Acceptance and classification

The PoC may be classified PASS only when the authorized route succeeds, all negative cases fail closed, direct origin access fails from both client and ISP-A by name and inspected IP, federation trust is enforced before data-plane startup, adapter/origin failures expose no fallback, restart-based recovery succeeds for a new connection, and all owned resources return to baseline.

If Docker isolation or UDP forwarding cannot preserve the existing QUIC behavior, the result is INCONCLUSIVE and the implementation stops rather than changing transport semantics. Any protected-origin reachability from client/ISP-A, unauthorized connector invocation, state/resource leak, or permissive fallback is FAIL and its raw evidence is preserved.

Even on PASS, the claim is limited to a reproducible two-region Docker logical-isolation PoC on the recorded Windows/Docker host. It does not prove separate physical administration, WAN behavior, production orchestration, live session migration, or public deployment readiness.

## Resolved design decisions

- The private origin is a separate container and has no published port.
- Existing loopback listeners are preserved through namespace-local byte adapters.
- The Origin Connector uses the existing hashed stdin/stdout backend contract; `wp8_interop_server` is unchanged.
- Federation admission gates orchestration and is digest-correlated with the unchanged destination artifacts; no federation wire protocol is invented.
- Failure is fail-closed; recovery uses a new connection after adapter restart, not live session migration.
- The root legacy Compose stack is excluded.

There are no unresolved protocol, trust, cryptographic, wire, authority, or public-interface decisions in this design. Implementation feasibility of UDP forwarding is an evidence question: failure to preserve QUIC behavior yields INCONCLUSIVE rather than redesign.
