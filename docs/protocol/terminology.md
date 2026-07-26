# NBSR protocol terminology

This vocabulary is normative for repository documentation and tests. Protocol
Vision V3 remains authoritative if a conflict is discovered.

| Term | Canonical meaning | Must not be confused with |
|---|---|---|
| Name | Hierarchical application-visible identifier requested through NBSR | An origin IP address |
| Legacy name | Name resolved to conventional DNS-compatible records without creating NBSR route state | A failed or downgraded NBSR name |
| NBSR-enabled name | Name with a validated signed NBSR Service Record that resolves to secure route state | A DNS name that merely points to a public proxy |
| NBSR Name Node | Resolver/authoritative component for both legacy and NBSR resolution | A DNS bootstrap helper running before NBSR |
| Name/Resolution Plane | Name classification, legacy resolution, service-record validation, RouteIntent creation, and compatibility-handle allocation | Tunnel transport |
| Secure Route/Tunnel Plane | Source admission, destination admission, proof-of-possession, encrypted tunnels, streams, leases, and origin-connector reachability | DNS recursion |
| Resolution Context ID | Non-exported source-local identifier binding a name query to a subscriber, device, CPE, authenticated resolver session, or native client session | Raw source IP alone |
| Synthetic handle | Scoped IP-shaped compatibility token that represents NBSR route state | An origin address or globally meaningful service IP |
| RouteIntent | Short-lived internal plan created by NBSR resolution before the first matching connection | Authorization to open a route |
| Route Grant | Signed, short-lived, proof-of-possession-bound authorization for a source edge to request one bounded route | A reusable bearer ticket |
| Source edge | NBSR gateway closest to the endpoint or subscriber; acts as the protocol client for legacy devices | The protected origin |
| Destination edge | Independently admitting NBSR gateway authorized to reach an origin connector | A blind forwarding relay |
| Origin connector | Outbound-only authenticated component exposing a private service to an authorized destination edge | A public inbound listener |
| Tunnel | Authenticated encrypted transport between NBSR protocol peers | Application end-to-end TLS |
| Stream | One admitted application flow multiplexed inside a tunnel | An entire tunnel |
| Handle TTL | Compatibility cache lifetime for a synthetic handle | A route authorization lease |
| Route lease | Bounded interval during which route state can admit or renew streams according to policy | DNS TTL |
| Operator | ISP, cloud, enterprise, or other administrative domain running NBSR infrastructure | A globally omnipotent NBSR root |
| Federation | Signed trust, ownership, delegation, routing, and revocation relationship between operators | A blockchain or single central operator |
| Core v0.1 | Pre-standardization protocol profile defined by Vision V3 and future WP1-WP4 evidence | The current Build Week prototype |
| Enterprise profile | Optional identity and fine-grained authorization extension using workload policy | A mandatory dependency of the ISP/core profile |

## Canonical statements

- NBSR is the configured resolver in an upgraded network.
- NBSR is not a component that always runs after DNS.
- Legacy names retain DNS-compatible behavior through the NBSR Name Node.
- NBSR-enabled names resolve to secure route state, not an origin IP.
- The existing IP Internet remains the underlay between NBSR edges.
- The operational package may be installed as one product, but the two planes
  remain separate processes and failure domains.
- A synthetic handle is correlation state, never authorization.
- A Route Grant is proof-of-possession-bound and is not a bearer credential.
- The first no-agent lab places the Source NBSR Edge on the client's traffic
  path; a standalone remote resolver is insufficient.
