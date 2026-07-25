# NBSR terminology

The authoritative direction is [NBSR Protocol Vision v2](NBSR_Protocol_Vision_v2.pdf).
Its North Star is: **NBSR turns a name into a secure route, not an IP address.**
The earlier feasibility study remains supporting research, but its binary is
not present in this repository.

## Core terms

| Term | Meaning | Current prototype status |
|---|---|---|
| Name | The application-visible identifier requested through NBSR. | `facebook.test` is the registered ISP-profile demo name; `payments.internal` is the enterprise logical service. |
| Registered NBSR name | A canonical name admitted by an operator-controlled default-deny registry. It is not an arbitrary caller-supplied destination. | Implemented locally in `config/name-routes.json`. |
| Route ID | A stable operator-assigned identifier for one registry entry. | Bound into signed ISP route capabilities. |
| Origin hostname | The operator-configured upstream hostname for a registered route. It is never supplied as a request override. | Resolved only by the name control/relay boundary. |
| Authorized endpoint set | The exact resolved addresses admitted when the capability is issued, constrained by the registry CIDRs or exact addresses. | Signed into the route capability and compared with a fresh relay resolution. |
| Route policy fingerprint | A deterministic fingerprint and version for the registry entry. | Signed by name control and independently checked against relay-local policy. |
| NBSR client | The local protocol endpoint used by applications to request names and open secure routes. | A Python Windows-first loopback adapter prototype, not an OS-integrated production client. |
| NBSR edge | An ISP, cloud, enterprise, or regional endpoint participating in route and tunnel enforcement. | Represented by local control, relay, Envoy, and verifier services. |
| Regional NBSR server | Regional control and data-plane infrastructure that resolves names, selects paths, and manages tunnels. | Design target only; the repository runs a single local region. |
| Route | The authorized name-based connectivity decision. | Implemented as an enterprise routing ticket or ISP name-route capability. |
| Route capability | A signed, bounded authorization for one registered name, route, gateway, port, endpoint set, policy fingerprint, client session, and expiry. | Implemented for the ISP-profile vertical slice. |
| Tunnel | The cryptographically protected transport carrying one or more streams. | The prototype has TLS-protected connections, not a multiplexed native NBSR tunnel implementation. |
| Stream | An individual application flow multiplexed through a tunnel. | Each current relay connection carries one TCP flow; multiplexing is not implemented. |
| Lease | The bounded authorization period for a route or tunnel. | Route capabilities expire; active renewal semantics are design-only. |
| Federation | Trust, delegation, revocation, and routing between NBSR operators or domains. | Not implemented. |

## Profile terms

| Term | Meaning |
|---|---|
| Core protocol | Native naming, mandatory authenticated and encrypted transport, name-based routing, and session lifecycle. Enterprise IAM is not a prerequisite. |
| ISP profile | The name-first route path without enterprise workload JWT, billing, subscriber inspection, or content inspection. |
| Enterprise extension | Optional workload identity, OPA authorization, method/path scope, compliance, device posture, and audit controls above the core protocol. |
| Compatibility HTTP | Port 80 application traffic carried inside the authenticated client-to-relay TLS channel. It carries no NBSR credential to the origin and is not end-to-end authenticated native NBSR. |
| HTTPS origin mode | Preferred demo path. The relay preserves opaque application TLS so the client validates the origin certificate and sends the registered name as SNI and Host. |
| Synthetic address | A local compatibility address owned by the client adapter. It is not the durable origin address and is used only to intercept an existing application's connection. |
| DNS transition | DNS may help bootstrap, migrate, or resolve an operator-configured origin. Native NBSR naming must not permanently depend on conventional DNS semantics in the critical route decision. |

## Naming rules in this prototype

- The caller supplies only a canonical registered NBSR name.
- Mixed case, trailing dots, direct IP literals, Unicode ambiguity, unknown
  fields, and destination overrides fail closed.
- Public global-unicast status never grants authorization.
- The relay trusts neither the caller nor a signed capability alone. It also
  requires a matching enabled local registry entry and a fresh, exact endpoint
  set within that entry's constraints.
- `Host` and TLS SNI come from the registry, not from an attacker-controlled
  destination field.
