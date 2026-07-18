# NBSR Prototype Design

## Goal

Demonstrate that `payments.internal` is an authenticated, policy-authorized,
short-lived route rather than a DNS lookup.

## Architecture

The client exchanges a signed EdDSA workload JWT for a 60-second Ed25519 route
ticket at the FastAPI control plane. The control plane delegates authorization
to OPA. Envoy is the only public data-plane endpoint and calls a FastAPI
`ext_authz` verifier before forwarding to a fixed payments upstream. The
payments container has no published port and joins only the protected network.

Identity and route-ticket keys are separate. Only the control plane receives
the route-ticket private key; the verifier receives its public key. The fixed
gateway mapping prevents client-selected upstreams. All validation fails
closed.

## Components and data flow

1. `nbsr.security` validates workload identity JWTs and issues/verifies tickets.
2. `control-plane` validates input and identity, calls OPA, then issues a ticket.
3. `policy/nbsr.rego` explicitly default-denies and returns decision metadata.
4. Envoy calls `ticket-verifier` using the original method/path and ticket.
5. The verifier checks signature, issuer, audience, service, method, and path.
6. Envoy forwards authorized traffic to the fixed payments cluster.

## Error handling and security

Public errors are stable and contain no token or cryptographic detail. Network
calls use bounded timeouts. Configuration is validated at process startup.
Unknown services, identities, methods, and paths are denied. The prototype does
not implement replay storage; short TTL and `jti` reduce but do not eliminate
replay risk.

## Testing

Unit tests cover identity and ticket validation. FastAPI tests cover resolution
and verifier behavior. OPA tests cover every default-deny branch. Compose
scripts exercise the mandatory scenarios and actual network isolation. Static
Compose and Kubernetes checks are run when their local tools exist.

## Constraints

Docker Compose is primary; kind is secondary. mTLS is an isolated optional
demonstration and cannot destabilize JWT mode. This is a local hackathon
prototype and makes no production-readiness claim.
