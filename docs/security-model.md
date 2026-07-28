# NBSR security model

This document describes the controls actually present in the hardened
prototype. Current architecture direction comes from
[NBSR Protocol Vision V3.6](architecture/NBSR_Protocol_Vision_V3.6.md).
This security model does not claim production readiness or full Protocol Core
v0.1 conformance.

## Security invariants

- Native NBSR direction is name-first and has no optional insecure mode.
- A caller cannot turn a name request into an arbitrary public or private TCP
  proxy.
- Security-sensitive traffic crossing a container boundary is authenticated
  and encrypted.
- A route capability is necessary but not sufficient: the relay also enforces
  current operator-local default-deny policy.
- Authorization failures, ambiguous resolution, TLS failures, replay-state
  exhaustion, and partial policy availability fail closed.
- Enterprise IAM is an optional extension, not a prerequisite for the ISP
  name-routing profile.

## Trust boundaries and keys

| Boundary | Private material | Trust decision |
|---|---|---|
| Enterprise workload bootstrap | Ed25519 identity signing key | Creates eight-hour local demo workload JWTs. |
| Enterprise control plane | Ed25519 route-ticket signing key; TLS server and mTLS client keys | Validates workload JWT, requires OPA allow, issues scoped bearer ticket. |
| OPA | TLS server key | Evaluates default-deny identity/service/method/path policy over mTLS. |
| Envoy gateway | TLS server key; mTLS client key | Enforces ext_authz, fixed verifier, and fixed backend routes. |
| Ticket verifier | Ed25519 ticket public key; TLS server key | Verifies ticket claims against the actual Envoy method/path/service context. |
| ISP name control | Ed25519 name-binding signing key; ISP TLS server key | Admits only enabled registered names and signs bounded route capabilities. |
| ISP name relay | Name-binding public key; separate ISP TLS server key | Verifies capability and proof, consumes replay nonce, rechecks local registry and resolution. |
| Windows prototype | Ephemeral Ed25519 session key; synthetic-address journal | Proves possession for one route and recovers only adapter state it created. |

Identity, enterprise ticket, and ISP name-binding signing keys are separate.
Service TLS leaf keys use ECDSA P-256 for Envoy/Python interoperability and have
role-specific SAN/EKU extensions. Demo certificate authorities are separate for
enterprise and ISP paths. These are local generated credentials, not production
PKI.

## Default-deny route registry

`nbsr/route_registry.py` validates the operator document and derives a stable
fingerprint. Each entry specifies canonical name, route ID, configured origin,
allowed ports, endpoint constraints, expected Host/SNI, enabled state, and
policy version.

Name control:

1. accepts only the canonical registered name;
2. rejects unknown fields and any destination override;
3. resolves only the configured origin;
4. rejects empty, excessive, ambiguous, or out-of-policy endpoint sets; and
5. signs the admitted set and policy identity into a short-lived capability.

Relay:

1. verifies issuer, audience, expiry, gateway, session, name, route, and port;
2. consumes a fresh client proof and nonce in a bounded replay cache;
3. loads its independent local registry;
4. requires matching enabled route ID, version, and fingerprint;
5. re-resolves immediately before connection; and
6. requires exact agreement between the signed endpoint set, fresh resolution,
   and local CIDR/exact-address constraints.

Public global-unicast status never grants access. Direct IP literals, loopback,
RFC1918, CGNAT, link-local, metadata, multicast, unspecified, reserved, and
IPv4-mapped IPv6 bypasses are rejected unless a narrowly registered route
explicitly constrains the exact endpoint.

## Enterprise authorization

The control plane validates an Ed25519 workload JWT with an explicit algorithm,
issuer, audience, expiry, JWT ID, and SPIFFE-like subject. It sends the
authenticated subject and requested logical service/method/path to OPA over
TLS 1.3 mTLS. An OPA default-deny allow result controls ticket issuance.

The short-lived Ed25519 ticket contains issuer, subject, audience, issue/not
before/expiry times, JWT ID, logical service, method set, path prefix, and
policy version. Envoy sends the received request to the verifier over mTLS.
The verifier uses Envoy's actual request method/path and a gateway-overwritten
fixed service identity. Missing, duplicate, or spoofed context cannot broaden
the ticket.

Enterprise tickets remain bearer credentials. Expiry, tampering, missing
credentials, method/path escalation, and service mismatch are rejected, but a
valid ticket can be replayed within its lifetime. Channel binding or a
distributed one-time replay store remains a production blocker.

## TLS and mTLS rules

- Client-facing enterprise control, Envoy gateway, ISP name control, and relay
  endpoints require server-authenticated TLS.
- Control plane to OPA, Envoy to verifier, and Envoy to payments require
  TLS 1.3 mTLS with CA, chain, hostname/SAN, expiry, EKU, and client certificate
  validation.
- Missing CA, untrusted CA, wrong SAN, wrong-service certificate, expired
  certificate, missing client identity, plaintext endpoint, or negotiation
  failure is terminal.
- There is no certificate-validation disable flag and no plaintext retry.
- Tokens, route capabilities, and full authorization payloads are not
  deliberately logged.

Port 80 origin traffic is compatibility mode inside client-to-relay TLS. No
NBSR credential is placed in the origin HTTP request. HTTPS remains the
preferred demonstration and preserves end-to-end origin certificate, SNI, and
Host validation.

## Deployment enforcement

Compose uses separate enterprise client, control, protected, ISP client, and
ISP origin networks. The name relay is not attached to the enterprise
protected network. No backend or origin port is published. Developer ingress
ports bind only to `127.0.0.1`.

The Kind deployment disables the non-enforcing default CNI and installs a
checksum-pinned Calico manifest. Namespace ingress/egress start default-deny.
DNS is allowed only to `k8s-app: kube-dns` pods in `kube-system`. Live probes
confirm the exact allowed flows and deny relay-to-payments, unrelated pods,
cross-namespace targets, metadata, and link-local addresses.

## Resource and local-secret safety

Replay, synthetic allocation, and admission state have explicit capacities,
expiry cleanup, and fail-closed behavior. Generated keys, tokens, and
certificates are ignored, excluded from Docker/release contexts, written
atomically, and protected with POSIX owner permissions or Windows DACLs.
Deterministic release packaging rejects sensitive paths and secret-like
content, re-extracts the archive, compares inventories, and validates the
extracted copy.

These controls are process-local and demo-oriented. Durable distributed replay,
revocation, quotas, HSM/KMS protection, automated rotation, audit retention,
and incident response are not implemented.
