# NBSR final security hardening report

This report records the historical Vision V2 baseline and is not V3
implementation evidence. Current direction is
[NBSR Protocol Vision V3](architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md).

## Outcome and scope

This bounded pass remediated the seven specified gaps on
`codex/nbsr-final-hardening-validation`. It did not invoke the broken Codex
Security Start scan/Deep Scan sealing workflow. Evidence came from direct code
inspection, focused regression tests, fresh Compose and Kind deployments,
manual trust-boundary review, and extracted-package validation.

The result is a hardened local prototype, not a production system and not full
[NBSR Protocol Vision v2](architecture/NBSR_Protocol_Vision_v2.pdf)
conformance. QUIC, federation, native ownership/delegation, lifecycle renewal,
key rotation, migration/resumption, and full ISP deployment were not
implemented.

## Finding dispositions

| Finding | Vulnerable path | Enforcement boundary | Disposition | Focused evidence |
|---|---|---|---|---|
| 1. Default-allow public destination routing | Caller-controlled hostname reached `destination_policy.py` global-unicast allowance and could be signed by name control | `route_registry.py`, name control issuance, relay-local registry, relay connect-time resolution | **Fixed.** Only canonical enabled registered names are admitted. Signed and relay-local route ID, port, endpoint set, policy fingerprint/version, gateway, session, and expiry must agree. | Route registry, name service, relay, destination-policy, and API suites; arbitrary public name/IP, override, alias, Unicode, rebinding, stale policy, cross-route replay, CIDR, and special-use negatives |
| 2. Compose relay-to-backend bypass | `name-relay` shared enterprise protected network with payments | Compose network attachment and internal addressing | **Fixed.** Relay uses only ISP client/origin networks; enterprise protected network contains gateway, verifier, and payments. | Live relay DNS lookup failed; direct `172.30.0.10:7000` connection timed out; enterprise and registered ISP positive paths passed |
| 3. Host ports on all interfaces | Compose ports and Kind extra mappings defaulted to all host interfaces | Docker/Kind host publication | **Fixed.** Necessary developer ports explicitly bind `127.0.0.1`; backends publish none. | Compose `port` showed loopback for 8000/8080/8443/8444; Kind socket inspection showed loopback for 8080/8443/8444 |
| 4. Sensitive internal plaintext hops | Control plane to OPA, Envoy ext_authz, and gateway to payments used HTTP | Service TLS contexts, OPA/Uvicorn servers, Envoy upstream TLS | **Fixed.** Internal enterprise hops use TLS 1.3 mTLS with separate service identities; gateway default is HTTPS; failures never retry plaintext. | Missing/untrusted CA, SAN, wrong-service, expiry, client-cert, plaintext, negotiation, no-retry, and valid mTLS tests; fresh live Compose flow |
| 5. Incomplete Kubernetes policy/probes | DNS allowed any kube-system pod; Kind policy enforcement was inferred; required denials absent | Calico CNI and namespace/workload NetworkPolicy | **Fixed for the reference lab.** Kind disables default CNI, installs checksum-verified Calico v3.32.1, selects only kube-dns pods, and runs exhaustive probes. | Fresh cluster: Calico 1/1, all 18 observed pods ready, zero restarts; Service IP, Pod IP, unrelated pod, cross-namespace, metadata, and link-local denials; required flows allowed |
| 6. No deterministic release packaging | Manual ZIP had no reproducible source/inventory/validation workflow | `package_release.py` plus PowerShell/Bash wrappers | **Fixed.** Explicit ref resolves to commit; tracked dirt blocks; Git archive source, prohibited path/content scan, deterministic inventory/ZIP, safe extraction, inventory comparison, extracted Python 3.13 pytest/Ruff, and SHA-256 sidecar are mandatory. | PowerShell and Bash/WSL clean-commit runs produced the same byte-identical ZIP; extracted tests/Ruff and an independent 121-entry prohibited-content scan passed |
| 7. Python 3.14 remained allowed | `requires-python` had no upper bound and container used Python 3.12 | Package metadata, constraints, pinned container runtime | **Fixed.** Supported range is `>=3.12,<3.14`; primary image is digest-pinned Python 3.13.14; exact runtime/dev constraints are repository-native; project deprecations fail tests. | Python 3.12.13: 248 passed, 1 skipped; Python 3.13.14: 248 passed, 1 skipped; primary Docker build and Ruff check/format passed |

## Route registry security details

`config/name-routes.json` registers the private demo explicitly. The request
model exposes no destination field. Canonicalization accepts only the exact
ASCII registry name and rejects case/trailing-dot aliases and IDNA ambiguity.
An operator entry defines route ID, origin, ports, CIDR/exact endpoints,
expected Host/SNI, enabled state, and version/fingerprint.

The relay independently loads the registry and re-resolves the configured
origin immediately before connection. A valid signature does not override local
policy. Fresh resolution must exactly match the signed endpoint set and every
endpoint must remain within current constraints. Empty, expanded, changed, or
stale results fail closed.

## TLS identity details

Signing and transport roles remain separate:

- Ed25519 signs workload identities, enterprise route tickets, and ISP route
  capabilities with different keys.
- TLS leaf keys use ECDSA P-256, signed by the appropriate local demo CA.
- Control plane, gateway, OPA, verifier, payments, name control, relay, and
  origin have distinct certificates and SAN/EKU roles.
- Enterprise and ISP demo trust domains are separate.

The TLS test matrix covers valid connection, missing CA, untrusted CA, wrong
hostname/SAN, wrong service certificate, expired certificate, missing client
certificate, plaintext endpoint, and no plaintext retry. The live enterprise
demo passed all eight allow/deny scenarios after internal mTLS was enabled.

## Deployment evidence

### Compose

- Fresh image build completed.
- `docker compose config --quiet` and Envoy `--mode validate` passed.
- Authorized enterprise request passed through OPA, ticket issuance, Envoy
  ext_authz, verifier, and payments.
- Unauthorized identity, unknown service, missing/tampered/expired ticket,
  method/path escalation, and direct backend access were denied.
- ISP HTTP compatibility and HTTPS origin-security paths passed.
- Client-visible state omitted the origin address; origin observed the relay
  peer and HTTPS SNI.
- Relay could neither resolve payments by service name nor connect to its
  container IP/port.

### Kind

- Kind v0.32.0 created a Kubernetes v1.35.0 node from a digest-pinned image.
- The Calico manifest URL and SHA-256 are fixed and checked before apply.
- Calico node/controller, CoreDNS, control-plane components, and all eight NBSR
  pods were ready with zero restart counts.
- Required gateway-to-verifier/payments, control-to-OPA, relay-to-origin 80/443,
  and DNS flows passed.
- Relay-to-payments Service/Pod IP, relay-to-enterprise services, unrelated
  pod-to-backends, cross-namespace, metadata, and second link-local flows were
  denied.
- Temporary probe pods and namespace were absent after the harness completed.

## Test evidence recorded during the pass

| Gate | Result |
|---|---|
| Baseline before modification | 180 passed, 1 skipped, 12 third-party Python 3.14 warnings |
| Default-deny route focused set | 172 passed; Ruff and Compose config passed |
| TLS/deployment focused set | 57 passed; 6 Python 3.14 third-party warnings; Ruff passed |
| Kind static focused set | 12 passed |
| Python 3.12.13 full suite | 255 passed, 1 skipped |
| Python 3.13.14 extracted-ZIP suite | 255 passed, 1 skipped from both wrappers |
| Ruff | All checks passed; all Python files formatted |
| OPA/Rego | 5 of 5 policy tests passed |
| Enterprise Compose | 8 of 8 scenarios passed |
| ISP Compose | HTTP/80 and HTTPS/443 passed; concealment and peer checks passed |
| Kind NetworkPolicy | All required allow/deny probes passed; zero restarts |
| Release packaging | PowerShell and Bash/WSL produced the same SHA-256; 121 entries and zero prohibited/secret-like content |

Final host pytest, OPA, Python 3.12, both extracted-ZIP Python 3.13 runs,
Ruff, clean-commit packaging, independent archive scanning, and SHA-256
verification passed. Exact artifact paths and digests are emitted in the
generated release summary and SHA sidecar because they depend on the final
commit.

## Residual risks and production blockers

No confirmed Critical vulnerability remains inside this bounded local scope,
but the following prevent production claims:

- signing-key/CA compromise lacks HSM/KMS, automated rotation, and distributed
  revocation;
- enterprise bearer tickets can be replayed during their short lifetime;
- route, replay, admission, and allocation state is process-local;
- native signed name ownership, federation, and lifecycle are absent;
- Kind is single-node/single-replica and has no SLO/chaos/HA evidence;
- the Windows adapter is unit/in-process tested, not a signed live WFP driver;
- compatibility HTTP lacks end-to-end origin authentication;
- privacy retention, audit, incident response, and operator governance are not
  implemented; and
- there are no independent interoperable native NBSR implementations.
