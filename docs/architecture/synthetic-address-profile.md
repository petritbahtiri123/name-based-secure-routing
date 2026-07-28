# NBSR synthetic address profile

**Status:** Prototype recommendation with production allocation unresolved

## Invariant

Every successful upgraded-network resolution returns a scoped Synthetic IP.
The address is a local correlation handle, not Service Identity and not an
Origin Endpoint. Packets to it must be intercepted by the correct NBSR trust
context; they must not escape toward ordinary routing.

## Address-space assessment

| Choice | Benefit | Collision and leakage risk | Appropriate use |
|---|---|---|---|
| IPv4 loopback | Strong single-host locality and simple interception | Conflicts with applications that assume all loopback is local service; not routable to a gateway | Single-host prototype only, with a dedicated configured subrange |
| RFC 1918 | Widely supported by host and network stacks | Common LAN, VPN, container, and enterprise conflicts | Only after active route/address collision checks in a controlled site |
| 100.64.0.0/10 | Larger shared block and often filtered from the public Internet | It is CGN Shared Address Space and may already be used by an access network or VPN | Never a universal default; only operator-selected after collision checks |
| Operator-assigned IPv4 | Fits known local routing plan | Consumes operator space and can leak if filters fail | Preferred production IPv4 option when the operator controls the prefix |
| Future dedicated allocation | Could standardize filtering and collision expectations | No such NBSR allocation is approved | Standards-track future option |
| IPv6 ULA | Large space and high-probability uniqueness when generated correctly | Site mergers, VPNs, and bad fixed prefixes can still collide; leakage must be blocked | Preferred prototype/site IPv6 option with a generated per-operator /48 |
| Operator-assigned IPv6 | Integrates with an operator's routing and policy | Requires ownership, filtering, and lifecycle management | Production option where routing is controlled |
| Local-only interception | Can avoid routed synthetic prefixes outside the host | Platform-specific capture and bypass risks | Strong default for endpoint agents |

100.64.0.0/10 is not universally safe. It is allocated for service-provider
Shared Address Space, so an NBSR deployment cannot assume it is unused.

## Prototype recommendations

- Keep all prefixes configurable.
- For a single-host lab, use a dedicated loopback subrange that is checked
  against listeners and existing routes before activation.
- For a routed lab, prefer a generated RFC 4193 ULA /48 for IPv6 and an
  operator-selected IPv4 prefix only after collision checks.
- Namespace the mapping by tenant and trusted resolution context, not only by
  address.
- Install explicit reject routes at the containment boundary and remove them
  reversibly during teardown.
- Never publish synthetic addresses into global DNS.

These are prototype defaults, not universal production allocations.

## Required collision detection

Before enabling a prefix:

1. enumerate local interfaces, routes, VPNs, container networks, and configured
   enterprise/CGN ranges;
2. reject any overlap unless the operator explicitly owns that route;
3. probe platform routing ownership without sending synthetic traffic outside
   the containment boundary;
4. reserve mappings atomically within tenant/context scope;
5. detect duplicate address ownership after restart or replica recovery; and
6. fail closed if route capture is absent or ambiguous.

Collision checks repeat on interface, VPN, route, tenant, and gateway changes.
A collision never permits direct fallback.

## Isolation and leakage

- A synthetic address is meaningful only with its tenant, resolver context,
  mapping generation, client/subscriber context, and expiry.
- Different tenants may reuse the same address only when interception and
  lookup namespaces are provably isolated.
- Routing and firewall policy must prevent synthetic source or destination
  traffic from leaving its local/operator scope.
- Logs exposed to clients identify the Synthetic IP or pseudonymous route
  handle, never the Origin Endpoint.
- Unmapped, expired, or wrong-context synthetic traffic fails closed.

## Platform behavior

Linux/OpenWrt deployments may use local DNS interception with policy routing,
nftables/TPROXY, TUN, or eBPF. Windows may use resolver integration and WFP,
with signed production driver/service requirements. These are deployment
mechanisms, not Core wire protocol.

The NBSR requirement is consistent: capture only configured synthetic prefixes,
correlate them to the correct RouteIntent context, detect bypass, and restore
prior system state safely.

## Production gate

The universal production prefix remains unresolved pending standardization.
Production approval must select operator-owned/configured prefixes, collision
and route-leak controls, tenant scoping, persistence/recovery rules, and
platform interception evidence. No document may claim RFC 1918, CGN Shared
Address Space, loopback, or ULA is collision-free in every deployment.
