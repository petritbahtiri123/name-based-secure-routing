# WP5 Linux gateway packaging decision

**Status:** Approved and in progress at deterministic planning and simulated
policy-conformance scope. This is not live platform validation or production
readiness.

## Approved platform boundary

WP5 is Linux/OpenWrt-first. It models nftables Synthetic IP destination
capture plus policy routing to a local source-edge listener. Both configured
address families require a terminal reject path so ambiguous or uncaptured
Synthetic IP traffic fails closed.

The implementation emits declarative operations only. It does not invoke
`nft`, `ip`, `sysctl`, `uci`, resolver tools, or service managers. Exact live
translation and application remain a separate platform-validation gate.

The Name/Resolution plane and Secure Route/Tunnel plane retain separate health
and failure evidence. A failure in one plane never converts into direct origin
fallback or implicit authorization by the other plane.

## Prefix and collision policy

There is no universal production Synthetic IP prefix. The routed-gateway lab
profile requires one operator-selected IPv4 documentation or operator-owned
prefix and one IPv6 ULA prefix. IPv4 loopback, RFC 1918, and CGN Shared Address
Space are rejected. Supplied interface, route, VPN, container, and reserved
prefix inventories must be collision-free. An exact entry may be reused only
when it is already owned by the same package instance.

## Ownership and rollback

Every planned resource has a stable identifier, normalized argument vector,
and typed inverse. A secure ownership journal records the profile digest,
bounded prior resolver state, and only successfully applied NBSR operation
identifiers. Rollback uses reverse application order, removes only journaled
NBSR resources, and restores exact prior resolver state last.

Unreadable, incomplete, mismatched, or equivocated journal state fails closed
and authorizes no destructive rollback operation.

## Required simulated conformance evidence

The verifier requires exact-prefix capture, dual-stack terminal reject,
matching marks and policy routes, DNS forwarding, resolver parity evidence,
independent plane health, ownership agreement, per-service attribution,
bounded fair-share evidence, no origin fallback, and rollback completeness.
Reports use stable check codes and redacted identifiers only.

This is simulated policy-conformance evidence over injected snapshots. It is
not evidence of privileged Linux or OpenWrt state.

## Preserved boundaries and non-claims

WP5 retains no new wire values and no frozen Core v0.1 change.
It retains no OriginSet selection and no Origin Endpoint connection or forwarding.
It retains no NameRelay integration, no production readiness, no cross-edge
resume, no 0-RTT, and no WP6 behavior.

It also makes no live nftables/TPROXY installation claim.
It makes no clean no-agent client demonstration and no live legacy-site parity claim.
It makes no operational rollback claim, no signed Windows component claim,
and no production prefix or policy-default claim. Those require separately
approved and directly observed platform evidence.
