# NBSR protocol terminology

This vocabulary is normative for forward-looking repository documentation and
tests. [NBSR Protocol Vision V3.6](../architecture/NBSR_Protocol_Vision_V3.6.md)
is authoritative when a forward-looking document conflicts with it. Approved
Core v0.1 D1-D6 wire meanings remain frozen.

## Canonical glossary and invariants

| Term | Canonical meaning | Protocol invariant |
|---|---|---|
| Service Name | Canonical application-visible name requested through NBSR | MUST identify the requested service without carrying an Origin Endpoint |
| Service Identity | Stable authorized identity bound to Service Name/service ID, issuer or owner, policy, generation, and revocation state | MUST NOT be derived from an IP address or other mutable reachability data |
| Synthetic IP | Scoped client-facing IP-shaped compatibility handle returned for every successful resolution through an upgraded NBSR network | MUST NOT be an Origin Endpoint or globally meaningful service location |
| Origin Endpoint | Mutable internal address, discovery name, connector, or controlled-egress target used for the final route segment | MUST remain internal and MUST NOT create Service Identity or authorization |
| OriginSet | Versioned bounded collection of eligible Origin Endpoints and their reachability metadata for one Service Identity | MUST be generation/sequence validated, rollback resistant, and issuer authorized before use |
| Source Edge | NBSR gateway owning the Synthetic IP traffic path and performing source correlation/admission | MUST bind traffic to trustworthy resolution and client/device or subscriber context |
| Destination Edge | Independently admitting NBSR gateway authorized to reach a connector or Origin Endpoint | MUST validate route authority and MUST NOT derive owner identity from reachability |
| Transport Session | Authenticated encrypted edge-to-edge relationship, expected to use QUIC/TLS 1.3 in the planned profile | MUST NOT serve as universal authorization for every carried service |
| Route Context | Bounded authorization and lifecycle state for one Service Identity and route | MUST remain name/service, grant, edge, lease, policy, replay, and revocation bound |
| Service Channel | Independently authorized service-bound logical security context carried inside a Transport Session | MUST have independent authorization, revocation, quota, audit, failure, and security context |
| Application Stream | One proxied application flow inside one Service Channel, initially one TCP connection | MUST NOT be forwarded before both applicable source and destination admission succeed |
| Route Grant | Signed short-lived proof-of-possession-bound authorization for a bounded Route Context | MUST NOT be treated as a reusable bearer credential or authorize another service |
| Publication Mode | Conceptual origin lifecycle mode `LEGACY_DNS`, `HYBRID`, or `NBSR_NATIVE` | MUST NOT silently reinterpret the four frozen D6 ServiceRecord wire values |
| Migration | Validated movement of an active Transport Session network path or approved route context | MUST NOT create new Service Identity or application authorization |
| Resumption | Re-establishment of transport and eligible state after interruption | MUST recheck expiry, revocation, replay, gateway, client/device, service, and policy binding |
| Handover | Explicitly authorized transfer of responsibility to a different Source Edge or Destination Edge | MUST NOT transfer a grant or Route Context blindly |
| Drain | Bounded refusal of new work while existing permitted streams complete or are explicitly invalidated | MUST have policy bounds and MUST NOT become indefinite authorization |

## Supporting terms

| Term | Canonical meaning | Must not be confused with |
|---|---|---|
| NBSR Name Node | DNS-compatible resolver/authoritative component that returns a Synthetic IP for every successful upgraded-network resolution | A DNS bootstrap helper that returns origins to clients |
| Name/Resolution Plane | Name handling, internal metadata discovery, Service Identity/policy validation, RouteIntent creation, and Synthetic IP allocation | Transport or final-origin forwarding |
| Secure Route/Tunnel Plane | Source/destination admission, Transport Sessions, Service Channels, Application Streams, revocation, failover, and Origin Endpoint selection | DNS recursion |
| Resolution Context ID | Non-exported scoped identifier binding a name query and Synthetic IP to trustworthy source context | Raw source IP alone |
| RouteIntent | Short-lived internal plan created by resolution before connection-triggered authorization | A Route Grant |
| Connector | Authenticated controlled component or target used to reach a protected service | Service Identity or public inbound origin |
| DNS TTL | Cache/refresh lifetime for legacy reachability discovery | Route Grant, route lease, channel lifetime, or revocation expiry |
| Core v0.1 | Frozen pre-standardization wire/data decisions D1-D6 and their exact registries/schemas | The complete V3.6 runtime architecture |
| Enterprise profile | Optional identity and fine-grained application-policy extension | A mandatory dependency of the ISP/core route |

## Canonical statements

- Every successful resolution through an upgraded NBSR network returns a
  scoped Synthetic IP.
- The origin IP is never returned to the client and direct fallback is
  forbidden.
- Service Identity is independent of Origin Endpoint.
- Legacy DNS is internal compatibility reachability only.
- A Transport Session may be reused; service authorization may not.
- Each Service Channel is independently authorized and independently
  revocable.
- The existing IP Internet remains the underlay between NBSR edges.
- Name/Resolution and Secure Route/Tunnel remain separate security and failure
  domains even when packaged as one product.
- Application login, OAuth, transaction, and payload semantics remain outside
  NBSR.
