# NBSR capability validation report

## Executive verdict

**Security remediation outcome: fixed within the bounded local prototype.**
All seven specified gaps have code/configuration fixes, focused regression
tests, and proportionate live evidence.

**Overall NBSR capability verdict: partially functional.** The repository
credibly demonstrates a default-deny registered-name route, hidden origin,
verified TLS relay, optional enterprise policy enforcement, isolated Compose
topology, and enforced Kind NetworkPolicy. It does not implement the complete
native NBSR tunnel, lifecycle, signed name ownership, regional HA, ISP
federation, or production trust operations required by Protocol Vision v2.

No status below means production-ready. Status values are exactly:
`Confirmed functional`, `Partially functional`,
`Implemented but not live-verified`, `Design/documentation only`,
`Not implemented`, or `Blocked/unverified`.

## Component and trust-boundary inventory

| Component | Boundary and privilege | Key data | Client-visible addressing |
|---|---|---|---|
| Workload demo client | Enterprise client network | Eight-hour local Ed25519 JWT | Logical service only |
| Enterprise control plane | Enterprise client/control networks; ticket signer | Identity public key, ticket private key, TLS server cert, OPA mTLS client cert | Returns logical service and signed ticket, no backend IP |
| OPA | Enterprise control network only | Policy and TLS server identity | Not client-visible |
| Envoy gateway | Enterprise client/protected networks | TLS server and backend mTLS client identities | Fixed gateway address only |
| Ticket verifier | Enterprise protected network only | Ticket public key and TLS server identity | No host port |
| Payments | Enterprise protected network only | TLS server identity | No host port |
| Name control | ISP client/control network | Name-binding private key and ISP TLS server identity | Returns synthetic address and bounded route capability |
| Windows-first client adapter | Local application boundary | Ephemeral Ed25519 session key and owned-address journal | Synthetic loopback address only |
| Name relay | ISP client and ISP origin networks | Binding public key and distinct ISP TLS server identity | Configured gateway address |
| Name origin | ISP origin network only | HTTPS origin TLS identity | No host port |
| Route registry | Operator-controlled configuration | Canonical route metadata and deterministic fingerprint | Registered name metadata, not caller override |
| Calico | Kind cluster enforcement plane | NetworkPolicy state | Not part of NBSR wire semantics |

## Allowed communication matrix

Everything not listed is denied by topology, default-deny NetworkPolicy, service
configuration, or lack of a host publication.

| Source | Destination | Port | Security and purpose |
|---|---|---:|---|
| Enterprise client | Control plane | 8000 | Server-authenticated TLS; workload identity and route request |
| Enterprise client | Envoy | 8080 | Server-authenticated TLS; scoped enterprise ticket |
| Control plane | OPA | 8181 | TLS 1.3 mTLS; authorization decision |
| Envoy | Ticket verifier | 9000 | TLS 1.3 mTLS; ext_authz request context |
| Envoy | Payments | 7000 | TLS 1.3 mTLS; fixed protected application route |
| ISP client/adapter | Name control | 8444 | Server-authenticated TLS; registered-name request |
| ISP client/adapter | Name relay | 8443 | TLS 1.3 plus Ed25519 session proof and nonce |
| Name relay | Registered origin | 80 | Compatibility HTTP inside outer TLS; no NBSR credential at origin |
| Name relay | Registered origin | 443 | Opaque end-to-end HTTPS preserving registered SNI/Host |
| Name-resolving workloads | CoreDNS/kube-dns pods | 53 TCP/UDP | Kubernetes service/origin lookup only |

## Capability validation

## Enterprise authorization proof of concept

| Capability | Status | Components | Exact test/live command | Observed result | Security property proven | What remains unproven | Vision v2 placement | Class |
|---|---|---|---|---|---|---|---|---|
| Ed25519 workload identity | Confirmed functional | `security.py`, control plane, bootstrap | `python -m pytest -q tests/test_control_plane.py tests/test_security.py` and Compose demo | Valid identity admitted; denied/tampered/invalid claims rejected | Explicit EdDSA, issuer, audience, expiry, JTI, subject validation | Production workload attestation, revocation, rotation | Phase 6 identity extension | Enterprise extension |
| OPA default-deny decision | Confirmed functional | `policy/`, control plane, OPA | `opa test policy -v`; Compose unauthorized identity/unknown service | Explicit allow required; other requests return 403/no ticket | Policy failure and non-match fail closed | Signed bundles, HA policy distribution, audit | Phase 6 authorization | Enterprise extension |
| Method/path authorization | Confirmed functional | OPA, ticket, verifier | Compose method/path escalation plus verifier tests | GET status allowed; POST/payment escalation denied | Ticket scope checked against actual request | Richer action semantics and policy lifecycle | Phase 6 authorization | Enterprise extension |
| Short-lived signed routing ticket | Confirmed functional | `security.py`, control plane | Compose authorized and expiry scenarios | Ticket works before expiry and fails afterward | Integrity, bounded lifetime, service/method/path scope | Channel binding and one-time distributed use | Phase 6 authorization | Enterprise extension |
| Envoy ext_authz enforcement | Confirmed functional | Envoy, verifier | `docker compose run --rm --no-deps gateway --mode validate`; Compose demo | Authorized request reaches payments; missing/invalid ticket denied | Enforcement occurs before fixed upstream | Envoy compromise/attestation, HA | Phase 6 enforcement | Enterprise extension |
| Header-spoofing resistance | Confirmed functional | Envoy ext_authz request, verifier | `python -m pytest -q tests/test_verifier.py tests/test_security.py` | Missing/duplicate/forged service context cannot widen request | Gateway-overwritten service and actual method/path are authoritative | Live hostile proxy test beyond local Envoy | Phase 6 enforcement | Enterprise extension |
| Backend not publicly reachable | Confirmed functional | Compose networks, Kind policy, payments | Compose direct-backend scenario; relay DNS/IP probes; `docker compose ps` | No host port; direct client and relay paths denied | Gateway is the only admitted application path | Host/root and cluster-admin compromise | Backend concealment invariant | Deployment support |
| Missing/tampered/expired credentials | Confirmed functional | Envoy, verifier, JWT validation | Compose 8-scenario demo | All three classes denied | Fail-closed ticket validation | Distributed revocation | Mandatory security | Enterprise extension |
| Enterprise ticket replay rejection | Not implemented | Enterprise verifier | Review plus existing enterprise ticket tests | Valid bearer ticket remains reusable until expiry | None beyond bounded lifetime/scope | Channel binding or distributed one-time replay store | Anti-replay property | Enterprise extension |

## Name-based routing vertical slice

| Capability | Status | Components | Exact test/live command | Observed result | Security property proven | What remains unproven | Vision v2 placement | Class |
|---|---|---|---|---|---|---|---|---|
| Application requests registered name, not origin IP | Confirmed functional | API model, registry, Windows prototype | `python services/name-relay/app.py demo` and name-service tests | `facebook.test` accepted; arbitrary hostname/IP rejected | Name-first caller contract | Native global ownership/delegation | Phase 1 name request | Core protocol |
| Bounded route capability | Confirmed functional | Registry, name security, name control | Route-registry/name-security tests | Capability binds name, route, port, endpoint set, fingerprint, gateway, session, expiry | Capability cannot be widened by caller fields | Normative wire format and distributed issuers | Phase 1 route creation | Core protocol |
| Client does not receive durable backend IP | Confirmed functional | Name response, adapter mapping | ISP live demo and E2E tests | Client-visible state contains synthetic address; concealment assertion passed | Backend address concealment from client | Operator anonymity is not provided | Backend concealment invariant | Core protocol |
| TLS client-to-relay route | Confirmed functional | Windows client, relay | ISP live demo; untrusted relay certificate tests | Authenticated TLS route succeeds; untrusted TLS fails | Confidentiality/integrity and server identity | Native peer-mutual tunnel profile | Mandatory security | Core protocol |
| HTTPS SNI and Host preservation | Confirmed functional | Adapter, opaque relay, origin | ISP live HTTPS scenario | Origin certificate validated; `facebook.test` SNI/Host preserved | End-to-end service authentication | Real public origin/interoperability | Phase 1 stream | Core protocol |
| Unknown names and destination overrides fail | Confirmed functional | API model, registry | Name-service/API negative tests | Unknown, override, direct IP, alias, Unicode rejected | Default-deny/public-proxy prevention | Registry governance | Name-first invariant | Core protocol |
| Relay failover within registered policy | Implemented but not live-verified | Relay resolver/connector, client gateways | `python -m pytest -q tests/test_name_relay.py tests/test_windows_agent.py` | In-process unit tests choose ordered endpoint and fall back only within constraints | Failure cannot widen destination | Multi-container/regional failure exercise | Phase 3 selection/failover | Core protocol |
| DNS rebinding and stale policy fail closed | Implemented but not live-verified | Relay fresh resolver, local registry | Focused relay rebinding/fingerprint tests | Changed/extra endpoint and stale fingerprint rejected | TOCTOU and rollback resistance in code | Adversarial live DNS infrastructure | Native naming transition | Core protocol |

## Windows client/adapter prototype

| Capability | Status | Components | Exact test/live command | Observed result | Security property proven | What remains unproven | Vision v2 placement | Class |
|---|---|---|---|---|---|---|---|---|
| Synthetic address ownership | Partially functional | `windows_agent.py`, adapter journal | `python -m pytest -q tests/test_windows_agent.py tests/test_synthetic.py` | Unit adapter adds/removes only owned synthetic addresses | No blind deletion of pre-existing address in modeled adapter | Live full Windows adapter/WFP behavior | Phase 1 local client | Core protocol |
| Durable recovery after restart | Partially functional | Windows journal/recovery | Windows-agent recovery tests | Modeled crash journal is retried and bounded | Recovery does not claim unowned addresses | Machine restart and real adapter mutation | Phase 2 lifecycle | Core protocol |
| Local listener behavior | Partially functional | DNS stub, TCP interception | DNS/Windows E2E tests | Local listeners map synthetic route and forward one TCP flow | Application avoids origin address | Broad application compatibility and OS resolver integration | Phase 1 local API | Core protocol |
| TLS relay validation | Partially functional | Windows client TLS context | Windows TLS tests and in-process E2E | CA/hostname validated; TLS below 1.3 disabled | No silent certificate bypass | Hardware/OS trust store deployment | Mandatory security | Core protocol |
| Gateway failover | Implemented but not live-verified | Ordered `RelayGateway` list | Windows-agent failover tests | Failed first gateway moves to authenticated second | No plaintext/untrusted fallback | Live network transition | Phase 2 migration | Core protocol |
| No plaintext downgrade | Partially functional | Windows client config | Plaintext/missing-CA tests | Invalid TLS configuration fails before connection | Fail-closed transport selection | Native version negotiation | Downgrade resistance | Core protocol |
| Real Windows full-device test | Blocked/unverified | OS network stack | Not run; no signed WFP driver exists | Only Python loopback/in-process evidence available | None for system-wide interception | Driver signing, install, multi-app QA | Phase 1 platform integration | Deployment support |

## Deployment capabilities

| Capability | Status | Components | Exact test/live command | Observed result | Security property proven | What remains unproven | Vision v2 placement | Class |
|---|---|---|---|---|---|---|---|---|
| Fresh Compose build/deployment | Confirmed functional | Dockerfile, Compose | `docker compose build`; `docker compose up -d --force-recreate`; demos | All services healthy and both profiles pass | Integrated service and TLS topology works locally | HA, upgrades, production runtime hardening | Reference implementation | Deployment support |
| Kind all pods ready | Confirmed functional | Kind scripts/manifests | `./scripts/kind-up.ps1`; `kubectl get pods -A` | 18 observed pods ready, zero restarts | Deployment manifests and pinned CNI work together | Multi-node/zone failure | Phase 3 reference | Deployment support |
| Enforced least-privilege connectivity | Confirmed functional | Calico, NetworkPolicies, probe scripts | `./scripts/verify-kind-security.ps1` | All required allow/deny probes passed | Policy is enforced, not merely accepted | Production admission governance | Phase 3 security | Deployment support |
| Loopback-only host publication | Confirmed functional | Compose, Kind cluster config | Compose port inspection; `Get-NetTCPConnection` | Only `127.0.0.1` listeners for tested NBSR ports | Reduced developer host exposure | Host firewall/production ingress | Deployment invariant | Deployment support |
| Clean teardown | Confirmed functional | Compose/Kind down scripts | `docker compose down -v --remove-orphans`; `kind delete cluster --name nbsr` | Local resources removed during the run | Reproducible local cleanup | Production deprovisioning | Test hygiene | Deployment support |

## Security capabilities

| Capability | Status | Components | Exact test/live command | Observed result | Security property proven | What remains unproven | Vision v2 placement | Class |
|---|---|---|---|---|---|---|---|---|
| Default-deny route registry | Confirmed functional | Registry, config, control, relay | Registry/name-service/relay tests | Only enabled exact route works | Caller cannot choose arbitrary destination | Signed ownership and admin workflow | Native naming | Core protocol |
| SSRF and public-proxy prevention | Confirmed functional | Endpoint constraints, special-use checks | Public name/IP and special-use negative tests; live relay-to-payments denial | Public/special address status alone grants nothing | Default-deny and connect-time checks | External adversarial DNS lab | Source/destination enforcement | Core protocol |
| Anti-replay | Partially functional | ISP proof/replay cache; enterprise ticket | ISP replay/capacity tests | ISP nonce replay denied; enterprise bearer replay remains | Bounded local ISP replay | Durable regional and enterprise anti-replay | Mandatory anti-replay | Core and enterprise |
| TLS/mTLS identity | Confirmed functional | Service TLS, Envoy, OPA/Uvicorn | TLS matrix, Envoy validation, live Compose | Valid paths succeed; CA/SAN/EKU/expiry/client failures close | Authenticated encrypted container boundaries | Managed PKI/rotation/revocation | Mandatory security | Deployment support |
| Origin concealment | Confirmed functional | Synthetic mapping, topology, relay | ISP live demo and host-port inspection | No client origin IP; no origin/backend host port | Concealment from unprivileged client | Operator/admin visibility | Backend concealment | Core protocol |
| Control/data-plane isolation | Confirmed functional | Five Compose networks, Kind policies | Compose relay DNS/IP denials; Kind probes | Relay cannot reach enterprise protected services | Named boundaries constrain compromise | Host/cluster-admin bypass | Platform-neutral architecture | Deployment support |
| Fail-closed behavior | Confirmed functional | Registry, TLS, OPA, verifier, state bounds | Focused negative suites | Unknown/stale/ambiguous/TLS/policy/cache failures deny | Partial failure does not become allow | Distributed outage/partition behavior | Mandatory security | Core and enterprise |
| Bounded admission/rate-limit state | Confirmed functional | Replay cache, allocator, admission registry | Relay/synthetic/name-service capacity tests | Hard bounds and expiry cleanup pass | Single-process memory growth bounded | Distributed tenant quotas/DDoS service | Phase 4 abuse control | Core protocol |
| Safe ephemeral key/certificate handling | Partially functional | Bootstrap, secure files, ignore/build/package rules | Secure-file tests; build context and package scans | Generated material is atomic/protected/ignored and excluded | Source/archive leakage reduced | Developer host compromise, HSM/KMS, rotation | Trust operations | Deployment support |
| Deterministic release archive | Implemented but not live-verified | Packaging engine and wrappers | Unit packaging tests; final clean-commit command pending | Dirty-source rejection and byte-stable ZIP unit controls pass | Design prevents uncommitted/sensitive archive input | Final commit-dependent ZIP/hash until handoff gate | Signed artifacts direction | Deployment support |

## Vision v2 conformance summary

| Vision invariant/phase | Status | Evidence | Remaining requirement |
|---|---|---|---|
| Name-first and backend concealment | Partially functional | Registered name, synthetic address, bounded capability, hidden origin live | Native signed ownership/delegation |
| Mandatory secure transport | Partially functional | Verified TLS/mTLS and no plaintext retry | Normative native peer/tunnel conformance profile |
| Enterprise IAM optional | Confirmed functional | ISP profile runs independently | Extension negotiation specification |
| DNS transitional | Partially functional | DNS stays behind gateway registry boundary | Native naming without DNS in critical path |
| Phase 1 core client/server | Partially functional | Local vertical slice meets no-backend-IP criterion | Platform integration and native tunnel |
| Phase 2 lifecycle | Not implemented | State-machine design only | Renewal, rotation, revocation, migration/resumption |
| Phase 3 regional Kubernetes | Partially functional | Enforced single-node Kind lab | HA, zones, autoscaling, observability, failure SLO |
| Phase 4 ISP lab | Partially functional | Local ISP-shaped profile and bounded controls | Actual ISP source/destination enforcement |
| Phase 5 federation | Not implemented | None | Multi-operator trust, delegation, routing, revocation |
| Phase 6 enterprise extensions | Partially functional | Strong authorization proof of concept | Production identity, audit, replay, compliance |
| Phase 7 standardization | Not implemented | None | Normative draft, conformance suite, two implementations |

## Test evidence

| Evidence | Result |
|---|---|
| Baseline suite before modification | 180 passed, 1 skipped, 12 third-party warnings on unsupported Python 3.14 |
| Route registry/security focused suite | 172 passed |
| Service TLS/deployment focused suite | 57 passed |
| Kind static focused suite | 12 passed |
| Full Python 3.12.13 suite | 248 passed, 1 skipped |
| Full Python 3.13.14 suite | 248 passed, 1 skipped |
| Ruff check and format | Passed |
| OPA/Rego policy tests | 5 of 5 passed |
| Enterprise Compose scenarios | 8/8 passed |
| ISP Compose scenarios | HTTP/80 and HTTPS/443 passed; concealment and SNI/peer assertions passed |
| Compose relay-to-payments | DNS failed; direct IP/7000 timed out |
| Kind Calico enforcement | All required positive/negative probes passed; zero restarts |
| Host binding inspection | Tested NBSR host listeners were loopback-only |

The final post-documentation pytest, OPA, extracted-ZIP pytest/Ruff, inventory,
and SHA-256 checks are intentionally rerun on the final clean commit. The
commit-dependent artifact path and hash are reported in the branch handoff.

## Remaining attack paths

- Compromise of a signing key, demo CA, Docker host, or Kubernetes cluster-admin
  is not contained.
- Enterprise ticket replay remains possible inside the short validity window.
- Process-local replay/admission/allocation state is inconsistent across
  replicas unless future shared state or sticky routing is added.
- Local registry administration is trusted; signed ownership and delegation do
  not exist.
- Gateway/operator metadata visibility and retention are not controlled.
- Compatibility HTTP provides no end-to-end origin authentication.
- A malicious or compromised Envoy is still the enterprise enforcement
  authority.
- Real Windows system-wide interception and restart behavior are unverified.

## Production blockers

Managed PKI/HSM and rotation, distributed revocation/replay state, signed name
ownership, normative tunnel/version negotiation, lifecycle semantics, HA and
failure SLOs, production admission policy, privacy/audit operations, signed
Windows networking integration, external penetration/protocol review, and two
independent interoperable implementations.

## Prioritized next roadmap

1. Define the normative native discovery, handshake transcript, downgrade
   rules, and name ownership/delegation model.
2. Add enterprise ticket channel binding or a bounded distributed one-time
   replay mechanism.
3. Specify lease renewal, active-stream handling, rotation, revocation,
   migration, resumption, and closure; build conformance tests first.
4. Move signing and CA operations to managed keys with rotation and emergency
   revocation drills.
5. Build a multi-node regional lab with shared bounded state, multiple gateways,
   zone failure, rollback, and observability evidence.
6. Run a real ISP source/destination enforcement experiment without adding
   enterprise IAM to the core path.
7. Implement and validate a signed Windows client integration, then add an
   independent client/server implementation.
